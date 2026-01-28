"""
JSON track file parser for SailArchive.

Parses JSON track files (e.g., from RaceQs or similar systems) and extracts
track data with timestamps, speeds, and courses.
"""

import json
import logging
import re
from datetime import datetime, timezone
from math import radians, sin, cos, sqrt, atan2

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


def parse_course_string(course_str):
    """
    Parse a course string like "192°S" or "297°NW" to numeric bearing.
    
    Returns:
        Bearing in degrees (0-360), or None if parsing fails
    """
    if not course_str:
        return None
    
    # Extract numeric value from string like "192°S" or "297°NW"
    match = re.search(r'(\d+(?:\.\d+)?)', str(course_str))
    if match:
        return float(match.group(1))
    
    return None


class JSONTrackParser:
    """
    Parser for JSON track files.
    
    Extracts track points with timestamps, calculates speeds and courses,
    and normalizes data for storage.
    """
    
    def __init__(self, json_content):
        """
        Initialize parser with JSON file content.
        
        Args:
            json_content: string, bytes, or file-like object containing JSON
        """
        if isinstance(json_content, bytes):
            json_content = json_content.decode('utf-8')
        
        if isinstance(json_content, str):
            self.data = json.loads(json_content)
        else:
            self.data = json_content
        
        self.points = []
        self.metadata = {}
    
    def parse(self):
        """
        Parse the JSON file and extract all track points.
        
        Expected format: Array of objects with:
        - l: latitude
        - n: longitude (negative for west)
        - t: timestamp (Unix epoch, float)
        - s: speed (optional, in knots)
        - r: course string (optional, e.g., "192°S")
        - h: elevation (optional)
        
        Returns:
            List of track points as dicts with lat, lon, timestamp, speed, course
        """
        self.points = []
        
        if not isinstance(self.data, list):
            raise ValueError("JSON file must contain an array of track points")
        
        for item in self.data:
            if not isinstance(item, dict):
                continue
            
            # Extract required fields
            lat = item.get('l')
            lon = item.get('n')
            timestamp = item.get('t')
            
            if lat is None or lon is None or timestamp is None:
                continue  # Skip invalid points
            
            try:
                lat = float(lat)
                lon = float(lon)
                timestamp = float(timestamp)
            except (ValueError, TypeError):
                continue  # Skip points with invalid numeric values
            
            # Convert timestamp to datetime
            try:
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            except (ValueError, OSError):
                continue  # Skip points with invalid timestamps
            
            # Extract optional fields
            speed = item.get('s')
            if speed is not None:
                try:
                    speed = float(speed)
                except (ValueError, TypeError):
                    speed = None
            
            # Parse course from string if available
            course = None
            course_str = item.get('r')
            if course_str:
                course = parse_course_string(course_str)
            
            elevation = item.get('h')
            if elevation is not None:
                try:
                    elevation = float(elevation)
                except (ValueError, TypeError):
                    elevation = None
            
            self.points.append({
                'lat': lat,
                'lon': lon,
                'timestamp': dt.isoformat(),
                'elevation': elevation,
                'speed': speed,  # May be None, will be calculated if missing
                'course': course,  # May be None, will be calculated if missing
            })
        
        # Sort by timestamp
        self.points.sort(key=lambda p: p['timestamp'])
        
        # Calculate missing speeds and courses
        self._calculate_derived_values()
        
        # Extract metadata
        self._extract_metadata()
        
        return self.points
    
    def _calculate_derived_values(self):
        """Calculate speed and course from consecutive points if missing."""
        for i in range(1, len(self.points)):
            prev = self.points[i - 1]
            curr = self.points[i]
            
            # Parse timestamps
            prev_time = datetime.fromisoformat(prev['timestamp'].replace('Z', '+00:00'))
            curr_time = datetime.fromisoformat(curr['timestamp'].replace('Z', '+00:00'))
            time_delta = (curr_time - prev_time).total_seconds()
            
            if time_delta > 0:
                # Calculate distance
                distance = haversine_distance(
                    prev['lat'], prev['lon'],
                    curr['lat'], curr['lon']
                )
                
                # Calculate speed if missing
                if curr['speed'] is None:
                    speed = calculate_speed_knots(distance, time_delta)
                    curr['speed'] = round(speed, 2)
                
                # Calculate course if missing
                if curr['course'] is None:
                    course = calculate_bearing(
                        prev['lat'], prev['lon'],
                        curr['lat'], curr['lon']
                    )
                    curr['course'] = round(course, 1)
        
        # First point gets values from second point if available
        if len(self.points) > 1:
            if self.points[0]['speed'] is None:
                self.points[0]['speed'] = self.points[1]['speed']
            if self.points[0]['course'] is None:
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
