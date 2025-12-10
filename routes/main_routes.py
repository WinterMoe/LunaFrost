from flask import Blueprint, render_template, request, send_file, redirect, url_for, session
from models.novel import load_novels, get_display_title, sort_chapters_by_number
from models.settings import load_settings
import os
import mimetypes

main_bp = Blueprint('main', __name__)

def get_user_id():

    return session.get('user_id')

def get_user_images_dir():

    from models.image_service import get_user_images_dir
    return get_user_images_dir(get_user_id())

DATA_DIR = 'data'

@main_bp.route('/shared/<token>')
def view_shared_novel(token):
    from database.database import db_session_scope
    from database.db_models import Novel, Chapter
    
    with db_session_scope() as session:
        novel = session.query(Novel).filter(
            Novel.share_token == token,
            Novel.is_shared == True
        ).first()
        
        if not novel:
            return render_template('404.html'), 404
            
        chapters = session.query(Chapter).filter(
            Chapter.novel_id == novel.id
        ).order_by(Chapter.position).all()
        
                                   
        novel_data = {
            'title': novel.translated_title or novel.title,
            'author': novel.translated_author or novel.author,
            'synopsis': novel.translated_synopsis or novel.synopsis,
            'cover_url': novel.cover_url,
            'tags': novel.translated_tags or novel.tags,
            'chapters': chapters,
            'glossary': novel.glossary or {}                                 
        }
        
        return render_template('shared_novel.html', novel=novel_data, token=token)

@main_bp.route('/shared/<token>/read/<chapter_number>')
def view_shared_chapter(token, chapter_number):
    from database.database import db_session_scope
    from database.db_models import Novel, Chapter
    
    with db_session_scope() as session:
        novel = session.query(Novel).filter(
            Novel.share_token == token,
            Novel.is_shared == True
        ).first()
        
        if not novel:
            return render_template('404.html'), 404
            
        chapter = session.query(Chapter).filter(
            Chapter.novel_id == novel.id,
            Chapter.chapter_number == str(chapter_number)
        ).first()
        
        if not chapter:
            return render_template('404.html'), 404
            
                                
        prev_chapter = session.query(Chapter).filter(
            Chapter.novel_id == novel.id,
            Chapter.position < chapter.position
        ).order_by(Chapter.position.desc()).first()
        
        next_chapter = session.query(Chapter).filter(
            Chapter.novel_id == novel.id,
            Chapter.position > chapter.position
        ).order_by(Chapter.position.asc()).first()
            
        chapter_data = {
            'title': chapter.translated_title or chapter.title,
            'content': chapter.translated_content or chapter.content,
            'chapter_number': chapter.chapter_number
        }
        
        novel_data = {
            'title': novel.translated_title or novel.title,
            'glossary': novel.glossary or {}                                        
        }
        
        return render_template(
            'shared_chapter.html', 
            novel=novel_data, 
            chapter=chapter_data, 
            token=token,
            prev_chapter=prev_chapter.chapter_number if prev_chapter else None,
            next_chapter=next_chapter.chapter_number if next_chapter else None,
            glossary=novel.glossary or {}
        )

def count_regular_chapters(chapters):
                                                 
    if not chapters:
        return 0
    count = 0
    for ch in chapters:
        if not ch:
            continue
        is_bonus = ch.get('is_bonus', False)
        chapter_num = str(ch.get('chapter_number', '')).upper()
        if not is_bonus and chapter_num != 'BONUS':
            count += 1
    return count

def count_bonus_chapters(chapters):
                                   
    if not chapters:
        return 0
    count = 0
    for ch in chapters:
        if not ch:
            continue
        is_bonus = ch.get('is_bonus', False)
        chapter_num = str(ch.get('chapter_number', '')).upper()
        if is_bonus or chapter_num == 'BONUS':
            count += 1
    return count

