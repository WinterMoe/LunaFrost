

import re
import time
import hashlib
from database.db_novel import (
    create_novel_db, get_novel_db, find_novel_by_source_url_db, 
    find_novel_by_title_db, add_chapter_atomic, update_novel_db
)
from models.settings import load_settings
from services.image_service import download_image, extract_images_from_content

def process_chapter_import(user_id, chapter_data, skip_translation=False):

    original_title = chapter_data.get('original_title', '')
    chapter_title = chapter_data.get('chapter_title', '')
    content = chapter_data.get('content', '')
    source_url = chapter_data.get('source_url', '')
    novel_source_url = chapter_data.get('novel_source_url', source_url)
    if not source_url:
        source_url = novel_source_url
    images_from_extension = chapter_data.get('images', [])
    
    
    is_novel_page = False
    url_for_detection = source_url or novel_source_url or ''
    if url_for_detection:
        if '/viewer/' in url_for_detection:
            is_novel_page = False
        elif '/novel/' in url_for_detection:
            is_novel_page = True
    
    
    if is_novel_page or (not content and not chapter_data.get('chapter_number')):
        
        novel_data = find_novel_by_title_db(user_id, original_title)
        if not novel_data:
            novel_data = find_novel_by_source_url_db(user_id, novel_source_url)
        
        novel_id = novel_data['slug'] if novel_data else None
        
        if novel_id:
            update_data = {}
            
            cover_url = chapter_data.get('cover_url', '')
            if cover_url:
                cover_image_path = download_image(cover_url, user_id, overwrite=True)
                if cover_image_path:
                    update_data['cover_url'] = cover_image_path
            
            from services.ai_service import translate_text
            settings = load_settings(user_id)
            provider = settings.get('selected_provider', 'openrouter')
            api_key = settings.get('api_keys', {}).get(provider, '')
            selected_model = settings.get('provider_models', {}).get(provider, '')
            
            
            import re
            has_korean = lambda text: bool(re.search(r'[\uac00-\ud7a3]', text)) if text else False
            
            if api_key and original_title:
                try:
                    translated_title = translate_text(original_title, provider, api_key, selected_model, {})
                    if isinstance(translated_title, dict):
                        translated_title = translated_title.get('translated_text', original_title)
                    update_data['translated_title'] = translated_title
                except Exception as e:
                    update_data['translated_title'] = original_title
            
            author = chapter_data.get('author', '')
            if author:
                update_data['author'] = author
                if api_key:
                    try:
                        translated_author = translate_text(author, provider, api_key, selected_model, {})
                        if isinstance(translated_author, dict):
                            translated_author = translated_author.get('translated_text', author)
                        update_data['translated_author'] = translated_author
                    except Exception as e:
                        update_data['translated_author'] = author
            
            tags = chapter_data.get('tags', [])
            if tags:
                update_data['tags'] = tags
                if api_key:
                    try:
                        tags_text = ', '.join(tags)
                        translated_tags_result = translate_text(tags_text, provider, api_key, selected_model, {})
                        if isinstance(translated_tags_result, dict):
                            translated_tags_result = translated_tags_result.get('translated_text', tags_text)
                        translated_tags = [tag.strip() for tag in translated_tags_result.split(',')]
                        update_data['translated_tags'] = translated_tags
                    except Exception as e:
                        update_data['translated_tags'] = tags
            
            synopsis = chapter_data.get('synopsis', '')
            if synopsis:
                update_data['synopsis'] = synopsis
                if api_key:
                    try:
                        translated_synopsis = translate_text(synopsis, provider, api_key, selected_model, {})
                        if isinstance(translated_synopsis, dict):
                            translated_synopsis = translated_synopsis.get('translated_text', synopsis)
                        update_data['translated_synopsis'] = translated_synopsis
                    except Exception as e:
                        update_data['translated_synopsis'] = synopsis
            
            if update_data:
                update_novel_db(user_id, novel_id, update_data)
            else:
                pass                         
        else:
                                                  
            from services.settings_service import can_user_import_novel
            can_import, error_msg, current_count, limit = can_user_import_novel(user_id)
            
            if not can_import:
                return {
                    'success': False,
                    'error': error_msg,
                    'error_code': 'NOVEL_LIMIT_REACHED',
                    'current_count': current_count,
                    'limit': limit
                }
            
            novel_id = create_novel_from_data(user_id, chapter_data, skip_translation)
        
        return {
            'success': True, 
            'message': 'Novel metadata captured from overview page', 
            'novel_id': novel_id,
            'is_overview': True
        }
    
    if not content:
        return {'success': False, 'error': 'No content provided'}
    
    novel_data = find_novel_by_title_db(user_id, original_title)
    
    if not novel_data:
        novel_data = find_novel_by_source_url_db(user_id, novel_source_url)
    
    novel_id = novel_data['slug'] if novel_data else None
    
    if novel_id and not is_novel_page:
        update_data = {}

        cover_url = chapter_data.get('cover_url', '')
        if cover_url:
            cover_image_path = download_image(cover_url, user_id, overwrite=True)
            if cover_image_path:
                update_data['cover_url'] = cover_image_path
        
        if chapter_data.get('translated_title'):
            update_data['translated_title'] = chapter_data.get('translated_title')
        if chapter_data.get('author'):
            update_data['author'] = chapter_data.get('author')
        if chapter_data.get('translated_author'):
            update_data['translated_author'] = chapter_data.get('translated_author')
        if chapter_data.get('tags'):
            update_data['tags'] = chapter_data.get('tags')
        if chapter_data.get('translated_tags'):
            update_data['translated_tags'] = chapter_data.get('translated_tags')
        if chapter_data.get('synopsis'):
            update_data['synopsis'] = chapter_data.get('synopsis')
        if chapter_data.get('translated_synopsis'):
            update_data['translated_synopsis'] = chapter_data.get('translated_synopsis')
            
        if update_data:
            update_novel_db(user_id, novel_id, update_data)
    
    images = []
    for img_data in images_from_extension:
        img_url = img_data.get('url', '')
        if img_url:
            local_filename = download_image(img_url, user_id)
            if local_filename:
                images.append({
                    'url': img_url,
                    'local_path': local_filename,
                    'alt': img_data.get('alt', 'Chapter Image')
                })
    
    content_images = extract_images_from_content(content, user_id)
    existing_urls = {img['url'] for img in images}
    for content_img in content_images:
        if content_img['url'] not in existing_urls:
            images.append(content_img)
    
    if not novel_id:
                                              
        from services.settings_service import can_user_import_novel
        can_import, error_msg, current_count, limit = can_user_import_novel(user_id)
        
        if not can_import:
            return {
                'success': False,
                'error': error_msg,
                'error_code': 'NOVEL_LIMIT_REACHED',
                'current_count': current_count,
                'limit': limit
            }
        
        novel_id = create_novel_from_data(user_id, chapter_data, skip_translation)
    
    result = add_chapter_to_novel(
        user_id=user_id,
        novel_id=novel_id,
        chapter_data=chapter_data,
        images=images,
        skip_translation=skip_translation
    )
    
    return result

