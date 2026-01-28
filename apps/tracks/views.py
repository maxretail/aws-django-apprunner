"""
Views for tracks app.
"""

import os
import tempfile
import uuid

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django_q.tasks import async_task

from .models import Recording, Vessel, VesselPermission, Event
from .forms import GPXUploadForm, VesselForm, VesselClaimForm, EventGPXUploadForm, EventForm
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


def home(request):
    """Home page."""
    from django.db.models import Count
    
    if request.user.is_authenticated:
        # Show user's accessible recordings
        recordings = Recording.get_accessible_recordings(request.user).filter(
            status='ready',
            original_recording__isnull=False  # Only cropped recordings
        ).annotate(
            cropped_count=Count('cropped_versions')
        ).filter(
            cropped_count=0  # Only leaf nodes
        ).distinct().order_by('-created_at')[:10]
    else:
        # Anonymous users see nothing
        recordings = Recording.objects.none()
    
    context = {
        'recent_recordings': recordings
    }
    return render(request, 'tracks/home.html', context)


@login_required
def recording_list(request):
    """List recordings for the current user."""
    from django.db.models import Count
    # Show recordings the user uploaded OR recordings for vessels they're connected with.
    #
    # We show only "leaf" recordings (i.e., recordings that do not have any further
    # cropped_versions). This includes:
    # - Original uploads (original_recording is NULL), and
    # - Cropped children (original_recording is NOT NULL),
    # as long as they're the most recent/active version.
    recordings = Recording.get_accessible_recordings(request.user).annotate(
        cropped_count=Count('cropped_versions')
    ).filter(
        cropped_count=0  # Only show leaf nodes (no further crops)
    ).order_by('-created_at')
    return render(request, 'tracks/recording_list.html', {
        'recordings': recordings
    })


@login_required
def recording_detail(request, pk):
    """View a recording on a map."""
    recording = get_object_or_404(Recording, pk=pk)
    
    # Check access
    if not recording.is_accessible_by(request.user):
        messages.error(request, 'You do not have access to this recording.')
        return redirect('tracks:recording_list')
    
    # Check for overlapping events if this recording has an event and is ready
    overlapping_events = None
    if recording.event and recording.status == 'ready' and recording.bounding_box and recording.start_time and recording.end_time:
        # Only check if this is the first recording for the event (just created)
        if recording.event.recordings.count() == 1:
            overlapping_events = Event.find_overlapping_events(
                bounding_box=recording.bounding_box,
                start_time=recording.start_time,
                end_time=recording.end_time,
                exclude_event=recording.event
            )
    
    return render(request, 'tracks/recording_detail.html', {
        'recording': recording,
        'overlapping_events': overlapping_events
    })


@login_required
def recording_map(request, pk):
    """Full-screen map view for a recording."""
    recording = get_object_or_404(Recording, pk=pk)
    
    # Check access
    if not recording.is_accessible_by(request.user):
        messages.error(request, 'You do not have access to this recording.')
        return redirect('tracks:recording_list')
    
    # If recording is part of an event, redirect to event map
    if recording.event:
        return redirect('tracks:event_map', token=recording.event.share_token)
    
    # Otherwise, show single recording using event_map template with one recording
    return render(request, 'tracks/event_map.html', {
        'event': None,  # No event for single recording
        'recordings': [recording]
    })


@login_required
def multi_recording_map(request):
    """
    Full-screen map view for multiple recordings without creating an Event.

    Query params:
      - recording_id=<uuid> (repeatable)
      - ids=<uuid,uuid,...> (comma-separated fallback)
    """
    recording_ids = request.GET.getlist('recording_id')
    if not recording_ids:
        ids_csv = (request.GET.get('ids') or '').strip()
        if ids_csv:
            recording_ids = [x.strip() for x in ids_csv.split(',') if x.strip()]

    if not recording_ids:
        messages.error(request, 'Select at least one track to view on the map.')
        return redirect('tracks:recording_list')

    # Load recordings, enforce access control, and keep ordering consistent with selection
    recordings_by_id = {}
    accessible = Recording.get_accessible_recordings(request.user).filter(
        status='ready',
        id__in=recording_ids,
    ).select_related('vessel', 'event')
    for rec in accessible:
        recordings_by_id[str(rec.id)] = rec

    recordings = [recordings_by_id.get(str(rid)) for rid in recording_ids if recordings_by_id.get(str(rid))]

    if not recordings:
        messages.error(request, 'No accessible ready tracks were found for that selection.')
        return redirect('tracks:recording_list')

    return render(request, 'tracks/event_map.html', {
        'event': None,
        'recordings': recordings,
        'is_virtual_multi': True,
    })


