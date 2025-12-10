

from database.db_models import ReadingPreference
from database.database import db_session_scope
from sqlalchemy.exc import SQLAlchemyError

def get_default_reading_preferences():

    return {
        'color_mode': 'light',
        'font_size': 16,
        'line_height': '1.8',
        'font_family': 'var(--font-serif)',
        'reading_width': '720px',
        'text_alignment': 'left'
    }

def get_reading_preferences(user_id):

    try:
        with db_session_scope() as session:
            prefs = session.query(ReadingPreference).filter_by(user_id=user_id).first()
            
            if prefs:
                return _to_camel_case(prefs.to_dict())
            else:
                return _to_camel_case(get_default_reading_preferences())
                
    except SQLAlchemyError as e:
        return _to_camel_case(get_default_reading_preferences())

def _to_camel_case(snake_dict):

    mapping = {
        'color_mode': 'colorMode',
        'font_size': 'fontSize',
        'line_height': 'lineHeight',
        'font_family': 'fontFamily',
        'reading_width': 'readingWidth',
        'text_alignment': 'textAlignment',
        'user_id': 'userId',
        'created_at': 'createdAt',
        'updated_at': 'updatedAt'
    }
    
    result = {}
    for key, value in snake_dict.items():
        new_key = mapping.get(key, key)
        result[new_key] = value
    return result

def save_reading_preferences(user_id, prefs_dict):

    try:
        with db_session_scope() as session:
            prefs = session.query(ReadingPreference).filter_by(user_id=user_id).first()
            
            if prefs:
                prefs.color_mode = prefs_dict.get('colorMode', prefs_dict.get('color_mode', prefs.color_mode))
                prefs.font_size = prefs_dict.get('fontSize', prefs_dict.get('font_size', prefs.font_size))
                prefs.line_height = str(prefs_dict.get('lineHeight', prefs_dict.get('line_height', prefs.line_height)))
                prefs.font_family = prefs_dict.get('fontFamily', prefs_dict.get('font_family', prefs.font_family))
                prefs.reading_width = prefs_dict.get('readingWidth', prefs_dict.get('reading_width', prefs.reading_width))
                prefs.text_alignment = prefs_dict.get('textAlignment', prefs_dict.get('text_alignment', prefs.text_alignment))
            else:
                defaults = get_default_reading_preferences()
                prefs = ReadingPreference(
                    user_id=user_id,
                    color_mode=prefs_dict.get('colorMode', prefs_dict.get('color_mode', defaults['color_mode'])),
                    font_size=prefs_dict.get('fontSize', prefs_dict.get('font_size', defaults['font_size'])),
                    line_height=str(prefs_dict.get('lineHeight', prefs_dict.get('line_height', defaults['line_height']))),
                    font_family=prefs_dict.get('fontFamily', prefs_dict.get('font_family', defaults['font_family'])),
                    reading_width=prefs_dict.get('readingWidth', prefs_dict.get('reading_width', defaults['reading_width'])),
                    text_alignment=prefs_dict.get('textAlignment', prefs_dict.get('text_alignment', defaults['text_alignment']))
                )
                session.add(prefs)
            
            session.commit()
            session.refresh(prefs)                                     
            return _to_camel_case(prefs.to_dict())
            
    except SQLAlchemyError as e:
        return None