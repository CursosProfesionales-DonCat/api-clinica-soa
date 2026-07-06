import os
import requests
import jwt
import smtplib
import base64
import hmac
import struct
import time
import hashlib

from email.mime.text import MIMEText
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date, text
from database import get_db

# Importamos las tablas y esquemas de la base de datos
from models.clinica import CitaDB, ProcedimientoDB, UsuarioDB 
from schemas.clinica import CitaBase, CitaResponse, ProcedimientoBase, ProcedimientoResponse
from pathlib import Path
from pydantic import BaseModel

# Definimos la ruta de la carpeta templates de forma absoluta pero dinámica
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/clinica", tags=["Módulo Clínica (Grupo 2)"])

# ==========================================
# CONFIGURACIÓN JWT Y MICROSERVICIOS
# ==========================================
URL_GRUPO1_DOCTORES = "https://serviciodoctor.onrender.com"
SECRET_KEY = "8f4e92b3a6d71c85f0e9b4a1c3d2e5f68a7b9c0d1e2f3a4b5c6d7e8f9a0b1c2d" # Cambiar en producción
ALGORITHM = "HS256"

# ==========================================
# ESQUEMAS DE AUTENTICACIÓN
# ==========================================
class LoginRequest(BaseModel):
    email: str
    password: str

class Verify2FARequest(BaseModel):
    email: str
    codigo_2fa: str

# ==========================================
# LÓGICA 2FA NATIVA (TOTP DINÁMICO)
# ==========================================
def generar_hotp(secret_key: str, counter: int, digits: int = 6, digest=hashlib.sha1):
    # Decodifica la clave secreta y empaqueta el contador
    key = base64.b32decode(secret_key.upper() + '=' * ((8 - len(secret_key)) % 8))
    counter_bytes = struct.pack('>Q', counter)
    
    # Genera la firma matemática
    mac = hmac.new(key, counter_bytes, digest).digest()
    
    # Trunca y extrae los 6 dígitos
    offset = mac[-1] & 0x0f
    binary = struct.unpack('>L', mac[offset:offset+4])[0] & 0x7fffffff
    return str(binary)[-digits:].zfill(digits)

def generar_totp(secret_key: str, time_step: int = 30, digits: int = 6):
    # Calcula el contador basado en el tiempo exacto del servidor (cambia cada 30 seg)
    counter = int(time.time() / time_step)
    return generar_hotp(secret_key, counter, digits)

# ==========================================
# FUNCIÓN PARA ENVIAR EL CORREO (CON BREVO)
# ==========================================
def enviar_codigo_por_correo(destinatario: str, codigo: str):
    remitente = "zaidxerneas@gmail.com" 
    usuario_brevo = "b106bc001@smtp-brevo.com" 
    
    # LEYENDO LA CLAVE DESDE RENDER PARA MAYOR SEGURIDAD
    password_smtp = os.environ.get("BREVO_SMTP_KEY") 

    msg = MIMEText(f"Hola, tu código de verificación para entrar a ECOSALUD es: {codigo}\n\nEste código expira en 30 segundos.")
    msg['Subject'] = "Código de Seguridad 2FA - ECOSALUD"
    msg['From'] = remitente
    msg['To'] = destinatario

    try:
        # Nos conectamos al servidor SMTP Relay de Brevo
        with smtplib.SMTP('smtp-relay.brevo.com', 587) as server:
            server.starttls() # Seguridad obligatoria en Brevo
            server.login(usuario_brevo, password_smtp)
            server.send_message(msg)
            print("Correo enviado exitosamente mediante Brevo a", destinatario)
    except Exception as e:
        print(f"Error enviando correo con Brevo: {e}")
        raise HTTPException(status_code=500, detail="Error interno al enviar el correo.")

@router.get("/interfaz", response_class=HTMLResponse)
async def ver_interfaz_clinica(request: Request):
    return templates.TemplateResponse(request=request, name="clinica_agenda.html")

# ==========================================
# AUTENTICACIÓN Y 2FA
# ==========================================
@router.post("/login")
def login_admin(datos: LoginRequest, db: Session = Depends(get_db)):
    """Fase 1: Verifica credenciales y envía el código dinámico por correo"""
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == datos.email).first()
    
    if not usuario or usuario.password != datos.password:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    if not usuario.codigo_2fa:
        raise HTTPException(status_code=400, detail="El usuario no tiene configurada la semilla 2FA")

    # Generamos el código basado en el tiempo actual usando la semilla de Supabase
    codigo_generado = generar_totp(usuario.codigo_2fa)
    
    # Disparamos el correo
    enviar_codigo_por_correo(usuario.email, codigo_generado)
    
    return {
        "status": "success", 
        "message": "Código enviado. Revisa tu bandeja de entrada.",
        "requiere_2fa": True
    }

