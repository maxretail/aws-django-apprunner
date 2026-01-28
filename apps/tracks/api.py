"""
REST API views for tracks app.
"""

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import serializers
from django_q.tasks import async_task
from django.utils import timezone
from django.core.cache import cache
from datetime import datetime, timezone as dt_timezone

from openmeteopy.client import OpenMeteo
from openmeteopy.options import HistoricalOptions
from openmeteopy.hourly import HourlyHistorical
from openmeteopy.utils.constants import unixtime, kn

from .models import Recording, Vessel, VesselPermission, Event, EventWindField
from .storage import get_signed_url, get_all_signed_urls
from .track_processor import get_appropriate_zoom_level


class VesselSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vessel
        fields = ['id', 'name', 'sail_number', 'model_info', 'icon']


class RecordingSerializer(serializers.ModelSerializer):
    vessel = VesselSerializer(read_only=True)
    duration_seconds = serializers.SerializerMethodField()
    
    class Meta:
        model = Recording
        fields = [
            'id', 'name', 'vessel', 'status', 'visibility',
            'start_time', 'end_time', 'duration_seconds',
            'bounding_box', 'point_count', 'distance_nm',
            'created_at',
        ]
    
    def get_duration_seconds(self, obj):
        if obj.duration:
            return obj.duration.total_seconds()
        return None


class RecordingDetailSerializer(RecordingSerializer):
    """Detailed serializer including track URLs."""
    track_urls = serializers.SerializerMethodField()
    
    class Meta(RecordingSerializer.Meta):
        fields = RecordingSerializer.Meta.fields + ['track_urls', 'event', 'original_filename']
    
    def get_track_urls(self, obj):
        if obj.status != 'ready':
            return None
        return get_all_signed_urls(str(obj.id))


class RecordingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for recordings.
    
    list: Get recordings accessible by the current user (recordings they uploaded or for vessels they're connected with)
    retrieve: Get recording details including signed track URLs (only accessible recordings)
    track: Get signed URL for a specific zoom level (only accessible recordings)
    """
    serializer_class = RecordingSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return recordings accessible by the current user."""
        from django.db.models import Count
        user = self.request.user
        
        if not user.is_authenticated:
            return Recording.objects.none()
        
        # Get recordings the user uploaded OR recordings for vessels they're connected with
        # Only cropped children (leaf nodes)
        accessible_recordings = Recording.get_accessible_recordings(user).filter(
            original_recording__isnull=False  # Only cropped recordings
        ).annotate(
            cropped_count=Count('cropped_versions')
        ).filter(
            cropped_count=0  # Only leaf nodes
        ).distinct()
        
        return accessible_recordings.order_by('-start_time')
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return RecordingDetailSerializer
        return RecordingSerializer
    
    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def track(self, request, pk=None):
        """
        Get a signed URL for the track data at a specific zoom level.
        
        Query params:
            zoom: Map zoom level (0-22), defaults to 14
        
        Only accessible for recordings the user uploaded or recordings for vessels they're connected with.
        """
        try:
            recording = Recording.objects.get(pk=pk)
        except Recording.DoesNotExist:
            return Response(
                {'error': 'Recording not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if recording.status != 'ready':
            return Response(
                {'error': 'Recording is not ready'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check access - user must own the recording or have access via vessel
        if not recording.is_accessible_by(request.user):
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get zoom level
        try:
            zoom = int(request.query_params.get('zoom', 14))
        except ValueError:
            zoom = 14
        
        zoom_level = get_appropriate_zoom_level(zoom)
        
        try:
            url = get_signed_url(str(recording.id), zoom_level)
            return Response({
                'url': url,
                'zoom_level': zoom_level,
                'expires_in': 900,  # 15 minutes
            })
        except Exception as e:
            return Response(
                {'error': f'Failed to generate URL: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def wind(self, request):
        """
        Get wind data for a bounding box and timestamp.

        Query params:
            timestamp: Epoch seconds (required)
            min_lat, max_lat, min_lon, max_lon: Bounding box coordinates (required for on-demand)
            grid: Number of points per axis (optional, default 4)
            event_token: Event share token (optional, uses stored wind data)
            event_id: Event UUID (optional, uses stored wind data)
        """
        try:
            timestamp = int(request.query_params.get('timestamp'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'timestamp is required and must be an integer'},
                status=status.HTTP_400_BAD_REQUEST
            )

        event_token = request.query_params.get('event_token')
        event_id = request.query_params.get('event_id')

        if event_token or event_id:
            event = None
            if event_token:
                event = Event.objects.filter(share_token=event_token).first()
            elif event_id:
                event = Event.objects.filter(pk=event_id).first()

            if event:
                wind_field = EventWindField.objects.filter(
                    event=event,
                    grid_size=6,
                    interval_minutes=30
                ).first()
                if wind_field:
                    interval_seconds = wind_field.interval_minutes * 60
                    time_bucket = timestamp - (timestamp % interval_seconds)
                    points = (wind_field.data or {}).get('points', {}).get(str(time_bucket))
                    if points is None:
                        times = (wind_field.data or {}).get('times', [])
                        if times:
                            nearest = min(times, key=lambda t: abs(t - time_bucket))
                            points = (wind_field.data or {}).get('points', {}).get(str(nearest), [])
                        else:
                            points = []
                    return Response({
                        'timestamp': time_bucket,
                        'grid': wind_field.grid_size,
                        'units': {
                            'speed': 'kn',
                            'direction': 'degrees',
                        },
                        'points': points,
                    })

        try:
            min_lat = float(request.query_params.get('min_lat'))
            max_lat = float(request.query_params.get('max_lat'))
            min_lon = float(request.query_params.get('min_lon'))
            max_lon = float(request.query_params.get('max_lon'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'Invalid bounding box parameters'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            grid = int(request.query_params.get('grid', 4))
        except (TypeError, ValueError):
            grid = 4

        grid = max(2, min(grid, 6))

        min_lat, max_lat = sorted([min_lat, max_lat])
        min_lon, max_lon = sorted([min_lon, max_lon])

        time_bucket = timestamp - (timestamp % 3600)
        date_str = datetime.fromtimestamp(time_bucket, tz=dt_timezone.utc).date().isoformat()

        cache_key = (
            f"wind:{time_bucket}:{grid}:"
            f"{round(min_lat, 2)}:{round(max_lat, 2)}:{round(min_lon, 2)}:{round(max_lon, 2)}"
        )
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        lat_step = (max_lat - min_lat) / (grid - 1) if grid > 1 else 0
        lon_step = (max_lon - min_lon) / (grid - 1) if grid > 1 else 0

        hourly = HourlyHistorical().windspeed_10m().winddirection_10m()
        points = []

        def fetch_point(lat, lon):
            options = HistoricalOptions(
                lat,
                lon,
                windspeed_unit=kn,
                timeformat=unixtime,
                timezone='UTC',
                start_date=date_str,
                end_date=date_str
            )
            manager = OpenMeteo(options, hourly)
            data = manager.get_dict()
            hourly_data = data.get('hourly') if data else None
            if not hourly_data:
                return None

            times = hourly_data.get('time', [])
            speeds = hourly_data.get('windspeed_10m', [])
            directions = hourly_data.get('winddirection_10m', [])
            if not times:
                return None

            try:
                idx = times.index(time_bucket)
            except ValueError:
                idx = min(range(len(times)), key=lambda i: abs(times[i] - time_bucket))

            if idx >= len(speeds) or idx >= len(directions):
                return None

            return {
                'lon': lon,
                'lat': lat,
                'speed': speeds[idx],
                'direction': directions[idx],
            }

        for row in range(grid):
            lat = min_lat + (row * lat_step)
            for col in range(grid):
                lon = min_lon + (col * lon_step)
                try:
                    point = fetch_point(lat, lon)
                except Exception:
                    point = None
                if point:
                    points.append(point)

        response = {
            'timestamp': time_bucket,
            'grid': grid,
            'units': {
                'speed': 'kn',
                'direction': 'degrees',
            },
            'points': points,
        }
        cache.set(cache_key, response, 300)
        return Response(response)
    
    @action(detail=False, methods=['get'])
    def in_bounds(self, request):
        """
        Get recordings within a bounding box.
        
        Query params:
            min_lat, max_lat, min_lon, max_lon: Bounding box coordinates
        """
        try:
            min_lat = float(request.query_params.get('min_lat'))
            max_lat = float(request.query_params.get('max_lat'))
            min_lon = float(request.query_params.get('min_lon'))
            max_lon = float(request.query_params.get('max_lon'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'Invalid bounding box parameters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Filter recordings that intersect with the bounding box
        queryset = self.get_queryset().filter(
            status='ready',
            bounding_box__isnull=False,
        )
        
        # Filter by bounding box intersection
        # This is a simple check - recordings whose box overlaps with query box
        recordings = []
        for recording in queryset:
            bbox = recording.bounding_box
            if bbox:
                # Check if bounding boxes overlap
                if (bbox['min_lat'] <= max_lat and bbox['max_lat'] >= min_lat and
                    bbox['min_lon'] <= max_lon and bbox['max_lon'] >= min_lon):
                    recordings.append(recording)
        
        serializer = self.get_serializer(recordings, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def status(self, request, pk=None):
        """
        Get the processing status of a recording.
        
        Returns:
            Recording status and error message (if any)
        
        Only accessible for recordings the user uploaded or recordings for vessels they're connected with.
        """
        try:
            recording = Recording.objects.get(pk=pk)
        except Recording.DoesNotExist:
            return Response(
                {'error': 'Recording not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check access - user must own the recording or have access via vessel
        if not recording.is_accessible_by(request.user):
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return Response({
            'status': recording.status,
            'error_message': recording.error_message,
        })
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def crop(self, request, pk=None):
        """
        Crop a recording (remove beginning or end).
        
        Body params:
            crop_before: boolean (crop everything before current time)
            crop_after: boolean (crop everything after current time)
            current_time: float (timestamp in seconds from track start)
            context: string ('event' or 'recording')
            event_id: optional UUID (required if context='event')
        
        Returns:
            New cropped recording ID
        """
        try:
            original_recording = Recording.objects.get(pk=pk)
        except Recording.DoesNotExist:
            return Response(
                {'error': 'Recording not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions - only owner can crop
        if not original_recording.is_accessible_by(request.user) or original_recording.user != request.user:
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if original_recording.status != 'ready':
            return Response(
                {'error': 'Recording is not ready for cropping'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate request data
        crop_before = request.data.get('crop_before', False)
        crop_after = request.data.get('crop_after', False)
        current_time = request.data.get('current_time')
        context = request.data.get('context', 'recording')
        event_id = request.data.get('event_id')
        
        if not (crop_before or crop_after):
            return Response(
                {'error': 'Either crop_before or crop_after must be True'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if crop_before and crop_after:
            return Response(
                {'error': 'Cannot crop both before and after at the same time'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if current_time is None:
            return Response(
                {'error': 'current_time is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            current_time = float(current_time)
        except (ValueError, TypeError):
            return Response(
                {'error': 'current_time must be a number'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if context not in ['event', 'recording']:
            return Response(
                {'error': 'context must be "event" or "recording"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if context == 'event':
            # Get event from original recording (it should already be in an event)
            if not original_recording.event:
                return Response(
                    {'error': 'Recording is not part of an event'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            event_id = str(original_recording.event.id)
        
        # Validate crop parameters
        if not original_recording.start_time or not original_recording.end_time:
            return Response(
                {'error': 'Recording does not have valid time bounds'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate absolute timestamp from current_time (seconds from start)
        from datetime import timedelta
        crop_timestamp = original_recording.start_time + timedelta(seconds=current_time)
        
        # Validate crop is not at boundaries
        if crop_before and crop_timestamp <= original_recording.start_time:
            return Response(
                {'error': 'Cannot crop before start time'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if crop_after and crop_timestamp >= original_recording.end_time:
            return Response(
                {'error': 'Cannot crop after end time'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create new cropped recording in processing state
        cropped_recording = Recording.objects.create(
            user=original_recording.user,
            vessel=original_recording.vessel,
            event=original_recording.event if context == 'event' else None,
            visibility=original_recording.visibility,
            original_recording=original_recording,
            is_cropped=True,
            crop_start_time=crop_timestamp if crop_before else original_recording.start_time,
            crop_end_time=crop_timestamp if crop_after else original_recording.end_time,
            status='processing',
            original_filename=original_recording.original_filename,
        )
        
        # Queue async processing task
        async_task(
            'apps.tracks.tasks.process_track_crop',
            str(cropped_recording.id),
            str(original_recording.id),
            crop_before,
            crop_after,
            crop_timestamp.isoformat(),
            context,
            event_id,
        )
        
        return Response({
            'cropped_recording_id': str(cropped_recording.id),
            'status': 'processing',
        }, status=status.HTTP_202_ACCEPTED)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def remove_from_event(self, request, pk=None):
        """
        Remove a recording from its event.
        
        This sets the recording's event FK to None, effectively removing it from the event.
        The recording itself is not deleted.
        
        Returns:
            Success message
        """
        try:
            recording = Recording.objects.get(pk=pk)
        except Recording.DoesNotExist:
            return Response(
                {'error': 'Recording not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions - only owner can remove
        if not recording.is_accessible_by(request.user) or recording.user != request.user:
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if recording is in an event
        if not recording.event:
            return Response(
                {'error': 'Recording is not part of an event'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        event_name = recording.event.name
        recording.event = None
        recording.save()
        
        return Response({
            'message': f'Recording removed from event "{event_name}"',
            'recording_id': str(recording.id),
        })


class VesselViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for vessels.
    """
    serializer_class = VesselSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return vessels the user has access to."""
        user = self.request.user
        return VesselPermission.get_user_vessels(user)
