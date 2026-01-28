"""
Async tasks for track processing using Django-Q2.
"""

import logging
import os
from datetime import datetime, timezone
from bisect import bisect_left

from django.conf import settings
from django_q.tasks import async_task

from openmeteopy.client import OpenMeteo
from openmeteopy.options import HistoricalOptions
from openmeteopy.hourly import HourlyHistorical
from openmeteopy.utils.constants import unixtime, kn

from .models import Recording, Event, EventWindField
from .gpx_parser import GPXTrackParser
from .json_parser import JSONTrackParser
from .track_processor import generate_zoom_levels
from .storage import upload_track_json, download_track_json

logger = logging.getLogger(__name__)


def process_track_upload(recording_id: str, temp_file_path: str):
    """
    Async task to process an uploaded track file (GPX or JSON).
    
    This task:
    1. Reads the track file from temporary storage
    2. Detects file type (GPX or JSON)
    3. Parses and validates the track data
    4. Generates zoom-level simplified versions
    5. Uploads all versions to DO Spaces
    6. Updates the Recording model with metadata
    
    Args:
        recording_id: UUID of the Recording model
        temp_file_path: Path to the temporary track file
    """
    logger.info(f"Processing track upload for recording {recording_id}")
    
    try:
        # Get the recording
        recording = Recording.objects.get(pk=recording_id)
        
        # Read the file from temp location
        if not os.path.exists(temp_file_path):
            raise FileNotFoundError(f"Track file not found: {temp_file_path}")
        
        # Detect file type from extension
        file_ext = os.path.splitext(temp_file_path)[1].lower()
        
        with open(temp_file_path, 'rb') as f:
            file_content = f.read()
        
        # Parse based on file type
        if file_ext == '.json':
            parser = JSONTrackParser(file_content)
            file_type = 'JSON'
        elif file_ext == '.gpx':
            parser = GPXTrackParser(file_content)
            file_type = 'GPX'
        else:
            raise ValueError(f"Unsupported file type: {file_ext}. Supported types: .gpx, .json")
        
        points = parser.parse()
        
        if not points:
            raise ValueError(f"No valid track points found in {file_type} file")
        
        metadata = parser.get_metadata()
        
        # Convert to GeoJSON
        geojson_data = parser.to_geojson()
        
        # Generate zoom levels
        zoom_levels = generate_zoom_levels(geojson_data)
        
        # Upload all zoom levels to DO Spaces (if configured)
        s3_prefix = f"{settings.TRACK_S3_PREFIX}{recording_id}/"
        
        if settings.DO_SPACES_KEY and settings.DO_SPACES_SECRET and settings.DO_SPACES_NAME:
            # DO Spaces is configured, upload track files
            for zoom_level, data in zoom_levels.items():
                upload_track_json(recording_id, zoom_level, data)
        else:
            # DO Spaces not configured - log warning but continue
            logger.warning(
                f"DO Spaces not configured. Track files for recording {recording_id} "
                "will not be uploaded. Set DO_SPACES_KEY, DO_SPACES_SECRET, and "
                "DO_SPACES_NAME environment variables to enable uploads."
            )
        
        # Update recording with metadata
        recording.start_time = datetime.fromisoformat(metadata['start_time'])
        recording.end_time = datetime.fromisoformat(metadata['end_time'])
        recording.bounding_box = metadata['bounding_box']
        recording.point_count = metadata['point_count']
        recording.distance_nm = metadata['distance_nm']
        recording.s3_prefix = s3_prefix
        recording.status = 'ready'
        recording.error_message = None
        
        # If recording has an event, update event date from recording start_time
        if recording.event and recording.start_time:
            from datetime import date
            event_date = recording.start_time.date()
            # Only update if event date is today (meaning it was just created)
            if recording.event.date == date.today():
                recording.event.date = event_date
                recording.event.save()
            
            # Check for overlapping events (only if this is the first recording for this event)
            if recording.event.recordings.count() == 1:
                overlapping_events = Event.find_overlapping_events(
                    bounding_box=recording.bounding_box,
                    start_time=recording.start_time,
                    end_time=recording.end_time,
                    exclude_event=recording.event
                )
                # Store overlapping event IDs in a JSON field or signal for user confirmation
                # For now, we'll check this on the detail page
                if overlapping_events.exists():
                    # Store the first overlapping event ID in a way we can access it
                    # We'll use a signal or check on the detail page
                    pass
        
        recording.save()

        if recording.event_id:
            async_task(
                'apps.tracks.tasks.compute_event_wind_field',
                str(recording.event_id),
                6,
                30
            )
        
        # Clean up temp file and directory
        try:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                # Also try to remove the temp directory if it's empty
                temp_dir = os.path.dirname(temp_file_path)
                try:
                    os.rmdir(temp_dir)
                except OSError:
                    pass  # Directory not empty or doesn't exist, that's fine
        except Exception as e:
            logger.warning(f"Failed to delete temp file {temp_file_path}: {e}")
        
        logger.info(f"Successfully processed {file_type} recording {recording_id}: {metadata['point_count']} points")
        
    except Recording.DoesNotExist:
        logger.error(f"Recording {recording_id} not found")
        raise
    except Exception as e:
        logger.error(f"Failed to process recording {recording_id}: {e}")
        
        # Update recording with error status
        try:
            recording = Recording.objects.get(pk=recording_id)
            recording.status = 'failed'
            recording.error_message = str(e)
            recording.save()
        except Recording.DoesNotExist:
            pass
        
        raise


