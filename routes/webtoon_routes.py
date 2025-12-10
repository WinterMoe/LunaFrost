from flask import Blueprint, request, jsonify, send_file, session
from utils.auth_decorator import require_auth
from database.db_models import WebtoonJob, WebtoonImage, UserOCRSettings
from database.database import db_session_scope
from tasks.webtoon_tasks import process_webtoon_job, process_webtoon_image
from services.image_service import get_user_images_dir, save_upload_strip_metadata
from services.settings_service import can_user_create_webtoon
from services.encryption_service import encrypt_value
from services.typeset_service import render_typeset_image
from werkzeug.utils import secure_filename
from PIL import Image
import uuid
import os
import json
import re

webtoon_bp = Blueprint('webtoon', __name__, url_prefix='/api/webtoon')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_current_user_id():
                                          
    return session.get('user_id')

def natural_sort_key(filename):
                                                                 
    return [int(text) if text.isdigit() else text.lower() 
            for text in re.split('([0-9]+)', filename)]

def normalize_typeset_overrides(data):
                                                           
    if not isinstance(data, dict):
        return {}
    regions = []
    for entry in data.get('regions', []):
        if not isinstance(entry, dict):
            continue
        bbox = entry.get('bbox') or []
        if not (isinstance(bbox, list) and len(bbox) == 4):
            continue
        regions.append({
            'bbox': [float(b) for b in bbox],
            'user_text': (entry.get('user_text') or '').strip(),
            'font_family': entry.get('font_family'),
            'font_size': int(entry.get('font_size') or 24),
            'color': entry.get('color') or '#000000',
            'stroke_color': entry.get('stroke_color') or '#FFFFFF',
            'stroke_width': int(entry.get('stroke_width') or 0),
            'line_height': float(entry.get('line_height') or 1.2),
            'align': entry.get('align') or 'center',
            'vertical_align': entry.get('vertical_align') or 'middle',
            'letter_spacing': float(entry.get('letter_spacing') or 0),
            'is_vertical': bool(entry.get('is_vertical'))
        })

    strokes = []
    for stroke in data.get('strokes', []):
        if not isinstance(stroke, dict):
            continue
        pts = stroke.get('points') or []
        if not isinstance(pts, list) or len(pts) < 2:
            continue
        strokes.append({
            'mode': stroke.get('mode') or 'paint',
            'color': stroke.get('color') or '#FFFFFF',
            'size': int(stroke.get('size') or 12),
            'points': pts
        })

    return {'regions': regions, 'strokes': strokes}

