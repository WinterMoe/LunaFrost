

from flask import Blueprint, request, jsonify, session
from database.database import db_session_scope
from database.db_models import Novel, Chapter
from urllib.parse import unquote

merge_bp = Blueprint('merge', __name__)

def get_user_id():

    return session.get('user_id')

@merge_bp.route('/novel/<novel_id>/merge/preview', methods=['POST'])
def preview_merge(novel_id):

    try:
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        novel_id = unquote(novel_id)
        data = request.get_json()
        target_novel_id = data.get('target_novel_id')
        
        if not target_novel_id:
            return jsonify({'error': 'Target novel ID required'}), 400
        
        target_novel_id = unquote(target_novel_id)
        
        with db_session_scope() as session:
                              
            source = session.query(Novel).filter(
                Novel.slug == novel_id,
                Novel.user_id == user_id
            ).first()
            
            target = session.query(Novel).filter(
                Novel.slug == target_novel_id,
                Novel.user_id == user_id
            ).first()
            
            if not source:
                return jsonify({'error': 'Source novel not found'}), 404
            if not target:
                return jsonify({'error': 'Target novel not found'}), 404
            
                                          
            source_chapters = session.query(Chapter).filter_by(novel_id=source.id).order_by(Chapter.position).all()
            target_chapters = session.query(Chapter).filter_by(novel_id=target.id).order_by(Chapter.position).all()
            
                                                  
            source_ch_map = {}
            for ch in source_chapters:
                ch_num = ch.chapter_number
                source_ch_map[ch_num] = ch
            
            target_ch_map = {}
            for ch in target_chapters:
                ch_num = ch.chapter_number
                target_ch_map[ch_num] = ch
            
                                                
            all_chapter_numbers = set(source_ch_map.keys()) | set(target_ch_map.keys())
            
            chapter_conflicts = []
            unique_source = []
            unique_target = []
            
            for ch_num in sorted(all_chapter_numbers):
                in_source = ch_num in source_ch_map
                in_target = ch_num in target_ch_map
                
                if in_source and in_target:
                                                       
                    s_ch = source_ch_map[ch_num]
                    t_ch = target_ch_map[ch_num]
                    chapter_conflicts.append({
                        'chapter_number': ch_num,
                        'source': {
                            'title': s_ch.title,
                            'translated_title': s_ch.translated_title,
                            'created_at': s_ch.created_at.isoformat() if s_ch.created_at else None,
                            'has_translation': bool(s_ch.translated_content),
                            'word_count': len(s_ch.content.split()) if s_ch.content else 0
                        },
                        'target': {
                            'title': t_ch.title,
                            'translated_title': t_ch.translated_title,
                            'created_at': t_ch.created_at.isoformat() if t_ch.created_at else None,
                            'has_translation': bool(t_ch.translated_content),
                            'word_count': len(t_ch.content.split()) if t_ch.content else 0
                        }
                    })
                elif in_source:
                    unique_source.append(ch_num)
                else:
                    unique_target.append(ch_num)
            
                                      
            metadata_conflicts = {}
            
                                              
            def has_conflict(s_val, t_val):
                                                                   
                return bool(s_val) and bool(t_val) and s_val != t_val
            
                                                                       
                                                                   
            source_titles = {
                'title': source.title,
                'original_title': source.original_title,
                'translated_title': source.translated_title
            }
            target_titles = {
                'title': target.title,
                'original_title': target.original_title,
                'translated_title': target.translated_title
            }
            
                                                       
            if (has_conflict(source.title, target.title) or 
                has_conflict(source.original_title, target.original_title) or
                has_conflict(source.translated_title, target.translated_title)):
                metadata_conflicts['title'] = {
                    'source': {
                        'title': source.title,
                        'original_title': source.original_title or source.title,
                        'translated_title': source.translated_title
                    },
                    'target': {
                        'title': target.title,
                        'original_title': target.original_title or target.title,
                        'translated_title': target.translated_title
                    }
                }
            
                                                                                 
            source_authors = {
                'author': source.author,
                'translated_author': source.translated_author
            }
            target_authors = {
                'author': target.author,
                'translated_author': target.translated_author
            }
            
            if (has_conflict(source.author, target.author) or
                has_conflict(source.translated_author, target.translated_author)):
                metadata_conflicts['author'] = {
                    'source': {
                        'author': source.author,                                      
                        'translated_author': source.translated_author
                    },
                    'target': {
                        'author': target.author,                                      
                        'translated_author': target.translated_author
                    }
                }
            
            if has_conflict(source.synopsis, target.synopsis):
                metadata_conflicts['synopsis'] = {
                    'source': source.synopsis,
                    'target': target.synopsis
                }
            
            if has_conflict(source.translated_synopsis, target.translated_synopsis):
                metadata_conflicts['translated_synopsis'] = {
                    'source': source.translated_synopsis,
                    'target': target.translated_synopsis
                }
            
                                                              
            s_tags = set(source.tags or [])
            t_tags = set(target.tags or [])
            if s_tags != t_tags:
                metadata_conflicts['tags'] = {
                    'source': list(s_tags),
                    'target': list(t_tags),
                    'merged': list(s_tags | t_tags)
                }
            
            s_trans_tags = set(source.translated_tags or [])
            t_trans_tags = set(target.translated_tags or [])
            if s_trans_tags != t_trans_tags:
                metadata_conflicts['translated_tags'] = {
                    'source': list(s_trans_tags),
                    'target': list(t_trans_tags),
                    'merged': list(s_trans_tags | t_trans_tags)
                }
            
                                                  
            total_after_merge = len(all_chapter_numbers)
            
            return jsonify({
                'success': True,
                'preview': {
                    'source_novel': {
                        'id': source.slug,
                        'title': source.translated_title or source.title,
                        'chapter_count': len(source_chapters)
                    },
                    'target_novel': {
                        'id': target.slug,
                        'title': target.translated_title or target.title,
                        'chapter_count': len(target_chapters)
                    },
                    'metadata_conflicts': metadata_conflicts,
                    'chapter_conflicts': chapter_conflicts,
                    'unique_source_chapters': unique_source,
                    'unique_target_chapters': unique_target,
                    'total_after_merge': total_after_merge
                }
            })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@merge_bp.route('/novel/<novel_id>/merge/execute', methods=['POST'])
