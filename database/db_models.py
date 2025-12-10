from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, Boolean, ForeignKey, Index, ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()

class Novel(Base):

    __tablename__ = 'novels'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    title = Column(String(500), nullable=False)                
    original_title = Column(String(500))                                                       
    translated_title = Column(String(500))                            
    author = Column(String(255))                 
    translated_author = Column(String(255))                             
    cover_url = Column(Text)
    tags = Column(ARRAY(String))               
    translated_tags = Column(ARRAY(String))                           
    synopsis = Column(Text)                   
    translated_synopsis = Column(Text)                               
    glossary = Column(JSONB)                                            
    source_url = Column(Text)
    share_token = Column(String(100), unique=True, index=True)
    is_shared = Column(Boolean, default=False)
    imported_from_share_token = Column(String(100), index=True)                                                   
    custom_prompt_suffix = Column(Text, nullable=True)                                                   
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    chapters = relationship('Chapter', back_populates='novel', cascade='all, delete-orphan', lazy='dynamic')
    exports = relationship('Export', back_populates='novel', cascade='all, delete-orphan')
    
    __table_args__ = (
        Index('idx_novels_user_slug', 'user_id', 'slug', unique=True),
    )
    
    def __repr__(self):
        return f"<Novel(id={self.id}, title='{self.title}', user_id='{self.user_id}')>"
    
    def to_dict(self):

        return {
            'id': self.id,
            'user_id': self.user_id,
            'slug': self.slug,
            'title': self.title,
            'original_title': self.original_title,
            'translated_title': self.translated_title,
            'author': self.author,
            'translated_author': self.translated_author,
            'cover_url': self.cover_url,
            'cover': self.cover_url,                          
            'cover_image': self.cover_url,                                   
            'tags': self.tags or [],
            'translated_tags': self.translated_tags or [],
            'synopsis': self.synopsis,
            'translated_synopsis': self.translated_synopsis,
            'glossary': self.glossary or {},
            'source_url': self.source_url,
            'novel_source_url': self.source_url,                          
            'share_token': self.share_token,
            'is_shared': self.is_shared,
            'imported_from_share_token': self.imported_from_share_token,
            'custom_prompt_suffix': self.custom_prompt_suffix,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'chapter_count': self.chapters.count() if self.chapters else 0
        }

class Chapter(Base):

    __tablename__ = 'chapters'
    
    id = Column(Integer, primary_key=True)
    novel_id = Column(Integer, ForeignKey('novels.id', ondelete='CASCADE'), nullable=False, index=True)
    slug = Column(String(255), nullable=False)
    title = Column(String(500), nullable=False)                
    original_title = Column(String(500))                         
    translated_title = Column(String(500))                            
    chapter_number = Column(String(50))
    content = Column(Text, nullable=False)                  
    translated_content = Column(Text)                              
    translation_model = Column(String(100))                              
    
    translation_status = Column(String(20), default='pending')                                           
    translation_task_id = Column(String(100))                  
    translation_started_at = Column(TIMESTAMP)
    translation_completed_at = Column(TIMESTAMP)
    
    images = Column(JSONB)                                         
    source_url = Column(Text)
    position = Column(Integer, nullable=False)
    is_bonus = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    novel = relationship('Novel', back_populates='chapters')
    
    __table_args__ = (
        Index('idx_chapters_novel_slug', 'novel_id', 'slug', unique=True),
        Index('idx_chapters_position', 'novel_id', 'position'),
    )
    
    def __repr__(self):
        return f"<Chapter(id={self.id}, title='{self.title}', novel_id={self.novel_id}, position={self.position})>"
    
    def to_dict(self, include_content=True):

        data = {
            'id': self.id,
            'novel_id': self.novel_id,
            'slug': self.slug,
            'title': self.title,
            'original_title': self.original_title,
            'translated_title': self.translated_title or self.title,                                   
            'chapter_number': self.chapter_number,
            'images': self.images or [],
            'source_url': self.source_url,
            'position': self.position,
            'is_bonus': self.is_bonus,
            'translation_status': self.translation_status or 'pending',
            'translation_task_id': self.translation_task_id,
            'translation_started_at': self.translation_started_at.isoformat() if self.translation_started_at else None,
            'translation_completed_at': self.translation_completed_at.isoformat() if self.translation_completed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'imported_at': self.created_at.isoformat() if self.created_at else None,                          
        }
        
        if include_content:
            data['content'] = self.content
            data['korean_text'] = self.content                          
            data['translated_text'] = self.translated_content or ''                
            data['translated_content'] = self.translated_content or ''                                 
            data['translation_model'] = self.translation_model or ''
        
        return data