@webtoon_bp.route('/create', methods=['POST'])
@require_auth
def create_manga_webtoon():
           
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

                                    
    allowed, error_msg, current_count, max_allowed = can_user_create_webtoon(user_id)
    if not allowed:
        return jsonify({
            'error': error_msg,
            'current_count': current_count,
            'max_webtoons': max_allowed
        }), 400
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
                    
    title = data.get('title', '').strip()
    if not title:
        return jsonify({'error': 'Title is required'}), 400
    
    if len(title) > 500:
        return jsonify({'error': 'Title must be 500 characters or less'}), 400
    
                           
    reading_mode = data.get('reading_mode', 'manga')
    if reading_mode not in ['manga', 'webtoon']:
        return jsonify({'error': 'Invalid reading mode. Must be "manga" or "webtoon"'}), 400
    
                              
    source_language = data.get('source_language', 'korean')
    if source_language not in ['korean', 'japanese']:
        return jsonify({'error': 'Invalid source language'}), 400
    
                     
    author = data.get('author', '').strip()[:255] if data.get('author') else None
    tags = data.get('tags', '').strip() if data.get('tags') else None
    synopsis = data.get('synopsis', '').strip() if data.get('synopsis') else None
    glossary = data.get('glossary') or []
    custom_prompt_suffix = data.get('custom_prompt_suffix', '').strip() if data.get('custom_prompt_suffix') else None

    
    with db_session_scope() as session_db:
        try:
            job_id = str(uuid.uuid4())
            
            job = WebtoonJob(
                user_id=user_id,
                job_id=job_id,
                title=title,
                author=author,
                tags=tags,
                synopsis=synopsis,
                reading_mode=reading_mode,
                source_language=source_language,
                glossary=glossary,
                custom_prompt_suffix=custom_prompt_suffix,
                status='draft',                                             
                total_images=0,
                ocr_method=None                                     
            )
            
            session_db.add(job)
            session_db.commit()
            
            return jsonify({
                'success': True,
                'job_id': job_id,
                'title': title,
                'reading_mode': reading_mode,
                'message': 'Manga/webtoon created successfully. Now upload images.'
            }), 201
            
        except Exception as e:
            session_db.rollback()
            print(f"❌ Error creating manga/webtoon: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Failed to create: {str(e)}'}), 500

@webtoon_bp.route('/<job_id>/upload', methods=['POST'])
@require_auth
def upload_images_to_job(job_id):
           
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401
    
                                  
    if 'images' not in request.files:
        return jsonify({'error': 'No images provided'}), 400
    
    files = request.files.getlist('images')
    if not files or len(files) == 0:
        return jsonify({'error': 'No images provided'}), 400
    
                    
    MAX_FILES = 100
    MAX_FILE_SIZE = 10 * 1024 * 1024        
    
    if len(files) > MAX_FILES:
        return jsonify({'error': f'Maximum {MAX_FILES} images allowed per upload'}), 400
    
    for file in files:
        if not allowed_file(file.filename):
            return jsonify({'error': f'Invalid file type: {file.filename}'}), 400
        
        file.seek(0, os.SEEK_END)
        if file.tell() > MAX_FILE_SIZE:
            return jsonify({'error': f'File {file.filename} exceeds 10MB limit'}), 400
        file.seek(0)
    
    with db_session_scope() as session_db:
                                               
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Manga/webtoon not found'}), 404
        
                       
        chapter_number = request.form.get('chapter_number', type=int)
        chapter_name = request.form.get('chapter_name', '').strip()
        ocr_method = request.form.get('ocr_method')
        overwrite_text = request.form.get('overwrite_text', 'true').lower() == 'true'
        
                                                          
        if job.reading_mode == 'manga':
                                                           
                                         
            max_chapter = session_db.query(WebtoonImage).filter_by(
                job_id=job_id
            ).with_entities(WebtoonImage.chapter_number).order_by(
                WebtoonImage.chapter_number.desc()
            ).first()
            
            next_chapter = (max_chapter[0] if max_chapter and max_chapter[0] else 0) + 1
        else:
                                                        
            if chapter_number:
                                         
                next_chapter = chapter_number
                                                    
                max_page = session_db.query(WebtoonImage).filter_by(
                    job_id=job_id,
                    chapter_number=chapter_number
                ).with_entities(WebtoonImage.page_order).order_by(
                    WebtoonImage.page_order.desc()
                ).first()
                start_page_order = (max_page[0] if max_page and max_page[0] else 0) + 1
            else:
                                    
                max_chapter = session_db.query(WebtoonImage).filter_by(
                    job_id=job_id
                ).with_entities(WebtoonImage.chapter_number).order_by(
                    WebtoonImage.chapter_number.desc()
                ).first()
                next_chapter = (max_chapter[0] if max_chapter and max_chapter[0] else 0) + 1
                start_page_order = 1
        
                                                     
        sorted_files = sorted(files, key=lambda f: natural_sort_key(f.filename))
        
                                 
        upload_dir = os.path.join(get_user_images_dir(user_id), 'webtoons', job_id, 'original')
        os.makedirs(upload_dir, exist_ok=True)
        
        uploaded_images = []
        
        try:
            for idx, file in enumerate(sorted_files):
                                          
                original_filename = secure_filename(file.filename)
                if not original_filename:
                    original_filename = f"image_{idx + 1}.jpg"
                
                                        
                base, ext = os.path.splitext(original_filename)
                unique_filename = f"{base}_{uuid.uuid4().hex[:8]}{ext}"
                
                           
                file_path = os.path.join(upload_dir, unique_filename)
                                                                              
                save_upload_strip_metadata(file, file_path)
                                                  
                if job.reading_mode == 'manga':
                    img_chapter = next_chapter + idx
                    img_page_order = 1
                else:
                    img_chapter = next_chapter
                    img_page_order = start_page_order + idx
                
                                        
                relative_path = os.path.relpath(file_path, get_user_images_dir(user_id))
                
                image = WebtoonImage(
                    job_id=job_id,
                    chapter_number=img_chapter,
                    chapter_name=chapter_name if job.reading_mode == 'webtoon' and idx == 0 else None,
                    page_order=img_page_order,
                    original_filename=original_filename,
                    original_path=relative_path,
                    status='pending'
                )
                
                session_db.add(image)
                uploaded_images.append({
                    'filename': original_filename,
                    'chapter': img_chapter,
                    'page_order': img_page_order
                })
            
                        
            job.total_images = (job.total_images or 0) + len(sorted_files)
            if ocr_method:
                job.ocr_method = ocr_method
                print(f"[Upload] Setting job OCR method to: {ocr_method}")
            elif not job.ocr_method:
                                                                                              
                ocr_settings = session_db.query(UserOCRSettings).filter_by(user_id=user_id).first()
                if ocr_settings and ocr_settings.default_ocr_method:
                    job.ocr_method = ocr_settings.default_ocr_method
                    print(f"[Upload] No OCR method provided, using user default: {job.ocr_method}")
                else:
                    job.ocr_method = 'google'
                    print(f"[Upload] No OCR method found, defaulting to Google Cloud Vision")
            job.overwrite_text = overwrite_text
            
                                                                 
            if job.status == 'draft':
                job.status = 'pending'
            
            session_db.commit()
            
            return jsonify({
                'success': True,
                'job_id': job_id,
                'uploaded_count': len(uploaded_images),
                'images': uploaded_images,
                'total_images': job.total_images,
                'message': f'Successfully uploaded {len(uploaded_images)} images'
            }), 200
            
        except Exception as e:
            session_db.rollback()
            print(f"❌ Error uploading images: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Failed to upload images: {str(e)}'}), 500

@webtoon_bp.route('/<job_id>/cover/<int:image_id>', methods=['PUT'])
@require_auth
def set_cover_image(job_id, image_id):
                                                       
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Manga/webtoon not found'}), 404
        
                                              
        image = session_db.query(WebtoonImage).filter_by(
            id=image_id,
            job_id=job_id
        ).first()
        
        if not image:
            return jsonify({'error': 'Image not found'}), 404
        
        job.cover_image_id = image_id
        session_db.commit()
        
        return jsonify({
            'success': True,
            'cover_image_id': image_id,
            'message': 'Cover image set successfully'
        }), 200

@webtoon_bp.route('/<job_id>', methods=['PUT'])
@require_auth
def update_manga_webtoon(job_id):
                                       
    user_id = get_current_user_id()
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    with db_session_scope() as session_db:
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Manga/webtoon not found'}), 404
        
                               
        if 'title' in data:
            job.title = data['title'].strip()[:500]
        if 'author' in data:
            job.author = data['author'].strip()[:255] if data['author'] else None
        if 'synopsis' in data:
            job.synopsis = data['synopsis'].strip() if data['synopsis'] else None
        if 'tags' in data:
            job.tags = data['tags'].strip() if data['tags'] else None
        if 'source_language' in data and data['source_language'] in ['korean', 'japanese']:
            job.source_language = data['source_language']
        if 'custom_prompt_suffix' in data:
            job.custom_prompt_suffix = data['custom_prompt_suffix'].strip() if data['custom_prompt_suffix'] else None
        
        session_db.commit()
        
        return jsonify({
            'success': True,
            'message': 'Updated successfully'
        }), 200

@webtoon_bp.route('/<job_id>/chapter/<int:chapter_num>', methods=['GET'])
@require_auth
def get_chapter_images(job_id, chapter_num):
                                               
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Manga/webtoon not found'}), 404
        
        images = session_db.query(WebtoonImage).filter_by(
            job_id=job_id,
            chapter_number=chapter_num
        ).order_by(WebtoonImage.page_order).all()
        
        return jsonify({
            'job_id': job_id,
            'chapter_number': chapter_num,
            'images': [img.to_dict() for img in images]
        }), 200

@webtoon_bp.route('/<job_id>/start-translation', methods=['POST'])
@require_auth
def start_translation_job(job_id):
                                                          
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Manga/webtoon not found'}), 404
        
        if job.total_images == 0:
            return jsonify({'error': 'No images to translate'}), 400
        
                                                     
        data = request.get_json() or {}
        ocr_method = data.get('ocr_method') or job.ocr_method or 'google'
        overwrite_text = data.get('overwrite_text', job.overwrite_text)
        skip_translation = data.get('skip_translation', False)
        
                                                                                                      
        if ocr_method != 'nanobananapro':
            skip_translation = True
        
        job.ocr_method = ocr_method
        job.overwrite_text = overwrite_text
        job.status = 'pending'
        session_db.commit()
        
                                
        try:
            task = process_webtoon_job.delay(job_id, skip_translation=skip_translation)
        except Exception as e:
            print(f"❌ Error queuing translation: {e}")
            return jsonify({'error': f'Failed to start translation: {str(e)}'}), 500
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': 'Translation started'
        }), 200

