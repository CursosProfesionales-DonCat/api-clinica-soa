from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional

# ---- Esquemas para Citas ----
class CitaBase(BaseModel):
    clinica_id: int = Field(..., gt=0)
    sede_id: int = Field(..., gt=0)
    paciente_id: int = Field(..., gt=0)
    doctor_id: int = Field(..., gt=0)
    fecha_hora: datetime
    duracion_minutos: int = Field(default=30, gt=0)
    motivo: Optional[str] = Field(None, max_length=200)

class CitaResponse(CitaBase):
    id: int
    estado: str
    creado_en: datetime

    # Configuración esencial para que SQLAlchemy se comunique con FastAPI
    class Config:
        orm_mode = True
        from_attributes = True

# ---- Esquemas para Procedimientos ----
class ProcedimientoBase(BaseModel):
    cita_id: Optional[int] = None
    paciente_id: int = Field(..., gt=0)
    clinica_id: int = Field(..., gt=0)
    nombre_procedimiento: str = Field(..., min_length=3, max_length=150)
    costo: float = Field(..., ge=0.0)

class ProcedimientoResponse(ProcedimientoBase):
    id: int
    estado: str

    # Configuración esencial para que SQLAlchemy se comunique con FastAPI
    class Config:
        orm_mode = True
        from_attributes = True