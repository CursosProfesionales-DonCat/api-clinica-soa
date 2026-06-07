from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date
from database import get_db
from models.clinica import CitaDB, ProcedimientoDB
from schemas.clinica import CitaBase, CitaResponse, ProcedimientoBase, ProcedimientoResponse
from datetime import date
from pathlib import Path

# Definimos la ruta de la carpeta templates de forma absoluta pero dinámica
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/clinica", tags=["Módulo Clínica (Grupo 2)"])

@router.get("/interfaz", response_class=HTMLResponse)
async def ver_interfaz_clinica(request: Request):
    # Corrección clave para la nube: request=request y name=...
    return templates.TemplateResponse(request=request, name="clinica_agenda.html")

# ==========================================
# BÚSQUEDA DE CITAS POR DOCTOR
# ==========================================
@router.get("/citas/doctor/{doctor_id}", response_model=list[CitaResponse])
def ver_agenda_doctor(doctor_id: int, db: Session = Depends(get_db)):
    """Permite a los otros grupos consultar todas las citas de un doctor específico"""
    citas_bd = db.query(CitaDB).filter(CitaDB.doctor_id == doctor_id).all()
    return citas_bd

# ==========================================
# RUTAS DE NEGOCIO
# ==========================================

@router.post("/cita", response_model=CitaResponse)
def agendar_cita(cita: CitaBase, db: Session = Depends(get_db)):
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