def load_webtoons(user_id):
                                                                     
    if not user_id:
        return {}
    
    try:
        from database.database import db_session_scope
        from database.db_models import WebtoonJob, WebtoonImage
        from services.image_service import get_user_images_dir
        import os
        
        webtoons_dict = {}
        
        with db_session_scope() as session_db:
                                                                                     
            jobs = session_db.query(WebtoonJob).filter_by(
                user_id=user_id
            ).order_by(WebtoonJob.created_at.desc()).all()
            
            for job in jobs:
                                                  
                if job.status == 'draft' and not job.title:
                    continue
                
                                       
                cover_image = None
                
                                                      
                if job.cover_image_id:
                    cover_img = session_db.query(WebtoonImage).filter_by(
                        id=job.cover_image_id,
                        job_id=job.job_id
                    ).first()
                    if cover_img:
                                                                      
                        cover_image = cover_img.translated_path or cover_img.original_path
                
                                                  
                if not cover_image:
                    first_image = session_db.query(WebtoonImage).filter_by(
                        job_id=job.job_id
                    ).order_by(WebtoonImage.chapter_number, WebtoonImage.page_order).first()
                    
                    if first_image:
                        cover_image = first_image.translated_path or first_image.original_path
                
                                                 
                images = session_db.query(WebtoonImage).filter_by(
                    job_id=job.job_id
                ).order_by(WebtoonImage.chapter_number, WebtoonImage.page_order).all()
                
                                               
                chapters = []
                current_chapter = None
                chapter_images = []
                
                for img in images:
                    if current_chapter != img.chapter_number:
                                                         
                        if chapter_images:
                            chapters.append({
                                'chapter_number': str(current_chapter),
                                'title': chapter_images[0].get('chapter_name') or f"Chapter {current_chapter}",
                                'images': chapter_images,
                                'is_webtoon': True
                            })
                        current_chapter = img.chapter_number
                        chapter_images = []
                    
                    chapter_images.append({
                        'id': img.id,
                        'page_order': img.page_order,
                        'chapter_name': img.chapter_name,
                        'original_filename': img.original_filename,
                        'original_path': img.original_path,
                        'translated_path': img.translated_path,
                        'status': img.status
                    })
                
                                               
                if chapter_images:
                    chapters.append({
                        'chapter_number': str(current_chapter),
                        'title': chapter_images[0].get('chapter_name') or f"Chapter {current_chapter}",
                        'images': chapter_images,
                        'is_webtoon': True
                    })
                
                            
                tags_list = []
                if job.tags:
                    tags_list = [t.strip() for t in job.tags.split(',') if t.strip()]
                
                                                       
                if job.reading_mode == 'manga' and 'manga' not in [t.lower() for t in tags_list]:
                    tags_list.insert(0, 'manga')
                elif job.reading_mode == 'webtoon' and 'webtoon' not in [t.lower() for t in tags_list]:
                    tags_list.insert(0, 'webtoon')
                
                                      
                display_title = job.title or f"Untitled {job.reading_mode.title()}"
                webtoon_slug = f"webtoon_{job.job_id}"
                
                webtoons_dict[webtoon_slug] = {
                    'slug': webtoon_slug,
                    'title': display_title,
                    'original_title': display_title,
                    'translated_title': display_title,
                    'author': job.author,
                    'synopsis': job.synopsis,
                    'cover_image': cover_image,
                    'cover_url': cover_image,
                    'tags': tags_list,
                    'translated_tags': tags_list,
                    'chapters': chapters,
                    'chapter_count': len(chapters),
                    'is_webtoon': True,
                    'reading_mode': job.reading_mode or 'manga',
                    'job_id': job.job_id,
                    'status': job.status,
                    'total_images': job.total_images or 0,
                    'processed_images': job.processed_images or 0,
                    'source_language': job.source_language,
                    'created_at': job.created_at.isoformat() if job.created_at else None
                }
        
        return webtoons_dict
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {}

@main_bp.route('/')
def index():

    user_id = get_user_id()
    novels = load_novels(user_id)
    webtoons = load_webtoons(user_id)
    settings = load_settings(user_id)
    
                                    
    has_webtoons = len(webtoons) > 0
    
    return render_template(
        'index.html', 
        novels=novels, 
        webtoons=webtoons,
        has_webtoons=has_webtoons,
        settings=settings, 
        get_display_title=get_display_title, 
        count_regular_chapters=count_regular_chapters
    )

