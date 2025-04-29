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
            logger.info("Router instance created")
        return cls._instance

    def route(self, url_pattern, methods=None):
        logger.info(f"Route decorator called for {url_pattern}")
        def decorator(view_func):
            @wraps(view_func)
            def _wrapped_view(request, *args, **kwargs):
                return asyncio.run(view_func(request, *args, **kwargs))
            
            # Apply HTTP method decorator if specified
            if methods:
                _wrapped_view = require_http_methods(methods)(_wrapped_view)
            
            # Store the pending route
            self._pending_routes.append((url_pattern, _wrapped_view, view_func.__name__))
            logger.info(f"Pending route added: {url_pattern} -> {view_func.__name__}")
            return view_func
        return decorator

    def register_routes(self):
        logger.info(f"Registering {len(self._pending_routes)} pending routes")
        for url_pattern, view, name in self._pending_routes:
            route = path(url_pattern, view, name=name)
            logger.info(f"Registering route: {url_pattern} -> {name}")
            self._routes.append(route)
        self._pending_routes = []
        logger.info(f"Total registered routes: {len(self._routes)}")

    def get_urlpatterns(self):
        logger.info(f"Getting URL patterns. Current routes: {[str(r) for r in self._routes]}")
        return self._routes

# Create a singleton instance
router = Router() 