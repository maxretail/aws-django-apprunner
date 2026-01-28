"""
Forms for tracks app.
"""

from django import forms
from .models import Recording, Vessel, VesselPermission, Event


class GPXUploadForm(forms.Form):
    """Form for uploading track files (GPX or JSON)."""
    gpx_file = forms.FileField(
        label='Track File',
        help_text='Upload a GPX or JSON file containing your track data'
    )
    vessel = forms.ModelChoiceField(
        queryset=Vessel.objects.none(),
        required=False,
        empty_label='Select a vessel (optional)',
        help_text='Associate this track with one of your vessels'
    )
    name = forms.CharField(
        max_length=200,
        required=False,
        help_text='Event name (optional - if provided, will create or find an event with this name)'
    )
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            # Limit vessel choices to vessels the user has permission to upload for
            user_vessels = VesselPermission.objects.filter(
                user=user,
                status='approved',
                can_upload_tracks=True
            ).values_list('vessel_id', flat=True)
            self.fields['vessel'].queryset = Vessel.objects.filter(id__in=user_vessels)
    
    def clean_gpx_file(self):
        """Validate the uploaded file is a GPX or JSON file."""
        gpx_file = self.cleaned_data.get('gpx_file')
        if gpx_file:
            # Check file extension
            filename_lower = gpx_file.name.lower()
            if not (filename_lower.endswith('.gpx') or filename_lower.endswith('.json')):
                raise forms.ValidationError('File must be a GPX file (.gpx) or JSON file (.json)')
            
            # Check file size (max 50MB)
            if gpx_file.size > 50 * 1024 * 1024:
                raise forms.ValidationError('File size must be less than 50MB')
        
        return gpx_file


class VesselForm(forms.ModelForm):
    """Form for creating/editing vessels."""
    
    class Meta:
        model = Vessel
        fields = ['name', 'sail_number', 'model_info', 'mmsi', 'icon']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'sail_number': forms.TextInput(attrs={'class': 'form-control'}),
            'model_info': forms.TextInput(attrs={'class': 'form-control'}),
            'mmsi': forms.TextInput(attrs={'class': 'form-control'}),
        }


class VesselClaimForm(forms.Form):
    """Form for claiming an existing vessel."""
    vessel = forms.ModelChoiceField(
        queryset=Vessel.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Select a vessel to claim'
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        required=False,
        help_text='Explain your connection to this vessel (optional)'
    )


class EventForm(forms.ModelForm):
    """Form for creating events."""

    class Meta:
        model = Event
        fields = ['name', 'event_type', 'date', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'event_type': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class EventGPXUploadForm(forms.Form):
    """Form for uploading track files (GPX or JSON) to an event (works for both authenticated and anonymous users)."""
    gpx_file = forms.FileField(
        label='Track File',
        help_text='Upload a GPX or JSON file containing your track data'
    )
    vessel_name = forms.CharField(
        max_length=200,
        required=False,
        help_text='Name of your boat',
        widget=forms.TextInput(attrs={
            'autocomplete': 'on',
            'autocapitalize': 'words',
            'spellcheck': 'true',
            'data-lpignore': 'false',  # Allow LastPass and similar password managers to see this field
        })
    )
    # Note: No name field - event already exists
    vessel = forms.ModelChoiceField(
        queryset=Vessel.objects.none(),
        required=False,
        empty_label='Select a vessel (optional)',
        help_text='Or select one of your vessels (only shown if logged in)'
    )
    
    def __init__(self, *args, user=None, event=None, last_vessel=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.event = event
        
        # Only show vessel dropdown if user is authenticated
        if user and user.is_authenticated:
            # Limit vessel choices to vessels the user has permission to upload for
            user_vessels = VesselPermission.objects.filter(
                user=user,
                status='approved',
                can_upload_tracks=True
            ).values_list('vessel_id', flat=True)
            self.fields['vessel'].queryset = Vessel.objects.filter(id__in=user_vessels)
            
            # Set default vessel to last uploaded vessel if available
            if last_vessel and last_vessel.id in user_vessels:
                self.fields['vessel'].initial = last_vessel.id
        else:
            # Hide vessel dropdown for anonymous users
            self.fields['vessel'].widget = forms.HiddenInput()
            # Make vessel_name required for anonymous users
            self.fields['vessel_name'].required = True
            self.fields['vessel_name'].help_text = 'Name of your boat (required)'
    
    def clean_gpx_file(self):
        """Validate the uploaded file is a GPX or JSON file."""
        gpx_file = self.cleaned_data.get('gpx_file')
        if gpx_file:
            # Check file extension
            filename_lower = gpx_file.name.lower()
            if not (filename_lower.endswith('.gpx') or filename_lower.endswith('.json')):
                raise forms.ValidationError('File must be a GPX file (.gpx) or JSON file (.json)')
            
            # Check file size (max 50MB)
            if gpx_file.size > 50 * 1024 * 1024:
                raise forms.ValidationError('File size must be less than 50MB')
        
        return gpx_file
    
    def clean(self):
        """Validate vessel requirements."""
        cleaned_data = super().clean()
        vessel_name = cleaned_data.get('vessel_name', '').strip()
        vessel = cleaned_data.get('vessel')
        
        # For anonymous users, vessel_name is required
        if not self.user or not self.user.is_authenticated:
            if not vessel_name:
                raise forms.ValidationError({
                    'vessel_name': 'Boat name is required.'
                })
        
        # For authenticated users, either vessel or vessel_name should be provided
        # (but both are optional - they can upload without specifying)
        # If vessel is selected, prefer that over vessel_name
        
        return cleaned_data