@webtoon_bp.route('/translate', methods=['POST'])
@require_auth
def create_translation_job():
           
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

                                    
    allowed, error_msg, current_count, max_allowed = can_user_create_webtoon(user_id)
    if not allowed:
        return jsonify({
            'error': error_msg,
            'current_count': current_count,
            'max_webtoons': max_allowed
        }), 400
    
                                  
    if 'images' not in request.files:
        return jsonify({'error': 'No images provided'}), 400
    
    files = request.files.getlist('images')
    
    if not files or len(files) == 0:
        return jsonify({'error': 'No images provided'}), 400
    
                                         
    MAX_FILES = 50
    if len(files) > MAX_FILES:
        return jsonify({'error': f'Maximum {MAX_FILES} images allowed per job'}), 400
    
                    
    ocr_method = request.form.get('ocr_method', 'google')
    
    if ocr_method not in ['google', 'azure', 'nanobananapro']:
        return jsonify({'error': 'Invalid OCR method'}), 400
    
                         
    source_language = request.form.get('source_language', 'korean')
    
    if source_language not in ['korean', 'japanese']:
        return jsonify({'error': 'Invalid source language. Must be "korean" or "japanese".'}), 400
    
                               
    overwrite_text = request.form.get('overwrite_text', 'true').lower() == 'true'
    
                                   
    MAX_FILE_SIZE = 10 * 1024 * 1024        
    total_size = 0
    
    for file in files:
        if not allowed_file(file.filename):
            return jsonify({'error': f'Invalid file type: {file.filename}. Only PNG, JPG, JPEG, WebP allowed.'}), 400
        
                         
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({'error': f'File {file.filename} exceeds maximum size of 10MB'}), 400
        
        total_size += file_size
    
                                      
    MAX_TOTAL_SIZE = 100 * 1024 * 1024               
    if total_size > MAX_TOTAL_SIZE:
        return jsonify({'error': f'Total file size exceeds maximum of 100MB'}), 400
    
    with db_session_scope() as session_db:
                                                                    
        if ocr_method in ['google', 'azure', 'nanobananapro']:
            ocr_settings = session_db.query(UserOCRSettings).filter_by(user_id=user_id).first()
            
            if not ocr_settings:
                return jsonify({'error': f'Please configure your API keys in settings for {ocr_method}'}), 400
            
            if ocr_method == 'google' and not ocr_settings.google_api_key:
                return jsonify({'error': 'Google API key not configured. Please add it in settings.'}), 400
            elif ocr_method == 'azure' and not ocr_settings.azure_api_key:
                return jsonify({'error': 'Azure API key not configured. Please add it in settings.'}), 400
            elif ocr_method == 'nanobananapro':
                                                        
                api_source = 'gemini'           
                if hasattr(ocr_settings, 'nanobananapro_api_source') and ocr_settings.nanobananapro_api_source:
                    api_source = ocr_settings.nanobananapro_api_source
                
                if api_source == 'openrouter':
                                                                   
                    from models.settings import load_settings
                    user_settings = load_settings(user_id)
                    openrouter_key = user_settings.get('api_keys', {}).get('openrouter', '')
                    if not openrouter_key:
                        return jsonify({'error': 'OpenRouter API key not configured. Please add it in Settings → API Keys → OpenRouter.'}), 400
                else:
                                                              
                    if not ocr_settings.gemini_api_key:
                        return jsonify({'error': 'Gemini API key not configured. Please add it in Webtoon Settings → Gemini API Key.'}), 400
        
                    
        job_id = str(uuid.uuid4())
        try:
            job = WebtoonJob(
                user_id=user_id,
                job_id=job_id,
                status='pending',
                total_images=len(files),
                ocr_method=ocr_method,
                source_language=source_language,
                overwrite_text=overwrite_text
            )
            
            session_db.add(job)
            session_db.flush()              
        except Exception as e:
            session_db.rollback()
            print(f"❌ Error creating webtoon job: {str(e)}")
            import traceback
            traceback.print_exc()
                                                              
            if 'overwrite_text' in str(e).lower() or 'column' in str(e).lower():
                return jsonify({
                    'error': 'Database migration required. Please run: python scripts/add_overwrite_text_column.py'
                }), 500
            return jsonify({
                'error': f'Failed to create job: {str(e)}'
            }), 500
        
                                                     
        try:
            upload_dir = os.path.join(get_user_images_dir(user_id), 'webtoons', job_id, 'originals')
            os.makedirs(upload_dir, exist_ok=True)
            
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                                                
                    filepath = os.path.join(upload_dir, filename)
                    counter = 1
                    while os.path.exists(filepath):
                        name, ext = os.path.splitext(filename)
                        filename = f"{name}_{counter}{ext}"
                        filepath = os.path.join(upload_dir, filename)
                        counter += 1
                    
                    save_upload_strip_metadata(file, filepath)
                    
                                         
                    relative_path = os.path.relpath(filepath, get_user_images_dir(user_id))
                    
                                         
                    webtoon_image = WebtoonImage(
                        job_id=job_id,
                        original_filename=filename,
                        original_path=relative_path,
                        status='pending'
                    )
                    session_db.add(webtoon_image)
            
            session_db.commit()
        except Exception as e:
            session_db.rollback()
            print(f"❌ Error saving images: {str(e)}")
            import traceback
            traceback.print_exc()
                                           
            try:
                job = session_db.query(WebtoonJob).filter_by(job_id=job_id).first()
                if job:
                    session_db.delete(job)
                    session_db.commit()
            except:
                pass
            return jsonify({
                'error': f'Failed to save images: {str(e)}'
            }), 500
    
                                  
    try:
        task_result = process_webtoon_job.delay(job_id)
        print(f"✅ Queued webtoon job {job_id} with task ID: {task_result.id}")
    except Exception as e:
        print(f"❌ Error queuing webtoon job {job_id}: {str(e)}")
        import traceback
        traceback.print_exc()
                                     
        with db_session_scope() as error_session:
            job = error_session.query(WebtoonJob).filter_by(job_id=job_id).first()
            if job:
                job.status = 'failed'
                job.error_message = f"Failed to queue job: {str(e)}"
                error_session.commit()
        return jsonify({
            'error': f'Failed to queue translation job: {str(e)}',
            'job_id': job_id
        }), 500
    
    return jsonify({
        'job_id': job_id,
        'status': 'pending',
        'total_images': len(files),
        'task_id': task_result.id if 'task_result' in locals() else None,
        'message': 'Translation job created successfully. Processing will begin shortly.'
    }), 201

@webtoon_bp.route('/job/<job_id>', methods=['GET'])
@require_auth
def get_job_status(job_id):
                                         
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
                            
        images = session_db.query(WebtoonImage).filter_by(job_id=job_id).all()
        
        image_data = [{
            'id': img.id,
            'filename': img.original_filename,
            'status': img.status,
            'translated_path': img.translated_path,
            'processing_time': img.processing_time,
            'error_message': img.error_message
        } for img in images]
        
        return jsonify({
            'job_id': job.job_id,
            'status': job.status,
            'total_images': job.total_images,
            'processed_images': job.processed_images,
            'failed_images': job.failed_images,
            'ocr_method': job.ocr_method,
            'source_language': job.source_language,
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'images': image_data
        }), 200

@webtoon_bp.route('/job/<job_id>/image/<int:image_id>/data', methods=['GET'])
@require_auth
def get_image_data(job_id, image_id):
                                                           
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
                                    
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        image = session_db.query(WebtoonImage).filter_by(
            id=image_id,
            job_id=job_id
        ).first()
        
        if not image:
            return jsonify({'error': 'Image not found'}), 404
        
                                        
        ocr_data = []
        bubble_groups = []
        panel_boundaries = []
        detected_bubbles = []
        translated_data = []
        
        if image.ocr_text:
            import json
            try:
                parsed_ocr = json.loads(image.ocr_text) if isinstance(image.ocr_text, str) else image.ocr_text
                
                                                                    
                if isinstance(parsed_ocr, dict) and 'regions' in parsed_ocr:
                                                           
                    ocr_data = parsed_ocr.get('regions', [])
                    bubble_groups = parsed_ocr.get('bubble_groups', [])
                    panel_boundaries = parsed_ocr.get('panel_boundaries', [])
                    detected_bubbles = parsed_ocr.get('detected_bubbles', [])
                else:
                                           
                    ocr_data = parsed_ocr if isinstance(parsed_ocr, list) else []
            except:
                pass
        
        if image.translated_text:
            import json
            try:
                translated_data = json.loads(image.translated_text) if isinstance(image.translated_text, str) else image.translated_text
            except:
                pass
        
        return jsonify({
            'ocr_regions': ocr_data,
            'translated_regions': translated_data,
            'bubble_groups': bubble_groups,
            'panel_boundaries': panel_boundaries,
            'detected_bubbles': detected_bubbles
        }), 200