def execute_merge(novel_id):

    try:
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        novel_id = unquote(novel_id)
        data = request.get_json()
        target_novel_id = data.get('target_novel_id')
        metadata_choices = data.get('metadata_choices', {})
        chapter_choices = data.get('chapter_choices', {})
        
        if not target_novel_id:
            return jsonify({'error': 'Target novel ID required'}), 400
        
        target_novel_id = unquote(target_novel_id)
        
        with db_session_scope() as session:
                              
            source = session.query(Novel).filter(
                Novel.slug == novel_id,
                Novel.user_id == user_id
            ).first()
            
            target = session.query(Novel).filter(
                Novel.slug == target_novel_id,
                Novel.user_id == user_id
            ).first()
            
            if not source:
                return jsonify({'error': 'Source novel not found'}), 404
            if not target:
                return jsonify({'error': 'Target novel not found'}), 404
            
                                    
            for field, choice in metadata_choices.items():
                if choice == 'target':
                                                
                    if field == 'title':
                                                              
                                                                   
                        source.original_title = target.original_title or target.title or source.original_title
                        source.title = target.title or source.title
                        source.translated_title = target.translated_title or source.translated_title
                        
                                                                                                     
                                                                                      
                                                                                                           
                                                                                                                     
                        source.new_slug_after_merge = target.slug
                        
                    elif field == 'author':
                                                               
                                                              
                        source.author = target.author or source.author
                        source.translated_author = target.translated_author or source.translated_author
                    elif field == 'synopsis':
                        source.synopsis = target.synopsis
                    elif field == 'translated_synopsis':
                        source.translated_synopsis = target.translated_synopsis
                else:                      
                                                                                             
                    if field == 'title':
                                                                                           
                                                                                   
                        if not source.original_title and (target.original_title or target.title):
                            source.original_title = target.original_title or target.title
                        if not source.translated_title and target.translated_title:
                            source.translated_title = target.translated_title
                    elif field == 'author':
                                         
                        if not source.author and target.author:
                            source.author = target.author
                        if not source.translated_author and target.translated_author:
                            source.translated_author = target.translated_author
            
                                        
            source_tags = set(source.tags or [])
            target_tags = set(target.tags or [])
            source.tags = list(source_tags | target_tags)
            
            source_trans_tags = set(source.translated_tags or [])
            target_trans_tags = set(target.translated_tags or [])
            source.translated_tags = list(source_trans_tags | target_trans_tags)
            
                                                                              
            source_glossary = source.glossary or {}
            target_glossary = target.glossary or {}
            
                                                                    
            for key, value in target_glossary.items():
                if key not in source_glossary:
                    source_glossary[key] = value
            
            source.glossary = source_glossary
            
                                                                            
            if not source.cover_url and target.cover_url:
                source.cover_url = target.cover_url
            
                                                                                    
            source_chapters = session.query(Chapter).filter_by(novel_id=source.id).order_by(Chapter.position).all()
            target_chapters = session.query(Chapter).filter_by(novel_id=target.id).order_by(Chapter.position).all()
            
                        
            source_ch_map = {ch.chapter_number: ch for ch in source_chapters}
            target_ch_map = {ch.chapter_number: ch for ch in target_chapters}
            
            all_chapter_numbers = set(source_ch_map.keys()) | set(target_ch_map.keys())
            
                                               
            chapters_to_add = []
            chapters_to_delete = []
            
            for ch_num in all_chapter_numbers:
                in_source = ch_num in source_ch_map
                in_target = ch_num in target_ch_map
                
                if in_source and in_target:
                                                  
                    choice = chapter_choices.get(str(ch_num), 'source')
                    if choice == 'target':
                                                                                    
                        chapters_to_delete.append(source_ch_map[ch_num])
                        target_ch = target_ch_map[ch_num]
                        target_ch.novel_id = source.id
                    else:
                                                                    
                        chapters_to_delete.append(target_ch_map[ch_num])
                elif in_target:
                                                     
                    target_ch = target_ch_map[ch_num]
                    target_ch.novel_id = source.id
                                                                              
            
                                         
            for ch in chapters_to_delete:
                session.delete(ch)
            
                                                                    
                                                                                   
                                                      
                                                                              
            
                                                               
            import re
            def get_anchor_num(ch_str):
                                                               
                try:
                    val = float(ch_str)
                    if val.is_integer():
                        return int(val)
                except:
                    pass
                
                                                            
                try:
                    match = re.search(r'(\d+(\.\d+)?)', str(ch_str))
                    if match:
                        val = float(match.group(1))
                        if val.is_integer():
                            return int(val)
                except:
                    pass
                    
                return None

                                                                                         
                                                                                                      
                                                                                                         
                                                                                                             
            
            position_map = {}                                                      
            
            for is_target, chapter_list in [(False, source_chapters), (True, target_chapters)]:
                last_anchor = -1                             
                rel_idx = 0
                
                for ch in chapter_list:
                                                                                               
                    if ch.is_bonus:
                        anchor = None
                    else:
                        anchor = get_anchor_num(ch.chapter_number)
                        
                    if anchor is not None:
                        last_anchor = anchor
                        rel_idx = 0
                                                                
                        position_map[ch.id] = (anchor, 0, 0, is_target)
                    else:
                        rel_idx += 1
                                                                           
                        position_map[ch.id] = (last_anchor, 1, rel_idx, is_target)

                                          
            all_merged_chapters = session.query(Chapter).filter_by(novel_id=source.id).all()
            
            def anchor_sort_key(chapter):
                                                  
                if chapter.id in position_map:
                    return position_map[chapter.id]
                
                                                                             
                                                       
                cn = str(chapter.chapter_number).strip()
                try:
                                           
                    clean_cn = cn.replace('-', '.')
                    match = re.search(r'(\d+(\.\d+)?)', clean_cn)
                    if match:
                        num = float(match.group(1))
                        return (int(num), 1, 999, 0)                             
                except:
                    pass
                return (999999, 0, 0, 0)              

            all_merged_chapters.sort(key=anchor_sort_key)
            
            for idx, ch in enumerate(all_merged_chapters):
                ch.position = idx
            
                                                                          
            session.delete(target)
            
                                                                                
                                                                                     
            session.flush()
            
                                                                                                       
            if hasattr(source, 'new_slug_after_merge'):
                source.slug = source.new_slug_after_merge
            
            session.commit()
            
                                     
            final_chapter_count = len(all_merged_chapters)
            
            return jsonify({
                'success': True,
                'merged_novel_id': source.slug,
                'total_chapters': final_chapter_count,
                'message': 'Novels merged successfully'
            })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500