# Backward compatibility alias
def process_gpx_upload(recording_id: str, temp_file_path: str):
    """
    Backward compatibility alias for process_track_upload.
    
    This function is kept for backward compatibility but now supports
    both GPX and JSON files.
    """
    return process_track_upload(recording_id, temp_file_path)


def process_track_crop(
    cropped_recording_id: str,
    original_recording_id: str,
    crop_before: bool,
    crop_after: bool,
    crop_timestamp_iso: str,
    context: str,
    event_id: str = None,
):
    """
    Async task to process a cropped track.
    
    This task:
    1. Downloads the original track data from S3
    2. Filters points based on crop parameters
    3. Recalculates metadata
    4. Generates zoom-level simplified versions
    5. Uploads all versions to DO Spaces
    6. Updates the cropped Recording model with metadata
    7. Handles replacement logic based on context
    
    Args:
        cropped_recording_id: UUID of the new cropped Recording (already created with status='processing')
        original_recording_id: UUID of the original Recording being cropped
        crop_before: If True, remove all points before crop_timestamp
        crop_after: If True, remove all points after crop_timestamp
        crop_timestamp_iso: ISO format timestamp string for the crop point
        context: 'event' or 'recording' - determines replacement behavior
        event_id: Optional UUID of event (required if context='event')
    """
    logger.info(f"Processing track crop for recording {cropped_recording_id} from {original_recording_id}")
    
    try:
        # Get the recordings
        cropped_recording = Recording.objects.get(pk=cropped_recording_id)
        original_recording = Recording.objects.get(pk=original_recording_id)
        
        # Parse crop timestamp
        crop_timestamp = datetime.fromisoformat(crop_timestamp_iso.replace('Z', '+00:00'))
        
        # Download original track data from S3
        try:
            geojson_data = download_track_json(original_recording_id, 'raw')
        except Exception as e:
            raise ValueError(f"Failed to download original track data: {e}")
        
        # Filter points based on crop parameters
        coordinates = geojson_data.get('geometry', {}).get('coordinates', [])
        if not coordinates:
            raise ValueError("No coordinates found in track data")
        
        # Filter coordinates: each is [lon, lat, timestamp_epoch, speed]
        filtered_coords = []
        for coord in coordinates:
            if len(coord) < 3:
                continue
            
            point_timestamp_epoch = coord[2]
            point_timestamp = datetime.fromtimestamp(point_timestamp_epoch, tz=timezone.utc)
            
            # Apply crop filters
            if crop_before and point_timestamp < crop_timestamp:
                continue  # Skip points before crop timestamp
            if crop_after and point_timestamp > crop_timestamp:
                continue  # Skip points after crop timestamp
            
            filtered_coords.append(coord)
        
        if not filtered_coords:
            raise ValueError("No points remaining after crop")
        
        # Update GeoJSON with filtered coordinates
        geojson_data['geometry']['coordinates'] = filtered_coords
        
        # Recalculate metadata from filtered points
        from .gpx_parser import GPXTrackParser  # Reuse metadata calculation logic
        # We need to extract timestamps and calculate bounds
        timestamps = [coord[2] for coord in filtered_coords if len(coord) >= 3]
        if not timestamps:
            raise ValueError("No valid timestamps in filtered coordinates")
        
        start_timestamp_epoch = min(timestamps)
        end_timestamp_epoch = max(timestamps)
        start_time = datetime.fromtimestamp(start_timestamp_epoch, tz=timezone.utc)
        end_time = datetime.fromtimestamp(end_timestamp_epoch, tz=timezone.utc)
        
        # Calculate bounding box
        lats = [coord[1] for coord in filtered_coords]
        lons = [coord[0] for coord in filtered_coords]
        bounding_box = {
            'min_lat': min(lats),
            'max_lat': max(lats),
            'min_lon': min(lons),
            'max_lon': max(lons),
        }
        
        # Calculate distance (nautical miles) - approximate using haversine
        from math import radians, sin, cos, sqrt, atan2
        def haversine_distance(lat1, lon1, lat2, lon2):
            """Calculate distance in nautical miles between two points."""
            R = 3440.065  # Earth radius in nautical miles
            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            return R * c
        
        total_distance = 0.0
        for i in range(len(filtered_coords) - 1):
            lat1, lon1 = filtered_coords[i][1], filtered_coords[i][0]
            lat2, lon2 = filtered_coords[i+1][1], filtered_coords[i+1][0]
            total_distance += haversine_distance(lat1, lon1, lat2, lon2)
        
        # Generate zoom levels for cropped track
        zoom_levels = generate_zoom_levels(geojson_data)
        
        # Upload all zoom levels to DO Spaces
        s3_prefix = f"{settings.TRACK_S3_PREFIX}{cropped_recording_id}/"
        
        if settings.DO_SPACES_KEY and settings.DO_SPACES_SECRET and settings.DO_SPACES_NAME:
            for zoom_level, data in zoom_levels.items():
                upload_track_json(cropped_recording_id, zoom_level, data)
        else:
            logger.warning(
                f"DO Spaces not configured. Track files for recording {cropped_recording_id} "
                "will not be uploaded."
            )
        
        # Update cropped recording with metadata
        cropped_recording.start_time = start_time
        cropped_recording.end_time = end_time
        cropped_recording.bounding_box = bounding_box
        cropped_recording.point_count = len(filtered_coords)
        cropped_recording.distance_nm = round(total_distance, 2)
        cropped_recording.s3_prefix = s3_prefix
        cropped_recording.status = 'ready'
        cropped_recording.error_message = None
        
        # Handle replacement logic based on context
        if context == 'event':
            # Event context: Only replace usage in this specific event
            if event_id:
                try:
                    event = Event.objects.get(pk=event_id)
                    # Update the original recording's event to None (only if it was in this event)
                    if original_recording.event == event:
                        original_recording.event = None
                        original_recording.save()
                    # Set the cropped recording's event to the event
                    cropped_recording.event = event
                except Event.DoesNotExist:
                    logger.warning(f"Event {event_id} not found, skipping event relationship update")
        else:
            # Original recording context: Replace all usages
            # Transfer event relationship from original to cropped
            if original_recording.event:
                cropped_recording.event = original_recording.event
                original_recording.event = None
                original_recording.save()
            # Note: In the future, if there are other direct references to recordings,
            # they would be updated here as well
        
        cropped_recording.save()

        if cropped_recording.event_id:
            async_task(
                'apps.tracks.tasks.compute_event_wind_field',
                str(cropped_recording.event_id),
                6,
                30
            )
        
        logger.info(
            f"Successfully processed cropped recording {cropped_recording_id}: "
            f"{len(filtered_coords)} points, {total_distance:.2f} nm"
        )
        
    except Recording.DoesNotExist:
        logger.error(f"Recording not found: {cropped_recording_id} or {original_recording_id}")
        raise
    except Exception as e:
        logger.error(f"Failed to process crop for recording {cropped_recording_id}: {e}")
        
        # Update cropped recording with error status
        try:
            cropped_recording = Recording.objects.get(pk=cropped_recording_id)
            cropped_recording.status = 'failed'
            cropped_recording.error_message = str(e)
            cropped_recording.save()
        except Recording.DoesNotExist:
            pass
        
        raise


