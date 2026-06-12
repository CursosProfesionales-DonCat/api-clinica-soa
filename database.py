from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ¡NUEVA CONEXIÓN A SUPABASE (Usando el Transaction Pooler puerto 6543)!
SQLALCHEMY_DATABASE_URL = "postgresql://postgres.okydwhigvrzdjfzumvun:Dn35vNv8dJeMi2Qv@aws-1-us-east-2.pooler.supabase.com:6543/postgres"

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
