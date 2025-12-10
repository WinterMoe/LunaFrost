from flask_wtf.csrf import CSRFProtect, CSRFError, validate_csrf
from functools import wraps
from flask import jsonify, request, session
import logging

csrf = CSRFProtect()
logger = logging.getLogger(__name__)

def init_csrf(app):
    csrf.init_app(app)
    
                                                                    
                                                                                   
    app.config.setdefault('WTF_CSRF_CHECK_DEFAULT', True)
    app.config.setdefault('WTF_CSRF_SSL_STRICT', False)                                    
    
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
                                        
        csrf_token = request.headers.get('X-CSRFToken') or request.headers.get('X-CSRF-Token')
        has_session = 'user_id' in session
        all_headers = dict(request.headers)
        
        error_details = {
            'error': 'CSRF token missing or invalid',
            'description': str(e.description) if hasattr(e, 'description') else str(e),
            'csrf_token_present': bool(csrf_token),
            'csrf_token_length': len(csrf_token) if csrf_token else 0,
            'session_present': has_session,
            'user_id': session.get('user_id') if has_session else None,
            'method': request.method,
            'url': request.url,
            'origin': request.headers.get('Origin'),
            'referer': request.headers.get('Referer'),
            'cookies': list(request.cookies.keys()),
            'cookie_count': len(request.cookies),
            'all_header_names': list(all_headers.keys()),
            'has_x_csrf_token': 'X-CSRFToken' in all_headers,
            'has_x_csrf_token_alt': 'X-CSRF-Token' in all_headers
        }
        
        logger.error(f"CSRF Error: {error_details}")
        print(f"CSRF Error Details: {error_details}")                                                  
        return jsonify(error_details), 400

def csrf_exempt(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        return view(*args, **kwargs)
    wrapped_view.csrf_exempt = True
    return wrapped_view
