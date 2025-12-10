

import os
from database.db_novel import (
    get_user_novels_db, get_novel_db, get_novel_with_chapters_db,
    create_novel_db, update_novel_db, delete_novel_db,
    create_chapter_db, update_chapter_db, delete_chapter_db,
    find_novel_by_source_url_db, get_next_chapter_position_db
)
from database.db_models import Novel as NovelModel

DATA_DIR = 'data'

def get_user_images_dir(user_id):

    return os.path.join(DATA_DIR, 'users', user_id, 'images')

def initialize_user_data_files(user_id):

    user_dir = os.path.join(DATA_DIR, 'users', user_id)
    os.makedirs(user_dir, exist_ok=True)
    os.makedirs(os.path.join(user_dir, 'images'), exist_ok=True)

def load_novels(user_id):

    novels_list = get_user_novels_db(user_id)
    
    novels_dict = {}
    for novel in novels_list:
        novel_slug = novel['slug']
        novel_with_chapters = get_novel_with_chapters_db(user_id, novel_slug)
        if novel_with_chapters:
            novel_data = novel_with_chapters.copy()
            novels_dict[novel_slug] = novel_data
    
    return novels_dict

def save_novels(user_id, novels):

    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"save_novels called for user {user_id} with {len(novels)} novels")
    
    from database.database import db_session_scope
    from database.db_models import Novel, Chapter
    
    try:
        with db_session_scope() as session:
            for novel_slug, novel in novels.items():
                logger.info(f"Processing novel: {novel_slug}")
                logger.info(f"Novel has {len(novel.get('chapters', []))} chapters")
                
                existing_novel = session.query(Novel).filter_by(
                    user_id=user_id, slug=novel_slug
                ).first()
                
                if not existing_novel:
                    new_slug = novel.get('slug')
                    if new_slug and new_slug != novel_slug:
                        logger.info(f"Dict key slug '{novel_slug}' not found, trying updated slug '{new_slug}'")
                        existing_novel = session.query(Novel).filter_by(
                            user_id=user_id, slug=new_slug
                        ).first()
                
                if not existing_novel:
                    korean_title = novel.get('title') or novel.get('original_title')
                    if korean_title:
                        logger.info(f"Trying to find novel by Korean title: {korean_title}")
                        existing_novel = session.query(Novel).filter_by(
                            user_id=user_id, title=korean_title
                        ).first()
                
                if existing_novel:
                    existing_novel.title = novel.get('title') or novel.get('translated_title', '')
                    existing_novel.original_title = novel.get('original_title')
                    existing_novel.translated_title = novel.get('translated_title')
                    existing_novel.author = novel.get('author')
                    existing_novel.translated_author = novel.get('translated_author')
                    existing_novel.cover_url = novel.get('cover_image')
                    existing_novel.tags = novel.get('tags', [])
                    existing_novel.translated_tags = novel.get('translated_tags', [])
                    existing_novel.synopsis = novel.get('synopsis')
                    existing_novel.translated_synopsis = novel.get('translated_synopsis')
                    existing_novel.glossary = novel.get('glossary', {})
                    existing_novel.source_url = novel.get('source_url')
                    
                    new_slug = novel.get('slug')
                    if new_slug and new_slug != novel_slug:
                        existing_novel.slug = new_slug
                        logger.info(f"Updated novel slug from {novel_slug} to {new_slug}")
                    
                    novel_id = existing_novel.id
                    logger.info(f"Updated existing novel ID: {novel_id}")
                else:
                    new_novel = Novel(
                        user_id=user_id,
                        slug=novel_slug,
                        title=novel.get('title') or novel.get('translated_title', ''),
                        original_title=novel.get('original_title'),
                        translated_title=novel.get('translated_title'),
                        author=novel.get('author'),
                        translated_author=novel.get('translated_author'),
                        cover_url=novel.get('cover_image'),
                        tags=novel.get('tags', []),
                        translated_tags=novel.get('translated_tags', []),
                        synopsis=novel.get('synopsis'),
                        translated_synopsis=novel.get('translated_synopsis'),
                        glossary=novel.get('glossary', {}),
                        source_url=novel.get('source_url')
                    )
                    session.add(new_novel)
                    session.flush()          
                    novel_id = new_novel.id
                    logger.info(f"Created new novel ID: {novel_id}")
                
                chapters = novel.get('chapters', [])
                logger.info(f"Chapters type: {type(chapters)}, count: {len(chapters) if isinstance(chapters, list) else 'N/A'}")
                
                if isinstance(chapters, list):
                    for idx, chapter in enumerate(chapters):
                        if not chapter:                      
                            logger.warning(f"Skipping None chapter at index {idx}")
                            continue
                        
                        chapter_slug = chapter.get('slug')
                        if not chapter_slug:
                            logger.warning(f"Skipping chapter without slug at index {idx}")
                            continue
                        
                        logger.info(f"Processing chapter: {chapter_slug}")
                        
                        existing_chapter = session.query(Chapter).filter_by(
                            novel_id=novel_id, slug=chapter_slug
                        ).first()
                        
                        if existing_chapter:
                            existing_chapter.title = chapter.get('title') or chapter.get('translated_title', '')
                            existing_chapter.original_title = chapter.get('original_title')
                            existing_chapter.translated_title = chapter.get('translated_title')
                            existing_chapter.chapter_number = chapter.get('chapter_number')
                            existing_chapter.content = chapter.get('content', '')
                            existing_chapter.images = chapter.get('images', [])
                            existing_chapter.source_url = chapter.get('source_url')
                            existing_chapter.position = chapter.get('position', 0)
                            existing_chapter.is_bonus = chapter.get('is_bonus', False)
                            logger.info(f"Updated chapter: {chapter_slug}")
                        else:
                            new_chapter = Chapter(
                                novel_id=novel_id,
                                slug=chapter_slug,
                                title=chapter.get('title') or chapter.get('translated_title', ''),
                                original_title=chapter.get('original_title'),
                                translated_title=chapter.get('translated_title'),
                                chapter_number=chapter.get('chapter_number'),
                                content=chapter.get('content', ''),
                                images=chapter.get('images', []),
                                source_url=chapter.get('source_url'),
                                position=chapter.get('position', 0),
                                is_bonus=chapter.get('is_bonus', False)
                            )
                            session.add(new_chapter)
                            logger.info(f"Created new chapter: {chapter_slug}")
        logger.info("save_novels completed successfully")
    except Exception as e:
        logger.error(f"Error in save_novels: {e}", exc_info=True)

