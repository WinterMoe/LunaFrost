

from database.database import db_session_scope
from database.db_models import UserSettings

def get_user_settings_db(user_id):

    with db_session_scope() as session:
        settings = session.query(UserSettings).filter_by(user_id=user_id).first()
        
        if settings:
            return settings.to_dict()
        else:
            return {
                'user_id': user_id,
                'translation_api_key': None,
                'translation_model': 'gpt-4o-mini'
            }

def create_user_settings_db(user_id, settings_data=None):

    if settings_data is None:
        settings_data = {}
    
    with db_session_scope() as session:
        existing = session.query(UserSettings).filter_by(user_id=user_id).first()
        if existing:
            return existing.to_dict()
        
        settings = UserSettings(
            user_id=user_id,
            translation_api_key=settings_data.get('translation_api_key'),
            translation_model=settings_data.get('translation_model', 'gpt-4o-mini')
        )
        session.add(settings)
        session.flush()
        return settings.to_dict()

def update_user_settings_db(user_id, updates):

    with db_session_scope() as session:
        settings = session.query(UserSettings).filter_by(user_id=user_id).first()
        
        if not settings:
            settings = UserSettings(user_id=user_id)
            session.add(settings)
        
        allowed_fields = ['translation_api_key', 'translation_model']
        for field in allowed_fields:
            if field in updates:
                setattr(settings, field, updates[field])
        
        session.flush()
        return settings.to_dict()

def delete_user_settings_db(user_id):

    with db_session_scope() as session:
        settings = session.query(UserSettings).filter_by(user_id=user_id).first()
        
        if not settings:
            return False
        
        session.delete(settings)
        return True