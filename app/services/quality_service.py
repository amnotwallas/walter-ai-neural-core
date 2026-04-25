from app.core.logger import get_logger

logger = get_logger("QualityGuard")

class QualityGuard:
    """
    Evalúa la calidad de las respuestas generadas por la IA basándose en 
    las reglas de negocio y estilo de Walter Ambriz.
    """
    
    @staticmethod
    def evaluate(query: str, response: str) -> dict:
        score = 100
        flags = []
        
        # 1. Validación de Concisión (Máximo 5 líneas de contenido real)
        lines = [line.strip() for line in response.split('\n') if line.strip()]
        if len(lines) > 5:
            score -= 30
            flags.append("TOO_LONG")
            
        # 2. Validación de Identidad (Evitar que suene como un asistente genérico)
        generic_phrases = [
            "como modelo de lenguaje", 
            "claro que sí", 
            "estoy aquí para ayudarte",
            "en qué puedo ayudarte hoy"
        ]
        if any(phrase in response.lower() for phrase in generic_phrases):
            score -= 40
            flags.append("GENERIC_TONE")
            
        # 3. Validación de Persona (Debe mencionar o actuar como WALTER_AI)
        # Si la respuesta es muy larga y no tiene el toque técnico
        if score < 100 and "WALTER_AI" not in response.upper() and len(response) > 100:
            score -= 10
            flags.append("LOSS_OF_IDENTITY")

        # Loguear resultado con etiquetas de texto profesional
        status = "PASSED" if score >= 80 else "WARNING" if score >= 50 else "FAILED"
        logger.info(f"Quality Assessment: [{status}] | Score: {score}/100 | Flags: {flags}")
        
        return {"score": score, "flags": flags}
