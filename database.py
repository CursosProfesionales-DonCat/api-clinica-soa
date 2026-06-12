from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ¡NUEVA CONEXIÓN A SUPABASE (El Puente)!
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:Dn35vNv8dJeMi2Qv@db.okydwhigvrzdjfzumvun.supabase.co:5432/postgres"

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
