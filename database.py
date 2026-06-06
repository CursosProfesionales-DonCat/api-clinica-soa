from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ¡AQUÍ ESTÁ LA CONEXIÓN A TU BD LOCAL "soa"!
SQLALCHEMY_DATABASE_URL = "postgresql://db_clinica_g2_user:zdPzp8MYGqfcUtgvCFZERuCEHLFZkUO3@dpg-d8ho3a5dt1ts73egtpdg-a.oregon-postgres.render.com/db_clinica_g2"

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()