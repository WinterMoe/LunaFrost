

from flask import Blueprint, render_template, request, session, jsonify, abort
from services.admin_service import is_admin_authorized, log_admin_action, get_client_ip
from database.database import db_session_scope
from database.db_models import GlobalModelPricing, WebtoonJob, User
from sqlalchemy import or_

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
def check_admin_auth():

    username = session.get('username')
    
    if not is_admin_authorized(request, username):
        client_ip = get_client_ip(request)
        abort(403)

@admin_bp.route('/')
def dashboard():

    username = session.get('username')
    log_admin_action(username, "Accessed admin dashboard")
    
    return render_template('admin/dashboard.html', username=username)

@admin_bp.route('/pricing')
def pricing_page():

    username = session.get('username')
    log_admin_action(username, "Accessed pricing management")
    
    return render_template('admin/pricing.html', username=username)

@admin_bp.route('/users')
def users_page():

    username = session.get('username')
    log_admin_action(username, "Accessed user management")
    
    return render_template('admin/users.html', username=username)

@admin_bp.route('/api/users', methods=['GET'])
def get_users():

    try:
        username = session.get('username')
        search_query = request.args.get('search', '').strip()
        
        from database.db_models import User, Novel, TranslationTokenUsage
        from sqlalchemy import func
        
        with db_session_scope() as db_session:
                        
            query = db_session.query(User)
            
                                 
            if search_query:
                search_pattern = f"%{search_query}%"
                query = query.filter(
                    or_(
                        User.username.ilike(search_pattern),
                        User.email.ilike(search_pattern)
                    )
                )
            
            users = query.order_by(User.created_at.desc()).all()
            
                                             
            user_list = []
            for user in users:
                                            
                novel_count = db_session.query(func.count(Novel.id)).filter(
                    Novel.user_id == user.username.lower()
                ).scalar() or 0

                webtoon_count = db_session.query(func.count(WebtoonJob.id)).filter(
                    WebtoonJob.user_id == user.username.lower()
                ).scalar() or 0
                
                                       
                token_usage = db_session.query(func.sum(TranslationTokenUsage.total_tokens)).filter(
                    TranslationTokenUsage.user_id == user.username.lower()
                ).scalar() or 0
                
                user_data = user.to_dict()
                user_data['novel_count'] = novel_count
                user_data['webtoon_count'] = webtoon_count
                user_data['total_tokens'] = int(token_usage)
                user_list.append(user_data)
            
            log_admin_action(username, f"Listed users (search: '{search_query}' if search_query else 'none')")
            
            return jsonify({
                'success': True,
                'users': user_list,
                'total_count': len(user_list)
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/users/<int:user_id>/toggle-admin', methods=['POST'])
def toggle_admin(user_id):

    try:
        admin_username = session.get('username')
        
        from database.db_models import User
        
        with db_session_scope() as db_session:
            user = db_session.query(User).filter(User.id == user_id).first()
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
                                 
            old_status = user.is_admin
            user.is_admin = not user.is_admin
            db_session.flush()
            
            action = "granted" if user.is_admin else "revoked"
            log_admin_action(
                admin_username,
                f"Admin privileges {action} for user '{user.username}'",
                f"Changed from {old_status} to {user.is_admin}"
            )
            
            return jsonify({
                'success': True,
                'is_admin': user.is_admin,
                'message': f"Admin privileges {action} for {user.username}"
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/users/<int:user_id>/novel-limit', methods=['POST'])
def api_set_user_novel_limit(user_id):

    try:
        admin_username = session.get('username')
        data = request.json
        limit = data.get('limit')                                                          
        
        with db_session_scope() as db_session:
            user = db_session.query(User).filter(User.id == user_id).first()
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            old_limit = user.max_novels_override
            user.max_novels_override = limit
            db_session.flush()
            
            limit_desc = "default" if limit is None else ("unlimited" if limit == 0 else str(limit))
            log_admin_action(
                admin_username,
                f"Set novel limit for user '{user.username}' to {limit_desc}",
                f"Changed from {old_limit} to {limit}"
            )
            
            return jsonify({
                'success': True,
                'limit': limit,
                'message': f"Novel limit updated for {user.username}"
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/users/<int:user_id>/webtoon-limit', methods=['POST'])
def api_set_user_webtoon_limit(user_id):

    try:
        admin_username = session.get('username')
        data = request.json
        limit = data.get('limit')

        with db_session_scope() as db_session:
            user = db_session.query(User).filter(User.id == user_id).first()
            if not user:
                return jsonify({'error': 'User not found'}), 404

            old_limit = getattr(user, 'max_webtoons_override', None)
            user.max_webtoons_override = limit
            db_session.flush()

            limit_desc = "default" if limit is None else ("unlimited" if limit == 0 else str(limit))
            log_admin_action(
                admin_username,
                f"Set webtoon limit for user '{user.username}' to {limit_desc}",
                f"Changed from {old_limit} to {limit}"
            )

            return jsonify({
                'success': True,
                'limit': limit,
                'message': f"Webtoon limit updated for {user.username}"
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/users/<int:user_id>/delete', methods=['DELETE'])
def api_delete_user(user_id):

    try:
        admin_username = session.get('username')
        
        with db_session_scope() as db_session:
            user = db_session.query(User).filter(User.id == user_id).first()
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            if user.username.lower() == admin_username.lower():
                return jsonify({'error': 'You cannot delete your own account from admin panel'}), 400
            
            target_username = user.username
        
        from services.user_service import delete_user_account
        success, message = delete_user_account(target_username)
        
        if success:
            log_admin_action(admin_username, f"Deleted user account: {target_username}")
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'error': message}), 400
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

                               

@admin_bp.route('/stats')
def stats_page():

    username = session.get('username')
    log_admin_action(username, "Accessed system statistics")
    return render_template('admin/stats.html', username=username)

@admin_bp.route('/api/stats/overview')
def api_stats_overview():

    try:
        from services.stats_service import get_overview_stats
        data = get_overview_stats()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/stats/tokens')
def api_stats_tokens():

    try:
        from services.stats_service import get_token_stats
        data = get_token_stats()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/stats/activity')
def api_stats_activity():

    try:
        from services.stats_service import get_activity_stats
        data = get_activity_stats()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/stats/top-lists')
def api_stats_top_lists():

    try:
        from services.stats_service import get_top_lists
        data = get_top_lists()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/stats/storage')
def api_stats_storage():

    try:
        from services.stats_service import get_storage_stats
        data = get_storage_stats()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/stats/charts')
def api_stats_charts():

    try:
        from services.stats_service import get_chart_data
        data = get_chart_data()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

                            

@admin_bp.route('/options')
def options_page():

    username = session.get('username')
    log_admin_action(username, "Accessed other options")
    return render_template('admin/options.html', username=username)

@admin_bp.route('/api/options/settings')
def api_get_settings():

    try:
        from services.settings_service import get_all_settings
        settings = get_all_settings()
        return jsonify({'success': True, 'data': settings})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/options/settings', methods=['POST'])
def api_update_settings():

    try:
        username = session.get('username')
        data = request.json
        key = data.get('key')
        value = data.get('value')
        
        if not key:
            return jsonify({'success': False, 'error': 'Key is required'}), 400
        
        from services.settings_service import set_global_setting
        set_global_setting(key, value)
        
        log_admin_action(username, f"Updated setting: {key} = {value}")
        
        return jsonify({'success': True, 'message': 'Setting updated'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

                          

@admin_bp.route('/queue')
def queue_page():

    username = session.get('username')
    log_admin_action(username, "Accessed translation queue")
    return render_template('admin/queue.html', username=username)

@admin_bp.route('/api/queue/status')
def api_queue_status():

    try:
        from services.queue_service import get_queue_status
        data = get_queue_status()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/queue/cancel/<task_id>', methods=['POST'])
def api_cancel_task(task_id):

    try:
        username = session.get('username')
        from services.queue_service import cancel_task
        
        cancel_task(task_id)
        log_admin_action(username, f"Cancelled task {task_id}")
        
        return jsonify({'success': True, 'message': 'Task cancelled'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/queue/purge', methods=['POST'])
def api_purge_queue():

    try:
        username = session.get('username')
        from services.queue_service import purge_queue
        
        purge_queue()
        log_admin_action(username, "Purged translation queue")
        
        return jsonify({'success': True, 'message': 'Queue purged'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/pricing', methods=['GET'])
def get_global_pricing():

    try:
        with db_session_scope() as session:
            pricing_records = session.query(GlobalModelPricing).all()
            

            pricing_by_provider = {}
            for record in pricing_records:
                provider = record.provider
                if provider not in pricing_by_provider:
                    pricing_by_provider[provider] = []
                
                pricing_by_provider[provider].append(record.to_dict())
            
            return jsonify({
                'success': True,
                'pricing': pricing_by_provider,
                'total_count': len(pricing_records)
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/pricing', methods=['POST'])
def update_global_pricing():

    try:
        username = session.get('username')
        data = request.json
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        

        provider = data.get('provider')
        model_name = data.get('model_name')
        input_price = data.get('input_price_per_1m')
        output_price = data.get('output_price_per_1m')
        notes = data.get('notes', '')
        
        if not provider or not model_name:
            return jsonify({'error': 'Provider and model_name are required'}), 400
        
        with db_session_scope() as db_session:

            existing = db_session.query(GlobalModelPricing).filter(
                GlobalModelPricing.provider == provider,
                GlobalModelPricing.model_name == model_name
            ).first()
            
            if existing:

                existing.input_price_per_1m = input_price
                existing.output_price_per_1m = output_price
                existing.notes = notes
                existing.updated_by = username
                db_session.flush()
                
                log_admin_action(username, f"Updated pricing for {provider}/{model_name}")
                
                return jsonify({
                    'success': True,
                    'message': 'Pricing updated',
                    'pricing': existing.to_dict()
                })
            else:

                new_pricing = GlobalModelPricing(
                    provider=provider,
                    model_name=model_name,
                    input_price_per_1m=input_price,
                    output_price_per_1m=output_price,
                    notes=notes,
                    updated_by=username
                )
                db_session.add(new_pricing)
                db_session.flush()
                
                log_admin_action(username, f"Created pricing for {provider}/{model_name}")
                
                return jsonify({
                    'success': True,
                    'message': 'Pricing created',
                    'pricing': new_pricing.to_dict()
                })
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/pricing/<int:pricing_id>', methods=['DELETE'])
def delete_global_pricing(pricing_id):

    try:
        username = session.get('username')
        
        with db_session_scope() as db_session:
            pricing = db_session.query(GlobalModelPricing).filter(
                GlobalModelPricing.id == pricing_id
            ).first()
            
            if not pricing:
                return jsonify({'error': 'Pricing not found'}), 404
            
            provider = pricing.provider
            model_name = pricing.model_name
            
            db_session.delete(pricing)
            db_session.flush()
            
            log_admin_action(username, f"Deleted pricing for {provider}/{model_name}")
            
            return jsonify({
                'success': True,
                'message': 'Pricing deleted'
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/pricing/upload', methods=['POST'])
def upload_pricing_excel():

    try:
        username = session.get('username')
        
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            return jsonify({'error': 'File must be Excel format (.xlsx or .xls)'}), 400
        

        try:
            import openpyxl
            workbook = openpyxl.load_workbook(file)
            sheet = workbook.active
            
            imported_count = 0
            errors = []
            

            for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                if not row or len(row) < 2:
                    continue
                
                provider = str(row[0]).strip() if row[0] else None
                model_name = str(row[1]).strip() if row[1] else None
                input_price = str(row[2]).strip() if len(row) > 2 and row[2] else ''
                output_price = str(row[3]).strip() if len(row) > 3 and row[3] else ''
                
                if not provider or not model_name:
                    errors.append(f"Row {row_idx}: Missing provider or model name")
                    continue
                

                input_price = input_price.replace('$', '').replace(',', '').strip()
                output_price = output_price.replace('$', '').replace(',', '').strip()
                
                try:
                    with db_session_scope() as db_session:

                        existing = db_session.query(GlobalModelPricing).filter(
                            GlobalModelPricing.provider == provider,
                            GlobalModelPricing.model_name == model_name
                        ).first()
                        
                        if existing:

                            existing.input_price_per_1m = input_price if input_price else None
                            existing.output_price_per_1m = output_price if output_price else None
                            existing.updated_by = username
                            db_session.flush()
                        else:

                            new_pricing = GlobalModelPricing(
                                provider=provider,
                                model_name=model_name,
                                input_price_per_1m=input_price if input_price else None,
                                output_price_per_1m=output_price if output_price else None,
                                updated_by=username
                            )
                            db_session.add(new_pricing)
                            db_session.flush()
                        
                        imported_count += 1
                        
                except Exception as e:
                    errors.append(f"Row {row_idx} ({provider}/{model_name}): {str(e)}")
            
            log_admin_action(username, f"Bulk imported {imported_count} pricing entries from Excel")
            
            result = {
                'success': True,
                'message': f'Import completed',
                'imported_count': imported_count
            }
            
            if errors:
                result['warnings'] = errors
            
            return jsonify(result)
            
        except ImportError:
            return jsonify({'error': 'openpyxl library not installed. Please install it.'}), 500
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Error parsing Excel file: {str(e)}'}), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500