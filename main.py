import os
import threading
import time
import webbrowser
import uvicorn
import jwt
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from routers import clinica 
from database import engine, Base

# Configuración para descifrar el Token (DEBE SER LA MISMA QUE EN clinica.py)
SECRET_KEY = "tu_clave_secreta_super_segura"
ALGORITHM = "HS256"

app = FastAPI(
    title="ECOSALUD - API Gateway", 
    description="Orquestación de servicios Hospitalarios",
    version="1.0"
)

# ========================================================
# 1. CONFIGURACIÓN DE CORS (PERMITE CONECTARSE A OTROS)
# ========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# ========================================================
# 2. MIDDLEWARE DE SEGURIDAD JWT Y 2FA (EL GUARDIÁN)
# ========================================================
@app.middleware("http")
async def verificar_token_2fa(request: Request, call_next):
    # Definimos qué rutas NO necesitan token para que el usuario pueda iniciar sesión
    rutas_publicas = [
        "/",
        "/clinica/interfaz",
        "/clinica/login",
        "/clinica/verificar-2fa",
        "/docs",           # Documentación de FastAPI
        "/openapi.json"    # Esquema de la API
    ]

    # Si la ruta es pública, dejamos pasar la petición sin revisar nada
    if request.url.path in rutas_publicas:
        return await call_next(request)

    # Si la ruta es privada, exigimos el Token en la cabecera
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401, 
            content={"detail": "No autorizado: Falta el token JWT o formato inválido"}
        )

    # Extraemos el token (quitando la palabra "Bearer ")
    token = auth_header.split(" ")[1]

    try:
        # Intentamos descifrar el token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Verificamos específicamente que el 2FA haya sido aprobado
        if not payload.get("2fa_aprobado"):
            return JSONResponse(
                status_code=403, 
                content={"detail": "Prohibido: No has completado la validación de 2 pasos"}
            )
            
    except jwt.ExpiredSignatureError:
        return JSONResponse(status_code=401, content={"detail": "Tu sesión ha expirado"})
    except jwt.InvalidTokenError:
        return JSONResponse(status_code=401, content={"detail": "Token inválido o corrupto"})

    # Si el token es válido y tiene el 2FA, procesamos la petición normalmente
    response = await call_next(request)
    return response
# ========================================================

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