@router.post("/verificar-2fa")
def verificar_codigo_2fa(datos: Verify2FARequest, db: Session = Depends(get_db)):
    """Fase 2: Valida el código del correo matemáticamente y devuelve el Token JWT"""
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == datos.email).first()
    
    if not usuario or not usuario.codigo_2fa:
        raise HTTPException(status_code=400, detail="Usuario no válido o semilla no configurada")

    # Calculamos cuál debería ser el código válido en este exacto segundo
    codigo_valido_actual = generar_totp(usuario.codigo_2fa)

    if datos.codigo_2fa != codigo_valido_actual:
        raise HTTPException(status_code=401, detail="El código 2FA es incorrecto o ha expirado")

    expiracion = datetime.utcnow() + timedelta(hours=2)
    payload = {
        "sub": usuario.email,
        "2fa_aprobado": True,
        "exp": expiracion
    }
    
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    return {
        "status": "success",
        "message": "Acceso autorizado",
        "access_token": token,
        "token_type": "bearer"
    }

# ==========================================
# BÚSQUEDA DE CITAS POR DOCTOR
# ==========================================
@router.get("/citas/doctor/{doctor_id}", response_model=list[CitaResponse])
def ver_agenda_doctor(doctor_id: int, db: Session = Depends(get_db)):
    citas_bd = db.query(CitaDB).filter(CitaDB.doctor_id == doctor_id).all()
    return citas_bd

# ==========================================
# RUTAS DE NEGOCIO (ORQUESTACIÓN)
# ==========================================
@router.post("/cita", response_model=CitaResponse)
def agendar_cita(cita: CitaBase, db: Session = Depends(get_db)):
    try:
        respuesta_doctores = requests.get(f"{URL_GRUPO1_DOCTORES}/doctores?activo=true", timeout=5)
        if respuesta_doctores.status_code == 200:
            doctores_activos = respuesta_doctores.json()
            doctor_existe = any(doc["id"] == cita.doctor_id for doc in doctores_activos)
            
            if not doctor_existe:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Integración G1: El doctor con ID {cita.doctor_id} no existe o no está activo."
                )
        else:
            raise HTTPException(status_code=503, detail="El microservicio del Grupo 1 no responde correctamente.")
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=503, detail="Error de conexión con el servidor del Grupo 1.")

    cita_existente = db.query(CitaDB).filter(
        CitaDB.doctor_id == cita.doctor_id,
        CitaDB.fecha_hora == cita.fecha_hora
    ).first()

    if cita_existente:
        raise HTTPException(
            status_code=400, 
            detail=f"Conflicto de Agenda: El doctor {cita.doctor_id} ya tiene una cita reservada para ese exacto horario."
        )

    nueva_cita_db = CitaDB(**cita.dict())
    db.add(nueva_cita_db)
    db.commit()
    db.refresh(nueva_cita_db)
    return nueva_cita_db

@router.get("/citas/{fecha}", response_model=list[CitaResponse])
def ver_agenda_diaria(fecha: date, db: Session = Depends(get_db)):
    citas_bd = db.query(CitaDB).filter(cast(CitaDB.fecha_hora, Date) == fecha).all()
    return citas_bd

@router.post("/procedimiento", response_model=ProcedimientoResponse)
def registrar_procedimiento(proc: ProcedimientoBase, db: Session = Depends(get_db)):
    nuevo_proc_db = ProcedimientoDB(**proc.dict())
    db.add(nuevo_proc_db)
    db.commit()
    db.refresh(nuevo_proc_db)
    return nuevo_proc_db

# ==========================================
# REPORTE DE PACIENTES ATENDIDOS
# ==========================================
@router.get("/pacientes-atendidos")
def ver_pacientes_atendidos(db: Session = Depends(get_db)):
    pacientes = db.query(CitaDB.paciente_id).distinct().all()
    lista_ids = [p[0] for p in pacientes]
    return {
        "total_pacientes_historicos": len(lista_ids),
        "ids_pacientes": lista_ids
    }