def _ensure_utc(value):
    if value.tzinfo:
        return value.astimezone(timezone.utc)
    return value.replace(tzinfo=timezone.utc)


def _interpolate_direction(direction_a, direction_b, ratio):
    if direction_a is None and direction_b is None:
        return None
    if direction_a is None:
        return direction_b
    if direction_b is None:
        return direction_a
    delta = ((direction_b - direction_a + 180) % 360) - 180
    return (direction_a + (delta * ratio)) % 360


def _interpolate_value(value_a, value_b, ratio):
    if value_a is None and value_b is None:
        return None
    if value_a is None:
        return value_b
    if value_b is None:
        return value_a
    return value_a + (value_b - value_a) * ratio


def _value_at_timestamp(times, values, timestamp):
    if not times or not values:
        return None, None, None

    if timestamp <= times[0]:
        return values[0], None, None
    if timestamp >= times[-1]:
        return values[-1], None, None

    index = bisect_left(times, timestamp)
    if index < len(times) and times[index] == timestamp:
        return values[index], None, None

    prev_index = max(0, index - 1)
    next_index = min(len(times) - 1, index)
    if times[next_index] == times[prev_index]:
        return values[prev_index], None, None

    ratio = (timestamp - times[prev_index]) / (times[next_index] - times[prev_index])
    return values[prev_index], values[next_index], ratio


