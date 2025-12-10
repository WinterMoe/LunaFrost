

from flask import jsonify
from database.database import db_session_scope
from database.db_models import (
    User, Novel, Chapter, TranslationTokenUsage, 
    GlobalModelPricing, Export
)
from sqlalchemy import func, or_
from datetime import datetime, timedelta
import os

def get_overview_stats():

    with db_session_scope() as db_session:
                      
        total_users = db_session.query(func.count(User.id)).scalar() or 0
        total_novels = db_session.query(func.count(Novel.id)).scalar() or 0
        total_chapters = db_session.query(func.count(Chapter.id)).scalar() or 0
        
                                
        total_translations = db_session.query(func.count(Chapter.id)).filter(
            Chapter.translation_status == 'completed'
        ).scalar() or 0
        
                      
        total_tokens = db_session.query(func.sum(TranslationTokenUsage.total_tokens)).scalar() or 0
        
                        
        one_month_ago = datetime.now() - timedelta(days=30)
        users_last_month = db_session.query(func.count(User.id)).filter(
            User.created_at >= one_month_ago
        ).scalar() or 0
        
        growth_rate = (users_last_month / total_users * 100) if total_users > 0 else 0
        
        return {
            'total_users': total_users,
            'total_novels': total_novels,
            'total_chapters': total_chapters,
            'total_translations': total_translations,
            'total_tokens': int(total_tokens),
            'user_growth_rate': round(growth_rate, 1)
        }

def get_token_stats():

    with db_session_scope() as db_session:
                     
        by_provider = db_session.query(
            TranslationTokenUsage.provider,
            func.sum(TranslationTokenUsage.total_tokens).label('total')
        ).group_by(TranslationTokenUsage.provider).all()
        
                          
        by_model = db_session.query(
            TranslationTokenUsage.model,
            func.sum(TranslationTokenUsage.total_tokens).label('total')
        ).group_by(TranslationTokenUsage.model).order_by(
            func.sum(TranslationTokenUsage.total_tokens).desc()
        ).limit(5).all()
        
                                  
        now = datetime.now()
        this_month_start = datetime(now.year, now.month, 1)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
        
        this_month_tokens = db_session.query(func.sum(TranslationTokenUsage.total_tokens)).filter(
            TranslationTokenUsage.created_at >= this_month_start
        ).scalar() or 0
        
        last_month_tokens = db_session.query(func.sum(TranslationTokenUsage.total_tokens)).filter(
            TranslationTokenUsage.created_at >= last_month_start,
            TranslationTokenUsage.created_at < this_month_start
        ).scalar() or 0
        
                                  
        total_cost = 0.0
        cost_breakdown = []
        
        for provider, tokens in by_provider:
            provider_cost = 0.0
            pricing = db_session.query(GlobalModelPricing).filter(
                GlobalModelPricing.provider == provider
            ).all()
            
            if pricing:
                avg_input = sum(float(p.input_price_per_1m or 0) for p in pricing) / len(pricing)
                avg_output = sum(float(p.output_price_per_1m or 0) for p in pricing) / len(pricing)
                provider_cost = (tokens / 1_000_000) * ((avg_input * 0.6) + (avg_output * 0.4))
            
            total_cost += provider_cost
            cost_breakdown.append({
                'provider': provider,
                'cost': round(provider_cost, 2)
            })
        
        return {
            'by_provider': [{'provider': p, 'tokens': int(t)} for p, t in by_provider],
            'by_model': [{'model': m, 'tokens': int(t)} for m, t in by_model],
            'this_month': int(this_month_tokens),
            'last_month': int(last_month_tokens),
            'estimated_cost': round(total_cost, 2),
            'cost_breakdown': cost_breakdown
        }

def get_activity_stats():

    with db_session_scope() as db_session:
        now = datetime.now()
        
                      
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)
        
        active_7d = db_session.query(func.count(User.id.distinct())).filter(
            User.last_login >= seven_days_ago
        ).scalar() or 0
        
        active_30d = db_session.query(func.count(User.id.distinct())).filter(
            User.last_login >= thirty_days_ago
        ).scalar() or 0
        
                   
        one_week_ago = now - timedelta(days=7)
        one_month_ago = now - timedelta(days=30)
        
        new_users_week = db_session.query(func.count(User.id)).filter(
            User.created_at >= one_week_ago
        ).scalar() or 0
        
        new_users_month = db_session.query(func.count(User.id)).filter(
            User.created_at >= one_month_ago
        ).scalar() or 0
        
                      
        today_start = datetime(now.year, now.month, now.day)
        
        translations_today = db_session.query(func.count(Chapter.id)).filter(
            Chapter.translation_completed_at >= today_start,
            Chapter.translation_status == 'completed'
        ).scalar() or 0
        
        translations_week = db_session.query(func.count(Chapter.id)).filter(
            Chapter.translation_completed_at >= one_week_ago,
            Chapter.translation_status == 'completed'
        ).scalar() or 0
        
        translations_month = db_session.query(func.count(Chapter.id)).filter(
            Chapter.translation_completed_at >= one_month_ago,
            Chapter.translation_status == 'completed'
        ).scalar() or 0
        
                        
        avg_tokens = db_session.query(func.avg(TranslationTokenUsage.total_tokens)).scalar() or 0
        
        return {
            'active_users_7d': active_7d,
            'active_users_30d': active_30d,
            'new_users_week': new_users_week,
            'new_users_month': new_users_month,
            'translations_today': translations_today,
            'translations_week': translations_week,
            'translations_month': translations_month,
            'avg_tokens_per_translation': round(avg_tokens, 0)
        }

