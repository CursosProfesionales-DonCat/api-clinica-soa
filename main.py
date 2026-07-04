import os
import threading
import time
import webbrowser
import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from routers import clinica 
from database import engine, Base

app = FastAPI(
    title="ECOSALUD - API Gateway", 
    description="Orquestación de servicios Hospitalarios",
    version="1.0"
)

# ========================================================
# CONFIGURACIÓN DE CORS (PERMITE CONECTARSE A OTROS)
# ========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# Crea las tablas en PostgreSQL automáticamente al arrancar
Base.metadata.create_all(bind=engine)

# Incluimos el router
app.include_router(clinica.router)

@app.get("/", include_in_schema=False)
def ruta_principal():
    """Si alguien entra a la URL base, lo mandamos a la interfaz"""
    return RedirectResponse(url="/clinica/interfaz")

# ========================================================
# DETECCIÓN CONSTANTE (HEALTH CHECK)
# ========================================================
@app.get("/actuator/health", tags=["Monitorización"])
def health_check():
    """Ruta para que un orquestador verifique la salud en tiempo real"""
    return {
        "status": "UP", 
        "timestamp": time.time(),
        "service": "ECOSALUD-Gateway"
    }

def abrir_navegador():
    time.sleep(2) 
    webbrowser.open("http://127.0.0.1:8000/clinica/interfaz")

if __name__ == "__main__":
    if os.getenv("RENDER") is None:
        threading.Thread(target=abrir_navegador).start()
    
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
