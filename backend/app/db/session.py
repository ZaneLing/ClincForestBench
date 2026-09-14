from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import Settings


settings = Settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

