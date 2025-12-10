from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, current_app
from flask_limiter import Limiter
from models.user import (
    create_user, authenticate_user, initialize_users_file, initialize_password_resets_file,
    request_password_reset, validate_reset_token, reset_password_with_token,
    update_user_email, update_user_password, get_user_info, cleanup_expired_reset_tokens
)
from models.settings import initialize_user_settings_file
from models.novel import initialize_user_data_files
from services.email_service import send_password_reset_email, send_welcome_email, send_email_change_confirmation
from utils.auth_decorator import require_auth
from utils.csrf_utils import csrf

auth_bp = Blueprint('auth', __name__)

def get_limiter():
    return current_app.limiter

@auth_bp.before_request
def initialize():

    initialize_users_file()
    initialize_password_resets_file()
    cleanup_expired_reset_tokens()

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():

    if request.method == 'GET':
        return render_template('signup.html')
    

    get_limiter().limit("5 per minute")(lambda: None)()
    

    try:
        data = request.json
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        password_confirm = data.get('password_confirm', '')
        

        if not username or len(username) < 3:
            return jsonify({'success': False, 'error': 'Username must be at least 3 characters'}), 400
        
        if not email or '@' not in email:
            return jsonify({'success': False, 'error': 'Invalid email address'}), 400
        
        if not password or len(password) < 8:
            return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400
        
        if password != password_confirm:
            return jsonify({'success': False, 'error': 'Passwords do not match'}), 400
        

        result = create_user(username, email, password)
        
        if not result['success']:
            return jsonify(result), 400
        
        user_id = result['user_id']
        

        initialize_user_data_files(user_id)
        initialize_user_settings_file(user_id)
        

        send_welcome_email(email, username)
        

        session['user_id'] = user_id
        session['username'] = username
        
        return jsonify({
            'success': True,
            'message': 'Account created successfully',
            'redirect': '/'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'GET':
        return render_template('login.html')
    

    get_limiter().limit("5 per minute")(lambda: None)()
    

    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password required'}), 400
        
        result = authenticate_user(username, password)
        
        if not result['success']:
            return jsonify(result), 401
        

        session['user_id'] = result['user_id']
        session['username'] = result['username']
        
        return jsonify({
            'success': True,
            'message': 'Logged in successfully',
            'redirect': '/'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():

    if request.method == 'GET':
        return render_template('forgot_password.html')
    

    get_limiter().limit("3 per minute")(lambda: None)()
    

    try:
        data = request.json
        email = data.get('email', '').strip()
        
        if not email:
            return jsonify({'success': False, 'error': 'Email address required'}), 400
        

        result = request_password_reset(email)
        
        if result.get('email_found'):

            reset_token = result['reset_token']
            user_id = result['user_id']
            send_password_reset_email(email, reset_token, user_id)
        

        return jsonify({
            'success': True,
            'message': 'If an account exists with that email, a password reset link has been sent'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():

    if request.method == 'GET':
        token = request.args.get('token', '')
        

        validation = validate_reset_token(token)
        
        if not validation['success']:
            return render_template('reset_password.html', 
                                 success=False, 
                                 error=validation['error'],
                                 token=token)
        
        return render_template('reset_password.html', 
                             success=True, 
                             token=token,
                             email=validation['email'])
    

    try:
        data = request.json
        token = data.get('token', '')
        new_password = data.get('password', '')
        password_confirm = data.get('password_confirm', '')
        
        if not token:
            return jsonify({'success': False, 'error': 'Reset token missing'}), 400
        
        if not new_password or len(new_password) < 8:
            return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400
        
        if new_password != password_confirm:
            return jsonify({'success': False, 'error': 'Passwords do not match'}), 400
        

        result = reset_password_with_token(token, new_password)
        
        if not result['success']:
            return jsonify(result), 400
        
        return jsonify({
            'success': True,
            'message': result['message'],
            'redirect': '/auth/login'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth_bp.route('/profile', methods=['GET'])
def profile():

    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_info = get_user_info(session['user_id'])
    return render_template('profile.html', user=user_info)

@auth_bp.route('/api/profile', methods=['GET'])
def get_profile():

    if 'user_id' not in session:
        return jsonify({'authenticated': False}), 401
    
    user_info = get_user_info(session['user_id'])
    return jsonify({'success': True, 'user': user_info})

@auth_bp.route('/api/update-email', methods=['POST'])
@require_auth
def api_update_email():

    try:
        
        data = request.json
        new_email = data.get('email', '').strip()
        
        if not new_email or '@' not in new_email:
            return jsonify({'success': False, 'error': 'Invalid email address'}), 400
        
        user_id = session['user_id']
        

        result = update_user_email(user_id, new_email)
        
        if not result['success']:
            return jsonify(result), 400
        

        send_email_change_confirmation(new_email, session.get('username', 'User'))
        
        return jsonify({'success': True, 'message': 'Email updated successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth_bp.route('/api/update-password', methods=['POST'])
@require_auth
def api_update_password():

    try:
        
        data = request.json
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')
        password_confirm = data.get('password_confirm', '')
        
        if not old_password:
            return jsonify({'success': False, 'error': 'Current password required'}), 400
        
        if not new_password or len(new_password) < 8:
            return jsonify({'success': False, 'error': 'New password must be at least 8 characters'}), 400
        
        if new_password != password_confirm:
            return jsonify({'success': False, 'error': 'New passwords do not match'}), 400
        
        if old_password == new_password:
            return jsonify({'success': False, 'error': 'New password must be different from current password'}), 400
        
        user_id = session['user_id']
        

        result = update_user_password(user_id, old_password, new_password)
        
        if not result['success']:
            return jsonify(result), 400
        
        return jsonify({'success': True, 'message': 'Password updated successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth_bp.route('/api/delete-account', methods=['POST'])
@require_auth
def api_delete_account():

    try:
        data = request.json
        password = data.get('password', '')
        
        if not password:
            return jsonify({'success': False, 'error': 'Password required for confirmation'}), 400
        
        username = session.get('username')
        
        result = authenticate_user(username, password)
        
        if not result['success']:
            return jsonify({'success': False, 'error': 'Incorrect password'}), 401
        
        from services.user_service import delete_user_account
        success, message = delete_user_account(username)
        
        if success:
            session.clear()
            return jsonify({'success': True, 'message': 'Account deleted successfully'})
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth_bp.route('/logout')
def logout():

    session.clear()
    return redirect(url_for('auth.login'))

@auth_bp.route('/api/check-auth')
def check_auth():

    if 'user_id' in session:
        from services.admin_service import is_admin_authorized
        is_admin = is_admin_authorized(request, session.get('username'))
        
        return jsonify({
            'authenticated': True,
            'user_id': session['user_id'],
            'username': session.get('username'),
            'is_admin': is_admin
        })
    return jsonify({'authenticated': False})