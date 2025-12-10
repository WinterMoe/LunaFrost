

from database.database import db_session_scope
from database.db_models import Novel, Chapter, TranslationTokenUsage
from sqlalchemy import and_
from sqlalchemy.orm import joinedload

def get_user_novels_db(user_id):

    with db_session_scope() as session:
        novels = session.query(Novel).filter_by(user_id=user_id).order_by(Novel.created_at.desc()).all()
        return [n.to_dict() for n in novels]

def get_novel_db(user_id, slug):

    with db_session_scope() as session:
        novel = session.query(Novel).filter(
            and_(Novel.user_id == user_id, Novel.slug == slug)
        ).first()
        return novel.to_dict() if novel else None

def get_novel_with_chapters_db(user_id, slug):

    with db_session_scope() as session:
        novel = session.query(Novel).filter(
            and_(Novel.user_id == user_id, Novel.slug == slug)
        ).first()
        if not novel:
            return None
        novel_dict = novel.to_dict()
        chapters = session.query(Chapter).filter_by(novel_id=novel.id).order_by(Chapter.position).all()
        novel_dict['chapters'] = [c.to_dict(include_content=True) for c in chapters]
        return novel_dict

def create_novel_db(user_id, novel_data):

    with db_session_scope() as session:
        novel = Novel(
            user_id=user_id,
            slug=novel_data['slug'],
            title=novel_data.get('title', ''),
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
            glossary=novel_data.get('glossary', {})
        )
        session.add(novel)
        session.flush()
        return novel.to_dict()

def update_novel_db(user_id, slug, updates):

    with db_session_scope() as session:
        novel = session.query(Novel).filter(
            and_(Novel.user_id == user_id, Novel.slug == slug)
        ).first()
        if not novel:
            return None
        allowed_fields = [
            'title', 'original_title', 'translated_title', 'author', 'translated_author',
            'cover_url', 'tags', 'translated_tags', 'synopsis', 'translated_synopsis',
            'source_url', 'slug', 'glossary'
        ]
        for field in allowed_fields:
            if field in updates:
                setattr(novel, field, updates[field])
        session.flush()
        return novel.to_dict()

def delete_novel_db(user_id, slug):

    with db_session_scope() as session:
        novel = session.query(Novel).filter(
            and_(Novel.user_id == user_id, Novel.slug == slug)
        ).first()
        if not novel:
            return False

        if novel.share_token:
            shared_copies = session.query(Novel).filter(
                Novel.imported_from_share_token == novel.share_token
            ).all()
            
            for shared_novel in shared_copies:
                shared_chapter_ids = [c.id for c in session.query(Chapter.id).filter_by(novel_id=shared_novel.id).all()]
                if shared_chapter_ids:
                    session.query(TranslationTokenUsage).filter(
                        TranslationTokenUsage.chapter_id.in_(shared_chapter_ids)
                    ).delete(synchronize_session=False)
                session.delete(shared_novel)

        chapter_ids = [c.id for c in session.query(Chapter.id).filter_by(novel_id=novel.id).all()]

        if chapter_ids:
            session.query(TranslationTokenUsage).filter(
                TranslationTokenUsage.chapter_id.in_(chapter_ids)
            ).delete(synchronize_session=False)

        session.delete(novel)
        return True

def find_novel_by_source_url_db(user_id, source_url):

    with db_session_scope() as session:
        novel = session.query(Novel).filter(
            and_(Novel.user_id == user_id, Novel.source_url == source_url)
        ).first()
        return novel.to_dict() if novel else None

def get_next_chapter_position_db(novel_id):

    with db_session_scope() as session:
        max_position = session.query(Chapter.position).filter_by(novel_id=novel_id).order_by(Chapter.position.desc()).first()
        return (max_position[0] + 1) if max_position else 0

def find_novel_by_title_db(user_id, title):

    with db_session_scope() as session:
        novel = session.query(Novel).filter(
            and_(
                Novel.user_id == user_id,
                (Novel.title == title) |
                (Novel.original_title == title) |
                (Novel.translated_title == title)
            )
        ).first()
        return novel.to_dict() if novel else None

def parse_chapter_number(num_str):

    if not num_str:
        return 999999.0
    if num_str == 'BONUS':
        return 999999.0
    try:
        return float(num_str)
    except (ValueError, TypeError):
        return 999999.0

def add_chapter_atomic(user_id, novel_slug, chapter_data):

    with db_session_scope() as session:
        novel = session.query(Novel).filter(
            and_(Novel.user_id == user_id, Novel.slug == novel_slug)
        ).with_for_update().first()
        if not novel:
            raise ValueError(f"Novel not found: {novel_slug}")
        
        source_url = chapter_data.get('source_url')
        
        if source_url:
            existing_chapter = session.query(Chapter).filter(
                and_(Chapter.novel_id == novel.id, Chapter.source_url == source_url)
            ).first()
            if existing_chapter:
                return {
                    'success': True,
                    'message': 'Chapter already exists - skipped',
                    'already_exists': True,
                    'novel_id': novel.slug,
                    'chapter_index': existing_chapter.position,
                    'chapter_id': existing_chapter.id
                }
        
        position = chapter_data.get('position')
        
        if position is None:
            new_episode_id = extract_episode_id_from_url(chapter_data.get('source_url'))
            
            
            existing_chapters = session.query(Chapter).filter(
                Chapter.novel_id == novel.id
            ).order_by(Chapter.position).all()
            
            
            insert_pos = len(existing_chapters)
            
            if new_episode_id is not None:
                for idx, existing_ch in enumerate(existing_chapters):
                    existing_episode_id = extract_episode_id_from_url(existing_ch.source_url)
                    
                    
                    if existing_episode_id is None:
                        continue
                    
                    if new_episode_id < existing_episode_id:
                        insert_pos = idx
                        break
            else:
                new_chapter_num = parse_chapter_number(chapter_data.get('chapter_number'))
                
                for idx, existing_ch in enumerate(existing_chapters):
                    existing_ch_num = parse_chapter_number(existing_ch.chapter_number)
                    
                    if new_chapter_num < existing_ch_num:
                        insert_pos = idx
                        break
            
            
            if insert_pos < len(existing_chapters):
                
                chapters_to_shift = session.query(Chapter).filter(
                    and_(Chapter.novel_id == novel.id, Chapter.position >= insert_pos)
                ).order_by(Chapter.position.desc()).all()
                
                for ch in chapters_to_shift:
                    temp_position = -(ch.position + 1000)                                            
                    ch.position = temp_position
                
                session.flush()
                
                for ch in chapters_to_shift:
                    original_position = abs(ch.position) - 1000
                    final_position = original_position + 1
                    ch.position = final_position
                
                session.flush()
            
            position = insert_pos
        
        new_chapter = Chapter(
            novel_id=novel.id,
            slug=chapter_data['slug'],
            title=chapter_data.get('title', ''),
            original_title=chapter_data.get('original_title'),
            translated_title=chapter_data.get('translated_title'),
            chapter_number=chapter_data.get('chapter_number'),
            content=chapter_data.get('content', ''),
            images=chapter_data.get('images', []),
            source_url=source_url,
            position=position,
            is_bonus=chapter_data.get('is_bonus', False)
        )
        session.add(new_chapter)
        session.flush()
        
        
        verify_order(session, novel.id)
        
        return {
            'success': True,
            'message': 'Chapter imported successfully',
            'novel_id': novel.slug,
            'chapter_index': new_chapter.position,
            'chapter_id': new_chapter.id
        }

def verify_order(session, novel_id):

    chapters = session.query(Chapter).filter_by(novel_id=novel_id).order_by(Chapter.position).all()
    for ch in chapters:
        episode_id = extract_episode_id_from_url(ch.source_url)

def create_chapter_db(user_id, novel_slug, chapter_data):

    return add_chapter_atomic(user_id, novel_slug, chapter_data)

def get_chapter_db(chapter_id):

    with db_session_scope() as session:
        chapter = session.query(Chapter).filter_by(id=chapter_id).first()
        return chapter.to_dict(include_content=True) if chapter else None

def update_chapter_db(chapter_id, updates):

    with db_session_scope() as session:
        chapter = session.query(Chapter).filter_by(id=chapter_id).first()
        if not chapter:
            return None
        
        allowed_fields = [
            'title', 'original_title', 'translated_title', 'chapter_number',
            'content', 'translated_content', 'translation_model',
            'images', 'source_url', 'position', 'is_bonus', 'slug',
            'translation_status', 'translation_task_id', 
            'translation_started_at', 'translation_completed_at'
        ]
        
        for field in allowed_fields:
            if field in updates:
                setattr(chapter, field, updates[field])
        
        session.flush()
        return chapter.to_dict(include_content=True)

def delete_chapter_db(chapter_id):

    with db_session_scope() as session:
        chapter = session.query(Chapter).filter_by(id=chapter_id).first()
        if not chapter:
            return False

        session.query(TranslationTokenUsage).filter_by(chapter_id=chapter_id).delete()

        session.delete(chapter)
        return True

def get_chapters_for_novel_db(user_id, novel_slug):

    with db_session_scope() as session:
        novel = session.query(Novel).filter(
            and_(Novel.user_id == user_id, Novel.slug == novel_slug)
        ).first()
        if not novel:
            return []
        
        chapters = session.query(Chapter).filter_by(
            novel_id=novel.id
        ).order_by(Chapter.position).all()
        
        return [c.to_dict(include_content=True) for c in chapters]

def extract_episode_id_from_url(source_url):

    if not source_url:
        return None
    
    import re
    match = re.search(r'/viewer/(\d+)', source_url)
    if match:
        return int(match.group(1))
    return None

def debug_chapter_positions(session, novel_id):

    chapters = session.query(Chapter).filter_by(novel_id=novel_id).order_by(Chapter.position).all()
    for ch in chapters:
        episode_id = extract_episode_id_from_url(ch.source_url)

def diagnose_chapter_order(user_id, novel_slug):

    with db_session_scope() as session:
        novel = session.query(Novel).filter(
            and_(Novel.user_id == user_id, Novel.slug == novel_slug)
        ).first()
        
        if not novel:
            return
        
        chapters = session.query(Chapter).filter_by(novel_id=novel.id).order_by(Chapter.position).all()
        
        
        for ch in chapters:
            episode_id = extract_episode_id_from_url(ch.source_url)
            ch_num = str(ch.chapter_number) if ch.chapter_number else 'N/A'
            title = (ch.title[:47] + '...') if len(ch.title) > 50 else ch.title
