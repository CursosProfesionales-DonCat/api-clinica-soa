import os
import threading
import time
import webbrowser
import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse  # <-- Agregamos esto
from routers import clinica 
from database import engine, Base

app = FastAPI(
    title="ECOSALUD - API Gateway", 
    description="Orquestación de servicios Hospitalarios",
    version="1.0"
)

# Crea las tablas en PostgreSQL automáticamente al arrancar
Base.metadata.create_all(bind=engine)

# Incluimos el router
app.include_router(clinica.router)

# ========================================================
# NUEVO: Redirección automática para el Profesor
# ========================================================
@app.get("/", include_in_schema=False)
def ruta_principal():
    """Si alguien entra a la URL base, lo mandamos a la interfaz"""
    return RedirectResponse(url="/clinica/interfaz")
# ========================================================

def abrir_navegador():
    time.sleep(2) 
    webbrowser.open("http://127.0.0.1:8000/clinica/interfaz")

if __name__ == "__main__":
    # Solo abre el navegador si NO estamos en Render
    if os.getenv("RENDER") is None:
        threading.Thread(target=abrir_navegador).start()
    
    # Puerto dinámico para Render o puerto 8000 local
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)