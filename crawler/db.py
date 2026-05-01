from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, UniqueConstraint, select
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class Job(Base):
    __tablename__ = 'jobs'
    id = Column(Integer, primary_key=True)
    source_site = Column(String, nullable=False, index=True)
    external_id = Column(String, nullable=False, index=True)
    title = Column(String)
    company = Column(String)
    location = Column(String)
    author = Column(String)
    date_posted = Column(DateTime)
    views = Column(Integer)
    votes = Column(Integer)
    category = Column(String)
    content = Column(Text)
    detail_url = Column(String)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint('source_site', 'external_id', name='uix_job_source_external'),
    )

def get_engine(db_path='jobs.db'):
    return create_engine(f'sqlite:///{db_path}', echo=False)

def init_db(engine):
    Base.metadata.create_all(engine)

def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()
