from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'

    def ready(self):
        logger.error("[STARTUP] Core app initializing...")
        
        # Import views to register routes
        from . import views
        from .router import router
        
        # Now register the routes
        router.register_routes()
        
        logger.error("[STARTUP] Core app ready - routes registered")
        logger.error(f"[STARTUP] Available routes: {[str(route) for route in router.get_urlpatterns()]}")
