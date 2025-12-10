

from database.database import db_session_scope
from database.db_models import GlobalSettings, User, Novel, WebtoonJob
from sqlalchemy import func

def get_global_setting(key, default=None):

    with db_session_scope() as session:
        setting = session.query(GlobalSettings).filter(
            GlobalSettings.key == key
        ).first()
        
        if setting:
            return setting.value
        return default

def set_global_setting(key, value, description=None):

    with db_session_scope() as session:
        setting = session.query(GlobalSettings).filter(
            GlobalSettings.key == key
        ).first()
        
        if setting:
            setting.value = str(value)
            if description:
                setting.description = description
        else:
            setting = GlobalSettings(
                key=key,
                value=str(value),
                description=description
            )
            session.add(setting)
        
        session.commit()
        return True

def get_all_settings():

    with db_session_scope() as session:
        settings = session.query(GlobalSettings).all()
        return [s.to_dict() for s in settings]

def get_max_novels_for_user(user):

                           
    if user.is_admin:
        return None
    
                                      
    if user.max_novels_override is not None:
                           
        if user.max_novels_override == 0:
            return None
        return user.max_novels_override
    
                                 
    global_limit = get_global_setting('max_novels_per_user', default='100')
    return int(global_limit)

def get_max_webtoons_for_user(user):
           
    if user.is_admin:
        return None

    override = getattr(user, 'max_webtoons_override', None)
    if override is not None:
        if override == 0:
            return None
        return override

    global_limit = get_global_setting('max_webtoons_per_user', default='5')
    try:
        return int(global_limit)
    except Exception:
        return 5

def can_user_import_novel(user_id):

    with db_session_scope() as session:
                                                                    
                                    
        user = session.query(User).filter(
            func.lower(User.username) == user_id.lower()
        ).first()
        
        if not user:
            return False, "User not found", 0, None
        
        max_novels = get_max_novels_for_user(user)
        
                   
        if max_novels is None:
            return True, None, 0, None
        
                              
        current_count = session.query(func.count(Novel.id)).filter(
            func.lower(Novel.user_id) == user_id.lower()
        ).scalar() or 0
        
        if current_count >= max_novels:
            return False, f"You have reached the maximum limit of {max_novels} novels", current_count, max_novels
        
        return True, None, current_count, max_novels

def can_user_create_webtoon(user_id):
           
    with db_session_scope() as session:
        user = session.query(User).filter(
            func.lower(User.username) == user_id.lower()
        ).first()

        if not user:
            return False, "User not found", 0, None

        max_webtoons = get_max_webtoons_for_user(user)

        if max_webtoons is None:
            return True, None, 0, None

        current_count = session.query(func.count(WebtoonJob.id)).filter(
            func.lower(WebtoonJob.user_id) == user_id.lower()
        ).scalar() or 0

        if current_count >= max_webtoons:
            return False, f"You have reached the maximum limit of {max_webtoons} webtoons", current_count, max_webtoons

        return True, None, current_count, max_webtoons

def set_user_novel_limit(user_id, limit):

    with db_session_scope() as session:
                                                                    
                                    
        user = session.query(User).filter(
            func.lower(User.username) == user_id.lower()
        ).first()
        if not user:
            return False, "User not found"
        
        user.max_novels_override = limit
        session.commit()
        return True, "Novel limit updated successfully"

def set_user_webtoon_limit(user_id, limit):
           
    with db_session_scope() as session:
        user = session.query(User).filter(
            func.lower(User.username) == user_id.lower()
        ).first()
        if not user:
            return False, "User not found"

        user.max_webtoons_override = limit
        session.commit()
        return True, "Webtoon limit updated successfully"