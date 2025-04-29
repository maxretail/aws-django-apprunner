from functools import wraps
from django.http import JsonResponse
import asyncio

def async_view(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        return asyncio.run(view_func(request, *args, **kwargs))
    return _wrapped_view 