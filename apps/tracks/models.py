"""
Data models for SailArchive tracks app.

Key design decisions:
- No TrackPoint table - all GPS data is stored on DO Spaces as JSON files
- Recording model stores only metadata (bounds, times, S3 prefix)
- Zoom-level simplified tracks are pre-computed on upload
"""

from django.db import models
from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image
import io
import uuid


class Vessel(models.Model):
    """
    A sailing vessel (boat, kayak, etc.) that can have track recordings.
    """
    name = models.CharField(max_length=200, help_text="Name of the vessel")
    sail_number = models.CharField(max_length=50, blank=True, null=True, help_text="Sail number")
    model_info = models.CharField(max_length=200, blank=True, null=True, help_text="Vessel model/type")
    mmsi = models.CharField(max_length=9, blank=True, null=True, help_text="MMSI for AIS tracking")
    aliases = models.JSONField(default=list, help_text="Alternative names for this vessel")
    icon = models.ImageField(
        upload_to='vessel_icons/',
        blank=True,
        null=True,
        help_text="96x96 pixel icon for this vessel"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        model_suffix = f" ({self.model_info})" if self.model_info else ""
        return f"{self.name}{model_suffix}"

    def save(self, *args, **kwargs):
        """Ensure name is in aliases and resize icon if needed."""
        if not self.aliases:
            self.aliases = [self.name]
        elif self.name not in self.aliases:
            self.aliases.append(self.name)

        # Resize icon to 96x96 if provided
        if self.icon and hasattr(self.icon, 'file'):
            try:
                img = Image.open(self.icon)
                if img.mode in ('P', 'LA'):
                    img = img.convert('RGBA')
                elif img.mode not in ('RGBA', 'RGB'):
                    img = img.convert('RGBA')

                # Crop to square
                width, height = img.size
                if width != height:
                    size = min(width, height)
                    left = (width - size) // 2
                    top = (height - size) // 2
                    img = img.crop((left, top, left + size, top + size))

                # Resize to 96x96
                img = img.resize((96, 96), Image.Resampling.LANCZOS)

                # Save to memory
                img_io = io.BytesIO()
                img.save(img_io, format='PNG')
                img_io.seek(0)

                filename = f'icon_{self.pk or "new"}.png'
                self.icon.save(filename, ContentFile(img_io.read()), save=False)
            except Exception:
                pass  # Continue without resizing if there's an error

        super().save(*args, **kwargs)

    @classmethod
    def find_by_name_or_alias(cls, name):
        """Find a vessel by name or any of its aliases."""
        return cls.objects.filter(
            models.Q(name__iexact=name) |
            models.Q(aliases__icontains=name)
        ).first()


class Collection(models.Model):
    """
    A collection of related recordings (e.g., a regatta, trip, or season).
    """
    name = models.CharField(max_length=200, help_text="Name of the collection")
    description = models.TextField(blank=True, null=True)
    date = models.DateField(null=True, blank=True, help_text="Primary date of the collection")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='collections')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'name']

    def __str__(self):
        return self.name


class Event(models.Model):
    """
    A specific event within a collection (e.g., a race, leg, or day).
    """
    EVENT_TYPES = [
        ('race', 'Race'),
        ('cruise', 'Cruise'),
        ('delivery', 'Delivery'),
        ('training', 'Training'),
        ('other', 'Other'),
    ]

    collection = models.ForeignKey(
        Collection,
        on_delete=models.CASCADE,
        related_name='events',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=200, help_text="Name of the event")
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, default='other')
    date = models.DateField(help_text="Date of the event")
    event_number = models.PositiveIntegerField(null=True, blank=True, help_text="Event number in collection")
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_events')
    share_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        help_text="Unique token for sharing this event and allowing anonymous uploads"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date', 'event_number']

    def __str__(self):
        return f"{self.name} ({self.date})"
    
    def get_share_url(self, request=None):
        """Generate the shareable URL for this event."""
        from django.urls import reverse
        if request:
            return request.build_absolute_uri(reverse('tracks:upload_to_event', kwargs={'token': str(self.share_token)}))
        # Fallback if no request object
        return f"/events/{self.share_token}/upload/"
    
    @classmethod
    def find_overlapping_events(cls, bounding_box, start_time, end_time, exclude_event=None):
        """
        Find events whose recordings overlap with the given bounding box and time range.
        
        Args:
            bounding_box: dict with min_lat, max_lat, min_lon, max_lon
            start_time: datetime start time
            end_time: datetime end time
            exclude_event: Event to exclude from results (e.g., the current event)
        
        Returns:
            QuerySet of overlapping events
        """
        if not bounding_box or not start_time or not end_time:
            return cls.objects.none()
        
        # Get all events with ready recordings that have bounding boxes
        events_with_recordings = cls.objects.filter(
            recordings__status='ready',
            recordings__bounding_box__isnull=False,
            recordings__start_time__isnull=False,
            recordings__end_time__isnull=False
        ).distinct()
        
        if exclude_event:
            events_with_recordings = events_with_recordings.exclude(pk=exclude_event.pk)
        
        # Check each event's recordings for overlap
        overlapping_events = []
        for event in events_with_recordings:
            # Get all ready recordings for this event
            recordings = event.recordings.filter(
                status='ready',
                bounding_box__isnull=False,
                start_time__isnull=False,
                end_time__isnull=False
            )
            
            for recording in recordings:
                rec_bbox = recording.bounding_box
                if not rec_bbox:
                    continue
                
                # Check bounding box intersection
                bbox_overlaps = (
                    rec_bbox['min_lat'] <= bounding_box['max_lat'] and
                    rec_bbox['max_lat'] >= bounding_box['min_lat'] and
                    rec_bbox['min_lon'] <= bounding_box['max_lon'] and
                    rec_bbox['max_lon'] >= bounding_box['min_lon']
                )
                
                # Check time overlap (time ranges intersect or are within 1 hour)
                if bbox_overlaps:
                    # Check if time ranges overlap
                    time_ranges_overlap = (
                        recording.start_time <= end_time and
                        recording.end_time >= start_time
                    )
                    
                    # Also check if they're close in time (within 1 hour) even if ranges don't overlap
                    time_diff_start = abs((recording.start_time - start_time).total_seconds())
                    time_diff_end = abs((recording.end_time - end_time).total_seconds())
                    time_close = time_diff_start < 3600 or time_diff_end < 3600
                    
                    if time_ranges_overlap or time_close:
                        overlapping_events.append(event.pk)
                        break  # Found overlap for this event, no need to check more recordings
        
        return cls.objects.filter(pk__in=overlapping_events).distinct()


