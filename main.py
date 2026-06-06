from fastapi import FastAPI
import webbrowser
import threading
import time
import uvicorn

# 1. Importamos el Router normal
from routers import clinica 

# 2. Importamos el Modelo CON UN APODO (alias) para que no choque el nombre
from models import clinica as modelos_clinica
from database import engine, Base

app = FastAPI(
    title="ECOSALUD - API Gateway", 
    description="Orquestación de servicios Hospitalarios",
    version="1.0"
)

# Esto crea la tabla en PostgreSQL
Base.metadata.create_all(bind=engine)

# Aquí agregamos el router (ahora Python sabe exactamente cuál es)
app.include_router(clinica.router)

def abrir_navegador():
    time.sleep(1.5) 
    webbrowser.open("http://127.0.0.1:8000/clinica/interfaz")

if __name__ == "__main__":
    # Solo abrimos el navegador si estamos en tu laptop (modo local)
    # Importamos os para detectar si estamos en un entorno de servidor
    import os
    if os.getenv("RENDER") is None:
        threading.Thread(target=abrir_navegador).start()
    
    # "0.0.0.0" es la clave para que la nube (Render) escuche las peticiones
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))