@main_bp.route('/novel/<novel_id>')
def view_novel(novel_id):

    user_id = get_user_id()
    novels = load_novels(user_id)
    novel = novels.get(novel_id)
    
    if not novel:
        return "Novel not found", 404
    
    settings = load_settings(user_id)
    
    has_positions = any(ch and 'position' in ch and ch['position'] is not None for ch in novel.get('chapters', []))
    
    if has_positions:
        order = novel.get('sort_order_override') or settings.get('default_sort_order', 'asc')
    else:
        order = novel.get('sort_order_override') or settings.get('default_sort_order', 'asc')
    
    novel['sort_order'] = order
    novel['chapters'] = sort_chapters_by_number(novel['chapters'], order)
    
    return render_template('novel.html', novel=novel, novel_id=novel_id, get_display_title=get_display_title, count_regular_chapters=count_regular_chapters, count_bonus_chapters=count_bonus_chapters)

@main_bp.route('/chapter/<novel_id>/<int:chapter_index>')
def view_chapter(novel_id, chapter_index):

    user_id = get_user_id()
    novels = load_novels(user_id)
    novel = novels.get(novel_id)
    
    if not novel or chapter_index >= len(novel.get('chapters', [])):
        return "Chapter not found", 404
    
    settings = load_settings(user_id)
    
    if 'sort_order_override' in novel and novel['sort_order_override'] is not None:
        order = novel['sort_order_override']
    else:
        order = settings.get('default_sort_order', 'asc')
    
    novel['sort_order'] = order
    novel['chapters'] = sort_chapters_by_number(novel['chapters'], order)
    
    chapter = novel['chapters'][chapter_index]
    
    return render_template(
        'chapter.html',
        novel=novel,
        novel_id=novel_id,
        chapter=chapter,
        chapter_index=chapter_index,
        glossary=novel.get('glossary', {}),
        get_display_title=get_display_title,
        thinking_mode_enabled=settings.get('thinking_mode_enabled', False),
        sort_order=order
    )

@main_bp.route('/token-usage')
def token_usage_dashboard():

    user_id = get_user_id()
    if not user_id:
        return redirect(url_for('auth.login'))
    
    return render_template('token_usage.html')

@main_bp.route('/chapter/<novel_id>/number/<chapter_number>')
def view_chapter_by_number(novel_id, chapter_number):

    user_id = get_user_id()
    novels = load_novels(user_id)
    novel = novels.get(novel_id)
    
    if not novel:
        return "Novel not found", 404
    
    settings = load_settings(user_id)
    
    if 'sort_order_override' in novel and novel['sort_order_override'] is not None:
        order = novel['sort_order_override']
    else:
        order = settings.get('default_sort_order', 'asc')
    
    novel['sort_order'] = order
    novel['chapters'] = sort_chapters_by_number(novel['chapters'], order)
    
    chapter_index = None
    for idx, chapter in enumerate(novel['chapters']):
        if chapter and str(chapter.get('chapter_number')) == str(chapter_number):
            chapter_index = idx
            break
    
    if chapter_index is None:
        return "Chapter not found", 404
    
    target_url = url_for('main.view_chapter', novel_id=novel_id, chapter_index=chapter_index)

    query_string = request.query_string.decode('utf-8') if request.query_string else ''
    if query_string:
        target_url = f"{target_url}?{query_string}"

    return redirect(target_url)

@main_bp.route('/settings')
def settings_page():

    user_id = get_user_id()
    settings = load_settings(user_id)
    return render_template('settings.html', settings=settings)

