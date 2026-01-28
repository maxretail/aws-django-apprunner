"""
Track processing utilities for SailArchive.

Handles track simplification using Douglas-Peucker algorithm and
generates zoom-level specific track files.
"""

import logging
from typing import List, Dict, Any

from django.conf import settings

try:
    from simplification.cutil import simplify_coords_idx
    SIMPLIFICATION_AVAILABLE = True
except ImportError:
    SIMPLIFICATION_AVAILABLE = False
    logging.warning("simplification library not available, using fallback")

logger = logging.getLogger(__name__)


def simplify_track_nth(coordinates: List[List[float]], target_points: int) -> List[List[float]]:
    """
    Simple nth-point simplification fallback.
    Keeps every nth point to achieve target point count.
    """
    if len(coordinates) <= target_points:
        return coordinates
    
    step = len(coordinates) / target_points
    result = []
    
    for i in range(target_points):
        idx = int(i * step)
        if idx < len(coordinates):
            result.append(coordinates[idx])
    
    # Always include the last point
    if result[-1] != coordinates[-1]:
        result.append(coordinates[-1])
    
    return result


def simplify_track_douglas_peucker(coordinates: List[List[float]], target_points: int) -> List[List[float]]:
    """
    Simplify track using Douglas-Peucker algorithm.
    
    Args:
        coordinates: List of [lon, lat, ...] coordinates
        target_points: Target number of points
    
    Returns:
        Simplified list of coordinates
    """
    if not SIMPLIFICATION_AVAILABLE:
        return simplify_track_nth(coordinates, target_points)
    
    if len(coordinates) <= target_points:
        return coordinates
    
    # Extract just lon/lat for simplification
    points_2d = [[c[0], c[1]] for c in coordinates]
    
    # Binary search for the right epsilon
    epsilon_min = 0.00001
    epsilon_max = 1.0
    best_result = coordinates
    
    for _ in range(20):  # Max iterations
        epsilon = (epsilon_min + epsilon_max) / 2
        
        # Get indices of points to keep
        indices = simplify_coords_idx(points_2d, epsilon)
        
        if len(indices) > target_points:
            epsilon_min = epsilon
        elif len(indices) < target_points * 0.9:  # Allow 10% tolerance
            epsilon_max = epsilon
        else:
            # Good enough
            best_result = [coordinates[i] for i in indices]
            break
        
        best_result = [coordinates[i] for i in indices]
    
    return best_result


def generate_zoom_levels(geojson_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Generate zoom-level specific GeoJSON files from a full-resolution track.
    
    Args:
        geojson_data: Full resolution GeoJSON Feature
    
    Returns:
        Dict mapping zoom levels to simplified GeoJSON Features
    """
    coordinates = geojson_data['geometry']['coordinates']
    properties = geojson_data['properties']
    
    # Target point counts for each zoom level
    zoom_targets = getattr(settings, 'TRACK_ZOOM_LEVELS', {
        'z6': 50,
        'z10': 200,
        'z14': 1000,
        'z18': 5000,
    })
    
    result = {
        'raw': geojson_data,  # Full resolution
    }
    
    for zoom_level, target_points in zoom_targets.items():
        if len(coordinates) <= target_points:
            # No need to simplify if we have fewer points
            simplified_coords = coordinates
        else:
            simplified_coords = simplify_track_douglas_peucker(coordinates, target_points)
        
        result[zoom_level] = {
            'type': 'Feature',
            'properties': {
                **properties,
                'zoom_level': zoom_level,
                'point_count': len(simplified_coords),
                'original_point_count': len(coordinates),
            },
            'geometry': {
                'type': 'LineString',
                'coordinates': simplified_coords,
            }
        }
        
        logger.info(f"Generated {zoom_level}: {len(simplified_coords)} points (from {len(coordinates)})")
    
    return result


def get_appropriate_zoom_level(zoom: int) -> str:
    """
    Get the appropriate pre-computed zoom level for a given map zoom.
    
    Args:
        zoom: Map zoom level (0-22)
    
    Returns:
        Zoom level key ('z6', 'z10', 'z14', 'z18', or 'raw')
    """
    if zoom <= 6:
        return 'z6'
    elif zoom <= 10:
        return 'z10'
    elif zoom <= 14:
        return 'z14'
    elif zoom <= 18:
        return 'z18'
    else:
        return 'raw'