@webtoon_bp.route('/job/<job_id>/image/<int:image_id>/translations', methods=['PUT'])
@require_auth
def save_image_translations(job_id, image_id):
                                                
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
                                    
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        image = session_db.query(WebtoonImage).filter_by(
            id=image_id,
            job_id=job_id
        ).first()
        
        if not image:
            return jsonify({'error': 'Image not found'}), 404
        
                                               
        import json
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
                                                                
                                                                                   
        translated_regions = data.get('translated_regions', [])
        
        try:
            image.translated_text = json.dumps(translated_regions)
            session_db.commit()
            
            return jsonify({
                'success': True,
                'message': 'Translations saved successfully',
                'image_id': image_id
            }), 200
        except Exception as e:
            session_db.rollback()
            return jsonify({'error': f'Failed to save translations: {str(e)}'}), 500

@webtoon_bp.route('/job/<job_id>/image/<int:image_id>/clean-text', methods=['POST'])
@require_auth
def clean_image_text(job_id, image_id):
           
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
                                    
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        image = session_db.query(WebtoonImage).filter_by(
            id=image_id,
            job_id=job_id
        ).first()
        
        if not image:
            return jsonify({'error': 'Image not found'}), 404
        
                          
        data = request.get_json() or {}
        method = data.get('method', 'opencv')
        custom_regions = data.get('regions')
        do_typeset = data.get('typeset', False)
        typeset_regions = data.get('typeset_regions')
        
        if method not in ['opencv', 'lama']:
            return jsonify({'error': 'Invalid method. Use "opencv" or "lama"'}), 400
        
                                                                
        regions = []
        translated_regions = []
        
        if custom_regions:
                                                                     
            regions = custom_regions
        elif image.ocr_text:
                                           
            try:
                parsed_ocr = json.loads(image.ocr_text) if isinstance(image.ocr_text, str) else image.ocr_text
                
                if isinstance(parsed_ocr, dict) and 'regions' in parsed_ocr:
                    regions = parsed_ocr.get('regions', [])
                elif isinstance(parsed_ocr, list):
                    regions = parsed_ocr
            except:
                pass
        
                                             
        if do_typeset and image.translated_text:
            try:
                translated_regions = json.loads(image.translated_text) if isinstance(image.translated_text, str) else image.translated_text
            except:
                pass
        
        if not regions:
            return jsonify({'error': 'No text regions found. Run OCR first or provide custom regions.'}), 400
        
                                 
        original_path = os.path.join(get_user_images_dir(user_id), image.original_path)
        
        if not os.path.exists(original_path):
            return jsonify({'error': 'Original image not found'}), 404
        
                                              
        output_dir = os.path.join(get_user_images_dir(user_id), 'webtoons', job_id, 'cleaned')
        os.makedirs(output_dir, exist_ok=True)
        
                                  
        import time
        base_name = os.path.splitext(image.original_filename)[0]
        suffix = '_cleaned_typeset' if do_typeset else '_cleaned'
        output_filename = f"{base_name}{suffix}_{int(time.time())}.png"
        output_path = os.path.join(output_dir, output_filename)
        
        try:
                                       
            from services.inpainting_service import inpainting_service
            
                                
            start_time = time.time()
            result_path = inpainting_service.clean_text(
                image_path=original_path,
                regions=regions,
                output_path=output_path,
                method=method
            )
            
                                               
            typeset_overrides = {'regions': [], 'strokes': []}
            
            if do_typeset:
                                        
                tr_regions = translated_regions or typeset_regions or []
                print(f"🔍 Typeset debug: Found {len(tr_regions)} translated regions")
                
                if typeset_regions:
                    typeset_overrides['regions'] = typeset_regions
                else:
                                                          
                    for i, tr in enumerate(tr_regions):
                                                                   
                        bbox = tr.get('bbox') or tr.get('region')
                        translated_text = tr.get('translatedText') or tr.get('translated_text') or tr.get('text') or ''
                        
                        print(f"  Region {i}: bbox={bbox}, text='{translated_text[:30] if translated_text else 'EMPTY'}...'")
                        
                        if bbox and translated_text:
                            typeset_overrides['regions'].append({
                                'bbox': bbox,
                                'user_text': translated_text,
                                'font_size': tr.get('font_size', 24),
                                'color': tr.get('color', '#000000'),
                                'stroke_color': tr.get('stroke_color', '#FFFFFF'),
                                'stroke_width': tr.get('stroke_width', 0),
                                'align': tr.get('align', 'center'),
                                'vertical_align': tr.get('vertical_align', 'middle'),
                            })
                
                print(f"📝 Typeset: Building {len(typeset_overrides['regions'])} text regions")
                
                if typeset_overrides['regions']:
                                                        
                    typeset_output_path = output_path.replace('.png', '_final.png')
                    render_typeset_image(
                        original_path=result_path,                             
                        output_path=typeset_output_path,
                        overrides=typeset_overrides
                    )
                    result_path = typeset_output_path
                    print(f"✅ Typeset complete: {typeset_output_path}")
            
            processing_time = time.time() - start_time
            
                                                      
            relative_path = os.path.relpath(result_path, get_user_images_dir(user_id))
            
                                                                              
            old_original_path = image.original_path
            old_original_full_path = os.path.join(get_user_images_dir(user_id), old_original_path)
            old_translated_path = image.translated_path
            old_translated_full_path = os.path.join(get_user_images_dir(user_id), old_translated_path) if old_translated_path else None
            
                                                                                                          
            image.original_path = relative_path
            image.translated_path = relative_path                                                
            session_db.commit()
            print(f"📝 Updated image path: {old_original_path} → {relative_path}")
            
                                                                
            if old_original_full_path != result_path and os.path.exists(old_original_full_path):
                try:
                    os.remove(old_original_full_path)
                    print(f"🗑️ Deleted old original: {old_original_full_path}")
                except Exception as del_err:
                    print(f"⚠️ Could not delete old file: {del_err}")
            
                                                                      
            if old_translated_full_path and old_translated_full_path != result_path and os.path.exists(old_translated_full_path):
                try:
                    os.remove(old_translated_full_path)
                    print(f"🗑️ Deleted old translated: {old_translated_full_path}")
                except Exception as del_err:
                    print(f"⚠️ Could not delete old translated file: {del_err}")
            
                                         
            cleaned_url = f"/images/{user_id}/{relative_path}"
            
                                              
            typeset_was_applied = False
            if do_typeset:
                try:
                    typeset_was_applied = bool(typeset_overrides.get('regions'))
                except:
                    typeset_was_applied = False
            
            return jsonify({
                'success': True,
                'cleaned_url': cleaned_url,
                'method': method,
                'regions_cleaned': len(regions),
                'typeset_applied': typeset_was_applied,
                'typeset_count': len(typeset_overrides.get('regions', [])),
                'processing_time': round(processing_time, 2),
                'image_updated': True
            }), 200
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Inpainting failed: {str(e)}'}), 500

@webtoon_bp.route('/job/<job_id>/image/<int:image_id>/rescan-ocr', methods=['POST'])
@require_auth
def rescan_image_ocr(job_id, image_id):
           
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
                                    
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        image = session_db.query(WebtoonImage).filter_by(
            id=image_id,
            job_id=job_id
        ).first()
        
        if not image:
            return jsonify({'error': 'Image not found'}), 404
        
        data = request.get_json()
        if not data or 'boxes' not in data:
            return jsonify({'error': 'No boxes provided'}), 400
        
        boxes = data['boxes']
                                                                      
        is_full_rescan = len(boxes) == 0
        
        try:
                                
            user_images_dir = get_user_images_dir(user_id)
            original_path = os.path.join(user_images_dir, image.original_path)
            
            if not os.path.exists(original_path):
                return jsonify({'error': 'Image file not found'}), 404
            
                                                                                             
            ocr_method = job.ocr_method                                       
            api_key = None
            endpoint = None
            
                                             
            ocr_settings = session_db.query(UserOCRSettings).filter_by(
                user_id=user_id
            ).first()
            
                                              
            print(f"[OCR Rescan] Job OCR method: {ocr_method}")
            
                                                                 
            if not ocr_method and ocr_settings:
                ocr_method = ocr_settings.default_ocr_method
                print(f"[OCR Rescan] Using user default OCR method: {ocr_method}")
            
                            
            if not ocr_method:
                ocr_method = 'google'
                print(f"[OCR Rescan] WARNING: No OCR method found, defaulting to Google Cloud Vision")
            
            print(f"[OCR Rescan] Final OCR method selected: {ocr_method}")
            
                                             
            if ocr_settings:
                if ocr_method == 'google' and ocr_settings.google_api_key:
                    from services.encryption_service import decrypt_value
                    api_key = decrypt_value(ocr_settings.google_api_key)
                elif ocr_method == 'azure' and ocr_settings.azure_api_key:
                    from services.encryption_service import decrypt_value
                    api_key = decrypt_value(ocr_settings.azure_api_key)
                    endpoint = ocr_settings.azure_endpoint
            
                                                                       
            from services.ocr_service import ocr_service
            
            source_language = job.source_language or 'korean'
            
            print(f"[OCR Rescan] Starting rescan with {len(boxes)} boxes using method: {ocr_method}")
            
                                                                       
                                                                          
            print(f"[OCR Rescan] Running full image OCR with grouping...")
            ocr_data = ocr_service.detect_text_with_grouping(
                original_path,
                ocr_method,
                source_language,
                api_key=api_key,
                endpoint=endpoint,
                enable_bubble_detection=True
            )
            all_ocr_results = ocr_data.get('regions', [])
            print(f"[OCR Rescan] Full image OCR found {len(all_ocr_results)} text regions")
            
                                                    
            ocr_regions = []
            
                                                                          
            rescan_bubble_groups = []
            
            if is_full_rescan:
                                                    
                ocr_regions = ocr_data.get('regions', [])
                rescan_bubble_groups = ocr_data.get('bubble_groups', [])
                sorted_panels = ocr_data.get('panel_boundaries', [])
                sorted_bubbles = ocr_data.get('detected_bubbles', [])
                
                print(f"[OCR Rescan] Full Auto completed. Found {len(ocr_regions)} regions, {len(rescan_bubble_groups)} groups.")
            else:
                                                 
                for i, box in enumerate(boxes):
                    if len(box) != 4:
                        continue
                        
                    box_x, box_y, box_w, box_h = [int(v) for v in box]
                    box_texts = []
                    
                                                                  
                    for ocr_result in all_ocr_results:
                        ocr_bbox = ocr_result.get('bbox', [0, 0, 0, 0])
                        ocr_x, ocr_y, ocr_w, ocr_h = ocr_bbox
                        
                                                                               
                        ocr_center_x = ocr_x + ocr_w / 2
                        ocr_center_y = ocr_y + ocr_h / 2
                        
                        if (box_x <= ocr_center_x <= box_x + box_w and
                            box_y <= ocr_center_y <= box_y + box_h):
                            text = ocr_result.get('text', '').strip()
                            if text:
                                box_texts.append({
                                    'text': text,
                                    'confidence': ocr_result.get('confidence', 0),
                                    'x': ocr_x,
                                    'y': ocr_y
                                })
                    
                                                                          
                    if box_texts:
                                                                                   
                        box_texts.sort(key=lambda t: (t['y'], -t['x'] if source_language == 'japanese' else t['x']))
                        
                                                                     
                        lines = []
                        line_tolerance = 30          
                        for t in box_texts:
                            if not lines:
                                lines.append([t])
                            else:
                                last_line = lines[-1]
                                last_y = sum(item['y'] for item in last_line) / len(last_line)
                                if abs(t['y'] - last_y) <= line_tolerance:
                                    last_line.append(t)
                                else:
                                    lines.append([t])
                        
                                                                                        
                        line_texts = []
                        for line in lines:
                            if source_language == 'japanese':
                                line.sort(key=lambda t: -t['x'])
                                separator = ''
                            else:
                                line.sort(key=lambda t: t['x'])
                                separator = ' '
                            line_texts.append(separator.join(item['text'] for item in line))
                        
                        combined_text = '\n'.join(line_texts)
                        avg_confidence = sum(t['confidence'] for t in box_texts) / len(box_texts)
                        
                                               
                        new_region_idx = len(ocr_regions)
                        ocr_regions.append({
                            'bbox': [box_x, box_y, box_w, box_h],
                            'text': combined_text,
                            'confidence': avg_confidence
                        })
                        
                                                                      
                                                                                            
                        rescan_bubble_groups.append({
                            'bubble_id': len(rescan_bubble_groups),
                            'region_indices': [new_region_idx],
                            'bbox': [box_x, box_y, box_w, box_h],
                            'is_ungrouped': False                   
                        })
                        
                        print(f"[OCR Rescan] Box ({box_x}, {box_y}) found text: {combined_text[:30]}...")
                    else:
                                                                                         
                                                                                                             
                                                   
                         ocr_regions.append({
                            'bbox': [box_x, box_y, box_w, box_h],
                            'text': '',
                            'confidence': 0
                        })
                
                                                                               
                sorted_panels = []
                sorted_bubbles = []
            
            print(f"[OCR Rescan] Total regions: {len(ocr_regions)}")
            
                                   
            ocr_data = {
                'regions': ocr_regions,
                'bubble_groups': rescan_bubble_groups,
                'panel_boundaries': sorted_panels,
                'detected_bubbles': sorted_bubbles,
                'custom_scan': not is_full_rescan
            }
            
            image.ocr_text = json.dumps(ocr_data)
            image.translated_text = None                                        
            session_db.commit()
            
            return jsonify({
                'success': True,
                'message': 'OCR rescan completed',
                'regions_count': len(ocr_regions),
                'regions': ocr_regions,
                'is_full_rescan': is_full_rescan
            }), 200
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            session_db.rollback()
            return jsonify({'error': f'OCR rescan failed: {str(e)}'}), 500

