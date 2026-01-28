"""
URL configuration for SailArchive project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # Authentication (django-registration-redux)
    path('accounts/', include('registration.backends.default.urls')),
    
    # Core app (health checks, etc.)
    path('', include('apps.core.urls', namespace='core')),
    
    # Tracks app (main functionality)
    path('', include('apps.tracks.urls', namespace='tracks')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