def create_novel_from_data(user_id, chapter_data, skip_translation=False):

    from services.ai_service import translate_text

    original_title = chapter_data.get('original_title', '')
    novel_source_url = chapter_data.get('novel_source_url', '')

    base_slug = slugify_english(original_title)
    if not base_slug:
        base_slug = f"novel_{hashlib.md5(original_title.encode()).hexdigest()[:8]}"

    slug = f"{base_slug}_{user_id}"
    
    if skip_translation or chapter_data.get('translated_title'):
        novel_translated_title = chapter_data.get('translated_title', original_title)
        translated_author = chapter_data.get('translated_author', chapter_data.get('author', ''))
        translated_synopsis = chapter_data.get('translated_synopsis', chapter_data.get('synopsis', ''))
    else:
        settings = load_settings(user_id)
        provider = settings.get('selected_provider', 'openrouter')
        api_key = settings.get('api_keys', {}).get(provider, '')
        selected_model = settings.get('provider_models', {}).get(provider, '')
        
        try:
            novel_translated_title_result = translate_text(
                original_title, provider, api_key, selected_model, {}
            )
            if isinstance(novel_translated_title_result, dict):
                novel_translated_title = novel_translated_title_result.get('translated_text', original_title)
            else:
                novel_translated_title = novel_translated_title_result
        except:
            novel_translated_title = original_title
        
        translated_author = chapter_data.get('author', '')
        translated_synopsis = chapter_data.get('synopsis', '')
    
    cover_image_path = ''
    cover_url = chapter_data.get('cover_url', '')
    if cover_url:
        cover_image_path = download_image(cover_url, user_id, overwrite=True)
    
    novel_data = {
        'slug': slug,
        'title': original_title,
        'original_title': original_title,
        'translated_title': novel_translated_title,
        'author': chapter_data.get('author', ''),
        'translated_author': translated_author,
        'tags': chapter_data.get('tags', []),
        'translated_tags': chapter_data.get('translated_tags', chapter_data.get('tags', [])),
        'synopsis': chapter_data.get('synopsis', ''),
        'translated_synopsis': translated_synopsis,
        'cover_url': cover_image_path,
        'source_url': novel_source_url,
        'glossary': {}
    }
    
    create_novel_db(user_id, novel_data)
    return slug