def compute_event_wind_field(event_id: str, grid_size: int = 6, interval_minutes: int = 30):
    """
    Precompute wind data for an event's bounding box and time range.
    """
    try:
        event = Event.objects.get(pk=event_id)
    except Event.DoesNotExist:
        logger.warning(f"Event {event_id} not found for wind precompute")
        return

    recordings = event.recordings.filter(
        status='ready',
        bounding_box__isnull=False,
        start_time__isnull=False,
        end_time__isnull=False
    )

    if not recordings.exists():
        logger.info(f"No recordings ready for event {event_id}; skipping wind precompute")
        return

    min_lat = min(rec.bounding_box['min_lat'] for rec in recordings if rec.bounding_box)
    max_lat = max(rec.bounding_box['max_lat'] for rec in recordings if rec.bounding_box)
    min_lon = min(rec.bounding_box['min_lon'] for rec in recordings if rec.bounding_box)
    max_lon = max(rec.bounding_box['max_lon'] for rec in recordings if rec.bounding_box)

    start_time = min(rec.start_time for rec in recordings)
    end_time = max(rec.end_time for rec in recordings)

    start_time = _ensure_utc(start_time)
    end_time = _ensure_utc(end_time)

    interval_seconds = interval_minutes * 60
    start_ts = int(start_time.timestamp())
    end_ts = int(end_time.timestamp())
    start_bucket = start_ts - (start_ts % interval_seconds)
    end_bucket = end_ts - (end_ts % interval_seconds)
    timestamps = list(range(start_bucket, end_bucket + interval_seconds, interval_seconds))

    start_date = start_time.date().isoformat()
    end_date = end_time.date().isoformat()

    lat_step = (max_lat - min_lat) / (grid_size - 1) if grid_size > 1 else 0
    lon_step = (max_lon - min_lon) / (grid_size - 1) if grid_size > 1 else 0

    hourly = HourlyHistorical().windspeed_10m().winddirection_10m()
    grid_points = []

    for row in range(grid_size):
        lat = min_lat + (row * lat_step)
        for col in range(grid_size):
            lon = min_lon + (col * lon_step)
            try:
                options = HistoricalOptions(
                    lat,
                    lon,
                    windspeed_unit=kn,
                    timeformat=unixtime,
                    timezone='UTC',
                    start_date=start_date,
                    end_date=end_date
                )
                manager = OpenMeteo(options, hourly)
                data = manager.get_dict()
                hourly_data = data.get('hourly') if data else None
                if not hourly_data:
                    continue
                times = hourly_data.get('time', [])
                speeds = hourly_data.get('windspeed_10m', [])
                directions = hourly_data.get('winddirection_10m', [])
                if not times:
                    continue
                grid_points.append({
                    'lon': lon,
                    'lat': lat,
                    'times': times,
                    'speeds': speeds,
                    'directions': directions,
                })
            except Exception as exc:
                logger.warning(f"Wind fetch failed for {lat},{lon}: {exc}")

    points_by_time = {}
    for timestamp in timestamps:
        time_points = []
        for point in grid_points:
            speed_a, speed_b, ratio = _value_at_timestamp(point['times'], point['speeds'], timestamp)
            direction_a, direction_b, direction_ratio = _value_at_timestamp(point['times'], point['directions'], timestamp)

            if speed_b is None:
                speed = speed_a
            else:
                speed = _interpolate_value(speed_a, speed_b, ratio)

            if direction_b is None:
                direction = direction_a
            else:
                direction = _interpolate_direction(direction_a, direction_b, direction_ratio)

            if speed is None or direction is None:
                continue

            time_points.append({
                'lon': point['lon'],
                'lat': point['lat'],
                'speed': speed,
                'direction': direction,
            })

        points_by_time[str(timestamp)] = time_points

    EventWindField.objects.update_or_create(
        event=event,
        grid_size=grid_size,
        interval_minutes=interval_minutes,
        defaults={
            'bounding_box': {
                'min_lat': min_lat,
                'max_lat': max_lat,
                'min_lon': min_lon,
                'max_lon': max_lon,
            },
            'start_time': start_time,
            'end_time': end_time,
            'data': {
                'interval_seconds': interval_seconds,
                'times': timestamps,
                'points': points_by_time,
            },
        }
    )

    logger.info(f"Precomputed wind field for event {event_id}")