@login_required
def upload_gpx(request):
    """Upload a GPX file."""
    if request.method == 'POST':
        form = GPXUploadForm(request.POST, request.FILES, user=request.user)
        
        if form.is_valid():
            gpx_file = form.cleaned_data['gpx_file']
            event_name = form.cleaned_data.get('name', '').strip()
            
            # Create or find event if name is provided
            event = None
            if event_name:
                from datetime import date
                # Try to find existing event with same name
                event = Event.objects.filter(name=event_name).first()
                if not event:
                    # Create new event - date will be set after GPX is processed
                    event = Event.objects.create(
                        name=event_name,
                        date=date.today(),  # Will be updated after processing
                        created_by=request.user if request.user.is_authenticated else None
                    )
            
            # Create recording in processing state (no name field, default to public)
            recording = Recording.objects.create(
                user=request.user,
                vessel=form.cleaned_data.get('vessel'),
                event=event,
                name='',  # Recordings don't have names anymore
                visibility='public',  # All recordings are public by default
                status='processing',
                original_filename=gpx_file.name,
            )
            
            # Save track file to temp location
            temp_dir = tempfile.mkdtemp()
            # Preserve original file extension
            file_ext = os.path.splitext(gpx_file.name)[1] or '.gpx'
            temp_path = os.path.join(temp_dir, f'{recording.id}{file_ext}')
            
            with open(temp_path, 'wb') as f:
                for chunk in gpx_file.chunks():
                    f.write(chunk)
            
            # Queue async processing task
            async_task(
                'apps.tracks.tasks.process_gpx_upload',
                str(recording.id),
                temp_path,
            )
            
            messages.success(
                request,
                'Your GPX file has been uploaded and is being processed. '
                'This page will update when processing is complete.'
            )
            return redirect('tracks:recording_detail', pk=recording.id)
    else:
        form = GPXUploadForm(user=request.user)
    
    return render(request, 'tracks/upload.html', {'form': form})


@login_required
def recording_status(request, pk):
    """AJAX endpoint to check recording processing status."""
    recording = get_object_or_404(Recording, pk=pk)
    
    # Check access
    if not recording.is_accessible_by(request.user):
        return JsonResponse({
            'error': 'Access denied'
        }, status=403)
    
    return JsonResponse({
        'status': recording.status,
        'error_message': recording.error_message,
    })


@login_required
def merge_event(request, pk):
    """Merge recording's event into an existing event."""
    recording = get_object_or_404(Recording, pk=pk)
    
    # Check access
    if not recording.is_accessible_by(request.user):
        messages.error(request, 'You do not have access to this recording.')
        return redirect('tracks:recording_list')
    
    if request.method == 'POST':
        target_event_id = request.POST.get('target_event_id')
        action = request.POST.get('action')
        
        if action == 'merge' and target_event_id and recording.event:
            try:
                target_event = Event.objects.get(pk=target_event_id)
                old_event = recording.event
                
                # Move recording to target event
                recording.event = target_event
                recording.save()
                
                # Delete old event if it has no more recordings
                if old_event.recordings.count() == 0:
                    old_event.delete()
                    messages.success(
                        request,
                        f'Your track has been merged into "{target_event.name}". '
                        f'The duplicate event has been removed.'
                    )
                else:
                    messages.success(
                        request,
                        f'Your track has been merged into "{target_event.name}".'
                    )
                
                return redirect('tracks:recording_detail', pk=recording.pk)
            except Event.DoesNotExist:
                messages.error(request, 'Target event not found.')
        else:
            messages.error(request, 'Invalid request.')
    
    return redirect('tracks:recording_detail', pk=recording.pk)


