   
from services.encryption_service import decrypt_dict, is_encrypted, migrate_to_encrypted

def get_default_settings():
                                           
    return {
        'selected_provider': 'openrouter',
        'api_keys': {
            'openrouter': '',
            'openai': '',
            'google': '',
            'deepl': ''
        },
        'provider_models': {
            'openrouter': 'google/gemini-2.0-flash-001',
            'openai': 'gpt-4',
            'google': 'gemini-2.5-flash',
            'deepl': ''
        },
        'show_covers': True,
        'dark_mode': False,
        'default_sort_order': 'asc',
        'encryption_enabled': True,
        'auto_translate_title': False,
        'auto_translate_content': False,
        'thinking_mode_enabled': False,
        'thinking_mode_models': {
            'openrouter': '',
            'openai': 'o1-preview',
            'google': 'gemini-2.0-flash-thinking-exp-1219',
            'xai': ''
        },
        'show_translation_cost': True,
        'available_models': {
            'openai': ['gpt-4', 'gpt-4-turbo', 'gpt-3.5-turbo'],
            'google': [
                'gemini-2.5-pro',
                'gemini-2.5-flash',
                'gemini-2.5-flash-lite',
                'gemini-2.0-flash',
                'gemini-2.0-flash-lite'
            ],
            'deepl': []
        },
        'custom_prompt_suffix': None
    }

def initialize_user_settings_file(user_id):
           
    pass

def load_settings(user_id):
           
    try:
        from database.database import db_session_scope
        from database.db_models import User as DBUser
        
        with db_session_scope() as session:
                                                             
            user = session.query(DBUser).filter(
                DBUser.username.ilike(user_id)
            ).first()
            
            if not user:
                return get_default_settings()
            
                                        
            data = user.settings or {}
            
                                                          
            defaults = get_default_settings()
            for key, value in defaults.items():
                if key not in data:
                    data[key] = value
            
                                                       
            if data.get('encryption_enabled', True):
                api_keys = data.get('api_keys', {})
                any_encrypted = any(
                    is_encrypted(key) 
                    for key in api_keys.values() 
                    if key
                )
                
                if any_encrypted:
                    data['api_keys'] = decrypt_dict(api_keys)
            
            return data
            
    except Exception as e:
                                           
        import traceback
        traceback.print_exc()
        return get_default_settings()

def save_settings(user_id, settings):
           
    try:
        from database.database import db_session_scope
        from database.db_models import User as DBUser
        
                                        
        settings_to_save = settings.copy()
        
        if settings_to_save.get('encryption_enabled', True):
            settings_to_save['api_keys'] = migrate_to_encrypted(settings_to_save.get('api_keys', {}))
        
        with db_session_scope() as session:
                                                             
            user = session.query(DBUser).filter(
                DBUser.username.ilike(user_id)
            ).first()
            
            if not user:
                raise ValueError(f"User '{user_id}' not found")
            
                                         
            user.settings = settings_to_save
            session.commit()
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise