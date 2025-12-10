   
from dotenv import load_dotenv

                                                              
load_dotenv()

from celery_app import celery
from database.db_models import WebtoonJob, WebtoonImage, UserOCRSettings
from database.database import db_session_scope
from services.ocr_service import ocr_service
from services.image_processing_service import image_processing_service
from services.nanobananapro_service import nanobananapro_service
from services.ai_service import translate_text
from services.encryption_service import decrypt_value
from models.settings import load_settings
from services.image_service import get_user_images_dir
import os
import json
import time
from datetime import datetime

def translate_webtoon_text(text: str, source_language: str, provider: str, api_key: str, selected_model: str, glossary=None):
           
                                                       
                                                                    
                                                                                                       
    result = translate_text(
        text,
        provider=provider,
        api_key=api_key,
        selected_model=selected_model,
        glossary=glossary,
        images=None,
        is_thinking_mode=False
    )
    
    return result

def glossary_list_to_dict(glossary_list):
           
    if not glossary_list:
        return None
    glossary_dict = {}
    for idx, entry in enumerate(glossary_list):
        if not isinstance(entry, dict):
            continue
        k = entry.get('korean_name') or ''
        e = entry.get('english_name') or ''
        g = entry.get('gender') or 'auto'
        if not k.strip() or not e.strip():
            continue
        glossary_dict[str(idx)] = {
            'korean_name': k,
            'english_name': e,
            'gender': g
        }
    return glossary_dict if glossary_dict else None

