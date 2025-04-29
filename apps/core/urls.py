from django.urls import path, include
from .router import router

app_name = 'core'
urlpatterns = router.get_urlpatterns() 