class UserSettings(Base):

    __tablename__ = 'user_settings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, unique=True, index=True)
    translation_api_key = Column(Text)
    translation_model = Column(String(100), default='gpt-4o-mini')
    custom_prompt_suffix = Column(Text, nullable=True)                                                 
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<UserSettings(user_id='{self.user_id}', model='{self.translation_model}')>"
    
    def to_dict(self):

        return {
            'user_id': self.user_id,
            'translation_api_key': self.translation_api_key,
            'translation_model': self.translation_model,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class Export(Base):

    __tablename__ = 'exports'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    novel_id = Column(Integer, ForeignKey('novels.id', ondelete='CASCADE'), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    format = Column(String(10), nullable=False)                   
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True)
    
    novel = relationship('Novel', back_populates='exports')
    
    def __repr__(self):
        return f"<Export(id={self.id}, filename='{self.filename}', format='{self.format}')>"
    
    def to_dict(self):

        return {
            'id': self.id,
            'user_id': self.user_id,
            'novel_id': self.novel_id,
            'filename': self.filename,
            'file_path': self.file_path,
            'format': self.format,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

class TranslationTokenUsage(Base):

    __tablename__ = 'translation_token_usage'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    chapter_id = Column(Integer, ForeignKey('chapters.id', ondelete='CASCADE'), nullable=False, index=True)
    provider = Column(String(50), nullable=False)                                    
    model = Column(String(100), nullable=False)                   
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    translation_type = Column(String(20), default='content')                              
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True)
    
    chapter = relationship('Chapter', backref='token_usage_records', passive_deletes=True)
    
    __table_args__ = (
        Index('idx_token_usage_user_date', 'user_id', 'created_at'),
        Index('idx_token_usage_chapter', 'chapter_id'),
    )
    
    def __repr__(self):
        return f"<TranslationTokenUsage(id={self.id}, chapter_id={self.chapter_id}, total_tokens={self.total_tokens})>"
    
    def to_dict(self):

        return {
            'id': self.id,
            'user_id': self.user_id,
            'chapter_id': self.chapter_id,
            'provider': self.provider,
            'model': self.model,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'total_tokens': self.total_tokens,
            'translation_type': self.translation_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

class GlobalModelPricing(Base):

    __tablename__ = 'global_model_pricing'
    
    id = Column(Integer, primary_key=True)
    provider = Column(String(50), nullable=False)                                    
    model_name = Column(String(200), nullable=False)                         
    input_price_per_1m = Column(String(50))                                                       
    output_price_per_1m = Column(String(50))                                                        
    notes = Column(Text)                                
    updated_by = Column(String(100))                             
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_global_pricing_provider_model', 'provider', 'model_name', unique=True),
    )
    
    def __repr__(self):
        return f"<GlobalModelPricing(provider='{self.provider}', model='{self.model_name}')>"
    
    def to_dict(self):

        return {
            'id': self.id,
            'provider': self.provider,
            'model_name': self.model_name,
            'input_price_per_1m': self.input_price_per_1m,
            'output_price_per_1m': self.output_price_per_1m,
            'notes': self.notes,
            'updated_by': self.updated_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class ReadingPreference(Base):

    __tablename__ = 'reading_preferences'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, unique=True, index=True)
    
    color_mode = Column(String(20), default='light')
    
    font_size = Column(Integer, default=16)      
    line_height = Column(String(10), default='1.8')                        
    font_family = Column(String(100), default='var(--font-serif)')
    
    reading_width = Column(String(20), default='720px')
    text_alignment = Column(String(20), default='left')
    
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<ReadingPreference(user_id='{self.user_id}', color_mode='{self.color_mode}')>"
    
    def to_dict(self):

        return {
            'user_id': self.user_id,
            'color_mode': self.color_mode,
            'font_size': self.font_size,
            'line_height': self.line_height,
            'font_family': self.font_family,
            'reading_width': self.reading_width,
            'text_alignment': self.text_alignment,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class User(Base):

    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(Text, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    settings = Column(JSONB, default={})                                             
    max_novels_override = Column(Integer, nullable=True)                                            
    max_webtoons_override = Column(Integer, nullable=True)                                           
    created_at = Column(TIMESTAMP, server_default=func.now())
    last_login = Column(TIMESTAMP)
    
    __table_args__ = (
        Index('idx_users_username_lower', func.lower(username), unique=True),
        Index('idx_users_email_lower', func.lower(email), unique=True),
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', is_admin={self.is_admin})>"
    
    def to_dict(self, include_sensitive=False):

        data = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_admin': self.is_admin,
            'max_novels_override': self.max_novels_override,
            'max_webtoons_override': getattr(self, 'max_webtoons_override', None),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
        }
        if include_sensitive:
            data['settings'] = self.settings or {}
        return data

class ContactMessage(Base):
    __tablename__ = 'contact_messages'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    read = Column(Boolean, default=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'subject': self.subject,
            'message': self.message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'read': self.read
        }

class GlobalSettings(Base):

    __tablename__ = 'global_settings'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    description = Column(Text)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<GlobalSettings(key='{self.key}', value='{self.value}')>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class PasswordReset(Base):

    __tablename__ = 'password_resets'
    
    id = Column(Integer, primary_key=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False, index=True)
    used_at = Column(TIMESTAMP, nullable=True)
    
    __table_args__ = (
        Index('idx_password_resets_token', 'token'),
        Index('idx_password_resets_user', 'user_id'),
    )
    
    def __repr__(self):
        return f"<PasswordReset(token='{self.token[:10]}...', user_id='{self.user_id}', used={self.used})>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'token': self.token,
            'user_id': self.user_id,
            'email': self.email,
            'used': self.used,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'used_at': self.used_at.isoformat() if self.used_at else None
        }

class WebtoonJob(Base):
                                               
    __tablename__ = 'webtoon_jobs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)                                    
    job_id = Column(String(255), unique=True, nullable=False, index=True)
    
                     
    title = Column(String(500), nullable=True)                                                             
    author = Column(String(255), nullable=True)               
    synopsis = Column(Text, nullable=True)                        
    tags = Column(Text, nullable=True)                                         
    reading_mode = Column(String(50), default='manga')                                                         
    cover_image_id = Column(Integer, nullable=True)                                                            
    glossary = Column(JSONB, nullable=True)                                                         
    custom_prompt_suffix = Column(Text, nullable=True)                                                 
    
                       
    status = Column(String(50), default='pending')                                                                 
    total_images = Column(Integer, nullable=False, default=0)
    processed_images = Column(Integer, default=0)
    failed_images = Column(Integer, default=0)
    ocr_method = Column(String(50), nullable=True)                                                        
    source_language = Column(String(50), nullable=False, default='korean')                    
    overwrite_text = Column(Boolean, default=True)                                                               
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    completed_at = Column(TIMESTAMP, nullable=True)
    error_message = Column(Text, nullable=True)
    
                   
    images = relationship('WebtoonImage', backref='job', cascade='all, delete-orphan', foreign_keys='WebtoonImage.job_id')
    
    __table_args__ = (
        Index('idx_webtoon_jobs_user_status', 'user_id', 'status'),
        Index('idx_webtoon_jobs_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f"<WebtoonJob(id={self.id}, job_id='{self.job_id}', title='{self.title}', status='{self.status}')>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'job_id': self.job_id,
            'title': self.title,
            'author': self.author,
            'synopsis': self.synopsis,
            'tags': self.tags.split(',') if self.tags else [],
            'reading_mode': self.reading_mode,
            'cover_image_id': self.cover_image_id,
            'status': self.status,
            'total_images': self.total_images,
            'processed_images': self.processed_images,
            'failed_images': self.failed_images,
            'ocr_method': self.ocr_method,
            'source_language': self.source_language,
            'overwrite_text': self.overwrite_text,
            'glossary': self.glossary or [],
            'custom_prompt_suffix': self.custom_prompt_suffix,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message,
        }

class WebtoonImage(Base):
                                                           
    __tablename__ = 'webtoon_images'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(String(255), ForeignKey('webtoon_jobs.job_id', ondelete='CASCADE'), nullable=False, index=True)
    
                                 
    chapter_number = Column(Integer, default=1)                                           
    chapter_name = Column(String(255), nullable=True)                                        
    page_order = Column(Integer, default=1)                                                          
    
                
    original_filename = Column(String(255), nullable=False)
    original_path = Column(String(500), nullable=False)
    translated_path = Column(String(500), nullable=True)
    typeset_path = Column(String(500), nullable=True)                               
    
                       
    status = Column(String(50), default='pending')                                          
    typeset_status = Column(String(50), default=None)                             
    ocr_text = Column(Text, nullable=True)                                
    translated_text = Column(Text, nullable=True)                                  
    typeset_overrides = Column(JSONB, nullable=True)                                                    
    processing_time = Column(Text, nullable=True)                                                    
    error_message = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_webtoon_images_job_status', 'job_id', 'status'),
        Index('idx_webtoon_images_job_chapter', 'job_id', 'chapter_number', 'page_order'),
    )
    
    def __repr__(self):
        return f"<WebtoonImage(id={self.id}, job_id='{self.job_id}', chapter={self.chapter_number}, page={self.page_order})>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'job_id': self.job_id,
            'chapter_number': self.chapter_number,
            'chapter_name': self.chapter_name,
            'page_order': self.page_order,
            'original_filename': self.original_filename,
            'original_path': self.original_path,
            'translated_path': self.translated_path,
            'typeset_path': self.typeset_path,
            'status': self.status,
            'typeset_status': self.typeset_status,
            'processing_time': self.processing_time,
            'error_message': self.error_message,
            'typeset_overrides': self.typeset_overrides or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class UserOCRSettings(Base):
                                                    
    __tablename__ = 'user_ocr_settings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), unique=True, nullable=False, index=True)                                    
    
                                                        
    google_api_key = Column(Text, nullable=True)
    azure_api_key = Column(Text, nullable=True)
    azure_endpoint = Column(String(500), nullable=True)
    gemini_api_key = Column(Text, nullable=True)                       
    
                 
    default_ocr_method = Column(String(50), default='nanobananapro')
    nanobananapro_api_source = Column(String(50), default='gemini')                            
    custom_prompt_suffix = Column(Text, nullable=True)                                                   
    
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<UserOCRSettings(user_id='{self.user_id}', default_ocr_method='{self.default_ocr_method}')>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'default_ocr_method': self.default_ocr_method,
            'google_api_key_configured': bool(self.google_api_key),
            'azure_api_key_configured': bool(self.azure_api_key),
            'azure_endpoint': self.azure_endpoint,
            'gemini_api_key_configured': bool(self.gemini_api_key),
            'custom_prompt_suffix': self.custom_prompt_suffix,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }