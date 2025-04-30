from functools import wraps
import asyncio
from django.urls import path
from django.views.decorators.http import require_http_methods
import logging

logger = logging.getLogger(__name__)

class Router:
    _instance = None
    _routes = []
    _pending_routes = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Router, cls).__new__(cls)
        return cls._instance

    def route(self, url_pattern, methods=None):
        def decorator(view_func):
            @wraps(view_func)
            async def _wrapped_view(request, *args, **kwargs):
                return await view_func(request, *args, **kwargs)
            
            # Apply HTTP method decorator if specified
            if methods:
                _wrapped_view = require_http_methods(methods)(_wrapped_view)
            
            # Store the pending route
            self._pending_routes.append((url_pattern, _wrapped_view, view_func.__name__))
            return view_func
        return decorator

    def register_routes(self):
        for url_pattern, view, name in self._pending_routes:
            route = path(url_pattern, view, name=name)
            self._routes.append(route)
        self._pending_routes = []

    def get_urlpatterns(self):
        return self._routes

# Create a singleton instance
router = Router() 