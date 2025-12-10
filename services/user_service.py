

import os
import shutil
from database.database import db_session_scope
from database.db_models import (
    User, Novel, Chapter, UserSettings, ReadingPreference,
    UserOCRSettings, TranslationTokenUsage, WebtoonJob, WebtoonImage, Export
)

DATA_DIR = 'data'

def get_user_data_dir(user_id):
    return os.path.join(DATA_DIR, 'users', user_id)

def delete_user_account(username):
    with db_session_scope() as session:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            return False, "User not found"
        
        user_id = user.username

        novels = session.query(Novel).filter(Novel.user_id == user_id).all()
        for novel in novels:
            if novel.share_token:
                shared_copies = session.query(Novel).filter(
                    Novel.imported_from_share_token == novel.share_token
                ).all()
                for shared_novel in shared_copies:
                    shared_chapter_ids = [c.id for c in session.query(Chapter.id).filter_by(novel_id=shared_novel.id).all()]
                    if shared_chapter_ids:
                        session.query(TranslationTokenUsage).filter(
                            TranslationTokenUsage.chapter_id.in_(shared_chapter_ids)
                        ).delete(synchronize_session=False)
                    session.delete(shared_novel)
            
            chapter_ids = [c.id for c in session.query(Chapter.id).filter_by(novel_id=novel.id).all()]
            if chapter_ids:
                session.query(TranslationTokenUsage).filter(
                    TranslationTokenUsage.chapter_id.in_(chapter_ids)
                ).delete(synchronize_session=False)
            
            session.delete(novel)

        session.query(WebtoonJob).filter(WebtoonJob.user_id == user_id).delete(synchronize_session=False)

        session.query(UserSettings).filter(UserSettings.user_id == user_id).delete(synchronize_session=False)
        session.query(ReadingPreference).filter(ReadingPreference.user_id == user_id).delete(synchronize_session=False)
        session.query(UserOCRSettings).filter(UserOCRSettings.user_id == user_id).delete(synchronize_session=False)

        session.delete(user)

    user_data_dir = get_user_data_dir(user_id)
    if os.path.exists(user_data_dir):
        try:
            shutil.rmtree(user_data_dir)
        except Exception:
            pass
    
    return True, "Account deleted successfully"
