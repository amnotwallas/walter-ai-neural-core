import os
import json
import httpx
from app.core.data_loader import data_provider
from app.tools.registry import tool_registry

async def get_projects_list(**kwargs) -> str:
    """PROJECT_AGENT: Returns a list of all projects with their slugs and short descriptions."""
    data = data_provider.get_data()
    if not data:
        return json.dumps([])
    
    projects = [
        {"name": p.name, "slug": p.slug, "description": p.description}
        for p in data.projects
    ]
    return json.dumps(projects, indent=2)

async def get_project_by_slug(slug: str) -> str:
    """PROJECT_AGENT: Returns full details for a specific project by its slug."""
    data = data_provider.get_data()
    if not data:
        return "Error: Data unavailable."
    
    project = next((p for p in data.projects if p.slug == slug), None)
    if not project:
        return f"Error: Project with slug '{slug}' not found."
    
    return json.dumps(project.model_dump(), indent=2)

async def search_projects(query: str) -> str:
    """PROJECT_AGENT: Searches projects by name, description, or stack."""
    data = data_provider.get_data()
    if not data:
        return json.dumps([])
    
    query = query.lower()
    results = []
    for p in data.projects:
        if (query in p.name.lower() or 
            query in p.description.lower() or 
            any(query in s.lower() for s in p.stack)):
            results.append({"name": p.name, "slug": p.slug, "description": p.description})
    
    return json.dumps(results, indent=2)

async def get_experience_info(**kwargs) -> str:
    """EXPERIENCE_AGENT: Extracts work history, companies, and dates."""
    return data_provider.get_section("work")

async def get_personal_info(**kwargs) -> str:
    """BIOGRAPHICAL_AGENT: Extracts education, skills, and contact info."""
    data = data_provider.get_data()
    if not data:
        return json.dumps({})
        
    personal_data = {
        "basics": data.basics.model_dump(),
        "education": [e.model_dump() for e in data.education],
        "skills": [s.model_dump() for s in data.skills]
    }
    return json.dumps(personal_data, indent=2)

async def trigger_navigation(target: str) -> str:
    """NAVIGATION_AGENT: Triggers a redirection in the user interface.
    Valid targets: 'EXPERIENCE', 'PROJECTS', 'HOME'."""
    allowed = {"EXPERIENCE", "PROJECTS", "HOME"}

    if target.upper() not in allowed:
        return f"Error: Invalid navigation target '{target}'. Valid targets are: {', '.join(allowed)}."

    return json.dumps({"__action__": {"type": "navigation", "target": target.upper()}})

async def highlight_element(element_type: str, item_id: str) -> str:
    """UI_AGENT: Highlights a specific element in the interface.
    element_type: 'PROJECT' or 'EXPERIENCE'.
    item_id: The project slug or company name."""
    if element_type.upper() not in {"PROJECT", "EXPERIENCE"}:
        return "Error: Invalid element type."

    if not item_id:
        return "Error: Missing item_id."

    return json.dumps({"__action__": {"type": "highlight", "element_type": element_type.upper(), "item_id": item_id}})

# --- Tool Registration ---

tool_registry.register_tool(
    {
        "type": "function",
        "function": {
            "name": "get_projects_list",
            "description": "Get a summary list of all Walter's projects.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    get_projects_list
)

tool_registry.register_tool(
    {
        "type": "function",
        "function": {
            "name": "get_project_by_slug",
            "description": "Get full technical details for a specific project using its slug.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "The unique identifier of the project (e.g., 'portfolio')."
                    }
                },
                "required": ["slug"]
            }
        }
    },
    get_project_by_slug
)

tool_registry.register_tool(
    {
        "type": "function",
        "function": {
            "name": "search_projects",
            "description": "Search for projects by keywords in name, description, or technology stack.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword or phrase."
                    }
                },
                "required": ["query"]
            }
        }
    },
    search_projects
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
            "description": "ONLY use this to change the user's page. Use 'EXPERIENCE' for work history, 'PROJECTS' for the portfolio list, or 'HOME' for the main screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "enum": ["EXPERIENCE", "PROJECTS", "HOME"],
                        "description": "The destination page."
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
            "description": "ONLY use this to focus on ONE specific item. For work history, use element_type='EXPERIENCE'. For projects, use element_type='PROJECT'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_type": {
                        "type": "string",
                        "enum": ["PROJECT", "EXPERIENCE"],
                        "description": "Category of the element."
                    },
                    "item_id": {
                        "type": "string",
                        "description": "The EXACT slug (for projects) or company name (for experience) from VALID_IDENTIFIERS."
                    }
                },
                "required": ["element_type", "item_id"]
            }
        }
    },
    highlight_element
)
