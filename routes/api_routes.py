from flask import Blueprint, request, jsonify, send_file, session
from datetime import datetime
from models.novel import (
    load_novels, save_novels, get_novel_glossary, 
    save_novel_glossary, delete_novel, delete_chapter, sort_chapters_by_number
)
from models.settings import load_settings, save_settings
from services.ai_service import translate_text, detect_characters, translate_names, detect_character_genders
from services.image_service import download_image, extract_images_from_content, delete_images_for_chapter, get_user_images_dir
from services.export_service import export_to_epub, export_to_pdf
from services.token_usage_service import save_token_usage, estimate_translation_tokens
from services.pricing_service import (
    calculate_cost, format_cost, get_model_pricing,
    get_model_pricing_with_key, fetch_openrouter_pricing_with_key,
    fetch_openrouter_raw_with_key, get_cached_openrouter_pricing
)
from utils.auth_decorator import require_auth
from utils.csrf_utils import csrf
import os
import re
import hashlib
import threading
import time

api_bp = Blueprint('api', __name__)

@api_bp.route('/csrf-token', methods=['GET'])
@csrf.exempt
def get_csrf_token():
                                                            
    from flask_wtf.csrf import generate_csrf
    return jsonify({'csrf_token': generate_csrf()})

def get_user_id():

    return session.get('user_id')

translation_cache = {}
MAX_CACHE_SIZE = 100

def get_cache_key(text):

    return hashlib.md5(text.encode('utf-8')).hexdigest()

user_import_semaphores = {}
user_semaphore_lock = threading.Lock()

def get_user_import_semaphore(user_id, max_concurrent=3):

    with user_semaphore_lock:
        if user_id not in user_import_semaphores:
            user_import_semaphores[user_id] = threading.Semaphore(max_concurrent)
        return user_import_semaphores[user_id]

def slugify_english(text):

    if not text:
        return 'unknown_novel'
    
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    text = text.strip('-')
    
    return text or 'unknown_novel'

def find_novel_by_korean_title(novels, korean_title):

    if not korean_title:
        return None
    
    korean_title = korean_title.strip()
    
    for novel_id, novel in novels.items():
        if novel.get('title') == korean_title:
            return novel_id
    
    return None

def find_novel_by_source_url(novels, source_url):

    if not source_url:
        return None
    
    source_url = source_url.split('?')[0].rstrip('/')
    
    for novel_id, novel in novels.items():
        novel_url = novel.get('novel_source_url', '')
        if novel_url:
            novel_url = novel_url.split('?')[0].rstrip('/')
            if novel_url == source_url:
                return novel_id
            
            if len(source_url) > 20 and len(novel_url) > 20:
                if source_url in novel_url or novel_url in source_url:
                    return novel_id
    
    return None

def recalculate_all_positions(chapters):

    if not chapters:
        return chapters
    
    chapters_list = [ch for ch in chapters if ch]
    
    all_have_positions = all(
        ch.get('position') is not None and isinstance(ch.get('position'), int) 
        for ch in chapters_list
    )
    
    has_conflicts = False
    if all_have_positions:
        positions = [ch.get('position') for ch in chapters_list]
        if len(positions) != len(set(positions)):
            has_conflicts = True
    
    if all_have_positions and not has_conflicts:
        sorted_chapters = sorted(chapters_list, key=lambda ch: ch.get('position', 999999))
    else:
        chapters_with_pos = [ch for ch in chapters_list if ch.get('position') is not None]
        chapters_without_pos = [ch for ch in chapters_list if ch.get('position') is None]
        
        if len(chapters_with_pos) > 0 and len(chapters_without_pos) > 0:
            sorted_base = sorted(chapters_with_pos, key=lambda ch: ch.get('position', 999999))
            
            for ch_without in chapters_without_pos:
                is_bonus = ch_without.get('is_bonus') or ch_without.get('chapter_number') == 'BONUS'
                
                if is_bonus:
                    sorted_base.append(ch_without)
                else:
                    try:
                        ch_num = int(ch_without.get('chapter_number'))
                        
                        insert_idx = len(sorted_base)
                        for idx, existing_ch in enumerate(sorted_base):
                            if existing_ch.get('is_bonus'):
                                continue
                            try:
                                existing_num = int(existing_ch.get('chapter_number'))
                                if ch_num < existing_num:
                                    insert_idx = idx
                                    break
                            except (ValueError, TypeError):
                                continue
                        
                        sorted_base.insert(insert_idx, ch_without)
                    except (ValueError, TypeError):
                        sorted_base.append(ch_without)
            
            sorted_chapters = sorted_base
        else:
            regular_chapters = []
            bonus_chapters = []
            
            for ch in chapters_list:
                is_bonus = ch.get('is_bonus') or ch.get('chapter_number') == 'BONUS'
                
                if is_bonus:
                    bonus_chapters.append(ch)
                else:
                    regular_chapters.append(ch)
            
            def get_chapter_num(ch):
                try:
                    num = ch.get('chapter_number')
                    if num == 'BONUS':
                        return 999999
                    return int(num) if num else 999999
                except (ValueError, TypeError):
                    return 999999
                                
            regular_chapters.sort(key=get_chapter_num)
            
            sorted_chapters = []
            bonus_inserted = set()
            
            for idx, reg_ch in enumerate(regular_chapters):
                sorted_chapters.append(reg_ch)
                
                for bonus_idx, bonus_ch in enumerate(bonus_chapters):
                    if bonus_idx in bonus_inserted:
                        continue
                    
                    bonus_pos = bonus_ch.get('position')
                    
                    if bonus_pos is not None:
                        reg_before = sum(1 for r in regular_chapters if r.get('position') is not None and r.get('position') < bonus_pos)
                        
                        if len([c for c in sorted_chapters if not c.get('is_bonus')]) == reg_before:
                            sorted_chapters.append(bonus_ch)
                            bonus_inserted.add(bonus_idx)
            
            for bonus_idx, bonus_ch in enumerate(bonus_chapters):
                if bonus_idx not in bonus_inserted:
                    sorted_chapters.append(bonus_ch)
    
    for idx, ch in enumerate(sorted_chapters):
        ch['position'] = idx
    
    return sorted_chapters

