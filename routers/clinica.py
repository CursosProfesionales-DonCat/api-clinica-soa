import requests
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date, text
from database import get_db
from models.clinica import CitaDB, ProcedimientoDB
from schemas.clinica import CitaBase, CitaResponse, ProcedimientoBase, ProcedimientoResponse
from datetime import date
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
# URLS DE MICROSERVICIOS EXTERNOS (SOA)
# ==========================================
URL_GRUPO1_DOCTORES = "https://serviciodoctor.onrender.com"
URL_GRUPO3_PACIENTES = "https://backend-ecosalud.onrender.com" 

class LoginRequest(BaseModel):
    email: str
    password: str

@router.get("/interfaz", response_class=HTMLResponse)
async def ver_interfaz_clinica(request: Request):
    return templates.TemplateResponse(request=request, name="clinica_agenda.html")

@router.post("/login")
def login_admin(datos: LoginRequest, db: Session = Depends(get_db)):
    query = text("SELECT * FROM usuarios WHERE email = :email AND password = :password")
    resultado = db.execute(query, {"email": datos.email, "password": datos.password}).fetchone()
    
    if resultado:
        return {"status": "success", "message": "Acceso autorizado"}
    else:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

@router.get("/citas", response_model=list[CitaResponse])
def ver_todas_las_citas(paciente_id: Optional[int] = None, db: Session = Depends(get_db)):
    if paciente_id:
        return db.query(CitaDB).filter(CitaDB.paciente_id == paciente_id).all()
    return db.query(CitaDB).all()

@router.get("/citas/doctor/{doctor_id}", response_model=list[CitaResponse])
def ver_agenda_doctor(doctor_id: int, db: Session = Depends(get_db)):
    return db.query(CitaDB).filter(CitaDB.doctor_id == doctor_id).all()

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