@webtoon_bp.route('/job/<job_id>/merge-images', methods=['POST'])
@require_auth
def merge_webtoon_images(job_id):
           
    user_id = get_current_user_id()
    data = request.get_json() or {}
    image_ids = data.get('image_ids') or []
    
    if not isinstance(image_ids, list) or len(image_ids) != 2:
        return jsonify({'error': 'Exactly two image_ids are required'}), 400
    
    try:
        image_ids = [int(i) for i in image_ids]
    except Exception:
        return jsonify({'error': 'Invalid image_ids'}), 400
    
    if len(set(image_ids)) != 2:
        return jsonify({'error': 'Select two different images to merge'}), 400
    
    queue_ocr_method = None
    queue_source_language = 'korean'
    new_image_id = None
    
    with db_session_scope() as session_db:
        job = session_db.query(WebtoonJob).filter_by(job_id=job_id, user_id=user_id).first()
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        queue_source_language = job.source_language or 'korean'
        
        images = session_db.query(WebtoonImage).filter(
            WebtoonImage.job_id == job_id,
            WebtoonImage.id.in_(image_ids)
        ).all()
        
        if len(images) != 2:
            return jsonify({'error': 'Images not found for this job'}), 404
        
        chapters = {img.chapter_number for img in images}
        if len(chapters) != 1:
            return jsonify({'error': 'Images must be in the same chapter to merge'}), 400
        
        chapter_number = images[0].chapter_number
        chapter_name = images[0].chapter_name or images[1].chapter_name
        
                                                 
        queue_ocr_method = job.ocr_method
        if not queue_ocr_method:
            ocr_settings = session_db.query(UserOCRSettings).filter_by(user_id=user_id).first()
            if ocr_settings and ocr_settings.default_ocr_method:
                queue_ocr_method = ocr_settings.default_ocr_method
            else:
                queue_ocr_method = 'google'
        job.status = 'pending'
        
                                                 
        ordered_images = sorted(images, key=lambda img: image_ids.index(img.id))
        
        user_images_dir = get_user_images_dir(user_id)
        original_paths = []
        translated_paths = []
        pil_images = []
        
        for img in ordered_images:
            abs_path = os.path.join(user_images_dir, img.original_path)
            if not os.path.exists(abs_path):
                return jsonify({'error': f'Original file for image {img.id} not found'}), 404
            original_paths.append(abs_path)
            if img.translated_path:
                translated_paths.append(os.path.join(user_images_dir, img.translated_path))
            pil_img = Image.open(abs_path).convert('RGB')
            pil_images.append(pil_img)
        
                                                                       
        target_width = max(im.width for im in pil_images)
        resized = []
        for im in pil_images:
            if im.width != target_width:
                new_height = int(im.height * (target_width / im.width))
                im = im.resize((target_width, new_height), Image.LANCZOS)
            resized.append(im)
        
        total_height = sum(im.height for im in resized)
        merged_image = Image.new('RGB', (target_width, total_height), (255, 255, 255))
        current_y = 0
        for im in resized:
            merged_image.paste(im, (0, current_y))
            current_y += im.height
        
        original_dir = os.path.join(user_images_dir, 'webtoons', job_id, 'original')
        os.makedirs(original_dir, exist_ok=True)
        base_name = f"merged_{ordered_images[0].id}_{ordered_images[1].id}"
        merged_filename = f"{base_name}.png"
        merged_abs_path = os.path.join(original_dir, merged_filename)
        merged_image.save(merged_abs_path, format='PNG')
        merged_rel_path = os.path.relpath(merged_abs_path, user_images_dir)
        
        new_image = WebtoonImage(
            job_id=job_id,
            chapter_number=chapter_number,
            chapter_name=chapter_name,
            page_order=min(img.page_order for img in ordered_images),
            original_filename=merged_filename,
            original_path=merged_rel_path,
            status='pending'
        )
        session_db.add(new_image)
        
        for img in images:
            session_db.delete(img)
        
        session_db.flush()
        
                                                
        chapter_images = session_db.query(WebtoonImage).filter_by(
            job_id=job_id,
            chapter_number=chapter_number
        ).order_by(WebtoonImage.page_order).all()
        
        for idx, img in enumerate(chapter_images, start=1):
            img.page_order = idx
        
        job.total_images = session_db.query(WebtoonImage).filter_by(job_id=job_id).count()
        job.processed_images = session_db.query(WebtoonImage).filter_by(job_id=job_id, status='completed').count()
        job.failed_images = session_db.query(WebtoonImage).filter_by(job_id=job_id, status='failed').count()
        if job.cover_image_id in image_ids:
            job.cover_image_id = new_image.id
        
        session_db.commit()
        new_image_id = new_image.id
    
                                          
    for path in original_paths + translated_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    
    try:
        process_webtoon_image.delay(new_image_id, queue_ocr_method, user_id, queue_source_language)
    except Exception as e:
        print(f"❌ Failed to queue merged image {new_image_id}: {str(e)}")
    
    return jsonify({
        'success': True,
        'merged_image_id': new_image_id,
        'message': 'Images merged. Originals removed; merged image will be reprocessed.'
    }), 200

@webtoon_bp.route('/job/<job_id>/images', methods=['GET'])
@require_auth
def get_job_images(job_id):
                                             
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        images = session_db.query(WebtoonImage).filter_by(
            job_id=job_id,
            status='completed'
        ).all()
        
        image_urls = []
        for img in images:
            if img.translated_path:
                                                                                        
                url = f'/images/{img.translated_path}'
                image_urls.append({
                    'original_filename': img.original_filename,
                    'url': url
                })
        
        return jsonify({
            'job_id': job_id,
            'images': image_urls
        }), 200

def build_image_urls(user_id, image):
    base_dir = get_user_images_dir(user_id)
    urls = {
        'original_url': f"/images/{user_id}/{image.original_path}" if image.original_path else None,
        'translated_url': f"/images/{user_id}/{image.translated_path}" if image.translated_path else None,
        'typeset_url': f"/images/{user_id}/{image.typeset_path}" if image.typeset_path else None,
    }
    return urls

@webtoon_bp.route('/job/<job_id>/image/<int:image_id>/typeset', methods=['GET', 'POST'])
@require_auth
def typeset_overrides(job_id, image_id):
                                                                              
    user_id = get_current_user_id()

    with db_session_scope() as session_db:
        job = session_db.query(WebtoonJob).filter_by(job_id=job_id, user_id=user_id).first()
        if not job:
            return jsonify({'error': 'Webtoon not found'}), 404

        image = session_db.query(WebtoonImage).filter_by(id=image_id, job_id=job_id).first()
        if not image:
            return jsonify({'error': 'Image not found'}), 404

        if request.method == 'GET':
            ocr_data = {}
            if image.ocr_text:
                try:
                    ocr_data = json.loads(image.ocr_text)
                except Exception:
                    ocr_data = {}
            translated_data = []
            if image.translated_text:
                try:
                    translated_data = json.loads(image.translated_text)
                except Exception:
                    translated_data = []

            return jsonify({
                'success': True,
                'image_id': image.id,
                'job_id': job_id,
                'paths': build_image_urls(user_id, image),
                'ocr_regions': ocr_data.get('regions', []) if isinstance(ocr_data, dict) else ocr_data,
                'translated_regions': translated_data,
                'overrides': image.typeset_overrides or {'regions': [], 'strokes': []},
                'fonts': ['DejaVuSans'],                                                 
            })

        data = request.get_json() or {}
        overrides = normalize_typeset_overrides(data)
        image.typeset_overrides = overrides
        image.typeset_status = None
        session_db.commit()

        return jsonify({
            'success': True,
            'overrides': overrides
        })

