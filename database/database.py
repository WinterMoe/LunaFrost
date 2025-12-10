

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager

                                                 
                                                 
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://lunafrost:change-me-in-production@localhost:5432/lunafrost_db')

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,                                   
    echo=False                                                  
)

SessionFactory = sessionmaker(bind=engine)

SessionLocal = scoped_session(SessionFactory)

def get_db_session():

    return SessionLocal()

@contextmanager
def db_session_scope():

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def init_db():

    from database.db_models import Base
    Base.metadata.create_all(bind=engine)

def drop_all_tables():

    from database.db_models import Base
    Base.metadata.drop_all(bind=engine)