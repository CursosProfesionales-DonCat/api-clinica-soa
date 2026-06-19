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

# Definimos la ruta de la carpeta templates de forma absoluta pero dinámica
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/clinica", tags=["Módulo Clínica (Grupo 2)"])

# ==========================================
# URLS DE MICROSERVICIOS EXTERNOS (SOA)
# ==========================================
URL_GRUPO1_DOCTORES = "https://serviciodoctor.onrender.com"
URL_GRUPO3_PACIENTES = "https://backend-ecosalud.onrender.com" 

# Esquema para recibir los datos del Login
class LoginRequest(BaseModel):
    email: str
    password: str

@router.get("/interfaz", response_class=HTMLResponse)
async def ver_interfaz_clinica(request: Request):
    return templates.TemplateResponse(request=request, name="clinica_agenda.html")

# ==========================================
# AUTENTICACIÓN (EXCLUSIVO PANEL G2)
# ==========================================
@router.post("/login")
def login_admin(datos: LoginRequest, db: Session = Depends(get_db)):
    """Verifica las credenciales del administrador directamente en Supabase"""
    query = text("SELECT * FROM usuarios WHERE email = :email AND password = :password")
    resultado = db.execute(query, {"email": datos.email, "password": datos.password}).fetchone()
    
    if resultado:
        return {"status": "success", "message": "Acceso autorizado"}
    else:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

# ==========================================
# BÚSQUEDA DE CITAS
# ==========================================
@router.get("/citas", response_model=list[CitaResponse])
def ver_todas_las_citas(paciente_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Devuelve todas las citas, con opción de filtrar por paciente_id usando query parameters (?paciente_id=X)"""
    if paciente_id:
        return db.query(CitaDB).filter(CitaDB.paciente_id == paciente_id).all()
    return db.query(CitaDB).all()

@router.get("/citas/doctor/{doctor_id}", response_model=list[CitaResponse])
def ver_agenda_doctor(doctor_id: int, db: Session = Depends(get_db)):
    """Permite a los otros grupos consultar todas las citas de un doctor específico"""
    return db.query(CitaDB).filter(CitaDB.doctor_id == doctor_id).all()

# ==========================================
# RUTAS DE NEGOCIO (ORQUESTACIÓN Y ESTADOS)
# ==========================================

@router.post("/cita", response_model=CitaResponse)
def agendar_cita(cita: CitaBase, db: Session = Depends(get_db)):
    """Orquesta la validación con el Grupo 1 y la disponibilidad de horarios"""
    
    # 1. CONSUMO SOA: Validar que el doctor existe y está activo en el Grupo 1
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

    # 2. VALIDACIÓN DE DISPONIBILIDAD: Verificar cruce de horarios en nuestra BD
    cita_existente = db.query(CitaDB).filter(
        CitaDB.doctor_id == cita.doctor_id,
        CitaDB.fecha_hora == cita.fecha_hora
    ).first()

    if cita_existente:
        raise HTTPException(
            status_code=400, 
            detail=f"Conflicto de Agenda: El doctor {cita.doctor_id} ya tiene una cita reservada para ese exacto horario."
        )

    # 3. GUARDAR: Se guarda la cita con estado inicial AGENDADA
    nueva_cita_db = CitaDB(**cita.dict())
    db.add(nueva_cita_db)
    db.commit()
    db.refresh(nueva_cita_db)
    return nueva_cita_db


@router.put("/cita/{cita_id}/estado")
def actualizar_estado_cita(cita_id: int, nuevo_estado: str, db: Session = Depends(get_db)):
    """NUEVO ENDPOINT: Cambia el estado de una cita (AGENDADA, ATENDIDA, CANCELADA)"""
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

# ==========================================
# REPORTE DE PACIENTES ATENDIDOS
# ==========================================
@router.get("/pacientes-atendidos")
def ver_pacientes_atendidos(db: Session = Depends(get_db)):
    """Devuelve la lista de IDs de pacientes únicos históricos para reportes de Dirección"""
    pacientes = db.query(CitaDB.paciente_id).distinct().all()
    lista_ids = [p[0] for p in pacientes]
    return {
        "total_pacientes_historicos": len(lista_ids),
        "ids_pacientes": lista_ids
    }
