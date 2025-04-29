from django.shortcuts import render
from django.http import JsonResponse
from django.db import connections
from django.db.utils import OperationalError
from asgiref.sync import sync_to_async
from .router import router
import asyncio
import logging

logger = logging.getLogger(__name__)
logger.info("Views module imported")

def test_db_connection():
    """Test if we can connect to the database."""
    try:
        db_conn = connections['default']
        db_conn.cursor()
        return True, None
    except OperationalError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

# Create async version of the database test
test_db_connection_async = sync_to_async(test_db_connection)

@router.route('health/', methods=['GET'])
async def health(request):
    """Health check endpoint for App Runner."""
    logger.info("Health check called")
    return JsonResponse({'status': 'healthy'})

@router.route('debug/', methods=['GET'])
async def debug(request):
    logger.info("Debug route called")
    
    # Test database connection using async version
    db_healthy, db_error = await test_db_connection_async()
    
    return JsonResponse({
        'message': 'Debug route working!',
        'routes': [str(route) for route in router.get_urlpatterns()],
        'database': {
            'connected': db_healthy,
            'error': db_error if not db_healthy else None
        }
    })

@router.route('test/async-example/', methods=['GET'])
async def async_example(request):
    logger.info("Async example route called")
    
    # Create three concurrent tasks that sleep for different durations
    tasks = [
        asyncio.create_task(async_sleep(1, "Task 1")),
        asyncio.create_task(async_sleep(2, "Task 2")),
        asyncio.create_task(async_sleep(3, "Task 3")),
    ]
    
    # Wait for all tasks to complete
    results = await asyncio.gather(*tasks)
    
    return JsonResponse({
        'message': 'Async tasks completed',
        'results': results
    })

async def async_sleep(seconds: int, task_name: str) -> dict:
    """Helper function to simulate async work with sleep."""
    await asyncio.sleep(seconds)
    return {
        'task': task_name,
        'slept_for': f"{seconds} seconds"
    }