def get_novel_glossary(user_id, novel_slug):

    novel = get_novel_db(user_id, novel_slug)
    if novel:
        return {}
    return {}

def save_novel_glossary(user_id, novel_slug, glossary):

    update_novel_db(user_id, novel_slug, {'glossary': glossary})

def delete_novel(user_id, novel_slug):

    from services.image_service import delete_images_for_novel
    
    novel = get_novel_with_chapters_db(user_id, novel_slug)
    if novel:
        delete_images_for_novel(novel, user_id)
        
        if novel.get('cover_url'):
            cover_path = os.path.join(get_user_images_dir(user_id), novel['cover_url'])
            if os.path.exists(cover_path):
                try:
                    os.remove(cover_path)
                except Exception:
                    pass

        return delete_novel_db(user_id, novel_slug)
    return False

def delete_chapter(user_id, novel_slug, chapter_index):

    from services.image_service import delete_images_for_chapter
    from database.database import db_session_scope
    from database.db_models import Novel, Chapter
    from sqlalchemy import and_
    
    novel = get_novel_with_chapters_db(user_id, novel_slug)
    if not novel or not novel.get('chapters'):
        return False
        
    from models.settings import load_settings
    settings = load_settings(user_id)
    
    if 'sort_order_override' in novel and novel['sort_order_override'] is not None:
        order = novel['sort_order_override']
    else:
        order = settings.get('default_sort_order', 'asc')
        
    sorted_chapters = sort_chapters_by_number(novel['chapters'], order)
    
    if chapter_index >= len(sorted_chapters):
        return False
        
    chapter = sorted_chapters[chapter_index]
    chapter_id = chapter['id']
    deleted_position = chapter['position']
    
    delete_images_for_chapter(chapter, user_id)
    
    with db_session_scope() as session:
        novel_obj = session.query(Novel).filter(
            and_(Novel.user_id == user_id, Novel.slug == novel_slug)
        ).with_for_update().first()
        
        if not novel_obj:
            return False
        
        chapter_to_delete = session.query(Chapter).filter_by(id=chapter_id).first()
        if not chapter_to_delete:
            return False
        
        session.delete(chapter_to_delete)
        session.flush()
        
        remaining_chapters = session.query(Chapter).filter_by(
            novel_id=novel_obj.id
        ).order_by(Chapter.position).all()
        
        
        for idx, ch in enumerate(remaining_chapters):
            if ch.position != idx:
                ch.position = idx
        
        session.flush()
    
    return True

def get_display_title(novel):

    if isinstance(novel, NovelModel):
        return novel.translated_title or novel.title or novel.original_title or 'Untitled'
    else:
        return novel.get('translated_title') or novel.get('title') or novel.get('original_title', 'Untitled')

def sort_chapters_by_number(chapters, order='asc'):

    if not chapters:
        return chapters
    
    valid_chapters = [ch for ch in chapters if ch is not None]
    
    if valid_chapters and isinstance(valid_chapters[0], dict):
        sorted_chapters = sorted(
            valid_chapters,
            key=lambda ch: ch.get('position', 999999),
            reverse=(order == 'desc')
        )
    else:
        sorted_chapters = sorted(
            valid_chapters,
            key=lambda ch: ch.position if hasattr(ch, 'position') else 999999,
            reverse=(order == 'desc')
        )
    
    return sorted_chapters

def find_novel_by_source_url(user_id, source_url):

    return find_novel_by_source_url_db(user_id, source_url)