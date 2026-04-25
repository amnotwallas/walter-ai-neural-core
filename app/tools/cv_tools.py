import json
import os

def _load_data():
    try:
        path = os.path.join(os.path.dirname(__file__), "../../../src/assets/data.json")
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {}

def get_projects_info() -> str:
    """AGENTE_DE_PROYECTOS: Extrae detalles técnicos y links de repositorios."""
    data = _load_data()
    return json.dumps(data.get("projects", []), indent=2)

def get_experience_info() -> str:
    """AGENTE_DE_EXPERIENCIA: Extrae historial laboral, empresas y fechas."""
    data = _load_data()
    return json.dumps(data.get("work", []), indent=2)

def get_personal_info() -> str:
    """AGENTE_BIOGRÁFICO: Extrae educación, habilidades y contacto."""
    data = _load_data()
    return json.dumps({
        "basics": data.get("basics", {}),
        "education": data.get("education", []),
        "skills": data.get("skills", [])
    }, indent=2)

def trigger_navigation(target: str) -> str:
    """AGENTE_DE_NAVEGACIÓN: Dispara una redirección en la interfaz del usuario. 
    Targets válidos: 'CV', 'PROJECTS'."""
    return f"[NAV:{target.upper()}]"

AVAILABLE_TOOLS = {
    "get_projects_info": get_projects_info,
    "get_experience_info": get_experience_info,
    "get_personal_info": get_personal_info,
    "trigger_navigation": trigger_navigation
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_projects_info",
            "description": "Get detailed information about Walter's projects and technical stacks.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_experience_info",
            "description": "Get Walter's work experience, companies, and roles.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_personal_info",
            "description": "Get Walter's contact info, core skills, and education.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_navigation",
            "description": "Redirect the user to a specific section of the website.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "enum": ["CV", "PROJECTS"],
                        "description": "The destination module."
                    }
                },
                "required": ["target"]
            }
        }
    }
]
