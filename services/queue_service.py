

import os
from celery import Celery
from database.database import db_session_scope
from database.db_models import Novel, Chapter

def get_celery_app():

    return Celery(
        'translator',
        broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    )

def get_queue_status():

    app = get_celery_app()
    inspect = app.control.inspect()
    
                      
    active = inspect.active() or {}
    reserved = inspect.reserved() or {}
    scheduled = inspect.scheduled() or {}
    stats = inspect.stats() or {}
    
                           
    total_concurrency = 0
    for node_stats in stats.values():
        total_concurrency += node_stats.get('pool', {}).get('max-concurrency', 0)
    
                                       
    tasks_list = []
    
                                  
    def process_tasks(task_dict, state):
        for worker, tasks in task_dict.items():
            for task in tasks:
                                                 
                task_info = {
                    'id': task['id'],
                    'name': task['name'],
                    'args': task['args'],
                    'time_start': task.get('time_start'),
                    'worker': worker,
                    'state': state,
                    'type': 'unknown',
                    'details': 'Unknown Task'
                }
                
                                                              
                                                                    
                if 'translate_chapter_task' in task['name']:
                    try:
                        args = task['args']
                        if isinstance(args, str):
                                                                          
                            import ast
                            args = ast.literal_eval(args)
                            
                        if len(args) >= 2:
                            novel_id = args[0]
                            chapter_id = args[1]
                            task_info['type'] = 'translation'
                            task_info['novel_id'] = novel_id
                            task_info['chapter_id'] = chapter_id
                    except:
                        pass
                
                tasks_list.append(task_info)

    process_tasks(active, 'active')
    process_tasks(reserved, 'queued')
    process_tasks(scheduled, 'scheduled')
    
                                                
    enrich_tasks_with_titles(tasks_list)
    
    return {
        'tasks': tasks_list,
        'stats': {
            'active_count': sum(len(t) for t in active.values()),
            'queued_count': sum(len(t) for t in reserved.values()),
            'scheduled_count': sum(len(t) for t in scheduled.values()),
            'workers_online': len(stats),
            'total_concurrency': total_concurrency
        }
    }

def enrich_tasks_with_titles(tasks):

    if not tasks:
        return
        
                          
    chapter_ids = [t['chapter_id'] for t in tasks if t.get('type') == 'translation']
    
    if not chapter_ids:
        return
        
    with db_session_scope() as session:
                                        
        chapters = session.query(Chapter, Novel).join(
            Novel, Chapter.novel_id == Novel.id
        ).filter(Chapter.id.in_(chapter_ids)).all()
        
                           
        info_map = {}
        for chapter, novel in chapters:
            info_map[chapter.id] = {
                'novel_title': novel.title,
                'chapter_title': chapter.title,
                'chapter_num': chapter.chapter_number
            }
            
                      
        for task in tasks:
            if task.get('type') == 'translation':
                cid = task.get('chapter_id')
                if cid in info_map:
                    info = info_map[cid]
                    task['details'] = f"{info['novel_title']} - Ch {info['chapter_num']}"
                    task['chapter_title'] = info['chapter_title']
                else:
                    task['details'] = f"Chapter ID: {cid}"

def cancel_task(task_id):

    app = get_celery_app()
    app.control.revoke(task_id, terminate=True)
    return True

def purge_queue():

    app = get_celery_app()
    app.control.purge()
    return True