class EventWindField(models.Model):
    """
    Precomputed wind data for an event bounding box and time range.
    """
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='wind_fields'
    )
    grid_size = models.PositiveSmallIntegerField(default=6)
    interval_minutes = models.PositiveSmallIntegerField(default=30)
    bounding_box = models.JSONField()
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    data = models.JSONField(default=dict)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('event', 'grid_size', 'interval_minutes')

    def __str__(self):
        return f"WindField {self.event_id} ({self.grid_size}x{self.grid_size}, {self.interval_minutes}m)"


class Recording(models.Model):
    """
    A GPS track recording. The actual track data is stored on DO Spaces,
    this model stores only metadata for querying and display.
    """
    VISIBILITY_CHOICES = [
        ('private', 'Private'),
        ('shared', 'Shared'),
        ('public', 'Public'),
    ]

    STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    # Generate a unique ID for S3 path
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relationships
    vessel = models.ForeignKey(
        Vessel,
        on_delete=models.CASCADE,
        related_name='recordings',
        null=True,
        blank=True
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recordings'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recordings',
        help_text="User who uploaded this recording"
    )

    # Track metadata
    name = models.CharField(max_length=200, blank=True, help_text="Optional name for this recording")
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    # Spatial bounds for viewport queries
    bounding_box = models.JSONField(
        null=True,
        blank=True,
        help_text='{"min_lat": x, "max_lat": x, "min_lon": x, "max_lon": x}'
    )

    # Statistics
    point_count = models.PositiveIntegerField(default=0)
    distance_nm = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total distance in nautical miles"
    )

    # S3 storage
    s3_prefix = models.CharField(
        max_length=255,
        blank=True,
        help_text="S3 prefix for track files (e.g., 'tracks/uuid/')"
    )

    # Processing status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='processing')
    error_message = models.TextField(blank=True, null=True)

    # Access control
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='private')

    # Original file info
    original_filename = models.CharField(max_length=255, blank=True, null=True)

    # Crop tracking
    original_recording = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cropped_versions',
        help_text="The recording this was cropped from (if any)"
    )
    crop_start_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp where crop started (if cropped from beginning)"
    )
    crop_end_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp where crop ended (if cropped from end)"
    )
    is_cropped = models.BooleanField(
        default=False,
        help_text="Quick flag to identify cropped recordings"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        if self.event:
            vessel_name = self.vessel.name if self.vessel else "Unknown Vessel"
            return f"{self.event.name} - {vessel_name} - {self.start_time}"
        elif self.vessel:
            return f"{self.vessel.name} - {self.start_time}"
        else:
            return f"Recording - {self.start_time}"

    @property
    def duration(self):
        """Return the duration of the recording."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    def get_s3_key(self, zoom_level='raw'):
        """Get the S3 key for a specific zoom level file."""
        if not self.s3_prefix:
            self.s3_prefix = f"tracks/{self.id}/"
        return f"{self.s3_prefix}{zoom_level}.json"

    def is_accessible_by(self, user):
        """Check if a user can access this recording."""
        if not user or not user.is_authenticated:
            return False
        
        # User owns the recording
        if self.user == user:
            return True
        
        # User has access via vessel permission
        if self.vessel:
            return VesselPermission.objects.filter(
                user=user,
                vessel=self.vessel,
                status='approved'
            ).exists()
        
        return False
    
    @classmethod
    def get_accessible_recordings(cls, user):
        """
        Get all recordings accessible by a user.
        Returns recordings the user uploaded OR recordings for vessels they're connected with.
        """
        if not user or not user.is_authenticated:
            return cls.objects.none()
        
        # Get vessels the user has access to
        user_vessels = VesselPermission.get_user_vessels(user)
        
        # Return recordings where:
        # 1. User uploaded them, OR
        # 2. Recording is for a vessel the user has access to
        return cls.objects.filter(
            models.Q(user=user) |
            models.Q(vessel__in=user_vessels)
        ).distinct()


class VesselPermission(models.Model):
    """
    Associates users with vessels for access control.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vessel_permissions')
    vessel = models.ForeignKey(Vessel, on_delete=models.CASCADE, related_name='user_permissions')
    is_primary_owner = models.BooleanField(default=False)
    can_upload_tracks = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'vessel']
        ordering = ['user', 'vessel']

    def __str__(self):
        owner_status = " (Primary Owner)" if self.is_primary_owner else ""
        return f"{self.user.email} -> {self.vessel.name}{owner_status}"

    @classmethod
    def get_user_vessels(cls, user, status='approved'):
        """Get all vessels a user has access to."""
        return Vessel.objects.filter(
            user_permissions__user=user,
            user_permissions__status=status
        )

    @classmethod
    def can_user_upload(cls, user, vessel):
        """Check if a user can upload tracks for a vessel."""
        perm = cls.objects.filter(user=user, vessel=vessel, status='approved').first()
        return perm and perm.can_upload_tracks
