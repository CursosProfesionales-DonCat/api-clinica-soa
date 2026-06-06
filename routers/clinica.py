from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date
from database import get_db
from models.clinica import CitaDB
from schemas.clinica import CitaBase, CitaResponse, ProcedimientoBase, ProcedimientoResponse
from datetime import datetime, date

router = APIRouter(prefix="/clinica", tags=["Módulo Clínica (Grupo 2)"])
templates = Jinja2Templates(directory="templates")

@router.get("/interfaz", response_class=HTMLResponse)
async def ver_interfaz_clinica(request: Request):
    """Renderiza la GUI de la Clínica (Dashboard Web)"""
    return templates.TemplateResponse(request=request, name="clinica_agenda.html")

# ==========================================
# 1. RUTA PARA AGENDAR (Guarda en BD real)
# ==========================================
@router.post("/cita", response_model=CitaResponse)
def agendar_cita(cita: CitaBase, db: Session = Depends(get_db)):
    nueva_cita_db = CitaDB(
        clinica_id=cita.clinica_id,
        sede_id=cita.sede_id,
        paciente_id=cita.paciente_id,
        doctor_id=cita.doctor_id,
        fecha_hora=cita.fecha_hora,
        duracion_minutos=cita.duracion_minutos,
        motivo=cita.motivo
    )
    db.add(nueva_cita_db)
    db.commit()
    db.refresh(nueva_cita_db)
    return nueva_cita_db

# ==========================================
# 2. RUTA PARA BUSCAR AGENDA (Lee la BD real)
# ==========================================
@router.get("/citas/{fecha}", response_model=list[CitaResponse])
def ver_agenda_diaria(fecha: date, db: Session = Depends(get_db)):
    # Le decimos a la base de datos que busque solo las fechas que coincidan
    citas_bd = db.query(CitaDB).filter(cast(CitaDB.fecha_hora, Date) == fecha).all()
    return citas_bd

# ==========================================
# 3. RUTA PARA PROCEDIMIENTOS (Guarda en BD real)
# ==========================================
from models.clinica import ProcedimientoDB # Asegúrate de que esta importación funcione o ponla arriba

@router.post("/procedimiento", response_model=ProcedimientoResponse)
def registrar_procedimiento(proc: ProcedimientoBase, db: Session = Depends(get_db)):
    
    # Transformamos el JSON recibido al Modelo de Base de datos
    nuevo_proc_db = ProcedimientoDB(
        cita_id=proc.cita_id,
        paciente_id=proc.paciente_id,
        clinica_id=proc.clinica_id,
        nombre_procedimiento=proc.nombre_procedimiento,
        costo=proc.costo
    )
    
    db.add(nuevo_proc_db)
    db.commit()
    db.refresh(nuevo_proc_db)
    
    return nuevo_proc_db