@login_required
def vessel_list(request):
    """List vessels the user has access to."""
    user_permissions = VesselPermission.objects.filter(
        user=request.user,
        status='approved'
    ).select_related('vessel')
    
    return render(request, 'tracks/vessel_list.html', {
        'permissions': user_permissions
    })


@login_required
def vessel_detail(request, pk):
    """View vessel details."""
    vessel = get_object_or_404(Vessel, pk=pk)
    
    # Check if user has access
    has_access = VesselPermission.objects.filter(
        user=request.user,
        vessel=vessel,
        status='approved'
    ).exists()
    
    if not has_access:
        messages.error(request, 'You do not have access to this vessel.')
        return redirect('tracks:vessel_list')
    
    # Get recordings for this vessel that the user can see
    # User can see recordings they uploaded OR recordings for vessels they're connected with
    recordings = Recording.get_accessible_recordings(request.user).filter(
        vessel=vessel,
        status='ready'
    ).order_by('-start_time')[:20]
    
    return render(request, 'tracks/vessel_detail.html', {
        'vessel': vessel,
        'has_access': has_access,
        'recordings': recordings
    })


@login_required
def claim_vessel(request):
    """Claim a vessel."""
    if request.method == 'POST':
        form = VesselClaimForm(request.POST)
        
        if form.is_valid():
            vessel = form.cleaned_data['vessel']
            
            # Check if already claimed
            existing = VesselPermission.objects.filter(
                user=request.user,
                vessel=vessel
            ).first()
            
            if existing:
                if existing.status == 'approved':
                    messages.info(request, 'You already have access to this vessel.')
                elif existing.status == 'pending':
                    messages.info(request, 'Your claim for this vessel is pending approval.')
                else:
                    messages.warning(request, 'Your previous claim was rejected. Please contact support.')
                return redirect('tracks:vessel_list')
            
            # Create pending claim
            VesselPermission.objects.create(
                user=request.user,
                vessel=vessel,
                status='pending',
                admin_notes=form.cleaned_data.get('notes', '')
            )
            
            messages.success(
                request,
                f'Your claim for "{vessel.name}" has been submitted and is pending approval.'
            )
            return redirect('tracks:vessel_list')
    else:
        form = VesselClaimForm()
    
    return render(request, 'tracks/claim_vessel.html', {'form': form})


@login_required
def create_vessel(request):
    """Create a new vessel."""
    if request.method == 'POST':
        form = VesselForm(request.POST, request.FILES)
        
        if form.is_valid():
            vessel = form.save()
            
            # Automatically grant the creator permission
            VesselPermission.objects.create(
                user=request.user,
                vessel=vessel,
                status='approved',
                is_primary_owner=True,
                can_upload_tracks=True
            )
            
            messages.success(request, f'Vessel "{vessel.name}" has been created.')
            return redirect('tracks:vessel_detail', pk=vessel.pk)
    else:
        form = VesselForm()
    
    return render(request, 'tracks/vessel_form.html', {
        'form': form,
        'title': 'Create New Vessel'
    })


def get_or_create_anonymous_user():
    """Get or create a system user for anonymous uploads."""
    User = get_user_model()
    email = 'anonymous@sailarchive.local'
    try:
        return User.objects.get(email=email)
    except User.DoesNotExist:
        # Create a system user for anonymous uploads
        return User.objects.create_user(
            email=email,
            password=None,  # No password - this user can't log in
            is_active=True
        )