@webtoon_bp.route('/job/<job_id>/image/<int:image_id>/typeset/render', methods=['POST'])
@require_auth
def typeset_render(job_id, image_id):
                                                                   
    user_id = get_current_user_id()

    with db_session_scope() as session_db:
        job = session_db.query(WebtoonJob).filter_by(job_id=job_id, user_id=user_id).first()
        if not job:
            return jsonify({'error': 'Webtoon not found'}), 404

        image = session_db.query(WebtoonImage).filter_by(id=image_id, job_id=job_id).first()
        if not image:
            return jsonify({'error': 'Image not found'}), 404

                                                           
        data = request.get_json() or {}
        print(f"🔍 Typeset render - raw data keys: {data.keys() if isinstance(data, dict) else 'not dict'}")
        print(f"🔍 Typeset render - regions count in data: {len(data.get('regions', []))}")
        
        replace_flag = bool(data.get('replace')) if isinstance(data, dict) else False
        overrides = normalize_typeset_overrides(data.get('overrides') or data) or (image.typeset_overrides or {'regions': [], 'strokes': []})
        
        print(f"🔍 Typeset render - normalized regions count: {len(overrides.get('regions', []))}")
        for i, r in enumerate(overrides.get('regions', [])[:3]):                   
            print(f"🔍 Region {i}: bbox={r.get('bbox')}, text='{r.get('user_text', '')[:30]}...', font_size={r.get('font_size')}")

                                                                          
        base_dir = get_user_images_dir(user_id)
        base_rel = image.translated_path or image.original_path
        if not base_rel:
            return jsonify({'error': 'No image available to typeset'}), 400
        base_abs = os.path.join(base_dir, base_rel)
        
        print(f"🔍 Typeset render - base image: {base_abs}")
        print(f"🔍 Typeset render - base image exists: {os.path.exists(base_abs)}")

                     
        typeset_dir = os.path.join(base_dir, 'webtoons', job_id, 'typeset')
        os.makedirs(typeset_dir, exist_ok=True)
        base_name, _ = os.path.splitext(os.path.basename(base_rel))
        output_filename = f"{base_name}_typeset.webp"
        output_abs = os.path.join(typeset_dir, output_filename)
        
        print(f"🔍 Typeset render - output path: {output_abs}")

        fonts_root = os.path.join(os.getcwd(), 'static', 'fonts')

        try:
            render_typeset_image(
                original_path=base_abs,
                output_path=output_abs,
                overrides=overrides,
                fonts_root=fonts_root
            )
        except Exception as e:
            image.typeset_status = 'failed'
            session_db.commit()
            return jsonify({'error': f'Typeset render failed: {str(e)}'}), 500

                            
        new_typeset_rel = os.path.relpath(output_abs, base_dir)
        image.typeset_path = new_typeset_rel
        image.typeset_overrides = overrides
        image.typeset_status = 'completed'
        
        if replace_flag:
                                                      
            old_base = base_abs
            old_translated = os.path.join(base_dir, image.translated_path) if image.translated_path and image.translated_path != base_rel else None
            
                                                              
            image.original_path = new_typeset_rel
            image.translated_path = new_typeset_rel
            image.typeset_path = None                                     
            
                                                                    
            try:
                if old_base and os.path.exists(old_base) and os.path.abspath(old_base) != os.path.abspath(output_abs):
                    os.remove(old_base)
                    print(f"🗑️ Deleted old base: {old_base}")
                if old_translated and os.path.exists(old_translated) and os.path.abspath(old_translated) != os.path.abspath(output_abs):
                    os.remove(old_translated)
                    print(f"🗑️ Deleted old translated: {old_translated}")
            except Exception as del_err:
                print(f"⚠️ Error deleting old files: {del_err}")
        
        session_db.commit()

        return jsonify({
            'success': True,
            'typeset_path': image.typeset_path,
            'url': f"/images/{user_id}/{new_typeset_rel}",
            'translated_url': f"/images/{user_id}/{image.translated_path}" if image.translated_path else None,
            'replaced': replace_flag
        })

def normalize_glossary_payload(payload):
                                                  
    if not isinstance(payload, list):
        return []
    normalized = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        korean = (entry.get('korean_name') or '').strip()
        english = (entry.get('english_name') or '').strip()
        gender = (entry.get('gender') or 'auto').strip().lower()
        if not korean or not english:
            continue
        if gender not in ['male', 'female', 'other', 'auto']:
            gender = 'auto'
        normalized.append({
            'korean_name': korean,
            'english_name': english,
            'gender': gender
        })
    return normalized

@webtoon_bp.route('/<job_id>/glossary', methods=['GET', 'POST'])
@require_auth
def webtoon_glossary(job_id):
                                                         
    user_id = get_current_user_id()

    with db_session_scope() as session_db:
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()

        if not job:
            return jsonify({'error': 'Webtoon not found'}), 404

        if request.method == 'GET':
            return jsonify({
                'success': True,
                'glossary': job.glossary or []
            })

        data = request.get_json() or {}
        entries = normalize_glossary_payload(data.get('glossary', []))
        job.glossary = entries
        session_db.commit()

        return jsonify({
            'success': True,
            'glossary': entries,
            'message': 'Glossary updated'
        })