@celery.task(bind=True, max_retries=3, name='tasks.webtoon_tasks.process_webtoon_job')
def process_webtoon_job(self, job_id: str, skip_translation: bool = False):
           
    print(f"🔄 Starting webtoon job processing: {job_id}")
    with db_session_scope() as session:
        try:
                     
            job = session.query(WebtoonJob).filter_by(job_id=job_id).first()
            if not job:
                raise ValueError(f"Job {job_id} not found")
            
            print(f"📋 Found job {job_id} with {job.total_images} images")
            
                           
            job.status = 'processing'
            session.commit()
            
                                                 
            images = session.query(WebtoonImage).filter_by(
                job_id=job_id,
                status='pending'
            ).all()
            
            print(f"🖼️ Found {len(images)} pending images to process")
            
            if len(images) == 0:
                print(f"⚠️ No pending images found for job {job_id}")
                                                           
                completed = session.query(WebtoonImage).filter_by(
                    job_id=job_id,
                    status='completed'
                ).count()
                if completed > 0:
                    print(f"✅ All {completed} images already completed, marking job as complete")
                    job.status = 'completed'
                    job.processed_images = completed
                    session.commit()
                return

                                                                                      
            resolved_ocr_method = job.ocr_method
            if not resolved_ocr_method:
                ocr_settings = session.query(UserOCRSettings).filter_by(user_id=job.user_id).first()
                if ocr_settings and ocr_settings.default_ocr_method:
                    resolved_ocr_method = ocr_settings.default_ocr_method
                else:
                    resolved_ocr_method = 'google'
                job.ocr_method = resolved_ocr_method
                session.commit()

            for image in images:
                try:
                                        
                    task_result = process_webtoon_image.delay(image.id, resolved_ocr_method, job.user_id, job.source_language, skip_translation=skip_translation)
                except Exception as e:
                    print(f"❌ Error queuing image {image.id}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    image.status = 'failed'
                    image.error_message = str(e)
                    job.failed_images += 1
                    session.commit()
            
            print(f"✅ Finished queuing all images for job {job_id}")
            
        except Exception as e:
            print(f"❌ Error processing webtoon job {job_id}: {str(e)}")
            import traceback
            traceback.print_exc()
                                         
            job = session.query(WebtoonJob).filter_by(job_id=job_id).first()
            if job:
                job.status = 'failed'
                job.error_message = str(e)
                session.commit()
            raise

@celery.task(bind=True, max_retries=3, name='tasks.webtoon_tasks.process_webtoon_image')
def process_webtoon_image(self, image_id: int, ocr_method: str, user_id: str, source_language: str = 'korean', skip_translation: bool = False):
           
    start_time = time.time()
    job_id_str = None                                    
    
    with db_session_scope() as session:
        try:
                              
            image = session.query(WebtoonImage).filter_by(id=image_id).first()
            if not image:
                                                        
                print(f"❌ Image {image_id} not found; marking task failed")
                return None
            
                                                                                   
                                                                     
            job_id_str = str(image.job_id)                                                
            original_filename = str(image.original_filename)                  
            original_path_str = str(image.original_path)              

                                                                      
            base_dir = get_user_images_dir(user_id)
            original_abs_path = os.path.join(base_dir, original_path_str)
            
                           
            image.status = 'processing'
            session.commit()
            
                                                                     
            job = session.query(WebtoonJob).filter_by(job_id=job_id_str).first()
            if not job:
                raise ValueError(f"Job {job_id_str} not found")
            
                                                                    
            ocr_method_str = str(job.ocr_method) if job.ocr_method else ''
            if not ocr_method_str or ocr_method_str.lower() in ['none', 'null', '']:
                                  
                fallback_method = None
                if ocr_settings and ocr_settings.default_ocr_method:
                    fallback_method = ocr_settings.default_ocr_method
                    print(f"🔧 No OCR method provided; using user default: {fallback_method}")
                else:
                    fallback_method = 'google'
                    print("🔧 No OCR method provided or user default missing; falling back to Google Cloud Vision")
                
                ocr_method_str = fallback_method
                                                         
                job.ocr_method = fallback_method
                session.commit()
            overwrite_text = job.overwrite_text if hasattr(job, 'overwrite_text') else True
            job_glossary = job.glossary or []
            
                                     
            ocr_settings = session.query(UserOCRSettings).filter_by(user_id=user_id).first()
            
            custom_prompt = job.custom_prompt_suffix
            if not custom_prompt:
                if ocr_settings and hasattr(ocr_settings, 'custom_prompt_suffix') and ocr_settings.custom_prompt_suffix:
                    custom_prompt = ocr_settings.custom_prompt_suffix
            
                                                               
            if ocr_method == 'nanobananapro':
                                                                          
                api_source = 'gemini'           
                if ocr_settings and hasattr(ocr_settings, 'nanobananapro_api_source') and ocr_settings.nanobananapro_api_source:
                    api_source = ocr_settings.nanobananapro_api_source
                
                api_key = None
                use_openrouter = False
                
                if api_source == 'openrouter':
                                                               
                    user_settings = load_settings(user_id)
                    openrouter_key = user_settings.get('api_keys', {}).get('openrouter', '')
                    if openrouter_key:
                        api_key = openrouter_key
                        use_openrouter = True
                        print(f"   Using OpenRouter API key for Nano Banana Pro (model: google/gemini-3-pro-image-preview)")
                    else:
                        raise Exception("OpenRouter API key not configured in main settings. Please configure it in Settings → API Keys → OpenRouter")
                else:
                                                          
                    if ocr_settings and ocr_settings.gemini_api_key:
                        api_key = decrypt_value(ocr_settings.gemini_api_key) if ocr_settings.gemini_api_key else None
                        use_openrouter = False
                        print(f"   Using Gemini API key for Nano Banana Pro")
                    else:
                        raise Exception("Gemini API key not configured in OCR settings. Please configure it in Webtoon Settings → Gemini API Key")
                
                if not api_key:
                    raise Exception(f"{'OpenRouter' if api_source == 'openrouter' else 'Gemini'} API key not configured for Nano Banana Pro")
                
                                                                                                 
                                                                            
                if use_openrouter:
                                               
                    translated_output = nanobananapro_service.translate_image(
                        original_abs_path,
                        api_key,
                        source_language,
                        'English',
                        use_openrouter=True,
                        custom_prompt_suffix=custom_prompt
                    )
                    
                                                                                  
                    if isinstance(translated_output, dict) and translated_output.get('image_bytes'):
                        out_dir = os.path.join(get_user_images_dir(user_id), 'webtoons', job_id_str, 'translated')
                        os.makedirs(out_dir, exist_ok=True)
                        ext = '.png'
                        mime = translated_output.get('mime_type') or ''
                        if 'jpeg' in mime or 'jpg' in mime:
                            ext = '.jpg'
                        elif 'webp' in mime:
                            ext = '.webp'
                        output_filename = f"translated_{os.path.basename(original_filename)}"
                        base, _ = os.path.splitext(output_filename)
                        output_filename = base + ext
                        output_abs = os.path.join(out_dir, output_filename)
                        
                        print(f"💾 Saving translated image to: {output_abs}")
                        with open(output_abs, 'wb') as f:
                            f.write(translated_output['image_bytes'])
                        print(f"✅ Image saved successfully ({len(translated_output['image_bytes'])} bytes)")
                        
                                                                                 
                        image = session.query(WebtoonImage).filter_by(id=image_id).first()
                        if not image:
                            raise ValueError(f"Image {image_id} not found when updating status")
                        
                        relative_path = os.path.relpath(output_abs, get_user_images_dir(user_id))
                        print(f"📝 Updating image record: translated_path={relative_path}")
                        
                        image.translated_path = relative_path
                        image.status = 'completed'
                        image.processing_time = str(time.time() - start_time)
                        session.commit()
                        print(f"✅ Image {image_id} marked as completed")
                        
                                                                                                        
                        if os.path.exists(original_abs_path):
                            try:
                                os.remove(original_abs_path)
                                print(f"🗑️ Deleted original image: {original_abs_path}")
                                                                                                              
                            except Exception as del_err:
                                print(f"⚠️ Could not delete original image: {del_err}")
                        
                        job = session.query(WebtoonJob).filter_by(job_id=job_id_str).first()
                        if job:
                            job.processed_images += 1
                                                                                                             
                            if not job.overwrite_text:
                                job.overwrite_text = True
                                print(f"📝 Set overwrite_text=True for NanoBananaPro job")
                            session.commit()
                        check_job_completion(job_id_str, session)
                        return
                    
                                                                                          
                    translated_regions = translated_output
                    
                    output_dir = os.path.join(get_user_images_dir(user_id), 'webtoons', job_id_str)
                    os.makedirs(output_dir, exist_ok=True)
                    output_filename = f"translated_{os.path.basename(original_filename)}"
                    output_path = os.path.join(output_dir, output_filename)
                    
                    ocr_results = []
                    for region in translated_regions:
                        ocr_results.append({
                            'text': region.get('original_text', ''),
                            'bbox': region.get('bbox', [0, 0, 0, 0]),
                            'confidence': region.get('confidence', 0.9)
                        })
                    
                    final_path = image_processing_service.process_image(
                        original_abs_path,
                        ocr_results,
                        translated_regions,
                        output_path,
                        overwrite_text=overwrite_text
                    )
                    
                    relative_path = os.path.relpath(final_path, get_user_images_dir(user_id))
                    image.translated_path = relative_path
                    image.ocr_text = json.dumps(ocr_results)
                    image.translated_text = json.dumps(translated_regions)
                    image.status = 'completed'
                    image.processing_time = str(time.time() - start_time)
                    session.commit()
                    
                    job = session.query(WebtoonJob).filter_by(job_id=job_id_str).first()
                    if job:
                        job.processed_images += 1
                        session.commit()
                    
                    check_job_completion(job_id_str, session)
                    return
                else:
                                                                          
                    translated_path = process_with_nanobananapro(
                        original_path_str,                     
                        api_key,
                        user_id,
                        source_language,
                        use_openrouter,
                        custom_prompt_suffix=custom_prompt
                    )
                    
                    image.translated_path = translated_path
                                                                       
                    image.status = 'completed'
                    image.processing_time = str(time.time() - start_time)
                    
                                                                                                    
                    if os.path.exists(original_abs_path):
                        try:
                            os.remove(original_abs_path)
                            print(f"🗑️ Deleted original image: {original_abs_path}")
                                                                                                          
                        except Exception as del_err:
                            print(f"⚠️ Could not delete original image: {del_err}")
                    
                    session.commit()
                    
                                                                           
                    job = session.query(WebtoonJob).filter_by(job_id=job_id_str).first()
                    if job:
                        job.processed_images += 1
                                                                                                         
                        if not job.overwrite_text:
                            job.overwrite_text = True
                            print(f"📝 Set overwrite_text=True for NanoBananaPro job")
                        session.commit()
                    
                                                                                     
                    check_job_completion(job_id_str, session)
                    return
            
                                                           
            
                                                                                               
            original_abs_path = os.path.join(get_user_images_dir(user_id), original_path_str)
            if not os.path.exists(original_abs_path):
                raise FileNotFoundError(f"Original image not found: {original_abs_path}")
            
                                                                  
            print(f"🔍 Starting OCR for image {image_id} using {ocr_method_str} (source language: {source_language})")
            print(f"   Image path: {original_abs_path}")
            print(f"   Image exists: {os.path.exists(original_abs_path)}")
            
            api_key = None
            endpoint = None
            
                                                                 
            if ocr_method_str == 'google' and ocr_settings and ocr_settings.google_api_key:
                api_key = decrypt_value(ocr_settings.google_api_key)
                print(f"   Using Google Cloud Vision API")
            elif ocr_method_str == 'azure' and ocr_settings:
                if ocr_settings.azure_api_key:
                    api_key = decrypt_value(ocr_settings.azure_api_key)
                endpoint = ocr_settings.azure_endpoint
                print(f"   Using Azure Computer Vision API")
                print(f"   Endpoint: {endpoint}")
                print(f"   API key configured: {bool(api_key)}")
            else:
                print(f"   ⚠️ OCR method {ocr_method_str} not properly configured")
            
                                                                                       
            ocr_data = ocr_service.detect_text_with_grouping(
                original_abs_path,
                ocr_method_str,                     
                source_language,
                api_key,
                endpoint,
                enable_bubble_detection=True
            )
            
                                                   
            ocr_results = ocr_data.get('regions', [])
            bubble_groups = ocr_data.get('bubble_groups', [])
            panel_boundaries = ocr_data.get('panel_boundaries', [])
            detected_bubbles = ocr_data.get('detected_bubbles', [])
            
            detected_bubbles = ocr_data.get('detected_bubbles', [])
            
                                         
            if not ocr_results or len(ocr_results) == 0:
                                                                            
                                                                            
                output_dir = os.path.join(get_user_images_dir(user_id), 'webtoons', job_id_str)
                os.makedirs(output_dir, exist_ok=True)
                output_filename = f"translated_{os.path.basename(original_filename)}"
                output_path = os.path.join(output_dir, output_filename)
                
                                     
                import shutil
                shutil.copy2(original_abs_path, output_path)
                final_path = output_path
                
                                                              
                empty_ocr_data = {
                    'regions': [],
                    'bubble_groups': [],
                    'panel_boundaries': panel_boundaries,
                    'detected_bubbles': []
                }
                image.ocr_text = json.dumps(empty_ocr_data)
                image.translated_text = json.dumps([])
                session.commit()
            else:
                                                                  
                ocr_data_to_save = {
                    'regions': ocr_results,
                    'bubble_groups': bubble_groups,
                    'panel_boundaries': panel_boundaries,
                    'detected_bubbles': detected_bubbles
                }
                image.ocr_text = json.dumps(ocr_data_to_save)
                session.commit()
                
                                                     
                if skip_translation:
                    
                                                                
                                                                                            
                                                                                        
                    
                    output_dir = os.path.join(get_user_images_dir(user_id), 'webtoons', job_id_str)
                    os.makedirs(output_dir, exist_ok=True)
                    
                    output_filename = f"translated_{os.path.basename(original_filename)}"
                    output_path = os.path.join(output_dir, output_filename)
                    
                                         
                    import shutil
                    shutil.copy2(original_abs_path, output_path)
                    final_path = output_path
                    
                                                                           
                    image.translated_text = json.dumps([])
                    session.commit()
                else:
                                                                                             
                                                        
                    user_settings = load_settings(user_id)
                    provider = user_settings.get('selected_provider', 'openrouter')
                    api_key_translation = user_settings.get('api_keys', {}).get(provider, '')
                    selected_model = user_settings.get('provider_models', {}).get(provider, '')
                    
                    if not api_key_translation:
                        raise Exception(f"Translation API key not configured for provider: {provider}")
                    
                    glossary_dict = glossary_list_to_dict(job_glossary)
                    translated_regions = []
                    
                                                                                                                   
                    translation_sources = []
                    if bubble_groups:
                                                                                     
                        for group in bubble_groups:
                            if not group.get('region_indices'):
                                continue
                                
                                                                        
                            group_text_parts = []
                            for idx in group['region_indices']:
                                if idx < len(ocr_results):
                                    text_part = ocr_results[idx].get('text', '')
                                    if text_part:
                                        group_text_parts.append(text_part)
                            
                            if not group_text_parts:
                                continue
                                
                                                                                                         
                                                                                               
                                                                                 
                            source_text = '\n'.join(group_text_parts)
                            
                            translation_sources.append({
                                'text': source_text,
                                'bbox': group['bbox'],
                                'confidence': 1.0,                                            
                                'is_group': True
                            })
                    else:
                                                                    
                        translation_sources = ocr_results

                    for region in translation_sources:
                        source_text = region['text']
                        
                        if not source_text or not source_text.strip():
                            continue                           
                        
                                                                
                        translation_result = translate_webtoon_text(
                            source_text,
                            source_language,
                            provider=provider,
                            api_key=api_key_translation,
                            selected_model=selected_model,
                            glossary=glossary_dict
                        )
                        
                        if translation_result.get('error'):
                            raise Exception(f"Translation failed: {translation_result['error']}")
                        
                        english_text = translation_result.get('translated_text', source_text)
                        
                        if english_text and english_text.strip():
                            translated_regions.append({
                                'text': english_text,
                                'bbox': region['bbox'],
                                'confidence': region.get('confidence', 1.0)
                            })
                    
                                          
                    image.translated_text = json.dumps(translated_regions)
                    session.commit()
                
                                                                              
                    output_dir = os.path.join(get_user_images_dir(user_id), 'webtoons', job_id_str)
                    os.makedirs(output_dir, exist_ok=True)
                    
                    output_filename = f"translated_{os.path.basename(original_filename)}"
                    output_path = os.path.join(output_dir, output_filename)
                    
                    if translated_regions:
                                                                           
                                                                                                                   
                                                                                            
                        
                        final_path = image_processing_service.process_image(
                            original_abs_path,
                            ocr_results,                                                    
                            translated_regions,                                            
                            output_path,
                            overwrite_text=overwrite_text
                        )
                    else:
                                                                  
                        import shutil
                        shutil.copy2(original_abs_path, output_path)
                        final_path = output_path
            
                                                       
            relative_path = os.path.relpath(final_path, get_user_images_dir(user_id))
            
                                                                            
            image = session.query(WebtoonImage).filter_by(id=image_id).first()
            if not image:
                raise ValueError(f"Image {image_id} not found when updating")
            
            image.translated_path = relative_path
            image.status = 'completed'
            image.processing_time = str(time.time() - start_time)
            
                                    
            if not os.path.exists(final_path):
                raise FileNotFoundError(f"Translated image file was not created: {final_path}")
            
            print(f"✅ Successfully processed image {image_id}: {relative_path}")
            
                                       
            session.commit()
            
                                                                   
            job = session.query(WebtoonJob).filter_by(job_id=job_id_str).first()
            if job:
                job.processed_images += 1
                session.commit()
            
                                                                             
            check_job_completion(job_id_str, session)
            
        except Exception as e:
            print(f"❌ Error processing image {image_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            
                                                                                              
            try:
                                
                image = session.query(WebtoonImage).filter_by(id=image_id).first()
                if image:
                    image.status = 'failed'
                    image.error_message = str(e)
                    image.processing_time = str(time.time() - start_time)
                    
                                                                                      
                    failed_job_id = image.job_id
                    
                                  
                    job = session.query(WebtoonJob).filter_by(job_id=failed_job_id).first()
                    if job:
                        job.failed_images += 1
                    
                    session.commit()
            except Exception as db_error:
                print(f"❌ Error updating database after failure: {str(db_error)}")
                session.rollback()
            
                         
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
            else:
                raise

def process_with_nanobananapro(image_path: str, api_key: str, user_id: str, source_language: str = 'korean', use_openrouter: bool = False, custom_prompt_suffix: str = None) -> str:
                                                        
                       
    abs_image_path = os.path.join(get_user_images_dir(user_id), image_path)
    if not os.path.exists(abs_image_path):
        raise FileNotFoundError(f"Image not found: {abs_image_path}")
    
                                                       
    translated_image_bytes = nanobananapro_service.translate_image(
        abs_image_path,
        api_key,
        source_language=source_language,
        target_lang='English',
        use_openrouter=use_openrouter,
        custom_prompt_suffix=custom_prompt_suffix
    )
    
                           
    output_dir = os.path.join(get_user_images_dir(user_id), 'webtoons', 'nanobananapro')
    os.makedirs(output_dir, exist_ok=True)
    
    output_filename = f"translated_{os.path.basename(image_path)}"
    output_path = os.path.join(output_dir, output_filename)
    
    nanobananapro_service.save_translated_image(translated_image_bytes, output_path)
    
                          
    relative_path = os.path.relpath(output_path, get_user_images_dir(user_id))
    return relative_path

def check_job_completion(job_id: str, session):
                                                  
    try:
                                                           
        job = session.query(WebtoonJob).filter_by(job_id=job_id).first()
        if not job:
            return
        
                                                                              
        total_images = job.total_images
        
                                                             
        completed_count = session.query(WebtoonImage).filter_by(
            job_id=job_id,
            status='completed'
        ).count()
        
        failed_count = session.query(WebtoonImage).filter_by(
            job_id=job_id,
            status='failed'
        ).count()
        
        total_processed = completed_count + failed_count
        
                                                                         
        job = session.query(WebtoonJob).filter_by(job_id=job_id).first()
        if not job:
            return
        
                                                                                
        if job.processed_images != completed_count:
            print(f"⚠️ Job {job_id}: Count mismatch - job.processed_images={job.processed_images}, actual completed={completed_count}")
            job.processed_images = completed_count
        if job.failed_images != failed_count:
            print(f"⚠️ Job {job_id}: Failed count mismatch - job.failed_images={job.failed_images}, actual failed={failed_count}")
            job.failed_images = failed_count
        
        print(f"📊 Job {job_id}: {completed_count} completed, {failed_count} failed, {total_images} total")
        
        if total_processed >= total_images:
            old_status = job.status
            job.status = 'completed' if job.failed_images == 0 else 'completed_with_errors'
            job.completed_at = datetime.utcnow()
            session.commit()
            print(f"✅ Job {job_id} marked as {job.status} (was {old_status})")
    except Exception as e:
        print(f"❌ Error in check_job_completion for job {job_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        session.rollback()
        raise

