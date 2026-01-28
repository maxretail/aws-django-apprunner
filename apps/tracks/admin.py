from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Vessel, Collection, Event, Recording, VesselPermission


@admin.register(Vessel)
class VesselAdmin(admin.ModelAdmin):
    list_display = ['name', 'sail_number', 'model_info', 'mmsi', 'created_at']
    search_fields = ['name', 'sail_number', 'aliases']
    list_filter = ['created_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ['name', 'date', 'created_by', 'created_at']
    search_fields = ['name', 'description']
    list_filter = ['date', 'created_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['name', 'event_type', 'date', 'collection', 'event_number']
    search_fields = ['name', 'description']
    list_filter = ['event_type', 'date', 'collection']
    readonly_fields = ['share_token', 'share_url', 'created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('name', 'event_type', 'date', 'collection', 'event_number', 'description')
        }),
        ('Sharing', {
            'fields': ('share_token', 'share_url'),
            'description': 'Share this event URL to allow anyone to upload tracks to this event.'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def share_url(self, obj):
        """Display the shareable URL for this event."""
        if obj.pk:
            try:
                url = reverse('tracks:upload_to_event', kwargs={'token': str(obj.share_token)})
                return format_html('<a href="{}" target="_blank">{}</a>', url, url)
            except:
                return 'N/A'
        return 'Save event to generate share URL'
    share_url.short_description = 'Share URL'


@admin.register(Recording)
class RecordingAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'vessel', 'user', 'status', 'visibility', 'start_time', 'point_count']
    search_fields = ['name', 'vessel__name', 'user__email', 'original_filename']
    list_filter = ['status', 'visibility', 'created_at']
    readonly_fields = ['id', 's3_prefix', 'created_at', 'updated_at']
    fieldsets = (
        (None, {
            'fields': ('name', 'vessel', 'event', 'user')
        }),
        ('Track Data', {
            'fields': ('start_time', 'end_time', 'bounding_box', 'point_count', 'distance_nm')
        }),
        ('Storage', {
            'fields': ('s3_prefix', 'original_filename')
        }),
        ('Status', {
            'fields': ('status', 'error_message', 'visibility')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(VesselPermission)
class VesselPermissionAdmin(admin.ModelAdmin):
    list_display = ['user', 'vessel', 'status', 'is_primary_owner', 'can_upload_tracks', 'created_at']
    search_fields = ['user__email', 'vessel__name']
    list_filter = ['status', 'is_primary_owner', 'created_at']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['approve_selected', 'reject_selected']

    @admin.action(description='Approve selected permissions')
    def approve_selected(self, request, queryset):
        queryset.update(status='approved')

    @admin.action(description='Reject selected permissions')
    def reject_selected(self, request, queryset):
        queryset.update(status='rejected')