@webtoon_bp.route('/settings', methods=['GET', 'POST'])
@require_auth
def manage_ocr_settings():
                                           
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
        if request.method == 'GET':
            settings = session_db.query(UserOCRSettings).filter_by(user_id=user_id).first()
            
            if not settings:
                return jsonify({
                    'default_ocr_method': 'google',
                    'google_api_key_configured': False,
                    'azure_api_key_configured': False,
                    'gemini_api_key_configured': False,
                    'nanobananapro_api_source': 'gemini'
                }), 200
            
            return jsonify({
                'default_ocr_method': settings.default_ocr_method,
                'google_api_key_configured': bool(settings.google_api_key),
                'azure_api_key_configured': bool(settings.azure_api_key),
                'azure_endpoint': settings.azure_endpoint,                                          
                'gemini_api_key_configured': bool(settings.gemini_api_key),
                'nanobananapro_api_source': settings.nanobananapro_api_source or 'gemini'
            }), 200
        
        elif request.method == 'POST':
            data = request.json
            
            settings = session_db.query(UserOCRSettings).filter_by(user_id=user_id).first()
            
            if not settings:
                settings = UserOCRSettings(user_id=user_id)
                session_db.add(settings)
            
                                                
                                                                
            if 'google_api_key' in data and data['google_api_key'] and data['google_api_key'].strip():
                settings.google_api_key = encrypt_value(data['google_api_key'].strip())
                print(f"✅ Updated Google API key for user {user_id}")
            
            if 'azure_api_key' in data and data['azure_api_key'] and data['azure_api_key'].strip():
                settings.azure_api_key = encrypt_value(data['azure_api_key'].strip())
                print(f"✅ Updated Azure API key for user {user_id}")
            
            if 'azure_endpoint' in data and data['azure_endpoint'] and data['azure_endpoint'].strip():
                settings.azure_endpoint = data['azure_endpoint'].strip()
                print(f"✅ Updated Azure endpoint for user {user_id}")
            
            if 'gemini_api_key' in data and data['gemini_api_key'] and data['gemini_api_key'].strip():
                settings.gemini_api_key = encrypt_value(data['gemini_api_key'].strip())
                print(f"✅ Updated Gemini API key for user {user_id}")
            
            if 'default_ocr_method' in data:
                settings.default_ocr_method = data['default_ocr_method']
                print(f"✅ Updated default OCR method to {data['default_ocr_method']} for user {user_id}")
            

            
            if 'nanobananapro_api_source' in data:
                api_source = data['nanobananapro_api_source']
                if api_source in ['gemini', 'openrouter']:
                    settings.nanobananapro_api_source = api_source
                    print(f"✅ Updated Nano Banana Pro API source to {api_source} for user {user_id}")
            
            try:
                session_db.commit()
                return jsonify({'message': 'Settings updated successfully', 'success': True}), 200
            except Exception as e:
                session_db.rollback()
                print(f"Error saving OCR settings: {str(e)}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'Failed to save settings: {str(e)}'}), 500

@webtoon_bp.route('/jobs', methods=['GET'])
@require_auth
def list_user_jobs():
                                                    
    user_id = get_current_user_id()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    with db_session_scope() as session_db:
        jobs = session_db.query(WebtoonJob).filter_by(
            user_id=user_id
        ).order_by(
            WebtoonJob.created_at.desc()
        ).offset((page - 1) * per_page).limit(per_page).all()
        
        total = session_db.query(WebtoonJob).filter_by(user_id=user_id).count()
        
        job_data = [{
            'job_id': job.job_id,
            'status': job.status,
            'total_images': job.total_images,
            'processed_images': job.processed_images,
            'failed_images': job.failed_images,
            'ocr_method': job.ocr_method,
            'source_language': job.source_language,
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None
        } for job in jobs]
        
        return jsonify({
            'jobs': job_data,
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page
        }), 200

@webtoon_bp.route('/job/<job_id>', methods=['DELETE'])
@require_auth
def delete_webtoon_job(job_id):
                                                 
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
                                           
        from services.image_service import get_user_images_dir
        import shutil
        import os
        
        webtoon_dir = os.path.join(get_user_images_dir(user_id), 'webtoons', job_id)
        if os.path.exists(webtoon_dir):
            try:
                shutil.rmtree(webtoon_dir)
            except Exception as e:
                print(f"Warning: Could not delete webtoon directory: {e}")
        
                                                                         
        session_db.delete(job)
        session_db.commit()
        
        return jsonify({
            'success': True,
            'message': 'Webtoon deleted successfully'
        }), 200

@webtoon_bp.route('/job/<job_id>/export', methods=['GET'])
@require_auth
def export_webtoon_job(job_id):
                                                    
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
        job = session_db.query(WebtoonJob).filter_by(
            job_id=job_id,
            user_id=user_id
        ).first()
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
                                  
        images = session_db.query(WebtoonImage).filter_by(
            job_id=job_id,
            status='completed'
        ).order_by(WebtoonImage.id.asc()).all()
        
        if not images:
            return jsonify({'error': 'No completed images to export'}), 400
        
                         
        from services.image_service import get_user_images_dir
        import zipfile
        import io
        import os
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for img in images:
                if img.translated_path:
                    image_path = os.path.join(get_user_images_dir(user_id), img.translated_path)
                    if os.path.exists(image_path):
                        zip_file.write(image_path, img.original_filename)
        
        zip_buffer.seek(0)
        
        from flask import Response
        return Response(
            zip_buffer.getvalue(),
            mimetype='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename=webtoon_{job_id[:8]}.zip'
            }
        )

@webtoon_bp.route('/job/<job_id>/image/<int:image_id>', methods=['DELETE'])
@require_auth
def delete_webtoon_image(job_id, image_id):
                                                                   
    user_id = get_current_user_id()
    
    with db_session_scope() as session_db:
                                                
        image = session_db.query(WebtoonImage).join(WebtoonJob).filter(
            WebtoonImage.id == image_id,
            WebtoonImage.job_id == job_id,
            WebtoonJob.user_id == user_id
        ).first()
        
        if not image:
            return jsonify({'error': 'Image not found'}), 404
            
        chapter_number = image.chapter_number
        deleted_page_order = image.page_order
        
                      
        from services.image_service import get_user_images_dir
        base_dir = get_user_images_dir(user_id)
        
        files_to_delete = [image.original_path, image.translated_path]
        try:
            for path in files_to_delete:
                if path:
                    abs_path = os.path.join(base_dir, path)
                    if os.path.exists(abs_path):
                        os.remove(abs_path)
        except Exception as e:
            print(f"Error deleting image files: {e}")
            
                          
        session_db.delete(image)
        
                                                     
        subsequent_images = session_db.query(WebtoonImage).filter(
            WebtoonImage.job_id == job_id,
            WebtoonImage.chapter_number == chapter_number,
            WebtoonImage.page_order > deleted_page_order
        ).order_by(WebtoonImage.page_order.asc()).all()
        
        for img in subsequent_images:
            img.page_order -= 1
            
                           
        job = session_db.query(WebtoonJob).filter_by(job_id=job_id).first()
        if job and job.total_images > 0:
            job.total_images -= 1
            if image.status == 'completed':
                job.processed_images = max(0, job.processed_images - 1)
            elif image.status == 'failed':
                job.failed_images = max(0, job.failed_images - 1)
                
        session_db.commit()
        
        return jsonify({'success': True}), 200

@webtoon_bp.route('/job/<job_id>/image/<int:image_id>/process', methods=['POST'])
@require_auth
def process_webtoon_image_route(job_id, image_id):
                                                                            
    user_id = get_current_user_id()
    data = request.get_json() or {}
    ocr_method = data.get('ocr_method')
    
    if not ocr_method:
        return jsonify({'error': 'ocr_method is required'}), 400
        
    with db_session_scope() as session_db:
                                                
        image = session_db.query(WebtoonImage).join(WebtoonJob).filter(
            WebtoonImage.id == image_id,
            WebtoonImage.job_id == job_id,
            WebtoonJob.user_id == user_id
        ).first()
        
        if not image:
            return jsonify({'error': 'Image not found'}), 404
            
                                                                  
                                                              
        image.status = 'pending'
        image.error_message = None                        
        session_db.commit()
        
                                         
        job = session_db.query(WebtoonJob).filter_by(job_id=job_id).first()
        source_language = job.source_language if job else 'korean'
        
                      
        from tasks.webtoon_tasks import process_webtoon_image
        task = process_webtoon_image.delay(image.id, ocr_method, user_id, source_language)
        
        return jsonify({
            'success': True,
            'message': f'Image processing started with {ocr_method}',
            'task_id': task.id
        }), 200
