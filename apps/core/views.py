from django.shortcuts import render
from django.http import JsonResponse
from django.db import connections
from django.db.utils import OperationalError
from asgiref.sync import sync_to_async
from django.db.backends.base.base import BaseDatabaseWrapper
from .router import router
import asyncio
import logging
import time

logger = logging.getLogger(__name__)
logger.debug("Views module imported")

def _test_db_connection_sync():
    """Synchronous version of database connection test."""
    try:
        db_conn = connections['default']
        cursor = db_conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        return True, None
    except OperationalError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

# Create async version of the database test
test_db_connection_async = sync_to_async(_test_db_connection_sync)

@router.route('health/', methods=['GET'])
async def health(request):
    """Health check endpoint for App Runner."""
    logger.debug("Health check called")
    return JsonResponse({'status': 'healthy'})

@router.route('debug/', methods=['GET'])
async def debug(request):
    logger.debug("Debug route called")
    
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
    logger.debug("Async example route called")
    
    start_time = time.time()
    
    # Create three concurrent tasks that sleep for 3 seconds each
    tasks = [
        asyncio.create_task(async_sleep(3, "Task 1")),
        asyncio.create_task(async_sleep(3, "Task 2")),
        asyncio.create_task(async_sleep(3, "Task 3")),
    ]
    
    # Wait for all tasks to complete
    results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    return JsonResponse({
        'message': 'Async tasks completed',
        'total_elapsed_time': f"{elapsed_time:.2f} seconds",
        'results': results,
        'expected_sequential_time': "9.00 seconds (3 tasks × 3 seconds)",
        'concurrency_benefit': f"Saved approximately {9 - elapsed_time:.2f} seconds by running concurrently"
    })

async def async_sleep(seconds: int, task_name: str) -> dict:
    """Helper function to simulate async work with sleep."""
    await asyncio.sleep(seconds)
    return {
        'task': task_name,
        'slept_for': f"{seconds} seconds"
    }

@router.route('protected/', methods=['GET'])
async def protected(request):
    """Protected endpoint that requires API key authentication."""
    logger.debug("Protected route called")
    return JsonResponse({
        'message': 'Protected endpoint accessed successfully',
        'authenticated': True
    })