def get_top_lists():

    with db_session_scope() as db_session:
                                  
        top_users = db_session.query(
            User.username,
            func.sum(TranslationTokenUsage.total_tokens).label('total_tokens')
        ).join(
            TranslationTokenUsage,
            func.lower(User.username) == TranslationTokenUsage.user_id
        ).group_by(User.username).order_by(
            func.sum(TranslationTokenUsage.total_tokens).desc()
        ).limit(10).all()
        
                        
        from database.db_models import Chapter
        largest_novels = db_session.query(
            Novel.title,
            Novel.translated_title,
            func.count(Chapter.id).label('chapter_count')
        ).outerjoin(Chapter, Novel.id == Chapter.novel_id
        ).group_by(Novel.id).order_by(
            func.count(Chapter.id).desc()
        ).limit(10).all()
        
                                 
        top_authors = db_session.query(
            Novel.author,
            Novel.translated_author,
            func.count(Chapter.id).label('translation_count')
        ).outerjoin(Chapter, Novel.id == Chapter.novel_id
        ).filter(Chapter.translation_status == 'completed'
        ).group_by(Novel.author, Novel.translated_author
        ).order_by(func.count(Chapter.id).desc()).limit(10).all()
        
        return {
            'top_users': [{'username': u, 'tokens': int(t)} for u, t in top_users],
            'largest_novels': [{
                'title': t or tt,
                'chapters': c
            } for tt, t, c in largest_novels],
            'top_authors': [{
                'author': ta or a or 'Unknown',
                'translations': c
            } for a, ta, c in top_authors]
        }

def get_storage_stats():

    with db_session_scope() as db_session:
                       
        db_size_result = db_session.execute(
            "SELECT pg_database_size(current_database())"
        ).scalar()
        db_size_mb = round(db_size_result / (1024 * 1024), 2) if db_size_result else 0
        
                
        images_dir = 'data/users'
        total_images = 0
        total_image_size = 0
        
        if os.path.exists(images_dir):
            for root, dirs, files in os.walk(images_dir):
                if 'images' in root:
                    for file in files:
                        file_path = os.path.join(root, file)
                        if os.path.isfile(file_path):
                            total_images += 1
                            total_image_size += os.path.getsize(file_path)
        
        image_size_mb = round(total_image_size / (1024 * 1024), 2)
        
                 
        epub_count = db_session.query(func.count(Export.id)).filter(
            Export.format == 'epub'
        ).scalar() or 0
        
        txt_count = db_session.query(func.count(Export.id)).filter(
            Export.format == 'txt'
        ).scalar() or 0
        
        return {
            'database_size_mb': db_size_mb,
            'images_count': total_images,
            'images_size_mb': image_size_mb,
            'exports_epub': epub_count,
            'exports_txt': txt_count,
            'exports_total': epub_count + txt_count
        }

def get_chart_data():

    with db_session_scope() as db_session:
        days = []
        translations_data = []
        tokens_data = []
        signups_data = []
        
        for i in range(29, -1, -1):
            day = datetime.now() - timedelta(days=i)
            day_start = datetime(day.year, day.month, day.day)
            day_end = day_start + timedelta(days=1)
            
            days.append(day.strftime('%b %d'))
            
                          
            translations = db_session.query(func.count(Chapter.id)).filter(
                Chapter.translation_completed_at >= day_start,
                Chapter.translation_completed_at < day_end,
                Chapter.translation_status == 'completed'
            ).scalar() or 0
            translations_data.append(translations)
            
                    
            tokens = db_session.query(func.sum(TranslationTokenUsage.total_tokens)).filter(
                TranslationTokenUsage.created_at >= day_start,
                TranslationTokenUsage.created_at < day_end
            ).scalar() or 0
            tokens_data.append(int(tokens))
            
                     
            signups = db_session.query(func.count(User.id)).filter(
                User.created_at >= day_start,
                User.created_at < day_end
            ).scalar() or 0
            signups_data.append(signups)
        
        return {
            'labels': days,
            'translations': translations_data,
            'tokens': tokens_data,
            'signups': signups_data
        }

def get_celery_stats():

    try:
        from celery import Celery
        
        celery_app = Celery(
            'translator',
            broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
            backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
        )
        
        inspect = celery_app.control.inspect()
        
                      
        active = inspect.active()
        active_count = sum(len(tasks) for tasks in (active or {}).values())
        
                        
        reserved = inspect.reserved()
        reserved_count = sum(len(tasks) for tasks in (reserved or {}).values())
        
                         
        scheduled = inspect.scheduled()
        scheduled_count = sum(len(tasks) for tasks in (scheduled or {}).values())
        
                                 
        stats = inspect.stats() or {}
        node_count = len(stats)
        
                                                       
        total_concurrency = 0
        for node_stats in stats.values():
            total_concurrency += node_stats.get('pool', {}).get('max-concurrency', 0)
        
        return {
            'active_tasks': active_count,
            'queued_tasks': reserved_count,
            'scheduled_tasks': scheduled_count,
            'workers': total_concurrency,                                
            'nodes': node_count,                                   
            'queue_length': active_count + reserved_count + scheduled_count
        }
    except Exception as e:
        return {
            'active_tasks': 0,
            'queued_tasks': 0,
            'scheduled_tasks': 0,
            'workers': 0,
            'queue_length': 0,
            'error': 'Could not connect to Celery'
        }