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
from fastapi import APIRouter, Request, Depends, HTTPException, BackgroundTasks
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
from typing import Optional

# Librerías de Resiliencia y Tolerancia a Fallos
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from circuitbreaker import circuit, CircuitBreakerError

# Definimos la ruta de la carpeta templates de forma absoluta pero dinámica
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/clinica", tags=["Módulo Clínica (Grupo 2)"])

# ==========================================
# CONFIGURACIÓN JWT Y MICROSERVICIOS
# ==========================================
URL_GRUPO1_DOCTORES = "https://servicio-doctor-soa.onrender.com"
SECRET_KEY = "8f4e92b3a6d71c85f0e9b4a1c3d2e5f68a7b9c0d1e2f3a4b5c6d7e8f9a0b1c2d" # Cambiar en producción
ALGORITHM = "HS256"

# ==========================================
# ESQUEMAS DE AUTENTICACIÓN
# ==========================================
URL_GRUPO3_PACIENTES = "https://backend-ecosalud.onrender.com/pacientes" 

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
    usuario_brevo = "b106bc001@smtp-brevo.com" # El usuario que confirmamos en tu captura
    
    # LEYENDO LA CLAVE DE BREVO DESDE LAS VARIABLES DE ENTORNO DE RENDER
    password_smtp = os.environ.get("BREVO_SMTP_KEY") 

    msg = MIMEText(f"Hola, tu código de verificación para entrar a ECOSALUD es: {codigo}\n\nEste código expira en 30 segundos.")
    msg['Subject'] = "Código de Seguridad 2FA - ECOSALUD"
    msg['From'] = remitente
    msg['To'] = destinatario

    try:
        # Nos conectamos al relay de Brevo usando el puerto 2525 seguro para Render
        with smtplib.SMTP('smtp-relay.brevo.com', 2525) as server:
            server.set_debuglevel(1)  # Modo espía activado para ver todo en el log de Render
            server.starttls()         # Cifrado obligatorio de Brevo
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
def login_admin(datos: LoginRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Fase 1: Verifica credenciales y envía el código dinámico por correo"""
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == datos.email).first()
    
    if not usuario or usuario.password != datos.password:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    if not usuario.codigo_2fa:
        raise HTTPException(status_code=400, detail="El usuario no tiene configurada la semilla 2FA")

    # Generamos el código basado en el tiempo actual
    codigo_generado = generar_totp(usuario.codigo_2fa)
    
    # ESTA ES LA LÍNEA QUE DEBES ASEGURARTE DE QUE NO TENGA UN '#'
    background_tasks.add_task(enviar_codigo_por_correo, usuario.email, codigo_generado)
    
    print(f"====== EL CÓDIGO DE ACCESO ES: {codigo_generado} ======")
    
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
    
    # RETORNO MODIFICADO: Agregamos el email y el código aquí
    return {
        "status": "success",
        "message": "Acceso autorizado",
        "access_token": token,
        "token_type": "bearer",
        "email": usuario.email,           # <-- Añadido a petición del frontend
        "codigo_2fa": datos.codigo_2fa    # <-- Añadido a petición del frontend
    }

# ==========================================
# BÚSQUEDA DE CITAS POR DOCTOR
# ==========================================
@router.get("/citas/doctor/{doctor_id}", response_model=list[CitaResponse])
def ver_agenda_doctor(doctor_id: int, db: Session = Depends(get_db)):
    citas_bd = db.query(CitaDB).filter(CitaDB.doctor_id == doctor_id).all()
    return citas_bd

@router.get("/citas", response_model=list[CitaResponse])
def ver_todas_las_citas(paciente_id: Optional[int] = None, db: Session = Depends(get_db)):
    if paciente_id:
        return db.query(CitaDB).filter(CitaDB.paciente_id == paciente_id).all()
    return db.query(CitaDB).all()

# ==========================================
# LÓGICA DE RESILIENCIA (CIRCUIT BREAKER & RETRIES)
# ==========================================
def fallback_doctores():
    """Atenuación: Se ejecuta si el circuito está abierto (servicio caído)"""
    raise HTTPException(
        status_code=503,
        detail="ATENUACIÓN ACTIVA: El servicio de Doctores está caído. Operación degradada temporalmente para proteger el sistema."
    )

# Reintenta 3 veces con tiempos de espera de 1s, 2s y 4s
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
# El disyuntor se abre tras 3 fallos y espera 15 segundos antes de intentar reconectar (Semi-Abierto)
@circuit(failure_threshold=3, recovery_timeout=15, fallback_function=fallback_doctores)
def consultar_doctores_seguro():
    """Encapsula la petición HTTP con control de fallos estricto"""
    respuesta = requests.get(f"{URL_GRUPO1_DOCTORES}/doctores?activo=true", timeout=4)
    respuesta.raise_for_status() # Dispara excepción si no responde 200 OK
    return respuesta.json()

# ==========================================
# RUTAS DE NEGOCIO (ORQUESTACIÓN Y ESTADOS)
# ==========================================
@router.post("/cita", response_model=CitaResponse)
def agendar_cita(cita: CitaBase, db: Session = Depends(get_db)):
    """Orquesta la validación con el Grupo 1 y la disponibilidad de horarios"""
    
    # 1. CONSUMO SOA BLINDADO (TOLERANCIA A FALLOS APLICADA)
    try:
        doctores_activos = consultar_doctores_seguro()
        doctor_existe = any(doc["id"] == cita.doctor_id for doc in doctores_activos)
        
        if not doctor_existe:
            raise HTTPException(
                status_code=400, 
                detail=f"Integración G1: El doctor con ID {cita.doctor_id} no existe o no está activo."
            )
            
    except HTTPException as e:
        # Re-lanzar las excepciones HTTP generadas por el fallback o lógica interna
        raise e
    except CircuitBreakerError:
        # Prevención en caso de que la función fallback no logre capturarlo
        raise HTTPException(status_code=503, detail="Circuito Abierto: Fallo general en dependencia externa.")
    except Exception:
        raise HTTPException(status_code=500, detail="Error catastrófico en la red.")

    # 2. VALIDACIÓN DE DISPONIBILIDAD
    cita_existente = db.query(CitaDB).filter(
        CitaDB.doctor_id == cita.doctor_id,
        CitaDB.fecha_hora == cita.fecha_hora
    ).first()

    if cita_existente:
        raise HTTPException(
            status_code=400, 
            detail=f"Conflicto de Agenda: El doctor {cita.doctor_id} ya tiene una cita reservada para ese exacto horario."
        )

    # 3. GUARDAR
    nueva_cita_db = CitaDB(**cita.dict())
    db.add(nueva_cita_db)
    db.commit()
    db.refresh(nueva_cita_db)
    return nueva_cita_db


@router.put("/cita/{cita_id}/estado")
def actualizar_estado_cita(cita_id: int, nuevo_estado: str, db: Session = Depends(get_db)):
    estados_validos = ["AGENDADA", "ATENDIDA", "CANCELADA"]
    nuevo_estado = nuevo_estado.upper()
    
    if nuevo_estado not in estados_validos:
        raise HTTPException(status_code=400, detail="Estado inválido. Use AGENDADA, ATENDIDA o CANCELADA.")
        
    cita = db.query(CitaDB).filter(CitaDB.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="La cita especificada no existe.")
        
    cita.estado = nuevo_estado
    db.commit()
    return {"status": "success", "message": f"Cita #{cita_id} cambiada a estado {nuevo_estado}"}

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

@router.get("/pacientes-atendidos")
def ver_pacientes_atendidos(db: Session = Depends(get_db)):
    pacientes = db.query(CitaDB.paciente_id).distinct().all()
    lista_ids = [p[0] for p in pacientes]
    return {
        "total_pacientes_historicos": len(lista_ids),
        "ids_pacientes": lista_ids
    }

@router.get("/instalar-admin")
def instalar_admin_prueba(db: Session = Depends(get_db)):
    """Ruta temporal para crear o RESETEAR el usuario de prueba"""
    semilla_prueba = "JBSWY3DPEHPK3PXP" 
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == "admin@ecosalud.com").first()
    
    if usuario:
        # Si ya existe, le FORZAMOS la contraseña y la semilla correcta
        usuario.password = "admin"
        usuario.codigo_2fa = semilla_prueba
        db.commit()
        return {"mensaje": "El administrador existía y ha sido reseteado con éxito. Clave actual: admin"}
    
    # Si no existe, lo crea
    nuevo_admin = UsuarioDB(
        email="admin@ecosalud.com",
        password="admin",
        codigo_2fa=semilla_prueba
    )
    db.add(nuevo_admin)
    db.commit()
    
    return {"mensaje": "Usuario creado exitosamente con clave: admin"}
