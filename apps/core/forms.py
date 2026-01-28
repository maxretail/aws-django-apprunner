"""
Custom forms for authentication and registration.
"""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from registration.forms import RegistrationForm

User = get_user_model()


class EmailRegistrationForm(RegistrationForm):
    """
    Custom registration form that uses email instead of username.
    """
    email = forms.EmailField(
        label='Email',
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'autofocus': True,
            'required': True,
        }),
        help_text='Required. Enter a valid email address.'
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        help_text='Your password must contain at least 8 characters.'
    )
    password2 = forms.CharField(
        label='Password confirmation',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        help_text='Enter the same password as before, for verification.'
    )

    class Meta:
        model = User
        fields = ('email',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove username field if it exists
        if 'username' in self.fields:
            del self.fields['username']
        
        # Make email required
        self.fields['email'].required = True

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email

    def save(self, commit=True):
        # Create user with email (no username needed)
        user = User.objects.create_user(
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password1']
        )
        return user
