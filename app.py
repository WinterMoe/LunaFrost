from flask import Flask, session
from dotenv import load_dotenv
import os
import secrets
import re

from utils.csrf_utils import init_csrf

load_dotenv()

def create_app():
    app = Flask(__name__, template_folder='pages')
    

    secret_key = os.getenv('SECRET_KEY')
    if not secret_key:
        secret_key = secrets.token_hex(32)
    app.secret_key = secret_key
    
    app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'True').lower() == 'true'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
                                                                                       
                                                           
    app.config['SESSION_COOKIE_SAMESITE'] = os.getenv('SESSION_COOKIE_SAMESITE', 'None' if app.config['SESSION_COOKIE_SECURE'] else 'Lax')
    
    app.config['WTF_CSRF_TIME_LIMIT'] = None
    app.config['WTF_CSRF_SSL_STRICT'] = os.getenv('WTF_CSRF_SSL_STRICT', 'True').lower() == 'true'
    
    init_csrf(app)
    

    DATA_DIR = 'data'
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, 'users'), exist_ok=True)
    

    from database.database import init_db
    init_db()
    

    from models.user import initialize_users_file, initialize_password_resets_file
    initialize_users_file()
    initialize_password_resets_file()
    

    from services.cleanup_service import start_cleanup_thread
    start_cleanup_thread()
    

    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        storage_uri=os.getenv('REDIS_URL', 'redis://redis:6379/0'),
        default_limits=[]
    )
    

    @app.before_request
    def check_authentication():
        from flask import request, redirect, url_for
        

        no_auth_required = [
            'auth.login', 
            'auth.signup', 
            'auth.forgot_password',
            'auth.reset_password',
            'static', 
            'auth.check_auth',
            'main.about',
            'main.contact',
            'main.view_shared_novel',
            'main.view_shared_chapter'
        ]
        
        if request.endpoint and request.endpoint not in no_auth_required:

            if 'user_id' not in session and request.endpoint:
                if not request.endpoint.startswith('auth.') and not request.endpoint.startswith('static'):
                    return redirect(url_for('auth.login'))
    

    from routes.auth_routes import auth_bp
    from routes.main_routes import main_bp
    from routes.api_routes import api_bp
    from routes.merge_routes import merge_bp
    from routes.webtoon_routes import webtoon_bp
    
    app.limiter = limiter
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(merge_bp, url_prefix='/api')
    app.register_blueprint(webtoon_bp)
    

    from routes.admin_routes import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    @app.template_filter('regex_search')
    def regex_search(text, pattern):

        if not text:
            return False
        return bool(re.search(pattern, str(text)))
    
    return app

if __name__ == '__main__':
    app = create_app()
    

    port = int(os.getenv('PORT', 5000))
    

    host = os.getenv('HOST', '0.0.0.0')
    app.run(host=host, port=port, debug=False)