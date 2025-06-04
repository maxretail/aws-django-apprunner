import os
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import get_user_model
import logging
from django.conf import settings

logger = logging.getLogger(__name__)
User = get_user_model()

class SimpleApiKeyMiddleware:
    """
    Simple middleware that authenticates requests using an API key.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Get API keys from settings
        self.api_keys = getattr(settings, 'API_KEYS', [])
        
        # Log warning if no API keys configured
        if not self.api_keys:
            logger.error("No API keys configured. Authentication will fail for all requests.")

    def __call__(self, request):
        # Check if API authentication is completely disabled via environment variable
        if os.environ.get('DISABLE_API_AUTH'):
            logger.debug("API authentication disabled via DISABLE_API_AUTH environment variable")
            return self.get_response(request)
            
        # Exclude admin URLs
        if request.path.startswith('/admin/'):
            return self.get_response(request)
            
        # Exclude core app endpoints from API key authentication
        core_exempt_paths = [
            '/health',
            '/debug',
            '/test/async-example',
        ]
        
        for exempt_path in core_exempt_paths:
            # Check if path matches exactly or starts with the path followed by '/'
            if request.path == exempt_path or request.path.startswith(exempt_path + '/'):
                return self.get_response(request)

        # Already authenticated
        if request.user.is_authenticated:
            return self.get_response(request)
            
        # Log request details
        logger.debug(f"Middleware processing request: {request.path}")
        logger.debug(f"Headers: {dict(request.headers)}")
        
        # Get API keys from settings
        api_keys = self.api_keys
        
        # Log the available API keys (don't log the actual keys in production)
        logger.debug(f"Number of configured API keys: {len(api_keys)}")
        
        # If no API keys configured, fail with clear error message
        if not api_keys:
            return JsonResponse(
                {"error": "No API keys configured on the server"}, 
                status=500
            )
        
        # Try to find API key in various places
        request_key = None
        
        # 1. Check X-API-KEY header
        if 'HTTP_X_API_KEY' in request.META:
            request_key = request.META['HTTP_X_API_KEY']
            
        # 2. Try Authorization header (ApiKey format)
        if not request_key and 'HTTP_AUTHORIZATION' in request.META:
            auth = request.META['HTTP_AUTHORIZATION']
            if auth.startswith('ApiKey '):
                request_key = auth.split(' ')[1]
                
        # 3. Try Basic Auth (for n8n)
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
                    
        # 4. Try query parameters
        if not request_key:
            request_key = request.GET.get('api_key')
            
        # Validate API key
        if request_key and request_key in api_keys:
            # Key is valid, let the request through
            return self.get_response(request)
            
        # If we've reached here, authentication has failed
        return JsonResponse(
            {"error": "API key missing or invalid"}, 
            status=401
        ) 