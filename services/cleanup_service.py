import os
import time
from datetime import datetime, timedelta
import threading

DATA_DIR = 'data'

def cleanup_old_exports(max_age_hours=1):

    while True:
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            deleted_count = 0
            
            users_dir = os.path.join(DATA_DIR, 'users')
            if os.path.exists(users_dir):
                for user_id in os.listdir(users_dir):
                    user_path = os.path.join(users_dir, user_id)
                    
                    if not os.path.isdir(user_path):
                        continue
                    
                    exports_dir = os.path.join(user_path, 'exports')
                    if not os.path.exists(exports_dir):
                        continue
                    
                    for filename in os.listdir(exports_dir):
                        if filename.endswith(('.pdf', '.epub')):
                            file_path = os.path.join(exports_dir, filename)
                            
                            if os.path.isdir(file_path):
                                continue
                            
                            file_mtime = os.path.getmtime(file_path)
                            file_age_seconds = current_time - file_mtime
                            
                            if file_age_seconds > max_age_seconds:
                                try:
                                    os.remove(file_path)
                                    age_hours = file_age_seconds / 3600
                                    deleted_count += 1
                                except Exception as e:
                                    pass                                        
            
            time.sleep(15 * 60)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            time.sleep(60)

def start_cleanup_thread(max_age_hours=1):

    cleanup_thread = threading.Thread(
        target=cleanup_old_exports, 
        args=(max_age_hours,),
        daemon=True
    )
    cleanup_thread.start()