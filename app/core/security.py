from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from app.core.config import get_settings
from slowapi import Limiter
from slowapi.util import get_remote_address

settings = get_settings()
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

# Inicializar el limitador basado en la IP del cliente
limiter = Limiter(key_func=get_remote_address)

async def validate_api_key(api_key: str = Security(api_key_header)):
    """Valida que el token enviado en el header coincida con el configurado."""
    if api_key == settings.API_KEY:
        return api_key
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="CRITICAL_ERROR: INVALID_API_KEY. ACCESS_DENIED."
    )