def add_chapter_to_novel(user_id, novel_id, chapter_data, images, skip_translation=False):

    
    chapter_data['images'] = images
    
    if 'chapter_title' in chapter_data and chapter_data.get('chapter_title'):
        chapter_data['title'] = chapter_data['chapter_title']
        chapter_data['original_title'] = chapter_data['chapter_title']
    
    if 'translated_chapter_title' in chapter_data and chapter_data.get('translated_chapter_title'):
        chapter_data['translated_title'] = chapter_data['translated_chapter_title']
    elif 'chapter_title' in chapter_data and chapter_data.get('chapter_title'):
        chapter_data['translated_title'] = chapter_data['chapter_title']
    
    if 'slug' not in chapter_data:
        chapter_num = chapter_data.get('chapter_number', '0')
        chapter_data['slug'] = f"{novel_id}_ch{chapter_num}_{int(time.time())}"
    
    result = add_chapter_atomic(user_id, novel_id, chapter_data)
    
    return result

def slugify_english(text):

    if not text:
        return 'unknown_novel'
    
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    text = text.strip('-')
    
    return text or 'unknown_novel'

def process_batch_chapter_import(user_id, chapters_data):

    from services.image_service import download_images_parallel
    
    results = []
    successful = 0
    failed = 0
    
    for idx, chapter_data in enumerate(chapters_data):
        try:
            original_title = chapter_data.get('original_title', '')
            source_url = chapter_data.get('source_url', '')
            novel_source_url = chapter_data.get('novel_source_url', source_url)
            images_from_extension = chapter_data.get('images', [])
            content = chapter_data.get('content', '')
            skip_translation = chapter_data.get('skip_translation', False)
            
            
            novel_data = find_novel_by_title_db(user_id, original_title)
            if not novel_data:
                novel_data = find_novel_by_source_url_db(user_id, novel_source_url)
            
            novel_id = novel_data['slug'] if novel_data else None
            
            if novel_id:
                update_data = {}
                
                cover_url = chapter_data.get('cover_url', '')
                if cover_url:
                    cover_image_path = download_image(cover_url, user_id, overwrite=True)
                    if cover_image_path:
                        update_data['cover_url'] = cover_image_path
                
                if chapter_data.get('translated_title'):
                    update_data['translated_title'] = chapter_data.get('translated_title')
                if chapter_data.get('author'):
                    update_data['author'] = chapter_data.get('author')
                if chapter_data.get('translated_author'):
                    update_data['translated_author'] = chapter_data.get('translated_author')
                if chapter_data.get('tags'):
                    update_data['tags'] = chapter_data.get('tags')
                if chapter_data.get('translated_tags'):
                    update_data['translated_tags'] = chapter_data.get('translated_tags')
                if chapter_data.get('synopsis'):
                    update_data['synopsis'] = chapter_data.get('synopsis')
                if chapter_data.get('translated_synopsis'):
                    update_data['translated_synopsis'] = chapter_data.get('translated_synopsis')
                    
                if update_data:
                    update_novel_db(user_id, novel_id, update_data)
            
            images = []
            if images_from_extension:
                images = download_images_parallel(images_from_extension, user_id)
            
            content_images = extract_images_from_content(content, user_id)
            existing_urls = {img['url'] for img in images}
            for content_img in content_images:
                if content_img['url'] not in existing_urls:
                    images.append(content_img)
            
            if not novel_id:
                                                      
                from services.settings_service import can_user_import_novel
                can_import, error_msg, current_count, limit = can_user_import_novel(user_id)
                
                if not can_import:
                    raise Exception(error_msg)
                
                novel_id = create_novel_from_data(user_id, chapter_data, skip_translation)
            
            result = add_chapter_to_novel(
                user_id=user_id,
                novel_id=novel_id,
                chapter_data=chapter_data,
                images=images,
                skip_translation=skip_translation
            )
            
            if result.get('success'):
                results.append({
                    'index': idx,
                    'success': True,
                    'data': {
                        'novel_id': novel_id,
                        'chapter_index': result.get('chapter_index')
                    },
                    'chapter_title': chapter_data.get('chapter_title', 'Unknown'),
                    'already_exists': result.get('already_exists', False)
                })
                successful += 1
            else:
                raise Exception(result.get('error', 'Unknown error'))
            
        except Exception as e:
            results.append({
                'index': idx,
                'success': False,
                'error': str(e),
                'chapter_title': chapter_data.get('chapter_title', 'Unknown')
            })
            failed += 1
    
    return {
        'success': True,
        'total': len(chapters_data),
        'successful': successful,
        'failed': failed,
        'results': results
    }
