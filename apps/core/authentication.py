from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
import os
import logging
from django.conf import settings

logger = logging.getLogger(__name__)
User = get_user_model()

class SimpleApiKeyAuthentication(BaseAuthentication):
    """
    Very simple API key authentication that checks for a key in various places:
    1. X-API-KEY header
    2. api_key GET/POST parameter
    3. Authorization header as 'ApiKey <key>'
    """
    def authenticate(self, request):
        # Log all request details for debugging
        logger.debug(f"Auth request received: {request.path}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"GET: {request.GET}")
        
        # Get API keys from settings
        api_keys = getattr(settings, 'API_KEYS', [])
        
        # Log the available API keys (don't log the actual keys in production)
        if not api_keys:
            logger.error("No API keys configured. Authentication will fail for all requests.")
            raise AuthenticationFailed('No API keys configured on the server')
            
        logger.debug(f"Number of configured API keys: {len(api_keys)}")
        
        # Get key from request
        request_key = None
        
        # Check X-API-KEY header (most common)
        request_key = request.META.get('HTTP_X_API_KEY')
        
        # Try Authorization header
        if not request_key:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('ApiKey '):
                request_key = auth_header.split(' ')[1]
                
        # Try Basic Auth (for n8n)
        if not request_key and 'HTTP_AUTHORIZATION' in request.META:
            auth = request.META['HTTP_AUTHORIZATION']
            if auth.startswith('Basic '):
                import base64
                try:
                    decoded = base64.b64decode(auth.split(' ')[1]).decode('utf-8')
                    username, password = decoded.split(':', 1)
                    # Use the password as the API key
                    request_key = password
                except Exception as e:
                    logger.error(f"Error decoding basic auth: {e}")
        
        # Try query parameters (for GET requests)
        if not request_key:
            request_key = request.GET.get('api_key')
            
        # Try POST parameters
        if not request_key and hasattr(request, 'data'):
            request_key = request.data.get('api_key')
        
        # If we have a key, validate it
        if request_key:
            if request_key in api_keys:
                # Find admin user or first user for attaching to request
                user = User.objects.filter(is_superuser=True).first() or User.objects.first()
                if not user:
                    # Create a default user if none exists
                    user = User.objects.create_superuser(
                        username='admin',
                        email='admin@example.com',
                        password='temppw123!'
                    )
                return (user, None)
            else:
                raise AuthenticationFailed('Invalid API key')
                
        # No API key found
        return None

    def authenticate_header(self, request):
        return 'ApiKey' 