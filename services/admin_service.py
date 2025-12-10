

import os
from flask import request, session

def get_allowed_admin_ips():

    allowed_ips_str = os.environ.get('ADMIN_ALLOWED_IPS', '24.88.90.213')
    return [ip.strip() for ip in allowed_ips_str.split(',') if ip.strip()]

def get_admin_username():

    return os.environ.get('ADMIN_USERNAME', 'admin')

def get_client_ip(request_obj):

    if request_obj.headers.get('X-Forwarded-For'):
        return request_obj.headers.get('X-Forwarded-For').split(',')[0].strip()
    
    if request_obj.headers.get('X-Real-IP'):
        return request_obj.headers.get('X-Real-IP').strip()
    
    return request_obj.remote_addr

def is_admin_authorized(request_obj, username):

    if not username:
        return False
    
                                           
    from database.database import db_session_scope
    from database.db_models import User
    
    try:
        with db_session_scope() as session:
            user = session.query(User).filter(
                User.username == username
            ).first()
            
            if not user:
                return False
            
                                                
            return user.is_admin
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False

def log_admin_action(username, action, details=None):

    from datetime import datetime
    
    log_entry = f"[{datetime.now().isoformat()}] ADMIN ({username}): {action}"
    if details:
        log_entry += f" - {details}"