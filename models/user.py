import json
import os
import hashlib
import secrets
from datetime import datetime, timedelta

DATA_DIR = 'data'
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
PASSWORD_RESET_FILE = os.path.join(DATA_DIR, 'password_resets.json')

def initialize_users_file():

    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)

def initialize_password_resets_file():

    if not os.path.exists(PASSWORD_RESET_FILE):
        with open(PASSWORD_RESET_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)

def hash_password(password):

    salt = secrets.token_hex(32)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode(), 100000)
    return f"{salt}${pwd_hash.hex()}"

def verify_password(stored_hash, password):

    try:
        salt, pwd_hash = stored_hash.split('$')
        new_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode(), 100000)
        return new_hash.hex() == pwd_hash
    except:
        return False

def load_users():

    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):

    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def load_password_resets():

    try:
        with open(PASSWORD_RESET_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_password_resets(resets):

    with open(PASSWORD_RESET_FILE, 'w', encoding='utf-8') as f:
        json.dump(resets, f, ensure_ascii=False, indent=2)

def create_user(username, email, password):
           
    user_id = username.lower()
    password_hash = hash_password(password)
    
    default_settings = {
        'selected_provider': 'openrouter',
        'api_keys': {
            'openrouter': '',
            'openai': '',
            'google': ''
        },
        'provider_models': {
            'openrouter': 'google/gemini-2.0-flash-001',
            'openai': 'gpt-4',
            'google': 'gemini-2.5-flash'
        },
        'show_covers': True,
        'dark_mode': False,
        'default_sort_order': 'asc',
        'encryption_enabled': True
    }
    
                                                    
    try:
        from database.database import db_session_scope
        from database.db_models import User as DBUser
        
        with db_session_scope() as db_session:
                                              
            existing_db_user = db_session.query(DBUser).filter(
                (DBUser.username.ilike(username)) | (DBUser.email.ilike(email))
            ).first()
            
            if existing_db_user:
                if existing_db_user.username.lower() == username.lower():
                    return {'success': False, 'error': 'Username already exists'}
                if existing_db_user.email.lower() == email.lower():
                    return {'success': False, 'error': 'Email already registered'}
            
                                                       
            db_user = DBUser(
                username=username,
                email=email,
                password_hash=password_hash,
                is_admin=False,
                settings=default_settings
            )
            db_session.add(db_user)
            db_session.commit()
            
    except Exception as e:
                                                                   
        import traceback
        traceback.print_exc()
        print(f"Warning: Database creation failed, falling back to JSON file system: {e}")
        
                                      
        users = load_users()
        
        if user_id in users:
            return {'success': False, 'error': 'Username already exists'}
        
        for user_data in users.values():
            if user_data.get('email', '').lower() == email.lower():
                return {'success': False, 'error': 'Email already registered'}
        
        users[user_id] = {
            'username': username,
            'email': email,
            'password_hash': password_hash,
            'created_at': datetime.now().isoformat(),
            'last_login': None,
            'settings': default_settings
        }
        
        save_users(users)
    
                                                                           
    user_dir = os.path.join(DATA_DIR, 'users', user_id)
    os.makedirs(user_dir, exist_ok=True)
    os.makedirs(os.path.join(user_dir, 'images'), exist_ok=True)
    
    novels_file = os.path.join(user_dir, 'novels.json')
    with open(novels_file, 'w', encoding='utf-8') as f:
        json.dump({}, f)
    
    settings_file = os.path.join(user_dir, 'settings.json')
    with open(settings_file, 'w', encoding='utf-8') as f:
        json.dump(default_settings, f, ensure_ascii=False, indent=2)
    
    return {'success': True, 'user_id': user_id, 'message': 'Account created successfully'}

def authenticate_user(username, password):
           
    try:
        from database.database import db_session_scope
        from database.db_models import User as DBUser
        
        with db_session_scope() as session:
            user = session.query(DBUser).filter(
                DBUser.username == username
            ).first()
            
            if not user:
                return {'success': False, 'error': 'Invalid username or password'}
            
            if not verify_password(user.password_hash, password):
                return {'success': False, 'error': 'Invalid username or password'}
            
                               
            user.last_login = datetime.now()
            session.commit()
            
            token = secrets.token_urlsafe(32)
            
            return {
                'success': True,
                'token': token,
                'user_id': username.lower(),
                'username': user.username,
                'email': user.email,
                'is_admin': user.is_admin
            }
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': 'Authentication failed'}

def get_user_info(user_id):
           
    try:
        from database.database import db_session_scope
        from database.db_models import User as DBUser
        
        with db_session_scope() as session:
                                                             
            user = session.query(DBUser).filter(
                DBUser.username.ilike(user_id)
            ).first()
            
            if not user:
                return None
            
            return {
                'username': user.username,
                'email': user.email,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'last_login': user.last_login.isoformat() if user.last_login else None
            }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None

def update_user_email(user_id, new_email):
           
    try:
        from database.database import db_session_scope
        from database.db_models import User as DBUser
        
        with db_session_scope() as session:
                                                             
            user = session.query(DBUser).filter(
                DBUser.username.ilike(user_id)
            ).first()
            
            if not user:
                return {'success': False, 'error': 'User not found'}
            
                                                              
            existing_user = session.query(DBUser).filter(
                DBUser.email.ilike(new_email),
                DBUser.id != user.id
            ).first()
            
            if existing_user:
                return {'success': False, 'error': 'Email already in use'}
            
                          
            user.email = new_email
            session.commit()
            
            return {'success': True, 'message': 'Email updated successfully'}
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': f'Failed to update email: {str(e)}'}

def update_user_password(user_id, old_password, new_password):
           
    try:
        from database.database import db_session_scope
        from database.db_models import User as DBUser
        
        if len(new_password) < 8:
            return {'success': False, 'error': 'New password must be at least 8 characters'}
        
        with db_session_scope() as session:
                                                             
            user = session.query(DBUser).filter(
                DBUser.username.ilike(user_id)
            ).first()
            
            if not user:
                return {'success': False, 'error': 'User not found'}
            
                                 
            if not verify_password(user.password_hash, old_password):
                return {'success': False, 'error': 'Current password is incorrect'}
            
                             
            user.password_hash = hash_password(new_password)
            session.commit()
            
            return {'success': True, 'message': 'Password updated successfully'}
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': f'Failed to update password: {str(e)}'}

def request_password_reset(email):
           
    try:
        from database.database import db_session_scope
        from database.db_models import User as DBUser, PasswordReset
        
        with db_session_scope() as session:
                                
            user = session.query(DBUser).filter(
                DBUser.email.ilike(email)
            ).first()
            
            if not user:
                return {
                    'success': True,
                    'message': 'If an account exists with that email, a reset link will be sent',
                    'email_found': False
                }
            
            user_id = user.username.lower()
            reset_token = secrets.token_urlsafe(32)
            
                                          
            password_reset = PasswordReset(
                token=reset_token,
                user_id=user_id,
                email=email,
                used=False,
                expires_at=datetime.now() + timedelta(hours=1)
            )
            session.add(password_reset)
            session.commit()
            
            return {
                'success': True,
                'message': 'If an account exists with that email, a reset link will be sent',
                'email_found': True,
                'reset_token': reset_token,
                'user_id': user_id
            }
            
    except Exception as e:
        import traceback
        traceback.print_exc()
                                                                   
        return {
            'success': True,
            'message': 'If an account exists with that email, a reset link will be sent',
            'email_found': False
        }

def validate_reset_token(reset_token):
           
    try:
        from database.database import db_session_scope
        from database.db_models import PasswordReset
        
        with db_session_scope() as session:
            reset = session.query(PasswordReset).filter(
                PasswordReset.token == reset_token
            ).first()
            
            if not reset:
                return {'success': False, 'error': 'Invalid reset token'}
            
            if reset.used:
                return {'success': False, 'error': 'This reset link has already been used'}
            
            if datetime.now() > reset.expires_at:
                return {'success': False, 'error': 'This reset link has expired. Please request a new one.'}
            
            return {
                'success': True,
                'user_id': reset.user_id,
                'email': reset.email
            }
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': 'Invalid reset token'}

def reset_password_with_token(reset_token, new_password):
           
    try:
        from database.database import db_session_scope
        from database.db_models import User as DBUser, PasswordReset
        
        if len(new_password) < 8:
            return {'success': False, 'error': 'Password must be at least 8 characters'}
        
        with db_session_scope() as session:
            reset = session.query(PasswordReset).filter(
                PasswordReset.token == reset_token
            ).first()
            
            if not reset:
                return {'success': False, 'error': 'Invalid reset token'}
            
            if reset.used:
                return {'success': False, 'error': 'This reset link has already been used'}
            
            if datetime.now() > reset.expires_at:
                return {'success': False, 'error': 'This reset link has expired'}
            
                                           
            user = session.query(DBUser).filter(
                DBUser.username.ilike(reset.user_id)
            ).first()
            
            if not user:
                return {'success': False, 'error': 'User not found'}
            
                             
            user.password_hash = hash_password(new_password)
            
                                      
            reset.used = True
            reset.used_at = datetime.now()
            
            session.commit()
            
            return {'success': True, 'message': 'Password reset successfully. Please log in with your new password.'}
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': f'Failed to reset password: {str(e)}'}

def cleanup_expired_reset_tokens():
           
    try:
        from database.database import db_session_scope
        from database.db_models import PasswordReset
        
        with db_session_scope() as session:
                                   
            deleted_count = session.query(PasswordReset).filter(
                PasswordReset.expires_at < datetime.now()
            ).delete()
            
            session.commit()
            
            if deleted_count > 0:
                print(f"Cleaned up {deleted_count} expired password reset tokens")
            
    except Exception as e:
        import traceback
        traceback.print_exc()
                                                                

def update_user_settings(user_id, new_settings):
           
    try:
        from models.settings import save_settings, load_settings
        
                                                                  
        current_settings = load_settings(user_id)
        current_settings.update(new_settings)
        save_settings(user_id, current_settings)
        
        return {'success': True}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': f'Failed to update settings: {str(e)}'}

def get_user_settings(user_id):
           
    try:
        from models.settings import load_settings
        return load_settings(user_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {}