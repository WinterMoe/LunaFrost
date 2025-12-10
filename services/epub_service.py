

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

def extract_text_from_html(html_content: str) -> str:

    soup = BeautifulSoup(html_content, 'html.parser')

                                      
    for script in soup(["script", "style"]):
        script.decompose()

                                      
    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = '\n'.join(chunk for chunk in chunks if chunk)

    return text

def extract_images_from_html(html_content: str, epub_book) -> List[Dict]:

    import sys
    soup = BeautifulSoup(html_content, 'html.parser')
    images = []

                         
    img_tags = soup.find_all('img')
    print(f"[EPUB] Found {len(img_tags)} img tags in HTML", file=sys.stderr, flush=True)

    for img in img_tags:
        src = img.get('src') or img.get('href')
        print(f"[EPUB] Processing image tag with src: {src}", file=sys.stderr, flush=True)

        if src:
                                                        
            try:
                                               
                original_src = src
                if src.startswith('../'):
                    src = src[3:]
                elif src.startswith('./'):
                    src = src[2:]

                print(f"[EPUB] Looking for image: {src} (original: {original_src})", file=sys.stderr, flush=True)

                                                   
                found = False
                for item in epub_book.get_items():
                    item_name = item.get_name()
                    if item_name == src or item_name.endswith(src) or src.endswith(item_name):
                        print(f"[EPUB] Found matching image: {item_name}", file=sys.stderr, flush=True)
                        images.append({
                            'name': src,
                            'data': item.get_content(),
                            'media_type': item.media_type
                        })
                        found = True
                        break

                if not found:
                    print(f"[EPUB] WARNING: Image not found in EPUB: {src}", file=sys.stderr, flush=True)

            except Exception as e:
                print(f"[EPUB] ERROR: Failed to extract image {src}: {e}", file=sys.stderr, flush=True)

    print(f"[EPUB] Successfully extracted {len(images)} images", file=sys.stderr, flush=True)
    return images

def detect_chapter_number(title: str, position: int) -> str:

    if not title:
        return str(position)

    title_lower = title.lower()

                                      
    if 'bonus' in title_lower or '보너스' in title:
                                                 
        bonus_match = re.search(r'bonus\s*(\d+)|보너스\s*(\d+)', title, re.IGNORECASE)
        if bonus_match:
            num = bonus_match.group(1) or bonus_match.group(2)
            return f"BONUS-{num}"
        return "BONUS"

    if 'prologue' in title_lower or '프롤로그' in title:
        return "0"

    if 'epilogue' in title_lower or '에필로그' in title:
        return "999"

                                                                                          
                                                                                                             
    start_patterns = [
        r'^chapter\s+(\d+)',
        r'^ep\.?\s*(\d+)',
        r'^제\s*(\d+)\s*화',
        r'^(\d+)\s*화',
        r'^제\s*(\d+)\s*장',
        r'^(\d+)\s*장',
    ]

    for pattern in start_patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return match.group(1)

                                                                            
                                                                                                      
    return str(position)

def clean_chapter_title(title: str) -> str:

    if not title:
        return title

                                              
    patterns = [
        r'^제\s*\d+\s*화\s*[:\-–—]?\s*',
        r'^\d+\s*화\s*[:\-–—]?\s*',
        r'^제\s*\d+\s*장\s*[:\-–—]?\s*',
        r'^\d+\s*장\s*[:\-–—]?\s*',
        r'^chapter\s+\d+\s*[:\-–—]?\s*',
        r'^ch\.?\s+\d+\s*[:\-–—]?\s*',
        r'^episode\s+\d+\s*[:\-–—]?\s*',
    ]

    cleaned = title
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE).strip()
        if cleaned:                                                 
            return cleaned

    return title

def parse_epub(file_path: str) -> Dict:

    try:
        book = epub.read_epub(file_path)

                          
        title = book.get_metadata('DC', 'title')
        title = title[0][0] if title else 'Untitled'

        author = book.get_metadata('DC', 'creator')
        author = author[0][0] if author else 'Unknown'

        description = book.get_metadata('DC', 'description')
        synopsis = description[0][0] if description else ''

        language = book.get_metadata('DC', 'language')
        language = language[0][0] if language else 'ko'

                          
        chapters = []
        position = 1

                                               
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        logger.info(f"Total EPUB document items: {len(items)}")

        for idx, item in enumerate(items):
            try:
                content_html = item.get_content().decode('utf-8', errors='ignore')
                content_text = extract_text_from_html(content_html)
                item_name = item.get_name()

                logger.info(f"Item {idx}: name={item_name}, content_length={len(content_text)}")

                                                                              
                                                                   
                if len(content_text.strip()) < 30:
                    logger.info(f"  -> Skipped (too short: {len(content_text)} chars)")
                    continue
            except Exception as e:
                logger.error(f"Error processing item {idx}: {e}")
                continue

                                                         
            item_title = item.get_name()
            item_title_lower = item_title.lower()

                                                                     
            skip_keywords = ['toc', 'nav', 'index', 'contents', 'copyright', 'cover', 'title']
            if any(keyword in item_title_lower for keyword in skip_keywords):
                logger.info(f"  -> Skipped (non-chapter file: {item_title})")
                continue

                                                     
            soup = BeautifulSoup(content_html, 'html.parser')

                                                                  
            chapter_title = ''
            for tag in ['h1', 'h2', 'h3', 'p']:
                element = soup.find(tag)
                if element and element.get_text().strip():
                    text = element.get_text().strip()
                                                                                                      
                    if any(keyword in text.lower() for keyword in ['chapter', '장', '화', 'prologue', 'epilogue', 'bonus', '보너스', '프롤로그', '에필로그']):
                        chapter_title = text
                        break
                                                                            
                    elif tag in ['h1', 'h2', 'h3'] and len(text) < 200:
                        chapter_title = text
                        break

                                               
            if not chapter_title:
                title_tag = soup.find('title')
                if title_tag and title_tag.get_text().strip():
                    chapter_title = title_tag.get_text().strip()
                else:
                    chapter_title = item_title

                                                                           
            chapter_title_lower = chapter_title.lower()
            if any(keyword in chapter_title_lower for keyword in ['table of contents', 'index', '목차', 'contents']):
                logger.info(f"  -> Skipped (TOC/index page: {chapter_title})")
                continue

                                                                
            chapter_number = detect_chapter_number(chapter_title, position)

                                                                                          
            cleaned_title = clean_chapter_title(chapter_title)

                                                             
            if not cleaned_title:
                if 'bonus' in chapter_title.lower() or '보너스' in chapter_title:
                    cleaned_title = 'Bonus Chapter'
                elif 'prologue' in chapter_title.lower() or '프롤로그' in chapter_title:
                    cleaned_title = 'Prologue'
                elif 'epilogue' in chapter_title.lower() or '에필로그' in chapter_title:
                    cleaned_title = 'Epilogue'
                else:
                    cleaned_title = f"Chapter {position}"
                                                                                                   
                                                                                    

                                                                                 
            chapter_images = extract_images_from_html(content_html, book)
                                                                                     
            image_count = len(chapter_images)

            chapters.append({
                'number': chapter_number,
                'title': cleaned_title,
                'original_title': chapter_title,
                'content': content_text,
                'position': position,
                'image_count': image_count,                              
                'epub_item_name': item_name                                                                           
            })

            logger.info(f"Found chapter {position}: Number={chapter_number}, Title={cleaned_title}, OriginalTitle={chapter_title[:50] if len(chapter_title) > 50 else chapter_title}, ContentLength={len(content_text)}")
            position += 1

        logger.info(f"Total chapters found: {len(chapters)}")
        logger.info(f"Total EPUB items processed: {len(items)}")

        return {
            'success': True,
            'title': title,
            'author': author,
            'synopsis': synopsis,
            'language': language,
            'chapters': chapters,
            'chapter_count': len(chapters)
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def find_duplicate_chapters(epub_chapters: List[Dict], existing_chapters: List[Dict]) -> Tuple[List[Dict], List[Dict]]:

    new_chapters = []
    duplicate_chapters = []

                                                              
    existing_lookup = set()
    for ch in existing_chapters:
        if ch:
            ch_num = str(ch.get('chapter_number', ''))
            ch_title = ch.get('title', '').strip()
            existing_lookup.add((ch_num, ch_title))

    for epub_ch in epub_chapters:
        ch_num = str(epub_ch['number'])
        ch_title = epub_ch['title'].strip()

        if (ch_num, ch_title) in existing_lookup:
            duplicate_chapters.append(epub_ch)
        else:
            new_chapters.append(epub_ch)

    return new_chapters, duplicate_chapters