"""
Async tasks for track processing using Django-Q2.
"""

import logging
import os
from datetime import datetime, timezone

from django.conf import settings

from .models import Recording, Event
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