@csrf_exempt
def upload_gpx_to_event(request, token):
    """
    Upload a GPX file to a specific event.
    Works for both authenticated and anonymous users.
    """
    # Look up event by share token
    try:
        event = Event.objects.get(share_token=token)
    except Event.DoesNotExist:
        messages.error(request, 'Invalid event link. Please check the URL and try again.')
        return redirect('tracks:home')
    
    # Determine user (authenticated or anonymous)
    if request.user.is_authenticated:
        upload_user = request.user
        is_anonymous = False
        # Get the last vessel the user uploaded a track for
        last_recording = Recording.objects.filter(
            user=upload_user,
            vessel__isnull=False
        ).order_by('-created_at').first()
        last_vessel = last_recording.vessel if last_recording else None
    else:
        upload_user = get_or_create_anonymous_user()
        is_anonymous = True
        last_vessel = None
    
    if request.method == 'POST':
        form = EventGPXUploadForm(request.POST, request.FILES, user=request.user, event=event, last_vessel=last_vessel)
        
        if form.is_valid():
            gpx_file = form.cleaned_data['gpx_file']
            
            # Handle vessel - either use provided vessel or create/find by name
            vessel = form.cleaned_data.get('vessel')
            vessel_name = form.cleaned_data.get('vessel_name', '').strip()
            
            if not vessel and vessel_name:
                # Find or create vessel by name
                vessel = Vessel.find_by_name_or_alias(vessel_name)
                if not vessel:
                    vessel = Vessel.objects.create(name=vessel_name)
            
            # Create recording in processing state (no name field - event already exists)
            recording = Recording.objects.create(
                user=upload_user,
                vessel=vessel,
                event=event,
                name='',  # Recordings don't have names anymore
                visibility='public',  # All event uploads are public
                status='processing',
                original_filename=gpx_file.name,
            )
            
            # Save track file to temp location
            temp_dir = tempfile.mkdtemp()
            # Preserve original file extension
            file_ext = os.path.splitext(gpx_file.name)[1] or '.gpx'
            temp_path = os.path.join(temp_dir, f'{recording.id}{file_ext}')
            
            with open(temp_path, 'wb') as f:
                for chunk in gpx_file.chunks():
                    f.write(chunk)
            
            # Queue async processing task
            async_task(
                'apps.tracks.tasks.process_gpx_upload',
                str(recording.id),
                temp_path,
            )
            
            messages.success(
                request,
                f'Your track has been uploaded to "{event.name}" and is being processed. '
                'Thank you for contributing!'
            )
            
            # Redirect to success page (different for anonymous users)
            if is_anonymous:
                return render(request, 'tracks/upload_success.html', {
                    'recording': recording,
                    'event': event,
                    'is_anonymous': True
                })
            else:
                return redirect('tracks:recording_detail', pk=recording.id)
    else:
        form = EventGPXUploadForm(user=request.user, event=event, last_vessel=last_vessel)
    
    # Get all ready recordings for this event that the user can see
    if request.user.is_authenticated:
        recordings = Recording.get_accessible_recordings(request.user).filter(
            event=event,
            status='ready'
        ).select_related('vessel').order_by('-start_time')
    else:
        # Anonymous users see nothing
        recordings = Recording.objects.none()
    
    return render(request, 'tracks/upload_to_event.html', {
        'form': form,
        'event': event,
        'is_anonymous': is_anonymous,
        'recordings': recordings
    })


def event_map(request, token):
    """
    Full-screen map view showing all tracks for an event.
    Shows only recordings the user uploaded OR recordings for vessels they're connected with.
    """
    # Look up event by share token
    try:
        event = Event.objects.get(share_token=token)
    except Event.DoesNotExist:
        messages.error(request, 'Invalid event link. Please check the URL and try again.')
        return redirect('tracks:home')
    
    # Get all ready recordings for this event that the user can see
    if request.user.is_authenticated:
        recordings = Recording.get_accessible_recordings(request.user).filter(
            event=event,
            status='ready'
        ).select_related('vessel').order_by('-start_time')
    else:
        # Anonymous users see nothing
        recordings = Recording.objects.none()
    
    return render(request, 'tracks/event_map.html', {
        'event': event,
        'recordings': recordings
    })


@login_required
def event_list(request):
    """
    List events the user has participated in.
    Shows events where the user has uploaded tracks OR events with recordings for vessels they're connected with.
    """
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            event.save()
            messages.success(request, f'Event "{event.name}" created.')
            return redirect('tracks:upload_to_event', token=event.share_token)
    else:
        form = EventForm()

    # Show events where user has accessible recordings
    # Get recordings the user can access
    accessible_recordings = Recording.get_accessible_recordings(request.user)
    # Get events from those recordings
    user_events = Event.objects.filter(
        recordings__in=accessible_recordings
    ).distinct().order_by('-date', '-created_at')
    
    return render(request, 'tracks/event_list.html', {
        'events': user_events,
        'is_authenticated': True,
        'event_form': form
    })
