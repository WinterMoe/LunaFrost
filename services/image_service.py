import os
import re
import requests
from io import BytesIO
from PIL import Image
from utils.url_validator import is_safe_url

DATA_DIR = 'data'

def get_user_images_dir(user_id):

    return os.path.join(DATA_DIR, 'users', user_id, 'images')

def save_upload_strip_metadata(file_storage, dest_path):
           
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                                                                               
    file_storage.stream.seek(0)
    raw_bytes = file_storage.stream.read()
    file_storage.stream.seek(0)

    try:
        with Image.open(BytesIO(raw_bytes)) as im:
            im.load()
            fmt = (im.format or 'PNG').upper()

            save_kwargs = {'icc_profile': None}

            if fmt in ('JPEG', 'JPG'):
                save_kwargs.update({
                    'format': 'JPEG',
                    'quality': 95,
                    'subsampling': 'keep',
                    'optimize': True,
                    'progressive': True,
                    'exif': None
                })
            elif fmt == 'PNG':
                save_kwargs.update({
                    'format': 'PNG',
                    'optimize': True,
                })
            elif fmt == 'WEBP':
                lossless = bool(im.info.get('lossless', False))
                save_kwargs.update({
                    'format': 'WEBP',
                    'lossless': lossless,
                    'quality': im.info.get('quality', 100 if lossless else 95),
                    'method': 6,
                    'exif': None
                })
            else:
                save_kwargs['format'] = fmt

            im.save(dest_path, **save_kwargs)
            return True
    except Exception:
                                                     
        file_storage.save(dest_path)
        return False

def download_image(image_url, user_id, overwrite=False):

    try:
        if image_url.startswith('//'):
            image_url = 'https:' + image_url
        
        is_safe, message = is_safe_url(image_url)
        if not is_safe:
            print(f'[Security] Blocked image download: {message} - URL: {image_url}')
            return None
        
        filename = os.path.basename(image_url.split('?')[0])
        if not filename:
            from datetime import datetime
            filename = f"image_{datetime.now().timestamp()}.jpg"
        
        safe_filename = re.sub(r'[^\w\.-]', '_', filename)
        images_dir = get_user_images_dir(user_id)
        local_path = os.path.join(images_dir, safe_filename)
        
        if overwrite or not os.path.exists(local_path):
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://novelpia.com/'
            }
            
            response = requests.get(image_url, headers=headers, timeout=10)
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(response.content)
        
        return safe_filename
    except Exception as e:
        print(f'[Error] Image download failed: {str(e)}')
        return None

def extract_images_from_content(content, user_id):

    images = []
    
    image_patterns = [
        r'//images\.novelpia\.com/imagebox/cover/[^\s<>"\']+',
        r'https?://images\.novelpia\.com/imagebox/cover/[^\s<>"\']+',
    ]
    
    for pattern in image_patterns:
        matches = re.finditer(pattern, content)
        for match in matches:
            img_url = match.group(0)
            local_filename = download_image(img_url, user_id)
            if local_filename:
                images.append({
                    'url': img_url,
                    'local_path': local_filename,
                    'position': match.start()
                })
    
    return images

def delete_images_for_chapter(chapter, user_id):

    if not chapter or not chapter.get('images'):
        return

    images_dir = get_user_images_dir(user_id)

    for img in chapter['images']:
                                                                         
        if isinstance(img, str):
            img_filename = img
        else:
            img_filename = img.get('local_path', '')

        if img_filename:
            img_path = os.path.join(images_dir, img_filename)
            if os.path.exists(img_path):
                try:
                    os.remove(img_path)
                except Exception as e:
                    pass                                   

def delete_images_for_novel(novel, user_id):

    if not novel or not novel.get('chapters'):
        return
    
    for chapter in novel['chapters']:
        if chapter:
            delete_images_for_chapter(chapter, user_id)

def download_images_parallel(image_data_list, user_id, max_workers=5):

    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    if not image_data_list:
        return []
    
    images = []
    
    def download_single_image(img_data):

        img_url = img_data.get('url', '')
        if not img_url:
            return None
        
        local_filename = download_image(img_url, user_id)
        if local_filename:
            return {
                'url': img_url,
                'local_path': local_filename,
                'alt': img_data.get('alt', 'Chapter Image')
            }
        return None
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_img = {executor.submit(download_single_image, img_data): img_data 
                        for img_data in image_data_list}
        
        for future in as_completed(future_to_img):
            try:
                result = future.result()
                if result:
                    images.append(result)
            except Exception as e:
                pass                                   
                img_data = future_to_img[future]
    
    return images
