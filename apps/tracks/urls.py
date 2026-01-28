"""
URL configuration for tracks app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from . import api

app_name = 'tracks'

# API router
router = DefaultRouter()
router.register(r'recordings', api.RecordingViewSet, basename='recording')
router.register(r'vessels', api.VesselViewSet, basename='vessel')

urlpatterns = [
    # Home
    path('', views.home, name='home'),
    
    # Recordings
    path('recordings/', views.recording_list, name='recording_list'),
    path('recordings/upload/', views.upload_gpx, name='upload_gpx'),
    path('recordings/<uuid:pk>/', views.recording_detail, name='recording_detail'),
    path('recordings/<uuid:pk>/map/', views.recording_map, name='recording_map'),
    path('recordings/<uuid:pk>/status/', views.recording_status, name='recording_status'),
    path('recordings/<uuid:pk>/merge-event/', views.merge_event, name='merge_event'),
    
    # Vessels
    path('vessels/', views.vessel_list, name='vessel_list'),
    path('vessels/create/', views.create_vessel, name='create_vessel'),
    path('vessels/claim/', views.claim_vessel, name='claim_vessel'),
    path('vessels/<int:pk>/', views.vessel_detail, name='vessel_detail'),
    
    # Events
    path('events/', views.event_list, name='event_list'),
    path('events/<str:token>/upload/', views.upload_gpx_to_event, name='upload_to_event'),
    path('events/<str:token>/map/', views.event_map, name='event_map'),
    
    # API
    path('api/', include(router.urls)),
]
