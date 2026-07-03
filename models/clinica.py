from sqlalchemy import Column, Integer, String, DateTime, Float
from database import Base
from datetime import datetime

# 1. TABLA DE CITAS (La que ya teníamos)
class CitaDB(Base):
    __tablename__ = "citas"
    
    id = Column(Integer, primary_key=True, index=True)
    clinica_id = Column(Integer, nullable=False)
    sede_id = Column(Integer, nullable=False)
    paciente_id = Column(Integer, nullable=False)
    doctor_id = Column(Integer, nullable=False)
    fecha_hora = Column(DateTime, nullable=False)
    duracion_minutos = Column(Integer, default=30)
    motivo = Column(String(200))
    estado = Column(String(30), default='AGENDADA')
    creado_en = Column(DateTime, default=datetime.utcnow)

# 2. NUEVA TABLA DE PROCEDIMIENTOS
class ProcedimientoDB(Base):
    __tablename__ = "procedimientos"

    id = Column(Integer, primary_key=True, index=True)
    cita_id = Column(Integer, nullable=True) 
    paciente_id = Column(Integer, nullable=False)
    clinica_id = Column(Integer, nullable=False)
    nombre_procedimiento = Column(String(150), nullable=False)
    costo = Column(Float, nullable=False)
    estado = Column(String(30), default='PROGRAMADO')

# 3. TABLA DE USUARIOS / ADMINISTRADORES (Para el Login y 2FA)
class UsuarioDB(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(150), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)  # Contraseña hash
    secreto_2fa = Column(String(32), nullable=True)  # Clave base32 generada por pyotp
