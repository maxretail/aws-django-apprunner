"""
GPX file parser for SailArchive.

Parses GPX files and extracts track data with timestamps, speeds, and courses.
Supports multiple GPX formats including RaceQs, Tacktracker, Strava, and Garmin.
"""

import logging
from datetime import datetime, timezone
from math import radians, sin, cos, sqrt, atan2

import gpxpy
import gpxpy.gpx

logger = logging.getLogger(__name__)


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance in nautical miles between two points.
    """
    R = 3440.065  # Earth's radius in nautical miles
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c


def calculate_speed_knots(distance_nm, time_delta_seconds):
    """Calculate speed in knots from distance and time."""
    if time_delta_seconds <= 0:
        return 0
    hours = time_delta_seconds / 3600
    return distance_nm / hours if hours > 0 else 0


def calculate_bearing(lat1, lon1, lat2, lon2):
    """Calculate bearing in degrees from point 1 to point 2."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    
    bearing = atan2(x, y)
    bearing = (bearing * 180 / 3.14159265359 + 360) % 360
    
    return bearing


class GPXTrackParser:
    """
    Parser for GPX track files.
    
    Extracts track points with timestamps, calculates speeds and courses,
    and normalizes data for storage.
    """
    
    def __init__(self, gpx_content):
        """
        Initialize parser with GPX file content.
        
        Args:
            gpx_content: string or bytes containing GPX XML
        """
        if isinstance(gpx_content, bytes):
            gpx_content = gpx_content.decode('utf-8')
        
        self.gpx = gpxpy.parse(gpx_content)
        self.points = []
        self.metadata = {}
        
    def parse(self):
        """
        Parse the GPX file and extract all track points.
        
        Returns:
            List of track points as dicts with lat, lon, timestamp, speed, course
        """
        self.points = []
        
        # Extract points from tracks
        for track in self.gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    if point.time is None:
                        continue  # Skip points without timestamps
                    
                    self.points.append({
                        'lat': float(point.latitude),
                        'lon': float(point.longitude),
                        'timestamp': point.time.isoformat(),
                        'elevation': float(point.elevation) if point.elevation else None,
                        'speed': None,  # Will be calculated
                        'course': None,  # Will be calculated
                    })
        
        # Extract points from routes (some GPS devices use routes instead of tracks)
        for route in self.gpx.routes:
            for point in route.points:
                if point.time is None:
                    continue
                
                self.points.append({
                    'lat': float(point.latitude),
                    'lon': float(point.longitude),
                    'timestamp': point.time.isoformat(),
                    'elevation': float(point.elevation) if point.elevation else None,
                    'speed': None,
                    'course': None,
                })
        
        # Sort by timestamp
        self.points.sort(key=lambda p: p['timestamp'])
        
        # Calculate speeds and courses between points
        self._calculate_derived_values()
        
        # Extract metadata
        self._extract_metadata()
        
        return self.points
    
    def _calculate_derived_values(self):
        """Calculate speed and course from consecutive points."""
        for i in range(1, len(self.points)):
            prev = self.points[i - 1]
            curr = self.points[i]
            
            # Parse timestamps
            prev_time = datetime.fromisoformat(prev['timestamp'].replace('Z', '+00:00'))
            curr_time = datetime.fromisoformat(curr['timestamp'].replace('Z', '+00:00'))
            time_delta = (curr_time - prev_time).total_seconds()
            
            if time_delta > 0:
                # Calculate distance and speed
                distance = haversine_distance(
                    prev['lat'], prev['lon'],
                    curr['lat'], curr['lon']
                )
                speed = calculate_speed_knots(distance, time_delta)
                
                # Calculate course
                course = calculate_bearing(
                    prev['lat'], prev['lon'],
                    curr['lat'], curr['lon']
                )
                
                # Apply to current point
                curr['speed'] = round(speed, 2)
                curr['course'] = round(course, 1)
        
        # First point gets values from second point
        if len(self.points) > 1:
            self.points[0]['speed'] = self.points[1]['speed']
            self.points[0]['course'] = self.points[1]['course']
    
    def _extract_metadata(self):
        """Extract metadata from parsed track."""
        if not self.points:
            return
        
        # Time bounds
        start_time = datetime.fromisoformat(self.points[0]['timestamp'].replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(self.points[-1]['timestamp'].replace('Z', '+00:00'))
        
        # Spatial bounds
        lats = [p['lat'] for p in self.points]
        lons = [p['lon'] for p in self.points]
        
        # Total distance
        total_distance = 0
        for i in range(1, len(self.points)):
            total_distance += haversine_distance(
                self.points[i-1]['lat'], self.points[i-1]['lon'],
                self.points[i]['lat'], self.points[i]['lon']
            )
        
        self.metadata = {
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': (end_time - start_time).total_seconds(),
            'point_count': len(self.points),
            'distance_nm': round(total_distance, 2),
            'bounding_box': {
                'min_lat': min(lats),
                'max_lat': max(lats),
                'min_lon': min(lons),
                'max_lon': max(lons),
            },
        }
        
        # GPX file metadata
        if self.gpx.name:
            self.metadata['name'] = self.gpx.name
        if self.gpx.description:
            self.metadata['description'] = self.gpx.description
    
    def get_metadata(self):
        """Return extracted metadata."""
        if not self.metadata:
            self.parse()
        return self.metadata
    
    def to_geojson(self):
        """
        Convert parsed track to GeoJSON format.
        
        Returns:
            GeoJSON Feature dict with LineString geometry
        """
        if not self.points:
            self.parse()
        
        # Create coordinates array: [lon, lat, timestamp_epoch, speed]
        coordinates = []
        for point in self.points:
            timestamp = datetime.fromisoformat(point['timestamp'].replace('Z', '+00:00'))
            coordinates.append([
                point['lon'],
                point['lat'],
                timestamp.timestamp(),
                point['speed'] or 0,
            ])
        
        return {
            'type': 'Feature',
            'properties': {
                **self.metadata,
            },
            'geometry': {
                'type': 'LineString',
                'coordinates': coordinates,
            }
        }
