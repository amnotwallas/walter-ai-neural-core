import os
import json
import httpx
from app.core.data_loader import data_provider
from app.tools.registry import tool_registry

async def get_projects_info(**kwargs) -> str:
    """PROJECT_AGENT: Extracts technical details and repository links."""
    data = data_provider.get_data()
    return json.dumps(data.get("projects", []), indent=2)

async def get_experience_info(**kwargs) -> str:
    """EXPERIENCE_AGENT: Extracts work history, companies, and dates."""
    data = data_provider.get_data()
    return json.dumps(data.get("work", []), indent=2)

async def get_personal_info(**kwargs) -> str:
    """BIOGRAPHICAL_AGENT: Extracts education, skills, and contact info."""
    data = data_provider.get_data()
    return json.dumps({
        "basics": data.get("basics", {}),
        "education": data.get("education", []),
        "skills": data.get("skills", [])
    }, indent=2)

async def trigger_navigation(target: str) -> str:
    """NAVIGATION_AGENT: Triggers a redirection in the user interface.
    Valid targets: 'EXPERIENCE', 'PROJECTS'."""
    return f"[NAV:{target.upper()}]"

async def highlight_element(element_type: str, item_id: str) -> str:
    """UI_AGENT: Highlights a specific element in the interface.
    element_type: 'PROJECT' or 'EXPERIENCE'.
    item_id: The project slug or company id."""
    return f"[HIGHLIGHT:{element_type.upper()}:{item_id}]"

# --- Tool Registration ---

tool_registry.register_tool(
    {
        "type": "function",
        "function": {
            "name": "get_projects_info",
            "description": "Get detailed information about Walter's projects and technical stacks.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    get_projects_info
)

tool_registry.register_tool(
    {
        "type": "function",
        "function": {
            "name": "get_experience_info",
            "description": "Get Walter's work experience, companies, and roles.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    get_experience_info
)

tool_registry.register_tool(
    {
        "type": "function",
        "function": {
            "name": "get_personal_info",
            "description": "Get Walter's contact info, core skills, and education.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    get_personal_info
)

tool_registry.register_tool(
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
    },
    trigger_navigation
)

tool_registry.register_tool(
    {
        "type": "function",
        "function": {
            "name": "highlight_element",
            "description": "Visually emphasize a project or work experience on the user's screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_type": {
                        "type": "string",
                        "enum": ["PROJECT", "EXPERIENCE"],
                        "description": "The type of element to highlight."
                    },
                    "item_id": {
                        "type": "string",
                        "description": "The project slug (e.g., 'portfolio') or company id (e.g., 'ibicare')."
                    }
                },
                "required": ["element_type", "item_id"]
            }
        }
    },
    highlight_element
)
