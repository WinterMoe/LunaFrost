from celery import Celery
import os
from dotenv import load_dotenv

                                           
load_dotenv()

def make_celery():

                                                                             
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    celery = Celery(
        'lunafrost',
        broker=redis_url,
        backend=redis_url
    )
    
    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,
        task_time_limit=300,                 
        task_soft_time_limit=240,                        
        broker_connection_retry_on_startup=True,
    )
    
    return celery

celery = make_celery()

                                                                     
import tasks.translation_tasks                            
import tasks.webtoon_tasks                                                                  