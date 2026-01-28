"""
DigitalOcean Spaces storage utilities for track files.
"""
import json
import logging
from datetime import timedelta

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage

logger = logging.getLogger(__name__)


class MediaStorage(S3Boto3Storage):
    """
    Custom storage class for media files (vessel icons, etc.) in DO Spaces.
    Files are stored with public-read ACL for easy access via CDN.
    """
    location = 'media'
    default_acl = 'public-read'  # Media files can be public
    file_overwrite = False
    querystring_auth = False  # No need for signed URLs for public media


def get_s3_client():
    """Get a boto3 S3 client configured for DO Spaces."""
    return boto3.client(
        's3',
        endpoint_url=settings.DO_SPACES_ENDPOINT,
        aws_access_key_id=settings.DO_SPACES_KEY,
        aws_secret_access_key=settings.DO_SPACES_SECRET,
        region_name=settings.DO_SPACES_REGION,
    )


def upload_track_json(recording_id, zoom_level, data):
    """
    Upload a track JSON file to DO Spaces.
    
    Args:
        recording_id: UUID of the recording
        zoom_level: 'raw', 'z6', 'z10', 'z14', or 'z18'
        data: dict to be serialized as JSON
    
    Returns:
        The S3 key of the uploaded file
    """
    s3_client = get_s3_client()
    key = f"{settings.TRACK_S3_PREFIX}{recording_id}/{zoom_level}.json"
    
    try:
        s3_client.put_object(
            Bucket=settings.DO_SPACES_NAME,
            Key=key,
            Body=json.dumps(data),
            ContentType='application/json',
            CacheControl='max-age=31536000',  # 1 year (immutable content)
        )
        logger.info(f"Uploaded track file: {key}")
        return key
    except ClientError as e:
        logger.error(f"Failed to upload track file {key}: {e}")
        raise


def get_signed_url(recording_id, zoom_level='z14', expiry_seconds=900):
    """
    Generate a signed URL for accessing a track file.
    
    Args:
        recording_id: UUID of the recording
        zoom_level: 'raw', 'z6', 'z10', 'z14', or 'z18'
        expiry_seconds: URL expiry time (default 15 minutes)
    
    Returns:
        Signed URL string
    """
    s3_client = get_s3_client()
    key = f"{settings.TRACK_S3_PREFIX}{recording_id}/{zoom_level}.json"
    
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.DO_SPACES_NAME,
                'Key': key,
            },
            ExpiresIn=expiry_seconds,
        )
        return url
    except ClientError as e:
        logger.error(f"Failed to generate signed URL for {key}: {e}")
        raise


def get_all_signed_urls(recording_id, expiry_seconds=900):
    """
    Generate signed URLs for all zoom levels of a recording.
    
    Returns:
        dict mapping zoom levels to signed URLs
    """
    zoom_levels = ['raw', 'z6', 'z10', 'z14', 'z18']
    urls = {}
    
    for level in zoom_levels:
        try:
            urls[level] = get_signed_url(recording_id, level, expiry_seconds)
        except ClientError:
            # Some zoom levels might not exist for small tracks
            pass
    
    return urls


def delete_track_files(recording_id):
    """
    Delete all track files for a recording from DO Spaces.
    """
    s3_client = get_s3_client()
    prefix = f"{settings.TRACK_S3_PREFIX}{recording_id}/"
    
    try:
        # List all objects with the prefix
        response = s3_client.list_objects_v2(
            Bucket=settings.DO_SPACES_NAME,
            Prefix=prefix,
        )
        
        if 'Contents' in response:
            objects = [{'Key': obj['Key']} for obj in response['Contents']]
            s3_client.delete_objects(
                Bucket=settings.DO_SPACES_NAME,
                Delete={'Objects': objects}
            )
            logger.info(f"Deleted {len(objects)} track files for recording {recording_id}")
    except ClientError as e:
        logger.error(f"Failed to delete track files for {recording_id}: {e}")
        raise


def download_track_json(recording_id, zoom_level='raw'):
    """
    Download and parse a track JSON file from DO Spaces.
    
    Returns:
        Parsed JSON data as dict
    """
    s3_client = get_s3_client()
    key = f"{settings.TRACK_S3_PREFIX}{recording_id}/{zoom_level}.json"
    
    try:
        response = s3_client.get_object(
            Bucket=settings.DO_SPACES_NAME,
            Key=key,
        )
        return json.loads(response['Body'].read().decode('utf-8'))
    except ClientError as e:
        logger.error(f"Failed to download track file {key}: {e}")
        raise