@main_bp.route('/novel/<novel_id>/settings')
def novel_settings_page(novel_id):
    try:
        user_id = get_user_id()
        novels = load_novels(user_id)
        novel = novels.get(novel_id)
        
                                                                                         
        if not novel:
            from database.db_novel import get_novel_with_chapters_db
            novel_dict = get_novel_with_chapters_db(user_id, novel_id)
            if novel_dict:
                novel = novel_dict
            else:
                return "Novel not found", 404

                                          
        if 'chapters' not in novel:
            novel['chapters'] = []
        if novel['chapters'] is None:
            novel['chapters'] = []
        if 'glossary' not in novel:
            novel['glossary'] = {}

        glossary = novel.get('glossary', {})
                                                                             
        chapter_number = request.args.get('chapter_number', type=str)
        chapter_index_param = request.args.get('chapter', type=int)

        settings = load_settings(user_id)
        if 'sort_order_override' in novel and novel['sort_order_override'] is not None:
            order = novel['sort_order_override']
        else:
            order = settings.get('default_sort_order', 'asc')

        novel['chapters'] = sort_chapters_by_number(novel['chapters'], order)

        chapter = None
        chapter_index = None

        if chapter_number is not None:
            for idx, ch in enumerate(novel['chapters']):
                if ch and str(ch.get('chapter_number')) == str(chapter_number):
                    chapter = ch
                    chapter_index = idx
                    break
                                                                               
        elif chapter_index_param is not None and chapter_index_param < len(novel.get('chapters', [])):
            chapter = novel['chapters'][chapter_index_param]
            chapter_index = chapter_index_param

        show_delete_novel = chapter is None
        
        return render_template(
            'novel_settings.html', 
            novel=novel, 
            novel_id=novel_id, 
            glossary=glossary,
            chapter_index=chapter_index,
            chapter=chapter,
            show_delete_novel=show_delete_novel,
            get_display_title=get_display_title,
            count_regular_chapters=count_regular_chapters,
            count_bonus_chapters=count_bonus_chapters
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Internal Server Error: {str(e)}", 500

@main_bp.route('/images/<path:filename>')
def serve_image(filename):

    user_id = session.get('user_id')
    
    

    if not user_id:
        return "Not authenticated", 401
    
    try:
        from services.image_service import get_user_images_dir
        import os
        
                                                                             
                                                                      
        parts = filename.split('/')
        if len(parts) >= 2 and parts[0] != 'images':
                                          
            image_user_id = parts[0]
            actual_filename = '/'.join(parts[1:])
            images_dir = get_user_images_dir(image_user_id)
            img_path = os.path.join(images_dir, actual_filename)
        elif len(parts) >= 3 and parts[0] == '' and parts[1] == 'images':
                                                  
            image_user_id = parts[2]
            actual_filename = '/'.join(parts[3:])
            images_dir = get_user_images_dir(image_user_id)
            img_path = os.path.join(images_dir, actual_filename)
        else:
                                                                         
            images_dir = get_user_images_dir(user_id)
            img_path = os.path.join(images_dir, filename)
        
        

        abs_img_path = os.path.abspath(img_path)
        abs_images_dir = os.path.abspath(images_dir)
        
        
        if not abs_img_path.startswith(abs_images_dir):
            return "Forbidden", 403
        
        if not os.path.exists(img_path):
            return "Image not found", 404
        
        content_type = mimetypes.guess_type(filename)[0]
        
        if not content_type:
            with open(img_path, 'rb') as f:
                header = f.read(12)
                if header[:8] == b'\x89PNG\r\n\x1a\n':
                    content_type = 'image/png'
                elif header[:3] == b'\xff\xd8\xff':
                    content_type = 'image/jpeg'
                elif header[:6] in (b'GIF87a', b'GIF89a'):
                    content_type = 'image/gif'
                elif header[:4] == b'RIFF' and header[8:12] == b'WEBP':
                    content_type = 'image/webp'
                else:
                    content_type = 'image/jpeg'
        
        return send_file(img_path, mimetype=content_type)
        
    except FileNotFoundError as e:
        return "Image not found", 404
    except Exception as e:
        import traceback
        traceback.print_exc()
        return "Error serving image", 500

@main_bp.route('/contact', methods=['GET', 'POST'])
def contact():

    import random
    from flask import current_app
    
    if request.method == 'POST':

        try:
            current_app.limiter.limit("3 per minute")(lambda: None)()
        except Exception:

            pass

        name = request.form.get('name')
        email = request.form.get('email')
        topic = request.form.get('topic')
        message = request.form.get('message')
        captcha_answer = request.form.get('captcha_answer')
        

        expected_answer = session.get('contact_captcha')
        if not expected_answer or str(captcha_answer) != str(expected_answer):

            num1 = random.randint(1, 10)
            num2 = random.randint(1, 10)
            session['contact_captcha'] = num1 + num2
            return render_template('contact.html', error="Incorrect math answer. Please try again.", num1=num1, num2=num2)
        

        session.pop('contact_captcha', None)
        
        if not email or not topic or not message:
            num1 = random.randint(1, 10)
            num2 = random.randint(1, 10)
            session['contact_captcha'] = num1 + num2
            return render_template('contact.html', error="Please fill in all required fields", num1=num1, num2=num2)
            
        from services.email_service import send_contact_email
        result = send_contact_email(name, email, topic, message)
        

        num1 = random.randint(1, 10)
        num2 = random.randint(1, 10)
        session['contact_captcha'] = num1 + num2
        
        if result['success']:
            return render_template('contact.html', success=True, message="Your message has been sent successfully!", num1=num1, num2=num2)
        else:
            return render_template('contact.html', error=f"Failed to send message: {result.get('error', 'Unknown error')}", num1=num1, num2=num2)
    

    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    session['contact_captcha'] = num1 + num2
    
    return render_template('contact.html', num1=num1, num2=num2)

@main_bp.route('/about')
def about():

    return render_template('about.html')

@main_bp.route('/webtoon/settings')
def webtoon_settings():
                                                                     
    return redirect(url_for('main.settings'))

@main_bp.route('/webtoon/<job_id>/settings')
def webtoon_job_settings(job_id):
                                   
    user_id = get_user_id()
    if not user_id:
        return redirect(url_for('auth.login'))
    
    try:
        from database.database import db_session_scope
        from database.db_models import WebtoonJob, WebtoonImage
        
        with db_session_scope() as session_db:
            job = session_db.query(WebtoonJob).filter_by(
                job_id=job_id,
                user_id=user_id
            ).first()
            
            if not job:
                return "Webtoon not found", 404
            
                            
            images = session_db.query(WebtoonImage).filter_by(
                job_id=job_id
            ).order_by(WebtoonImage.id.asc()).all()
            
                                       
            image_list = []
            for idx, img in enumerate(images):
                image_data = {
                    'id': img.id,
                    'index': idx + 1,
                    'original_filename': img.original_filename,
                    'status': img.status,
                    'error_message': img.error_message
                }
                if img.translated_path:
                    image_data['translated_path'] = img.translated_path
                    image_data['url'] = f'/images/{user_id}/{img.translated_path}'
                image_list.append(image_data)
            
            glossary = job.glossary or []
            
            webtoon_data = {
                'job_id': job.job_id,
                'title': job.title or job.job_id,
                'reading_mode': job.reading_mode or 'webtoon',
                'status': job.status,
                'total_images': job.total_images,
                'processed_images': job.processed_images,
                'failed_images': job.failed_images,
                'source_language': job.source_language,
                'ocr_method': job.ocr_method,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'images': image_list,
                'glossary': glossary,
                'custom_prompt_suffix': job.custom_prompt_suffix,
                'tags': job.tags
            }
            
            return render_template('webtoon_job_settings.html', webtoon=webtoon_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error loading webtoon settings: {str(e)}", 500

@main_bp.route('/webtoon/upload')
def webtoon_upload():
                                                                           
    return render_template('webtoon_upload.html')

@main_bp.route('/webtoon/create')
def webtoon_create():
                                                
    user_id = get_user_id()
    if not user_id:
        return redirect(url_for('auth.login'))
    return render_template('webtoon_create.html')

@main_bp.route('/webtoon/<job_id>/upload')
def webtoon_job_upload(job_id):
                                                    
    user_id = get_user_id()
    if not user_id:
        return redirect(url_for('auth.login'))
    
    try:
        from database.database import db_session_scope
        from database.db_models import WebtoonJob, WebtoonImage
        
        with db_session_scope() as session_db:
            job = session_db.query(WebtoonJob).filter_by(
                job_id=job_id,
                user_id=user_id
            ).first()
            
            if not job:
                return "Manga/Webtoon not found", 404
            
                                 
            images = session_db.query(WebtoonImage).filter_by(
                job_id=job_id
            ).order_by(WebtoonImage.chapter_number, WebtoonImage.page_order).all()
            
                                 
            chapters = {}
            for img in images:
                if img.chapter_number not in chapters:
                    chapters[img.chapter_number] = {
                        'number': img.chapter_number,
                        'name': img.chapter_name,
                        'image_count': 0
                    }
                chapters[img.chapter_number]['image_count'] += 1
            
            webtoon_data = {
                'job_id': job.job_id,
                'title': job.title or f"Untitled {job.reading_mode.title() if job.reading_mode else 'Manga'}",
                'reading_mode': job.reading_mode or 'manga',
                'source_language': job.source_language,
                'status': job.status,
                'total_images': job.total_images or 0,
                'chapters': list(chapters.values()),
                'images': [img.to_dict() for img in images]
            }
            
            return render_template('webtoon_job_upload.html', webtoon=webtoon_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error loading upload page: {str(e)}", 500

@main_bp.route('/webtoon/<job_id>/image/<int:image_id>/edit-ocr')
def edit_ocr(job_id, image_id):
                                                                               
    user_id = get_user_id()
    if not user_id:
        return redirect(url_for('auth.login'))
    
    try:
        from database.database import db_session_scope
        from database.db_models import WebtoonJob, WebtoonImage
        import json
        
        with db_session_scope() as session_db:
            job = session_db.query(WebtoonJob).filter_by(
                job_id=job_id,
                user_id=user_id
            ).first()
            
            if not job:
                return "Webtoon not found", 404
            
            image = session_db.query(WebtoonImage).filter_by(
                id=image_id,
                job_id=job_id
            ).first()
            
            if not image:
                return "Image not found", 404
            
                                                                              
            img_path = image.translated_path or image.original_path
            image_url = f'/images/{user_id}/{img_path}' if img_path else None
            
                            
            ocr_data = {}
            if image.ocr_text:
                try:
                    ocr_data = json.loads(image.ocr_text)
                except:
                    ocr_data = {}
            
            image_data = {
                'id': image.id,
                'url': image_url,
                'original_filename': image.original_filename
            }
            
                                                                                     
            ocr_method = job.ocr_method
            if not ocr_method:
                from database.db_models import UserOCRSettings
                ocr_settings = session_db.query(UserOCRSettings).filter_by(user_id=user_id).first()
                if ocr_settings and ocr_settings.default_ocr_method:
                    ocr_method = ocr_settings.default_ocr_method
                else:
                    ocr_method = 'nanobananapro'
            
            webtoon_data = {
                'job_id': job.job_id,
                'title': job.title or 'Untitled',
                'ocr_method': ocr_method
            }
            
            return render_template('webtoon_ocr_editor.html', 
                                 webtoon=webtoon_data, 
                                 image=image_data, 
                                 ocr_data=ocr_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error loading OCR editor: {str(e)}", 500

@main_bp.route('/webtoon/<job_id>/read')
@main_bp.route('/webtoon/<job_id>/read/<int:chapter>')
def webtoon_read(job_id, chapter=1):
                                       
    user_id = get_user_id()
    if not user_id:
        return redirect(url_for('auth.login'))
    
    try:
        from database.database import db_session_scope
        from database.db_models import WebtoonJob, WebtoonImage
        
        with db_session_scope() as session_db:
            job = session_db.query(WebtoonJob).filter_by(
                job_id=job_id,
                user_id=user_id
            ).first()
            
            if not job:
                return "Manga/Webtoon not found", 404
            
                                             
            images = session_db.query(WebtoonImage).filter_by(
                job_id=job_id,
                chapter_number=chapter
            ).order_by(WebtoonImage.page_order).all()
            
                                                    
            all_chapters = session_db.query(WebtoonImage.chapter_number).filter_by(
                job_id=job_id
            ).distinct().order_by(WebtoonImage.chapter_number).all()
            chapter_numbers = [c[0] for c in all_chapters]
            
                           
            image_list = []
            for img in images:
                img_path = img.translated_path or img.original_path
                if img_path:
                    image_list.append({
                        'id': img.id,
                        'url': f'/images/{user_id}/{img_path}',
                        'original_filename': img.original_filename,
                        'page_order': img.page_order,
                        'chapter_name': img.chapter_name
                    })
            
            webtoon_data = {
                'job_id': job.job_id,
                'title': job.title or f"Untitled {job.reading_mode.title() if job.reading_mode else 'Manga'}",
                'reading_mode': job.reading_mode or 'manga',
                'source_language': job.source_language,
                'current_chapter': chapter,
                'chapter_numbers': chapter_numbers,
                'total_chapters': len(chapter_numbers),
                'images': image_list,
                'has_prev': chapter > min(chapter_numbers) if chapter_numbers else False,
                'has_next': chapter < max(chapter_numbers) if chapter_numbers else False,
                'prev_chapter': chapter - 1 if chapter > 1 else None,
                'next_chapter': chapter + 1 if chapter_numbers and chapter < max(chapter_numbers) else None
            }
            
                                                   
            if job.reading_mode == 'webtoon':
                return render_template('webtoon_reader_vertical.html', webtoon=webtoon_data)
            else:
                return render_template('webtoon_reader_page.html', webtoon=webtoon_data)
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error loading reader: {str(e)}", 500

@main_bp.route('/webtoon/<job_id>')
def view_webtoon(job_id):
                                                
    user_id = get_user_id()
    if not user_id:
        return redirect(url_for('auth.login'))
    
    try:
        from database.database import db_session_scope
        from database.db_models import WebtoonJob, WebtoonImage
        
        with db_session_scope() as session_db:
            job = session_db.query(WebtoonJob).filter_by(
                job_id=job_id,
                user_id=user_id
            ).first()
            
            if not job:
                return "Webtoon not found", 404
            
                                                                         
            images = session_db.query(WebtoonImage).filter_by(
                job_id=job_id,
                status='completed'
            ).order_by(WebtoonImage.chapter_number.asc(), WebtoonImage.page_order.asc()).all()
            
                                     
            chapters_dict = {}
            for img in images:
                if img.translated_path:
                    chapter_num = img.chapter_number or 0
                    chapter_name = img.chapter_name or f'Chapter {chapter_num}'
                    
                    if chapter_num not in chapters_dict:
                        chapters_dict[chapter_num] = {
                            'number': chapter_num,
                            'name': chapter_name,
                            'images': []
                        }
                    
                                                                                 
                    chosen_path = img.typeset_path or img.translated_path or img.original_path
                    image_url = f'/images/{user_id}/{chosen_path}' if chosen_path else None
                                                                            
                    original_url = None
                    if hasattr(job, 'overwrite_text') and not job.overwrite_text:
                        original_url = f'/images/{user_id}/{img.original_path}'
                    
                    chapters_dict[chapter_num]['images'].append({
                        'id': img.id,
                        'original_filename': img.original_filename,
                        'translated_path': img.translated_path,
                        'typeset_path': img.typeset_path,
                        'original_path': img.original_path,
                        'url': image_url,
                        'original_url': original_url,
                        'page_order': img.page_order
                    })
            
                                    
            chapters_list = sorted(chapters_dict.values(), key=lambda x: x['number'])
            
                                                                    
            image_list = []
            for chapter in chapters_list:
                for img in chapter['images']:
                    image_list.append(img)
            
                             
            cover_image = None
            if hasattr(job, 'cover_image_id') and job.cover_image_id:
                for img_data in image_list:
                    if img_data['id'] == job.cover_image_id:
                        cover_image = img_data['url']
                        break
            if not cover_image and image_list:
                cover_image = image_list[0]['url']
            
            webtoon_data = {
                'job_id': job.job_id,
                'title': getattr(job, 'title', None) or f"Webtoon {job.job_id[:8]}",
                'author': getattr(job, 'author', None),
                'synopsis': getattr(job, 'synopsis', None),
                'tags': getattr(job, 'tags', '').split(',') if getattr(job, 'tags', None) else [],
                'reading_mode': getattr(job, 'reading_mode', 'manga') or 'manga',
                'status': job.status,
                'total_images': job.total_images or 0,
                'processed_images': job.processed_images or 0,
                'failed_images': job.failed_images or 0,
                'source_language': job.source_language,
                'ocr_method': job.ocr_method,
                'overwrite_text': getattr(job, 'overwrite_text', True),
                'cover_image_id': getattr(job, 'cover_image_id', None),
                'glossary': getattr(job, 'glossary', []) or [],
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'cover_image': cover_image,
                'images': image_list,
                'chapters': chapters_list
            }
            
            return render_template('webtoon.html', webtoon=webtoon_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error loading webtoon: {str(e)}", 500