@api_bp.route('/import-chapter', methods=['POST'])
@csrf.exempt                                                                         
def import_chapter():

    try:
        user_id = get_user_id()
        data = request.json
        
        max_concurrent = data.get('max_concurrent_imports', 3)
        max_concurrent = max(1, min(10, max_concurrent))
        
        semaphore = get_user_import_semaphore(user_id, max_concurrent)
        
        if not semaphore.acquire(blocking=False):
            return jsonify({
                'success': False,
                'error': f'Too many concurrent imports. Maximum allowed: {max_concurrent}. Please wait for current imports to complete.',
                'error_code': 'RATE_LIMIT_EXCEEDED'
            }), 429
        
        try:                                               
            original_title = data.get('original_title', '')
            source_url = data.get('source_url', '')
            novel_source_url = data.get('novel_source_url', source_url)
            content = data.get('content', '')
            chapter_title = data.get('chapter_title', '')
            translated_title_from_extension = data.get('translated_title', '')
            translated_chapter_title = data.get('translated_chapter_title', '')
            skip_translation = data.get('skip_translation', False)
            auto_translate_title = data.get('auto_translate_title', False)
            auto_translate_content = data.get('auto_translate_content', False)

            settings = load_settings(user_id)
            provider = settings.get('selected_provider', 'openrouter')
            api_key = settings.get('api_keys', {}).get(provider, '')
            selected_model = settings.get('provider_models', {}).get(provider, '')

            has_korean = lambda text: bool(re.search(r'[\uac00-\ud7a3]', text)) if text else False
            is_novel_page = False
            url_for_detection = source_url or novel_source_url or ''
            if url_for_detection:
                is_novel_page = '/novel/' in url_for_detection and '/viewer/' not in url_for_detection
            if not content and not is_novel_page:
                return jsonify({'error': 'No content provided'}), 400
            novels = load_novels(user_id)
            novel_id = find_novel_by_korean_title(novels, original_title)
            if not novel_id:
                novel_id = find_novel_by_source_url(novels, novel_source_url)
            
            novel_translated_title = translated_title_from_extension
            translated_author = data.get('author', '')
            translated_tags = data.get('tags', [])[:] 
            translated_synopsis = data.get('synopsis', '')
            author = data.get('author', '')
            tags = data.get('tags', [])
            synopsis = data.get('synopsis', '')
            
            if not novel_id:
                 novel_id = find_novel_by_korean_title(novels, original_title)
            if not novel_id:
                novel_id = find_novel_by_source_url(novels, novel_source_url)

            if api_key:
                try:
                    should_translate_title = True
                    
                    if novel_id and novels[novel_id].get('translated_title'):
                        existing_trans = novels[novel_id].get('translated_title')
                        if existing_trans != original_title and not has_korean(existing_trans):
                            novel_translated_title = existing_trans
                            should_translate_title = False
                    
                    if novel_translated_title and has_korean(novel_translated_title):
                        should_translate_title = True
                        novel_translated_title = None

                    if should_translate_title and not novel_translated_title and original_title:
                        cache_key = get_cache_key(f"title:{original_title}")
                        if cache_key in translation_cache:
                            novel_translated_title = translation_cache[cache_key]
                        else:
                            translated_title_result = translate_text(
                                original_title, provider, api_key, selected_model,
                                glossary=None, images=None
                            )
                            if isinstance(translated_title_result, dict):
                                translated_title_result = translated_title_result.get('translated_text', '')
                            if translated_title_result and not translated_title_result.startswith("Error") and not translated_title_result.startswith(provider.capitalize()):
                                novel_translated_title = translated_title_result
                                translation_cache[cache_key] = novel_translated_title
                                if len(translation_cache) > MAX_CACHE_SIZE:
                                    translation_cache.pop(next(iter(translation_cache)))
                    
                    if author:
                        cache_key = get_cache_key(f"author:{author}")
                        if cache_key in translation_cache:
                            translated_author = translation_cache[cache_key]
                        else:
                            translated_author_result = translate_text(
                                author, provider, api_key, selected_model,
                                glossary=None, images=None
                            )
                            if isinstance(translated_author_result, dict):
                                translated_author_result = translated_author_result.get('translated_text', '')
                            if translated_author_result and not translated_author_result.startswith("Error") and not translated_author_result.startswith(provider.capitalize()):
                                translated_author = translated_author_result
                                translation_cache[cache_key] = translated_author
                                if len(translation_cache) > MAX_CACHE_SIZE:
                                    translation_cache.pop(next(iter(translation_cache)))
                    
                    if tags:
                        tags_text = ', '.join(tags)
                        translated_tags_result = translate_text(
                            tags_text, provider, api_key, selected_model,
                            glossary=None, images=None
                        )
                        if isinstance(translated_tags_result, dict):
                            translated_tags_result = translated_tags_result.get('translated_text', '')
                        if translated_tags_result and not translated_tags_result.startswith("Error") and not translated_tags_result.startswith(provider.capitalize()):
                            translated_tags_text = translated_tags_result
                            translated_tags = [tag.strip() for tag in translated_tags_text.split(',')]
                    
                    if synopsis:
                        translated_synopsis_result = translate_text(
                            synopsis, provider, api_key, selected_model,
                            glossary=None, images=None
                        )
                        if isinstance(translated_synopsis_result, dict):
                            translated_synopsis_result = translated_synopsis_result.get('translated_text', '')
                        if translated_synopsis_result and not translated_synopsis_result.startswith("Error") and not translated_synopsis_result.startswith(provider.capitalize()):
                            translated_synopsis = translated_synopsis_result
                
                except Exception as e:
                    if not novel_translated_title:
                        novel_translated_title = original_title
                    if not translated_author:
                        translated_author = author
                    if not translated_tags:
                        translated_tags = tags
                    if not translated_synopsis:
                        translated_synopsis = synopsis
            else:
                if not novel_translated_title:
                    novel_translated_title = original_title
                translated_author = author if not translated_author else translated_author
                translated_tags = tags if not translated_tags else translated_tags
                translated_synopsis = synopsis if not translated_synopsis else translated_synopsis
            
            if not novel_translated_title:
                novel_translated_title = original_title
            
            data['translated_title'] = novel_translated_title
            data['translated_author'] = translated_author
            data['translated_tags'] = translated_tags
            data['translated_synopsis'] = translated_synopsis
            data['translated_chapter_title'] = translated_chapter_title
            
            from services.import_service import process_chapter_import
            result = process_chapter_import(user_id, data)
            
            if result.get('success'):
                if result.get('already_exists'):
                     return jsonify(result)
                
                translation_queued = False
                if (auto_translate_title or auto_translate_content) and not skip_translation and api_key:
                    try:
                        from tasks.translation_tasks import translate_chapter_task, translate_chapter_title_task
                        
                        chapter_id = result.get('chapter_id')
                        chapter_index = result.get('chapter_index')
                        
                        translate_title_only = auto_translate_title and not auto_translate_content
                        translate_both = auto_translate_title and auto_translate_content
                        translate_content_only = auto_translate_content and not auto_translate_title
                            
                        
                        if translate_title_only and chapter_id:
                            task = translate_chapter_title_task.delay(
                                user_id=user_id,
                                novel_id=result['novel_id'],
                                chapter_id=chapter_id
                            )
                            translation_queued = True
                        elif translate_content_only:
                            if chapter_id:
                                task = translate_chapter_task.delay(
                                    user_id=user_id,
                                    novel_id=result['novel_id'],
                                    chapter_id=chapter_id,
                                    translate_content=True,
                                    translate_title=False
                                )
                            else:
                                task = translate_chapter_task.delay(
                                    user_id=user_id,
                                    novel_id=result['novel_id'],
                                    chapter_index=chapter_index,
                                    translate_content=True,
                                    translate_title=False
                                )
                            translation_queued = True
                        elif translate_both:
                            if chapter_id:
                                task = translate_chapter_task.delay(
                                    user_id=user_id,
                                    novel_id=result['novel_id'],
                                    chapter_id=chapter_id,
                                    translate_content=True,
                                    translate_title=True
                                )
                            else:
                                task = translate_chapter_task.delay(
                                    user_id=user_id,
                                    novel_id=result['novel_id'],
                                    chapter_index=chapter_index,
                                    translate_content=True,
                                    translate_title=True
                                )
                            translation_queued = True
                            
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                else:
                    pass                                 
                
                return jsonify({
                    'success': True,
                    'message': 'Chapter imported successfully',
                    'novel_id': result['novel_id'],
                    'chapter_index': result['chapter_index'],
                    'chapter_url': f'http://localhost:5000/chapter/{result["novel_id"]}/{result["chapter_index"]}',
                    'translated_title': novel_translated_title,
                    'images_count': 0,
                    'translation_queued': translation_queued
                })
            else:
                return jsonify({'error': result.get('error')}), 500
        
        except Exception as e:                                    
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
        finally:
            semaphore.release()
    
    except Exception as e:                              
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/check-chapter-translation', methods=['GET'])
def check_chapter_translation():

    import sys
    
    def log(msg):

        sys.stdout.flush()
    
    try:
        user_id = get_user_id()
        novel_id = request.args.get('novel_id')
        chapter_index = request.args.get('chapter_index')
        
        log(f"Request received: novel_id={novel_id}, chapter_index={chapter_index}, user_id={user_id}")
        
        if not novel_id or chapter_index is None:
            log("ERROR: Missing parameters")
            return jsonify({'error': 'Missing parameters'}), 400
        
        try:
            chapter_index = int(chapter_index)
        except ValueError:
            log(f"ERROR: Invalid chapter index: {chapter_index}")
            return jsonify({'error': 'Invalid chapter index'}), 400
        
        from database.db_novel import get_novel_with_chapters_db
        from models.novel import sort_chapters_by_number
        from models.settings import load_settings
        
        log(f"Loading novel: {novel_id}")
        novel = get_novel_with_chapters_db(user_id, novel_id)
        if not novel or not novel.get('chapters'):
            log(f"ERROR: Novel not found: {novel_id}")
            return jsonify({'error': 'Novel not found'}), 404
        
        log(f"Novel loaded, total chapters: {len(novel.get('chapters', []))}")
        
        settings = load_settings(user_id)
        if 'sort_order_override' in novel and novel['sort_order_override'] is not None:
            order = novel['sort_order_override']
        else:
            order = settings.get('default_sort_order', 'asc')
        
        log(f"Sorting chapters with order: {order}")
        sorted_chapters = sort_chapters_by_number(novel['chapters'], order)
        
        if chapter_index >= len(sorted_chapters):
            log(f"ERROR: Chapter index {chapter_index} out of range (max: {len(sorted_chapters)-1})")
        chapter = sorted_chapters[chapter_index]
        log(f"Chapter found: id={chapter.get('id')}, title={chapter.get('title', 'N/A')[:50]}")
        
        has_translation = bool(chapter.get('translated_content'))
        translation_status = chapter.get('translation_status', 'none')
        
        log(f"Translation status: has_translation={has_translation}, status={translation_status}")
        
        if has_translation:
            content_length = len(chapter.get('translated_content', ''))
            log(f"✅ Translation available! Content length: {content_length}")
        else:
            log(f"⏳ No translation yet. Status: {translation_status}")
        
        response = {
            'success': True,
            'translated': has_translation,
            'translation_status': translation_status,
            'chapter_id': chapter.get('id'),
            'translated_title': chapter.get('translated_title'),
            'translated_content': chapter.get('translated_content') if has_translation else None,
            'translation_model': chapter.get('translation_model')
        }
        
        log(f"Returning response: translated={response['translated']}, status={response['translation_status']}")
        return jsonify(response)
        
    except Exception as e:
        import traceback
        log(f"ERROR: Exception occurred: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/batch-import-chapters', methods=['POST'])
def batch_import_chapters():

    try:
        from services.import_service import process_batch_chapter_import
        
        user_id = get_user_id()
        data = request.json
        chapters = data.get('chapters', [])
        
        if not chapters or not isinstance(chapters, list):
            return jsonify({
                'success': False, 
                'error': 'Invalid chapters array'
            }), 400
        if chapters:
            first_chapter = chapters[0]
        
        result = process_batch_chapter_import(user_id, chapters)
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/export/<novel_id>/<format>')
def export_novel(novel_id, format):

    try:
        user_id = get_user_id()
        novels = load_novels(user_id)
        if novel_id not in novels:
            return jsonify({'error': 'Novel not found'}), 404
        
        novel = novels[novel_id]
        
        if format == 'pdf':
            file_path = export_to_pdf(novel_id, novel, user_id)
        elif format == 'epub':
            file_path = export_to_epub(novel_id, novel, user_id)
        else:
            return jsonify({'error': 'Invalid format. Use pdf or epub'}), 400
        
        if file_path and os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({'error': 'Export failed. Make sure required libraries are installed.'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/translate', methods=['POST'])
@require_auth
def translate():

    try:
        user_id = get_user_id()
        data = request.json
        text = data.get('text', '')
        novel_id = data.get('novel_id', '')
        source_language = data.get('source_language')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        settings = load_settings(user_id)
        provider = settings.get('selected_provider', 'openrouter')
        api_key = settings.get('api_keys', {}).get(provider, '')
        selected_model = settings.get('provider_models', {}).get(provider, '')
        
        use_thinking_mode = data.get('use_thinking_mode', False)
        if use_thinking_mode:
            thinking_models = settings.get('thinking_mode_models', {})
            thinking_model = thinking_models.get(provider)
            if thinking_model:
                selected_model = thinking_model
        
        glossary = get_novel_glossary(user_id, novel_id) if novel_id else {}
        images = data.get('images', [])
        chapter_id = data.get('chapter_id')                                          
        
        result = translate_text(
            text,
            provider,
            api_key,
            selected_model,
            glossary,
            images,
            is_thinking_mode=use_thinking_mode,
            source_language=source_language
        )
        
        if isinstance(result, dict):
            if result.get('error'):
                return jsonify({
                    'success': False,
                    'error': result['error'],
                    'translated_text': None
                }), 500
            
            translated_text = result.get('translated_text', '')
            token_usage_data = result.get('token_usage')
            
            cost_info = None
            if token_usage_data:
                cost_info = calculate_cost(
                    token_usage_data.get('input_tokens', 0),
                    token_usage_data.get('output_tokens', 0),
                    token_usage_data.get('provider', provider),
                    token_usage_data.get('model', selected_model)
                )
            
            if token_usage_data and chapter_id:
                try:
                    save_token_usage(
                        user_id=user_id,
                        chapter_id=chapter_id,
                        provider=token_usage_data.get('provider', provider),
                        model=token_usage_data.get('model', selected_model),
                        input_tokens=token_usage_data.get('input_tokens', 0),
                        output_tokens=token_usage_data.get('output_tokens', 0),
                        total_tokens=token_usage_data.get('total_tokens', 0),
                        translation_type='content'
                    )
                except Exception as e:
                    pass
            
            return jsonify({
                'success': True,
                'translated_text': translated_text,
                'model_used': selected_model,
                'token_usage': token_usage_data,
                'cost_info': cost_info
            })
        else:
            return jsonify({
                'success': True,
                'translated_text': result if isinstance(result, str) else '',
                'model_used': selected_model,
                'token_usage': None
            })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/save-translation', methods=['POST'])
@require_auth
def save_translation():

    try:
        from database.database import db_session_scope
        from database.db_models import Chapter
        from models.settings import load_settings
        from models.novel import sort_chapters_by_number, get_novel_with_chapters_db
        
        user_id = get_user_id()
        data = request.json
        novel_id = data.get('novel_id')
        chapter_index = data.get('chapter_index')
        translated_text = data.get('translated_text', '')
        translation_model = data.get('translation_model', '')
        
        novel = get_novel_with_chapters_db(user_id, novel_id)
        if not novel or not novel.get('chapters'):
            return jsonify({'error': 'Novel not found'}), 404
        
        settings = load_settings(user_id)
        if 'sort_order_override' in novel and novel['sort_order_override'] is not None:
            order = novel['sort_order_override']
        else:
            order = settings.get('default_sort_order', 'asc')
        
        sorted_chapters = sort_chapters_by_number(novel['chapters'], order)
        
        if chapter_index >= len(sorted_chapters):
            return jsonify({'error': 'Chapter index out of range'}), 404
        
        target_chapter_id = sorted_chapters[chapter_index]['id']
        
        with db_session_scope() as session:
            chapter = session.query(Chapter).filter_by(id=target_chapter_id).first()
            if not chapter:
                return jsonify({'error': 'Chapter not found'}), 404
            
            chapter.translated_content = translated_text
            
            translated_title = data.get('translated_title')
            if translated_title:
                chapter.translated_title = translated_title
                
            if translation_model:
                chapter.translation_model = translation_model
            session.flush()
            
        return jsonify({'success': True, 'message': 'Translation saved'})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/chapter/<chapter_id>/token-usage', methods=['GET'])
def get_chapter_token_usage(chapter_id):

    try:
        from services.token_usage_service import get_chapter_token_usage
        user_id = get_user_id()
        
        from database.db_novel import get_chapter_db
        chapter = get_chapter_db(chapter_id)
        if not chapter or chapter.novel.user_id != user_id:
            return jsonify({'error': 'Chapter not found'}), 404
        
        records = get_chapter_token_usage(chapter_id)
        
        token_usage_with_costs = []
        for record in records:
            record_dict = record.to_dict()
            cost_info = calculate_cost(
                record.input_tokens,
                record.output_tokens,
                record.provider,
                record.model
            )
            record_dict['cost_info'] = cost_info if cost_info and cost_info.get('pricing_available') else None
            token_usage_with_costs.append(record_dict)
        
        return jsonify({
            'success': True,
            'token_usage': token_usage_with_costs
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/novel/<novel_id>/token-usage', methods=['GET'])
def get_novel_token_usage(novel_id):

    try:
        from services.token_usage_service import get_novel_token_usage
        user_id = get_user_id()
        
        stats = get_novel_token_usage(novel_id, user_id)
        return jsonify({
            'success': True,
            'token_usage': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/token-usage/stats', methods=['GET'])
def get_token_usage_stats():

    try:
        from services.token_usage_service import (
            get_user_token_usage, get_token_usage_by_provider,
            get_token_usage_by_model, get_recent_token_usage
        )
        from datetime import datetime, timedelta
        
        user_id = get_user_id()
        
        days = request.args.get('days', 30, type=int)
        start_date = None
        end_date = None
        
        if days:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
        
        all_time = get_user_token_usage(user_id)
        
        now = datetime.now()
        month_start = datetime(now.year, now.month, 1)
        this_month = get_user_token_usage(user_id, month_start, now)
        
        week_start = now - timedelta(days=now.weekday())
        this_week = get_user_token_usage(user_id, week_start, now)
        
        by_provider = get_token_usage_by_provider(user_id, start_date, end_date)
        by_model = get_token_usage_by_model(user_id, start_date, end_date)
        recent = get_recent_token_usage(user_id, days=30)
        
        model_costs = {}
        for model, model_stats in by_model.items():
            provider = model_stats.get('provider', 'openrouter')
            cost_info = calculate_cost(
                model_stats['input_tokens'],
                model_stats['output_tokens'],
                provider,
                model
            )
            model_costs[model] = cost_info if cost_info and cost_info.get('pricing_available') else None
        
        return jsonify({
            'success': True,
            'stats': {
                'all_time': all_time,
                'this_month': this_month,
                'this_week': this_week,
                'by_provider': by_provider,
                'by_model': by_model,
                'recent_daily': recent,
                'model_costs': model_costs
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/token-usage/clear', methods=['POST'])
def clear_token_usage():

    try:
        from services.token_usage_service import clear_user_token_usage
        user_id = get_user_id()
        
        if clear_user_token_usage(user_id):
            return jsonify({'success': True, 'message': 'Token usage stats cleared'})
        else:
            return jsonify({'error': 'Failed to clear stats'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/translate/estimate', methods=['POST'])
def estimate_translation_tokens_endpoint():

    try:
        user_id = get_user_id()
        data = request.json
        text = data.get('text', '')
        novel_id = data.get('novel_id', '')
        
        req_model = data.get('model')
        req_provider = data.get('provider')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        settings = load_settings(user_id)
        
        if req_model:
            selected_model = req_model
            if req_provider:
                provider = req_provider
            else:
                if '/' in selected_model:
                    provider = 'openrouter'
                else:
                    provider = settings.get('selected_provider', 'openrouter')
        else:
            provider = settings.get('selected_provider', 'openrouter')
            selected_model = settings.get('provider_models', {}).get(provider, '')
        
        use_thinking_mode = data.get('use_thinking_mode', False)
        if use_thinking_mode and not req_model:
            thinking_models = settings.get('thinking_mode_models', {})
            thinking_model = thinking_models.get(provider)
            if thinking_model:
                selected_model = thinking_model
        
        glossary = get_novel_glossary(user_id, novel_id) if novel_id else {}
        images = data.get('images', [])
        
        estimation = estimate_translation_tokens(text, provider, selected_model, glossary, images)
        
        cost_info = None
        if estimation:
            cost_info = calculate_cost(
                estimation.get('input_tokens', 0),
                estimation.get('output_tokens', 0),
                provider,
                selected_model
            )
        
        return jsonify({
            'success': True,
            'estimation': estimation,
            'provider': provider,
            'model': selected_model,
            'cost_info': cost_info
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/settings', methods=['GET', 'POST'])
@require_auth
def settings():

    user_id = get_user_id()
    
    if request.method == 'GET':
        return jsonify(load_settings(user_id))
    
    elif request.method == 'POST':
        try:
            new_settings = request.json
            save_settings(user_id, new_settings)
            return jsonify({'success': True, 'message': 'Settings saved'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@api_bp.route('/reading-preferences', methods=['GET', 'POST'])
@require_auth
def reading_preferences():

    from database.db_reading_preferences import get_reading_preferences, save_reading_preferences
    
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if request.method == 'GET':
        try:
            prefs = get_reading_preferences(user_id)
            return jsonify({'success': True, 'preferences': prefs})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'POST':
        try:
            data = request.json or {}
            saved_prefs = save_reading_preferences(user_id, data)
            
            if saved_prefs:
                return jsonify({'success': True, 'preferences': saved_prefs, 'message': 'Reading preferences saved'})
            else:
                return jsonify({'error': 'Failed to save reading preferences'}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@api_bp.route('/pricing', methods=['GET', 'POST'])
@require_auth
def pricing():

    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    if request.method == 'GET':
        try:
            settings = load_settings(user_id)
            pricing = settings.get('model_pricing', {}) or {}

            provider_models = settings.get('provider_models', {}) or {}

            suggested = {}
            
            try:
                from database.database import db_session_scope
                from database.db_models import GlobalModelPricing
                
                with db_session_scope() as session:
                    global_pricing_records = session.query(GlobalModelPricing).all()
                    
                    for record in global_pricing_records:
                        model_key = record.model_name
                        entry = {}
                        
                        if record.input_price_per_1m:
                            value = float(record.input_price_per_1m) / 1000.0
                            entry['input_per_1k'] = f"{value:.10f}".rstrip('0').rstrip('.')
                        if record.output_price_per_1m:
                            value = float(record.output_price_per_1m) / 1000.0
                            entry['output_per_1k'] = f"{value:.10f}".rstrip('0').rstrip('.')
                        
                        if entry:                                         
                            suggested[model_key] = entry
            except Exception as e:
                pass                                   
            
            api_key = settings.get('api_keys', {}).get('openrouter')
            try:
                for prov, model_name in (provider_models.items() if isinstance(provider_models, dict) else []):
                    if not model_name:
                        continue
                    if prov != 'openrouter':
                        continue

                    try:
                        mp = None
                        if api_key:
                            mp = get_model_pricing_with_key('openrouter', model_name, api_key)

                        if mp and mp.get('available'):
                            input_price_per_token = mp.get('input_price')
                            output_price_per_token = mp.get('output_price')
                            if input_price_per_token is not None or output_price_per_token is not None:
                                entry = {}
                                if input_price_per_token is not None:
                                    entry['input_per_1k'] = f"{(float(input_price_per_token) * 1000.0):.10f}"
                                if output_price_per_token is not None:
                                   entry['output_per_1k'] = f"{(float(output_price_per_token) * 1000.0):.10f}"
                                suggested[model_name] = entry
                    except Exception:
                        continue
            except Exception:
                suggested = {}

            try:
                for prov, model_name in (provider_models.items() if isinstance(provider_models, dict) else []):
                    if not model_name:
                        continue
                    if model_name not in pricing:
                        pricing[model_name] = {'input_per_1k': '', 'output_per_1k': ''}
            except Exception:
                pass

            for m, p in list(pricing.items()):
                try:
                    if isinstance(p, dict):
                        for key in ('input_per_1k', 'output_per_1k'):
                            val = p.get(key)
                            if val in (None, '', 0, '0', '0.0'):
                                p[key] = ''
                except Exception:
                    continue

            if suggested:
                pricing.setdefault('suggested', {})
                for k, v in suggested.items():
                    pricing['suggested'][k] = v
                    if k in pricing:
                        if not pricing[k].get('input_per_1k') and v.get('input_per_1k'):
                            pricing[k]['input_per_1k'] = v.get('input_per_1k')
                        if not pricing[k].get('output_per_1k') and v.get('output_per_1k'):
                            pricing[k]['output_per_1k'] = v.get('output_per_1k')

            return jsonify({'success': True, 'pricing': pricing})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    elif request.method == 'POST':
        try:
            data = request.json or {}
            settings = load_settings(user_id)
            settings['model_pricing'] = data
            save_settings(user_id, settings)
            return jsonify({'success': True, 'message': 'Pricing saved'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@api_bp.route('/novel/<novel_id>/glossary', methods=['GET', 'POST'])
@require_auth
def novel_glossary(novel_id):

    user_id = get_user_id()
    
    if request.method == 'GET':
        glossary = get_novel_glossary(user_id, novel_id)
        return jsonify({'success': True, 'glossary': glossary})
    
    elif request.method == 'POST':
        try:
            from urllib.parse import unquote
            novel_id = unquote(novel_id)
            
            data = request.json
            glossary = data.get('glossary', {})
            
            save_novel_glossary(user_id, novel_id, glossary)
            
            return jsonify({'success': True, 'message': 'Glossary saved'})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

@api_bp.route('/novel/<novel_id>/share', methods=['POST'])
@require_auth
def share_novel(novel_id):
    try:
        from urllib.parse import unquote
        import secrets
        from database.database import db_session_scope
        from database.db_models import Novel
        
        user_id = get_user_id()
        novel_id = unquote(novel_id)
        
        with db_session_scope() as session:
            novel = session.query(Novel).filter(
                Novel.slug == novel_id,
                Novel.user_id == user_id
            ).first()
            
            if not novel:
                return jsonify({'error': 'Novel not found'}), 404
            
            if not novel.share_token:
                novel.share_token = secrets.token_urlsafe(16)
            
            novel.is_shared = True
            session.flush()
            
            return jsonify({
                'success': True,
                'share_token': novel.share_token,
                'share_url': f"{request.host_url}shared/{novel.share_token}"
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/novel/<novel_id>/unshare', methods=['POST'])
@require_auth
def unshare_novel(novel_id):
    try:
        from urllib.parse import unquote
        from database.database import db_session_scope
        from database.db_models import Novel
        
        user_id = get_user_id()
        novel_id = unquote(novel_id)
        
        with db_session_scope() as session:
            novel = session.query(Novel).filter(
                Novel.slug == novel_id,
                Novel.user_id == user_id
            ).first()
            
            if not novel:
                return jsonify({'error': 'Novel not found'}), 404
            
            novel.is_shared = False
                                                                                          
                                                                       
            session.flush()
            
            return jsonify({'success': True})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/shared/<token>', methods=['GET'])
def get_shared_novel(token):
    try:
        from database.database import db_session_scope
        from database.db_models import Novel, Chapter
        
        with db_session_scope() as session:
            novel = session.query(Novel).filter(
                Novel.share_token == token,
                Novel.is_shared == True
            ).first()
            
            if not novel:
                return jsonify({'error': 'Novel not found or access revoked'}), 404
            
                                                                                          
            novel_data = {
                'title': novel.translated_title or novel.title,
                'author': novel.translated_author or novel.author,
                'synopsis': novel.translated_synopsis or novel.synopsis,
                'cover_url': novel.cover_url,
                'tags': novel.translated_tags or novel.tags,
                'glossary': novel.glossary or {},                                 
                'chapters': []
            }
            
            chapters = session.query(Chapter).filter(
                Chapter.novel_id == novel.id
            ).order_by(Chapter.position).all()
            
            for ch in chapters:
                novel_data['chapters'].append({
                    'chapter_number': ch.chapter_number,
                    'title': ch.translated_title or ch.title,
                    'position': ch.position
                })
                
            return jsonify({'success': True, 'novel': novel_data})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/shared/<token>/chapter/<chapter_number>', methods=['GET'])
def get_shared_chapter(token, chapter_number):
    try:
        from database.database import db_session_scope
        from database.db_models import Novel, Chapter
        
        with db_session_scope() as session:
            novel = session.query(Novel).filter(
                Novel.share_token == token,
                Novel.is_shared == True
            ).first()
            
            if not novel:
                return jsonify({'error': 'Novel not found or access revoked'}), 404
            
            chapter = session.query(Chapter).filter(
                Chapter.novel_id == novel.id,
                Chapter.chapter_number == str(chapter_number)
            ).first()
            
            if not chapter:
                return jsonify({'error': 'Chapter not found'}), 404
            
            return jsonify({
                'success': True,
                'chapter': {
                    'title': chapter.translated_title or chapter.title,
                    'content': chapter.translated_content or chapter.content,
                    'chapter_number': chapter.chapter_number,
                    'novel_title': novel.translated_title or novel.title
                }
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/shared/import', methods=['POST'])
@require_auth
def import_shared_novel():
                                                       
    try:
        from database.database import db_session_scope
        from database.db_models import Novel, Chapter
        from database.db_novel import create_novel_db
        from services.settings_service import can_user_import_novel
        import secrets
        import hashlib
        import re
        
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        data = request.get_json()
        token = data.get('token', '').strip()
        
        if not token:
            return jsonify({'error': 'Token is required'}), 400
        
                                              
                                                                                    
        can_import, error_msg, current_count, limit = can_user_import_novel(user_id)
        if not can_import:
                                                                                            
            if error_msg == "User not found":
                from sqlalchemy import func
                with db_session_scope() as check_session:
                    novel_count = check_session.query(func.count(Novel.id)).filter(
                        func.lower(Novel.user_id) == user_id.lower()
                    ).scalar() or 0
                                                                   
                    if novel_count >= 100:
                        return jsonify({'error': f'You have reached the maximum limit of 100 novels'}), 400
                                                             
            else:
                                                                      
                return jsonify({'error': error_msg}), 400
        
        with db_session_scope() as session:
                                   
            shared_novel = session.query(Novel).filter(
                Novel.share_token == token,
                Novel.is_shared == True
            ).first()
            
            if not shared_novel:
                return jsonify({'error': 'Shared novel not found or access revoked'}), 404
            
                                                             
            existing_novel = session.query(Novel).filter(
                Novel.user_id == user_id,
                Novel.title == shared_novel.title
            ).first()
            
            if existing_novel:
                return jsonify({
                    'error': f'You already have a novel titled "{shared_novel.title}" in your library',
                    'novel_id': existing_novel.slug
                }), 400
            
                                                                                      
            shared_chapters_query = session.query(Chapter).filter(
                Chapter.novel_id == shared_novel.id
            ).order_by(Chapter.position).all()
            
                                                             
            chapters_data = []
            for ch in shared_chapters_query:
                chapters_data.append({
                    'chapter_number': ch.chapter_number,
                    'title': ch.title,
                    'original_title': ch.original_title,
                    'translated_title': ch.translated_title,
                    'content': ch.content,
                    'translated_content': ch.translated_content,
                    'position': ch.position,
                    'is_bonus': ch.is_bonus if hasattr(ch, 'is_bonus') else False,
                    'source_url': ch.source_url if hasattr(ch, 'source_url') else None,
                    'images': ch.images if hasattr(ch, 'images') and ch.images else None
                })
            
                                           
            def slugify_english(text):
                if not text:
                    return 'unknown_novel'
                text = text.lower()
                text = re.sub(r'[^\w\s-]', '', text)
                text = re.sub(r'[-\s]+', '-', text)
                text = text.strip('-')
                return text or 'unknown_novel'
            
            base_slug = slugify_english(shared_novel.title)
            if not base_slug:
                base_slug = f"novel_{hashlib.md5(shared_novel.title.encode()).hexdigest()[:8]}"
            
            new_slug = f"{base_slug}_{user_id}"
            
                                                       
                                                                                                                    
                                                                                       
            cover_url = shared_novel.cover_url
            if cover_url and not cover_url.startswith('http://') and not cover_url.startswith('https://'):
                                                                         
                if cover_url.startswith('/images/'):
                                                                                    
                    parts = cover_url.split('/')
                    if len(parts) >= 4:
                                                                                               
                        cover_url = '/'.join(parts[2:])                            
                    else:
                                                                     
                        filename = parts[-1] if parts else cover_url
                        cover_url = f"{shared_novel.user_id}/{filename}"
                elif '/' in cover_url:
                                                                           
                    parts = cover_url.split('/')
                    if len(parts) >= 2:
                                                                           
                        pass
                    else:
                                                               
                        cover_url = f"{shared_novel.user_id}/{cover_url}"
                else:
                                                           
                    cover_url = f"{shared_novel.user_id}/{cover_url}"
            
            novel_data = {
                'slug': new_slug,
                'title': shared_novel.title,
                'original_title': shared_novel.original_title or shared_novel.title,
                'translated_title': shared_novel.translated_title,
                'author': shared_novel.author,
                'translated_author': shared_novel.translated_author,
                'tags': shared_novel.tags or [],
                'translated_tags': shared_novel.translated_tags or [],
                'synopsis': shared_novel.synopsis,
                'translated_synopsis': shared_novel.translated_synopsis,
                'cover_url': cover_url,
                'source_url': '',
                'glossary': shared_novel.glossary or {}
            }
            
                                                                                        
                                                
            new_novel = Novel(
                user_id=user_id,
                slug=novel_data['slug'],
                title=novel_data['title'],
                original_title=novel_data.get('original_title'),
                translated_title=novel_data.get('translated_title'),
                author=novel_data.get('author'),
                translated_author=novel_data.get('translated_author'),
                cover_url=novel_data.get('cover_url'),
                tags=novel_data.get('tags', []),
                translated_tags=novel_data.get('translated_tags', []),
                synopsis=novel_data.get('synopsis'),
                translated_synopsis=novel_data.get('translated_synopsis'),
                source_url=novel_data.get('source_url'),
                glossary=novel_data.get('glossary', {}),
                imported_from_share_token=token                                                   
            )
            session.add(new_novel)
            session.flush()                             
            
            if not new_novel.id:
                return jsonify({'error': 'Failed to create novel'}), 500
            
                                                        
            chapters_imported = 0
            for idx, ch_data in enumerate(chapters_data):
                chapter_slug = f"{new_slug}_ch{ch_data['chapter_number']}_{int(time.time())}_{idx}"
                new_chapter = Chapter(
                    novel_id=new_novel.id,
                    chapter_number=ch_data['chapter_number'],
                    title=ch_data['title'],
                    original_title=ch_data['original_title'],
                    translated_title=ch_data['translated_title'],
                    content=ch_data['content'] or '',
                    translated_content=ch_data['translated_content'],
                    position=ch_data['position'],
                    is_bonus=ch_data['is_bonus'],
                    slug=chapter_slug,
                    source_url=ch_data['source_url'],
                    images=ch_data['images']
                )
                session.add(new_chapter)
                chapters_imported += 1
            
            session.commit()
            
            return jsonify({
                'success': True,
                'novel_id': new_slug,
                'novel_title': shared_novel.translated_title or shared_novel.title,
                'chapters_imported': chapters_imported,
                'message': f'Successfully imported "{shared_novel.translated_title or shared_novel.title}" with {chapters_imported} chapters'
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/novel/<novel_id>/sync-shared', methods=['POST'])
@require_auth
def sync_shared_novel(novel_id):
                                                                             
    try:
        from database.database import db_session_scope
        from database.db_models import Novel, Chapter
        from urllib.parse import unquote
        
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        novel_id = unquote(novel_id)
        
        with db_session_scope() as session:
                                    
            imported_novel = session.query(Novel).filter(
                Novel.slug == novel_id,
                Novel.user_id == user_id
            ).first()
            
            if not imported_novel:
                return jsonify({'error': 'Novel not found'}), 404
            
            if not imported_novel.imported_from_share_token:
                return jsonify({'error': 'This novel was not imported from a shared novel'}), 400
            
                                           
            shared_novel = session.query(Novel).filter(
                Novel.share_token == imported_novel.imported_from_share_token,
                Novel.is_shared == True
            ).first()
            
            if not shared_novel:
                return jsonify({'error': 'Original shared novel not found or no longer shared'}), 404
            
                                                    
            shared_chapters_query = session.query(Chapter).filter(
                Chapter.novel_id == shared_novel.id
            ).order_by(Chapter.position).all()
            
                                                         
            existing_chapters = session.query(Chapter).filter(
                Chapter.novel_id == imported_novel.id
            ).all()
            
                                                                       
            existing_chapter_numbers = {ch.chapter_number for ch in existing_chapters}
            
                                                                    
            new_chapters_data = []
            for ch in shared_chapters_query:
                if ch.chapter_number not in existing_chapter_numbers:
                    new_chapters_data.append({
                        'chapter_number': ch.chapter_number,
                        'title': ch.title,
                        'original_title': ch.original_title,
                        'translated_title': ch.translated_title,
                        'content': ch.content,
                        'translated_content': ch.translated_content,
                        'position': ch.position,
                        'is_bonus': ch.is_bonus if hasattr(ch, 'is_bonus') else False,
                        'source_url': ch.source_url if hasattr(ch, 'source_url') else None,
                        'images': ch.images if hasattr(ch, 'images') and ch.images else None
                    })
            
            if not new_chapters_data:
                return jsonify({
                    'success': True,
                    'message': 'Novel is already up to date',
                    'new_chapters': 0
                })
            
                              
            chapters_added = 0
            for idx, ch_data in enumerate(new_chapters_data):
                chapter_slug = f"{novel_id}_ch{ch_data['chapter_number']}_{int(time.time())}_{idx}"
                new_chapter = Chapter(
                    novel_id=imported_novel.id,
                    chapter_number=ch_data['chapter_number'],
                    title=ch_data['title'],
                    original_title=ch_data['original_title'],
                    translated_title=ch_data['translated_title'],
                    content=ch_data['content'] or '',
                    translated_content=ch_data['translated_content'],
                    position=ch_data['position'],
                    is_bonus=ch_data['is_bonus'],
                    slug=chapter_slug,
                    source_url=ch_data['source_url'],
                    images=ch_data['images']
                )
                session.add(new_chapter)
                chapters_added += 1
            
                                                                                    
            metadata_updated = False
            if shared_novel.translated_title != imported_novel.translated_title:
                imported_novel.translated_title = shared_novel.translated_title
                metadata_updated = True
            if shared_novel.translated_author != imported_novel.translated_author:
                imported_novel.translated_author = shared_novel.translated_author
                metadata_updated = True
            if shared_novel.translated_synopsis != imported_novel.translated_synopsis:
                imported_novel.translated_synopsis = shared_novel.translated_synopsis
                metadata_updated = True
            if shared_novel.translated_tags != imported_novel.translated_tags:
                imported_novel.translated_tags = shared_novel.translated_tags
                metadata_updated = True
            if shared_novel.cover_url != imported_novel.cover_url:
                                                       
                cover_url = shared_novel.cover_url
                if cover_url and not cover_url.startswith('http://') and not cover_url.startswith('https://'):
                    if cover_url.startswith('/images/'):
                        parts = cover_url.split('/')
                        if len(parts) >= 4:
                            cover_url = '/'.join(parts[2:])
                        else:
                            filename = parts[-1] if parts else cover_url
                            cover_url = f"{shared_novel.user_id}/{filename}"
                    elif '/' not in cover_url:
                        cover_url = f"{shared_novel.user_id}/{cover_url}"
                imported_novel.cover_url = cover_url
                metadata_updated = True
            
            session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Successfully synced {chapters_added} new chapter(s)',
                'new_chapters': chapters_added,
                'metadata_updated': metadata_updated
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/novel/<novel_id>/check-shared-updates', methods=['GET'])
@require_auth
def check_shared_updates(novel_id):
                                                                           
    try:
        from database.database import db_session_scope
        from database.db_models import Novel, Chapter
        from urllib.parse import unquote
        
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        novel_id = unquote(novel_id)
        
        with db_session_scope() as session:
                                    
            imported_novel = session.query(Novel).filter(
                Novel.slug == novel_id,
                Novel.user_id == user_id
            ).first()
            
            if not imported_novel:
                return jsonify({'error': 'Novel not found'}), 404
            
            if not imported_novel.imported_from_share_token:
                return jsonify({
                    'success': True,
                    'is_imported': False,
                    'has_updates': False
                })
            
                                           
            shared_novel = session.query(Novel).filter(
                Novel.share_token == imported_novel.imported_from_share_token,
                Novel.is_shared == True
            ).first()
            
            if not shared_novel:
                return jsonify({
                    'success': True,
                    'is_imported': True,
                    'has_updates': False,
                    'message': 'Original novel is no longer shared'
                })
            
                            
            shared_chapter_count = session.query(Chapter).filter(
                Chapter.novel_id == shared_novel.id
            ).count()
            
            imported_chapter_count = session.query(Chapter).filter(
                Chapter.novel_id == imported_novel.id
            ).count()
            
            has_updates = shared_chapter_count > imported_chapter_count
            
            return jsonify({
                'success': True,
                'is_imported': True,
                'has_updates': has_updates,
                'shared_chapter_count': shared_chapter_count,
                'imported_chapter_count': imported_chapter_count,
                'new_chapters_available': max(0, shared_chapter_count - imported_chapter_count)
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/novel/<novel_id>/cover', methods=['POST'])
@require_auth
def upload_novel_cover(novel_id):

    import os
    import uuid
    from urllib.parse import unquote

    try:
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401

        novel_id = unquote(novel_id)

        if 'cover_image' not in request.files:
            return jsonify({'error': 'No cover image file provided'}), 400

        file = request.files['cover_image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

                            
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        file_ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            return jsonify({'error': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'}), 400

                                   
        from services.image_service import get_user_images_dir
        images_dir = get_user_images_dir(user_id)
        os.makedirs(images_dir, exist_ok=True)

                                  
        cover_filename = f"cover_{uuid.uuid4().hex}.{file_ext}"
        cover_path = os.path.join(images_dir, cover_filename)

                       
        file.save(cover_path)

                                                  
        from database.db_models import Novel
        from database.database import db_session_scope

        with db_session_scope() as session:
            novel = session.query(Novel).filter(
                Novel.slug == novel_id,
                Novel.user_id == user_id
            ).first()

            if not novel:
                                            
                if os.path.exists(cover_path):
                    os.remove(cover_path)
                return jsonify({'error': 'Novel not found'}), 404

                                                               
            if novel.cover_url:
                old_cover_path = os.path.join(images_dir, novel.cover_url)
                if os.path.exists(old_cover_path):
                    try:
                        os.remove(old_cover_path)
                    except:
                        pass

                              
            novel.cover_url = cover_filename
            session.commit()

        return jsonify({
            'success': True,
            'cover_url': cover_filename,
            'message': 'Cover image uploaded successfully'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/novel/<novel_id>/metadata', methods=['GET', 'POST'])
@require_auth
def novel_metadata(novel_id):

    import os
    import uuid
    from urllib.parse import unquote

    try:
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401

        novel_id = unquote(novel_id)

        from database.db_models import Novel
        from database.database import db_session_scope

        with db_session_scope() as session:
            novel = session.query(Novel).filter(
                Novel.slug == novel_id,
                Novel.user_id == user_id
            ).first()

            if not novel:
                return jsonify({'error': 'Novel not found'}), 404

            if request.method == 'GET':
                return jsonify({
                    'success': True,
                    'metadata': {
                        'title': novel.translated_title or novel.title,                                     
                        'author': novel.translated_author or '',                                              
                        'synopsis': novel.translated_synopsis or '',                                
                        'tags': novel.translated_tags or [],                            
                        'tags': novel.translated_tags or [],
                        'cover_url': novel.cover_url,
                        'custom_prompt_suffix': novel.custom_prompt_suffix
                    }
                })

                                    
            data = request.get_json()

                                                        
            if 'title' in data and data['title'].strip():
                new_title = data['title'].strip()
                
                                                                                               
                if '_' in new_title:
                    return jsonify({'error': 'Title cannot contain underscores'}), 400
                
                                                                             
                slug_parts = novel_id.split('_')
                if len(slug_parts) < 2:
                    return jsonify({'error': 'Invalid novel slug format'}), 400
                
                username = slug_parts[-1]                                
                
                                                           
                from urllib.parse import quote
                import re
                                                                                                       
                sanitized_title = new_title.lower()
                sanitized_title = re.sub(r'[^\w\s-]', '', sanitized_title)                        
                sanitized_title = re.sub(r'[-\s]+', '-', sanitized_title)                                              
                sanitized_title = sanitized_title.strip('-')                                                  
                
                new_slug = f"{sanitized_title}_{username}"
                
                                       
                if new_slug != novel_id:
                                                      
                    existing_novel = session.query(Novel).filter(
                        Novel.slug == new_slug,
                        Novel.user_id == user_id
                    ).first()
                    
                    if existing_novel:
                        return jsonify({'error': 'A novel with this title already exists'}), 400
                    
                                     
                    novel.slug = new_slug
                
                                          
                novel.translated_title = new_title
                if not novel.title:                                          
                    novel.title = new_title

            if 'author' in data:
                                                                            
                novel.translated_author = data['author'].strip()
                                                                                       
                if not novel.author:
                    novel.author = data['author'].strip()
            if 'synopsis' in data:
                                                                              
                novel.translated_synopsis = data['synopsis'].strip()
                                                                
                if not novel.synopsis:
                    novel.synopsis = data['synopsis'].strip()
            if 'tags' in data:
                                                                          
                novel.translated_tags = data['tags'] if isinstance(data['tags'], list) else []
                                                            
                if not novel.tags:
                    novel.tags = data['tags'] if isinstance(data['tags'], list) else []

            if 'custom_prompt_suffix' in data:
                novel.custom_prompt_suffix = data['custom_prompt_suffix'].strip() if data['custom_prompt_suffix'] else None

            session.commit()

            return jsonify({
                'success': True,
                'message': 'Metadata updated successfully',
                'new_slug': novel.slug                                      
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/novel/<novel_id>/auto-detect-characters', methods=['POST'])
def auto_detect_characters(novel_id):

    try:
        from urllib.parse import unquote
        user_id = get_user_id()
        novel_id = unquote(novel_id)
        
                                                               
        data = request.get_json() or {}
        chapter_number = data.get('chapter_number')             
        chapter_index = data.get('chapter_index')                           

        novels = load_novels(user_id)
        if novel_id not in novels:
            return jsonify({'error': f'Novel not found: {novel_id}'}), 404

        novel = novels[novel_id]

        if not novel.get('chapters') or len(novel['chapters']) == 0:
            return jsonify({'error': 'No chapters available to analyze'}), 400

                             
        sample_text = ""
        translated_text = ""                           
        target_chapter = None

                                                                                   
        if chapter_number is not None:
                                            
            for ch in novel['chapters']:
                if ch and str(ch.get('chapter_number')) == str(chapter_number):
                    target_chapter = ch
                    break

            if not target_chapter:
                return jsonify({'error': f'Chapter {chapter_number} not found'}), 404

        elif chapter_index is not None:
                                                                     
            try:
                chapter_index = int(chapter_index)
                if chapter_index >= len(novel['chapters']):
                    return jsonify({'error': f'Chapter index {chapter_index} out of range'}), 400

                target_chapter = novel['chapters'][chapter_index]

            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid chapter_index'}), 400

                                                       
        if target_chapter:
            sample_text = target_chapter.get('korean_text', '') or target_chapter.get('koreanText', '')
                                                                               
            translated_text = target_chapter.get('translated_text', '') or target_chapter.get('translatedText', '')

            if not sample_text:
                return jsonify({'error': 'Chapter has no content'}), 400
        else:
                                                                           
            for i, chapter in enumerate(novel['chapters'][:3]):
                if chapter:
                    sample_text += (chapter.get('korean_text', '') or chapter.get('koreanText', '')) + "\n\n"
                                                                                 
                    chapter_translation = chapter.get('translated_text', '') or chapter.get('translatedText', '')
                    if chapter_translation:
                        translated_text += chapter_translation + "\n\n"
                    if len(sample_text) > 10000:
                        break
        
        if not sample_text:
            return jsonify({'error': 'No text content available'}), 400
        
                         
        settings = load_settings(user_id)
        provider = settings.get('selected_provider', 'openrouter')
        api_key = settings.get('api_keys', {}).get(provider, '')
        selected_model = settings.get('provider_models', {}).get(provider, '')
        
        if not api_key:
            return jsonify({'error': 'API key not configured'}), 400
        
                                             
        print(f"[DEBUG] Translated text length: {len(translated_text)}")
        print(f"[DEBUG] Translated text exists: {bool(translated_text and translated_text.strip())}")
        
                                                     
        from services.ai_service import detect_characters_hybrid
        detect_result = detect_characters_hybrid(
            sample_text, provider, api_key, selected_model,
            translated_text=translated_text if translated_text.strip() else None
        )
        
        if not detect_result.get('success'):
            return jsonify({'error': detect_result.get('error', 'Failed to detect characters')}), 500
            
                                    
        detect_result['debug_info'] = {
            'translated_text_length': len(translated_text) if translated_text else 0,
            'has_translation': bool(translated_text and translated_text.strip())
        }
        
        korean_names = detect_result['characters']
        
        # Always use translate_names for proper romanization, even if bilingual
        # detection found English names - those may be incorrectly translated
        translate_result = translate_names(korean_names, provider, api_key, selected_model)
        translations = translate_result.get('translations', {}) if translate_result.get('success') else {}
        
        gender_result = detect_character_genders(korean_names, sample_text, provider, api_key, selected_model)
        
        if target_chapter:
            scanned_info = f"Chapter {target_chapter.get('chapter_number', 'Unknown')}"
        else:
            scanned_info = 'first 3 chapters'

        response_data = {
            'success': True,
            'characters': korean_names,
            'translations': translations,
            'genders': gender_result.get('genders', {}) if gender_result.get('success') else {name: 'auto' for name in korean_names},
            'stats': detect_result.get('stats', {}),
            'chapter_scanned': scanned_info
        }
        
        return jsonify(response_data)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/update-novel-title', methods=['POST'])
def update_novel_title():

    try:
        user_id = get_user_id()
        data = request.json
        novel_id = data.get('novel_id')
        translated_title = data.get('translated_title')
        
        if not novel_id or not translated_title:
            return jsonify({'error': 'Missing novel_id or translated_title'}), 400
        
        novels = load_novels(user_id)
        
        if novel_id not in novels:
            return jsonify({'error': 'Novel not found'}), 404
        
        novels[novel_id]['translated_title'] = translated_title
        save_novels(user_id, novels)
        
        return jsonify({'success': True, 'message': 'Novel title updated'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/update-novel-sort-order', methods=['POST'])
def update_novel_sort_order():

    try:
        user_id = get_user_id()
        data = request.json
        novel_id = data.get('novel_id')
        sort_order = data.get('sort_order')
        
        if not novel_id:
            return jsonify({'error': 'Invalid data'}), 400
        
        novels = load_novels(user_id)
        if novel_id not in novels:
            return jsonify({'error': 'Novel not found'}), 404
        
        if sort_order == 'default':
            if 'sort_order_override' in novels[novel_id]:
                del novels[novel_id]['sort_order_override']
            if 'sort_order' in novels[novel_id]:
                del novels[novel_id]['sort_order']
        elif sort_order in ['asc', 'desc']:
            novels[novel_id]['sort_order_override'] = sort_order
            novels[novel_id]['sort_order'] = sort_order
        else:
            return jsonify({'error': 'Invalid sort order'}), 400
        
        save_novels(user_id, novels)
        
        return jsonify({'success': True, 'message': 'Sort order updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/task-status/<task_id>', methods=['GET'])
def task_status(task_id):

    try:
        from celery.result import AsyncResult
        from celery_app import celery
        
        task = AsyncResult(task_id, app=celery)
        
        if task.state == 'PENDING':
            response = {
                'state': task.state,
                'status': 'Pending...',
                'progress': 0
            }
        elif task.state == 'STARTED':
            response = {
                'state': task.state,
                'status': 'Started...',
                'progress': 10
            }
        elif task.state == 'PROGRESS':
            response = {
                'state': task.state,
                'status': task.info.get('status', 'Processing...'),
                'progress': 50
            }
        elif task.state == 'SUCCESS':
            response = {
                'state': task.state,
                'status': 'Complete',
                'result': task.result,
                'progress': 100
            }
        elif task.state == 'FAILURE':
            response = {
                'state': task.state,
                'status': 'Failed',
                'error': str(task.info),
                'progress': 0
            }
        else:
            response = {
                'state': task.state,
                'status': str(task.info),
                'progress': 0
            }
        
        return jsonify(response)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/translate-novel-title', methods=['POST'])
def translate_novel_title():

    try:
        user_id = get_user_id()
        data = request.json
        novel_id = data.get('novel_id')
        
        if not novel_id:
            return jsonify({'error': 'Novel ID required'}), 400
        
        novels = load_novels(user_id)
        if novel_id not in novels:
            return jsonify({'error': f'Novel not found: {novel_id}'}), 404
        
        from tasks.translation_tasks import translate_novel_title_task
        task = translate_novel_title_task.delay(user_id, novel_id)
        
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'Translation queued'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/translate-novel-title-sync', methods=['POST'])
def translate_novel_title_sync():

    try:
        user_id = get_user_id()
        data = request.json
        novel_id = data.get('novel_id')
        
        if not novel_id:
            return jsonify({'error': 'Novel ID required'}), 400
        
        novels = load_novels(user_id)
        if novel_id not in novels:
            return jsonify({'error': f'Novel not found: {novel_id}'}), 404
        
        novel = novels[novel_id]
        
        korean_title = novel.get('title', '')
        korean_author = novel.get('author', '')
        korean_tags = novel.get('tags', [])
        korean_synopsis = novel.get('synopsis', '')
        
        settings = load_settings(user_id)
        provider = settings.get('selected_provider', 'openrouter')
        api_key = settings.get('api_keys', {}).get(provider, '')
        selected_model = settings.get('provider_models', {}).get(provider, '')
        
        if not api_key:
            return jsonify({'error': 'No API key configured for translations'}), 400
        
        translated_title = korean_title
        translated_author = korean_author
        translated_tags = korean_tags[:]
        translated_synopsis = korean_synopsis
        
        try:
            if korean_title:
                cache_key = get_cache_key(f"title:{korean_title}")
                if cache_key in translation_cache:
                    translated_title = translation_cache[cache_key]
                else:
                    translated_title_result = translate_text(
                        korean_title, provider, api_key, selected_model,
                        glossary=None, images=None
                    )
                    if isinstance(translated_title_result, dict):
                        translated_title_result = translated_title_result.get('translated_text', '')
                    if translated_title_result and not translated_title_result.startswith("Error") and not translated_title_result.startswith(provider.capitalize()):
                        translated_title = translated_title_result
                        translation_cache[cache_key] = translated_title
                        if len(translation_cache) > MAX_CACHE_SIZE:
                            translation_cache.pop(next(iter(translation_cache)))
            
            if korean_author:
                cache_key = get_cache_key(f"author:{korean_author}")
                if cache_key in translation_cache:
                    translated_author = translation_cache[cache_key]
                else:
                    translated_author_result = translate_text(
                        korean_author, provider, api_key, selected_model,
                        glossary=None, images=None
                    )
                    if isinstance(translated_author_result, dict):
                        translated_author_result = translated_author_result.get('translated_text', '')
                    if translated_author_result and not translated_author_result.startswith("Error") and not translated_author_result.startswith(provider.capitalize()):
                        translated_author = translated_author_result
                        translation_cache[cache_key] = translated_author
                        if len(translation_cache) > MAX_CACHE_SIZE:
                            translation_cache.pop(next(iter(translation_cache)))
            
            if korean_tags:
                tags_text = ', '.join(korean_tags)
                translated_tags_result = translate_text(
                    tags_text, provider, api_key, selected_model,
                    glossary=None, images=None
                )
                if isinstance(translated_tags_result, dict):
                    translated_tags_result = translated_tags_result.get('translated_text', '')
                if translated_tags_result and not translated_tags_result.startswith("Error") and not translated_tags_result.startswith(provider.capitalize()):
                    translated_tags_text = translated_tags_result
                    translated_tags = [tag.strip() for tag in translated_tags_text.split(',')]
            
            if korean_synopsis:
                translated_synopsis_result = translate_text(
                    korean_synopsis, provider, api_key, selected_model,
                    glossary=None, images=None
                )
                if isinstance(translated_synopsis_result, dict):
                    translated_synopsis_result = translated_synopsis_result.get('translated_text', '')
                if translated_synopsis_result and not translated_synopsis_result.startswith("Error") and not translated_synopsis_result.startswith(provider.capitalize()):
                    translated_synopsis = translated_synopsis_result
        
        except Exception as e:
            pass
        
        novels[novel_id]['translated_title'] = translated_title
        novels[novel_id]['translated_author'] = translated_author
        novels[novel_id]['translated_tags'] = translated_tags
        novels[novel_id]['translated_synopsis'] = translated_synopsis
        
        save_novels(user_id, novels)
        
        return jsonify({
            'success': True,
            'translated_title': translated_title,
            'translated_author': translated_author,
            'translated_tags': translated_tags,
            'translated_synopsis': translated_synopsis
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/check-auth')
def check_auth():

    if 'user_id' in session:
                                
        from services.admin_service import is_admin_authorized
        is_admin = is_admin_authorized(request, session.get('username'))
        
        return jsonify({
            'authenticated': True,
            'user_id': session['user_id'],
            'username': session.get('username'),
            'is_admin': is_admin
        })
    return jsonify({'authenticated': False})

@api_bp.route('/delete-novel', methods=['POST'])
def delete_novel_endpoint():

    try:
        data = request.get_json()
        novel_id = data.get('novel_id')
        user_id = get_user_id()
        
        if not novel_id:
            return jsonify({'error': 'Missing novel_id'}), 400
            
        success = delete_novel(user_id, novel_id)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Novel not found or could not be deleted'}), 404
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/delete-chapter', methods=['POST'])
def delete_chapter_endpoint():

    try:
        data = request.get_json()
        novel_id = data.get('novel_id')
        chapter_id = data.get('chapter_id')
        chapter_index = data.get('chapter_index')                           
        user_id = get_user_id()

        if not novel_id:
            return jsonify({'error': 'Missing novel_id parameter'}), 400

                                              
        if chapter_id is not None:
            from database.database import db_session_scope
            from database.db_models import Novel, Chapter
            from database.db_novel import delete_chapter_db

                                                          
            with db_session_scope() as session:
                                                                
                novel = session.query(Novel).filter(
                    Novel.slug == novel_id,
                    Novel.user_id == user_id
                ).first()

                if not novel:
                    return jsonify({'error': 'Novel not found'}), 404

                                                              
                chapter = session.query(Chapter).filter(
                    Chapter.id == chapter_id,
                    Chapter.novel_id == novel.id
                ).first()

                if not chapter:
                    return jsonify({'error': 'Chapter not found'}), 404

                                    
                success = delete_chapter_db(chapter_id)

                if success:
                    return jsonify({'success': True})
                else:
                    return jsonify({'error': 'Failed to delete chapter'}), 500
        elif chapter_index is not None:
                                                      
            success = delete_chapter(user_id, novel_id, int(chapter_index))

            if success:
                return jsonify({'success': True})
            else:
                return jsonify({'error': 'Chapter not found or could not be deleted'}), 404
        else:
            return jsonify({'error': 'Missing chapter_id or chapter_index parameter'}), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/chapters/batch-delete', methods=['POST'])
def batch_delete_chapters():

    try:
        from database.database import db_session_scope
        from database.db_models import Novel, Chapter
        from database.db_novel import get_novel_with_chapters_db
        from models.novel import sort_chapters_by_number
        from sqlalchemy import and_
        
        data = request.get_json()
        novel_id = data.get('novel_id')
        chapter_indices = data.get('chapter_indices', [])
        user_id = get_user_id()
        
        if not novel_id or not chapter_indices:
            return jsonify({'error': 'Missing parameters'}), 400
        
        if not isinstance(chapter_indices, list):
            return jsonify({'error': 'chapter_indices must be a list'}), 400
        
        from models.settings import load_settings
        novel = get_novel_with_chapters_db(user_id, novel_id)
        if not novel:
            return jsonify({'error': 'Novel not found'}), 404
        
        settings = load_settings(user_id)
        if 'sort_order_override' in novel and novel['sort_order_override'] is not None:
            order = novel['sort_order_override']
        else:
            order = settings.get('default_sort_order', 'asc')
        
        sorted_chapters = sort_chapters_by_number(novel['chapters'], order)
        
        chapter_ids_to_delete = []
        for idx in chapter_indices:
            if idx < len(sorted_chapters):
                chapter_ids_to_delete.append(sorted_chapters[idx]['id'])
        
        if not chapter_ids_to_delete:
            return jsonify({'error': 'No valid chapters to delete'}), 400
        
        with db_session_scope() as session:
            novel_obj = session.query(Novel).filter(
                and_(Novel.user_id == user_id, Novel.slug == novel_id)
            ).with_for_update().first()
            
            if not novel_obj:
                return jsonify({'error': 'Novel not found'}), 404
            
            deleted_count = 0
            for chapter_id in chapter_ids_to_delete:
                chapter = session.query(Chapter).filter_by(id=chapter_id).first()
                if chapter:
                    from services.image_service import delete_images_for_chapter
                    delete_images_for_chapter(chapter.to_dict(include_content=False), user_id)
                    
                    session.delete(chapter)
                    deleted_count += 1
            
            session.flush()
            
            remaining_chapters = session.query(Chapter).filter_by(
                novel_id=novel_obj.id
            ).order_by(Chapter.position).all()
            
            
            for idx, ch in enumerate(remaining_chapters):
                if ch.position != idx:
                    ch.position = idx
            
            session.flush()
        
        response_data = {
            'success': True,
            'deleted_count': deleted_count,
            'total_requested': len(chapter_indices)
        }
        
        return jsonify(response_data)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/version', methods=['GET'])
def get_version():

    try:
        log_path = os.path.join('data', 'debug_test.log')
        with open(log_path, 'a') as f:
            f.write(f"Test write at {datetime.now()}\n")
        write_status = "success"
    except Exception as e:
        write_status = f"failed: {str(e)}"
        
    return jsonify({
        'version': 'debug-v2', 
        'timestamp': datetime.now().isoformat(),
        'log_write': write_status
    })

@api_bp.route('/translate-chapter-titles', methods=['POST'])
def translate_chapter_titles():

    try:
        from database.database import db_session_scope
        from database.db_models import Novel, Chapter
        from services.ai_service import translate_text
        
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
            
        data = request.get_json()
        novel_slug = data.get('novel_id')
        
        if not novel_slug:
            return jsonify({'error': 'Novel ID required'}), 400
        
        settings = load_settings(user_id)
        provider = settings.get('selected_provider', 'openrouter')
        api_key = settings.get('api_keys', {}).get(provider, '')
        selected_model = settings.get('provider_models', {}).get(provider, '')
        
        if not api_key:
            return jsonify({'error': 'No API key configured'}), 400
        
        with db_session_scope() as session:
            novel = session.query(Novel).filter_by(slug=novel_slug, user_id=user_id).first()
            if not novel:
                return jsonify({'error': 'Novel not found'}), 404
            
            chapters = session.query(Chapter).filter_by(novel_id=novel.id).all()
            
            untranslated_chapters = []
            for ch in chapters:
                if ch.translated_title == ch.title or not ch.translated_title:
                    untranslated_chapters.append(ch)
            
            if not untranslated_chapters:
                return jsonify({
                    'success': True,
                    'message': 'All chapter titles already translated',
                    'translated_count': 0
                })
            
            titles_to_translate = [ch.title for ch in untranslated_chapters]
            batch_text = '\n'.join([f"{i+1}. {title}" for i, title in enumerate(titles_to_translate)])
            
            try:
                translated_batch = translate_text(
                    f"Translate these chapter titles from Korean to English (keep the numbering):\n{batch_text}",
                    provider, api_key, selected_model, {}
                )
                
                translated_lines = translated_batch.strip().split('\n')
                translated_titles = []
                for line in translated_lines:
                    cleaned = line.strip()
                    if '. ' in cleaned:
                        cleaned = cleaned.split('. ', 1)[1]
                    elif ') ' in cleaned:
                        cleaned = cleaned.split(') ', 1)[1]
                    translated_titles.append(cleaned)
                
                count = 0
                for i, ch in enumerate(untranslated_chapters):
                    if i < len(translated_titles):
                        ch.translated_title = translated_titles[i]
                        count += 1
                
                session.flush()
                
                return jsonify({
                    'success': True,
                    'message': f'Translated {count} chapter titles',
                    'translated_count': count
                })
                
            except Exception as e:
                return jsonify({'error': f'Translation failed: {str(e)}'}), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/resort-chapters', methods=['POST'])
def resort_chapters():

    try:
        from database.database import db_session_scope
        from database.db_models import Novel, Chapter
        
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
            
        data = request.get_json()
        novel_slug = data.get('novel_id')
        
        with db_session_scope() as session:
            novel = session.query(Novel).filter_by(slug=novel_slug).first()
            if not novel:
                return jsonify({'success': False, 'error': 'Novel not found'})
            
            chapters = session.query(Chapter).filter_by(novel_id=novel.id).all()
            
            def get_episode_no(ch):
                try:
                    if ch.source_url and '/viewer/' in ch.source_url:
                        return int(ch.source_url.split('/viewer/')[-1])
                    return 999999999            
                except (ValueError, AttributeError):
                    return 999999999
            
            sorted_chapters = sorted(chapters, key=get_episode_no)
            
            for idx, ch in enumerate(sorted_chapters):
                if ch.position != idx:
                    ch.position = idx
            
            return jsonify({'success': True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    

@api_bp.route('/find-chapter/<novel_slug>/<chapter_number>', methods=['GET'])
def find_chapter_by_number(novel_slug, chapter_number):

    try:
        from urllib.parse import unquote
        from database.db_novel import extract_episode_id_from_url
        from database.database import db_session_scope
        from database.db_models import Novel, Chapter
        from sqlalchemy import and_
        
        user_id = get_user_id()
        novel_slug = unquote(novel_slug)
        
        with db_session_scope() as session:
            novel = session.query(Novel).filter(
                and_(Novel.user_id == user_id, Novel.slug == novel_slug)
            ).first()
            
            if not novel:
                return jsonify({'error': 'Novel not found'}), 404
            
            chapters = session.query(Chapter).filter(
                and_(Chapter.novel_id == novel.id, Chapter.chapter_number == str(chapter_number))
            ).all()
            
            results = []
            for ch in chapters:
                episode_id = extract_episode_id_from_url(ch.source_url)
                results.append({
                    'id': ch.id,
                    'position': ch.position,
                    'chapter_number': ch.chapter_number,
                    'episode_id': episode_id,
                    'source_url': ch.source_url,
                    'title': ch.title
                })
            
            return jsonify({
                'found': len(results),
                'chapters': results
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/test-repair', methods=['GET'])
def test_repair():

    return jsonify({'status': 'repair endpoint exists', 'test': 'ok'})
    try:
        from urllib.parse import unquote
        from database.db_novel import extract_episode_id_from_url
        from database.database import db_session_scope
        from database.db_models import Novel, Chapter
        from sqlalchemy import and_
        
        user_id = get_user_id()
        novel_slug = unquote(novel_slug)
        
        with db_session_scope() as session:
            novel = session.query(Novel).filter(
                and_(Novel.user_id == user_id, Novel.slug == novel_slug)
            ).first()
            
            if not novel:
                return jsonify({'error': 'Novel not found'}), 404
            
            chapters = session.query(Chapter).filter_by(novel_id=novel.id).all()
            
            chapters_with_episodes = []
            for ch in chapters:
                episode_id = extract_episode_id_from_url(ch.source_url)
                if episode_id:
                    chapters_with_episodes.append((episode_id, ch))
                else:
                    chapters_with_episodes.append((999999999, ch))
            
            chapters_with_episodes.sort(key=lambda x: x[0])
            
            updates = []
            for new_pos, (ep_id, ch) in enumerate(chapters_with_episodes):
                old_pos = ch.position
                if old_pos != new_pos:
                    ch.position = new_pos
                    updates.append(f"Ch#{ch.chapter_number} (Ep {ep_id}): {old_pos} → {new_pos}")
            
            session.flush()
            
            return jsonify({
                'success': True,
                'message': f'Repaired {len(updates)} chapter positions',
                'total_chapters': len(chapters_with_episodes),
                'changes': updates[:50]                         
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/translate-chapter-title', methods=['POST'])
def translate_chapter_title():

    try:
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
            
        data = request.json
        novel_id = data.get('novel_id')
        chapter_index = data.get('chapter_index')
        
        if not novel_id or chapter_index is None:
            return jsonify({'error': 'Missing novel_id or chapter_index'}), 400
        
        from database.db_novel import get_novel_with_chapters_db
        from models.settings import load_settings
        from models.novel import sort_chapters_by_number
        
        novel = get_novel_with_chapters_db(user_id, novel_id)
        if not novel or not novel.get('chapters'):
            return jsonify({'error': 'Novel not found'}), 404
        
        settings = load_settings(user_id)
        if 'sort_order_override' in novel and novel['sort_order_override'] is not None:
            order = novel['sort_order_override']
        else:
            order = settings.get('default_sort_order', 'asc')
        
        sorted_chapters = sort_chapters_by_number(novel['chapters'], order)
        
        try:
            chapter_index = int(chapter_index)
        except ValueError:
            return jsonify({'error': 'Invalid chapter_index'}), 400
        
        if chapter_index >= len(sorted_chapters):
            return jsonify({'error': 'Chapter index out of range'}), 404
        
        chapter = sorted_chapters[chapter_index]
        chapter_id = chapter.get('id')
        
        if not chapter_id:
            return jsonify({'error': 'Chapter ID not found'}), 404
        
        from tasks.translation_tasks import translate_chapter_title_task
        task = translate_chapter_title_task.delay(
            user_id=user_id,
            novel_id=novel_id,
            chapter_id=chapter_id
        )
        
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'Title translation queued'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/contact', methods=['POST'])
def contact_form():

    try:
        data = request.json
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        subject = data.get('subject', '').strip()
        message = data.get('message', '').strip()
        
        if not name or not email or not subject or not message:
            return jsonify({'success': False, 'error': 'All fields are required'}), 400
        
        if '@' not in email or '.' not in email:
            return jsonify({'success': False, 'error': 'Invalid email address'}), 400
        
        from database.database import db_session_scope
        from database.db_models import ContactMessage
        from datetime import datetime
        
        with db_session_scope() as session:
            contact_message = ContactMessage(
                name=name,
                email=email,
                subject=subject,
                message=message,
                created_at=datetime.utcnow()
            )
            session.add(contact_message)
            session.flush()
        
        """
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_user = os.getenv('SMTP_USER')
        smtp_pass = os.getenv('SMTP_PASSWORD')
        recipient = os.getenv('CONTACT_EMAIL', 'support@lunafrost.com')
        
        if smtp_user and smtp_pass:
            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = recipient
            msg['Subject'] = f"Contact Form: {subject}"
            
            body = f'''
            New contact form submission:
            
            Name: {name}
            Email: {email}
            Subject: {subject}
            
            Message:
            {message}
            '''
            
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        """
        
        return jsonify({
            'success': True, 
            'message': 'Thank you for your message! We\'ll get back to you soon.'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': 'An error occurred. Please try again later.'}), 500

@api_bp.route('/epub/analyze', methods=['POST'])
def analyze_epub():

    try:
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401

        if 'epub_file' not in request.files:
            return jsonify({'error': 'No EPUB file provided'}), 400

        epub_file = request.files['epub_file']
        if not epub_file.filename.endswith('.epub'):
            return jsonify({'error': 'Invalid file type. Please upload an EPUB file.'}), 400

                                                                                    
        import tempfile
        import uuid

                                        
        temp_dir = tempfile.gettempdir()
        temp_filename = f"epub_{user_id}_{uuid.uuid4().hex}.epub"
        tmp_path = os.path.join(temp_dir, temp_filename)

                       
        epub_file.save(tmp_path)

        try:
                        
            from services.epub_service import parse_epub, find_duplicate_chapters
            result = parse_epub(tmp_path)

            if not result.get('success'):
                return jsonify({'error': result.get('error', 'Failed to parse EPUB')}), 400

                                                      
            from models.user import get_user_info
            user = get_user_info(user_id)
            username = user.get('username', user_id) if user else user_id

                                               
            title = result['title']
            novel_slug = f"{title}_{username}".lower().replace(' ', '-')
            novel_slug = re.sub(r'[^a-z0-9가-힣_-]', '', novel_slug)

                                           
            novels = load_novels(user_id)
            existing_novel = novels.get(novel_slug)

            new_chapters = result['chapters']
            duplicate_chapters = []

            if existing_novel:
                                 
                new_chapters, duplicate_chapters = find_duplicate_chapters(
                    result['chapters'],
                    existing_novel.get('chapters', [])
                )

            result['new_chapters'] = new_chapters
            result['duplicate_chapters'] = duplicate_chapters
            result['novel_slug'] = novel_slug
            result['novel_exists'] = existing_novel is not None

                                                                                              
                                                              
            import tempfile
            saved_epub_path = os.path.join(tempfile.gettempdir(), f"epub_{user_id}_{novel_slug}.epub")
            import shutil
            shutil.copy(tmp_path, saved_epub_path)
            result['epub_temp_file'] = saved_epub_path

                                            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"EPUB Analysis complete: {len(result['chapters'])} chapters found")
            for i, ch in enumerate(result['chapters'][:5]):                        
                logger.info(f"  Chapter {i}: number={ch.get('number')}, title='{ch.get('title')}'")

            return jsonify(result)

        finally:
                                
            try:
                os.unlink(tmp_path)
            except:
                pass

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/epub/import', methods=['POST'])
def import_epub():

    import os
    import re
    import time
    import uuid

    try:
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401

        data = request.get_json()
        title = data.get('title', '').strip()
        author = data.get('author', '').strip()
        synopsis = data.get('synopsis', '').strip()
        tags = data.get('tags', [])
        chapters = data.get('chapters', [])
        epub_temp_file = data.get('epub_temp_file')

        if not title:
            return jsonify({'error': 'Title is required'}), 400

        if not chapters:
            return jsonify({'error': 'No chapters to import'}), 400

                                         
        epub_book = None
        if epub_temp_file and os.path.exists(epub_temp_file):
            try:
                from ebooklib import epub
                epub_book = epub.read_epub(epub_temp_file)
            except Exception as e:
                logger.warning(f"Failed to re-parse EPUB for images: {e}")
                                         

                               
        from models.user import get_user_info
        user = get_user_info(user_id)
        username = user.get('username', user_id) if user else user_id

                                           
        novel_slug = f"{title}_{username}".lower().replace(' ', '-')
        novel_slug = re.sub(r'[^a-z0-9가-힣_-]', '', novel_slug)

                              
        from database.db_novel import get_novel_with_chapters_db, create_novel_db
        from database.db_models import Novel, Chapter
        from database.database import db_session_scope

        with db_session_scope() as session:
                                   
            novel_db = session.query(Novel).filter(
                Novel.slug == novel_slug,
                Novel.user_id == user_id
            ).first()

            if novel_db:
                                          
                novel_id = novel_db.id
            else:
                                  
                new_novel = Novel(
                    user_id=user_id,
                    slug=novel_slug,
                    title=title,
                    original_title=title,
                    author=author,
                    translated_author=author,
                    synopsis=synopsis,
                    translated_synopsis=synopsis,
                    tags=tags if tags else [],
                    glossary={}
                )
                session.add(new_novel)
                session.flush()
                novel_id = new_novel.id

                                                          
            existing_chapters = session.query(Chapter).filter(
                Chapter.novel_id == novel_id
            ).all()

                                                      
            existing_chapter_numbers = {str(ch.chapter_number) for ch in existing_chapters}

                                       
            max_position = max([ch.position for ch in existing_chapters], default=0)

                             
            chapters_imported = 0
            for idx, chapter_data in enumerate(chapters):
                ch_number = str(chapter_data['number'])
                ch_title = chapter_data['title']
                ch_content = chapter_data['content']
                epub_item_name = chapter_data.get('epub_item_name')

                                                       
                ch_images = []
                if epub_book and epub_item_name:
                    try:
                        from services.epub_service import extract_images_from_html
                        import ebooklib
                        import sys

                        print(f"[EPUB] Processing chapter {ch_number}, looking for EPUB item: {epub_item_name}", file=sys.stderr, flush=True)

                                                                
                        for item in epub_book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                            if item.get_name() == epub_item_name:
                                content_html = item.get_content().decode('utf-8', errors='ignore')
                                print(f"[EPUB] Extracting images from chapter {ch_number}", file=sys.stderr, flush=True)
                                ch_images = extract_images_from_html(content_html, epub_book)
                                print(f"[EPUB] Found {len(ch_images)} images for chapter {ch_number}", file=sys.stderr, flush=True)
                                break
                        else:
                            print(f"[EPUB] WARNING: Could not find EPUB item: {epub_item_name}", file=sys.stderr, flush=True)

                    except Exception as e:
                        print(f"[EPUB] ERROR: Failed to extract images for chapter {ch_number}: {e}", file=sys.stderr, flush=True)
                        import traceback
                        traceback.print_exc()

                                                                       
                exists = session.query(Chapter).filter(
                    Chapter.novel_id == novel_id,
                    Chapter.chapter_number == ch_number,
                    Chapter.title == ch_title
                ).first()

                if exists:
                                    
                    continue

                                                            
                try:
                    position = int(ch_number)
                except ValueError:
                                                                                  
                    max_position += 1
                    position = max_position

                                                                               
                timestamp = int(time.time() * 1000)                         
                chapter_slug = f"{novel_slug}-ch{ch_number}-{timestamp}".lower().replace(' ', '-')
                chapter_slug = re.sub(r'[^a-z0-9가-힣_-]', '', chapter_slug)

                                                 
                image_urls = []
                if ch_images:
                    from services.image_service import get_user_images_dir
                    import sys

                    user_images_dir = get_user_images_dir(user_id)
                    os.makedirs(user_images_dir, exist_ok=True)
                    print(f"[EPUB] Saving {len(ch_images)} images to {user_images_dir}", file=sys.stderr, flush=True)

                    for img_data in ch_images:
                        try:
                                                      
                            ext = img_data.get('media_type', 'image/jpeg').split('/')[-1]
                            img_filename = f"{uuid.uuid4().hex}.{ext}"
                            img_path = os.path.join(user_images_dir, img_filename)

                                             
                            with open(img_path, 'wb') as f:
                                f.write(img_data['data'])

                            print(f"[EPUB] Saved image: {img_filename} ({len(img_data['data'])} bytes)", file=sys.stderr, flush=True)
                            image_urls.append(img_filename)
                        except Exception as e:
                            print(f"[EPUB] ERROR: Failed to save image: {e}", file=sys.stderr, flush=True)
                            import traceback
                            traceback.print_exc()

                    print(f"[EPUB] Successfully saved {len(image_urls)} images for chapter {ch_number}", file=sys.stderr, flush=True)

                new_chapter = Chapter(
                    novel_id=novel_id,
                    slug=chapter_slug,
                    title=ch_title,
                    original_title=ch_title,
                    chapter_number=ch_number,
                    content=ch_content,
                    position=position,
                    is_bonus=False,
                    images=image_urls if image_urls else None
                )
                session.add(new_chapter)
                chapters_imported += 1

            session.commit()

                                 
        if epub_temp_file and os.path.exists(epub_temp_file):
            try:
                os.unlink(epub_temp_file)
            except:
                pass

        return jsonify({
            'success': True,
            'novel_slug': novel_slug,
            'chapters_imported': chapters_imported
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500