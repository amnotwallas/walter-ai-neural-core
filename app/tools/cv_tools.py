import os
import json
import httpx
from functools import lru_cache

async def get_github_activity(**kwargs) -> str:
    """CODE_AGENT: Fetches Walter's recent GitHub activity (Accounts: amnotwallas and notwallas)."""
    users = ["amnotwallas", "notwallas"]
    summary = []
    
    async with httpx.AsyncClient() as client:
        for user in users:
            try:
                response = await client.get(f"https://api.github.com/users/{user}/events/public", timeout=5.0)
                if response.status_code == 200:
                    events = response.json()[:5]  # Only last 5 events
                    for event in events:
                        etype = event.get("type")
                        repo = event.get("repo", {}).get("name")
                        summary.append(f"Account: {user} | Event: {etype} | Repo: {repo}")
                else:
                    summary.append(f"Could not fetch data for {user}: HTTP {response.status_code}")
            except Exception as e:
                summary.append(f"Error fetching data for {user}: {str(e)}")
    
    return "\n".join(summary) if summary else "No recent activity found."

@lru_cache()
def _load_data_sync():
    """Internal helper to load CV data from JSON file (cached)."""
    try:
        path = os.path.join(os.path.dirname(__file__), "../data/cv_data.json")
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading data: {e}")
        return {}

async def get_projects_info(**kwargs) -> str:
    """PROJECT_AGENT: Extracts technical details and repository links."""
    data = _load_data_sync()
    return json.dumps(data.get("projects", []), indent=2)

async def get_experience_info(**kwargs) -> str:
    """EXPERIENCE_AGENT: Extracts work history, companies, and dates."""
    data = _load_data_sync()
    return json.dumps(data.get("work", []), indent=2)

async def get_personal_info(**kwargs) -> str:
    """BIOGRAPHICAL_AGENT: Extracts education, skills, and contact info."""
    data = _load_data_sync()
    return json.dumps({
        "basics": data.get("basics", {}),
        "education": data.get("education", []),
        "skills": data.get("skills", [])
    }, indent=2)

async def trigger_navigation(target: str) -> str:
    """NAVIGATION_AGENT: Triggers a redirection in the user interface.
    Valid targets: 'CV', 'PROJECTS'."""
    return f"[NAV:{target.upper()}]"

AVAILABLE_TOOLS = {
    "get_projects_info": get_projects_info,
    "get_experience_info": get_experience_info,
    "get_personal_info": get_personal_info,
    "trigger_navigation": trigger_navigation,
    "get_github_activity": get_github_activity
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_github_activity",
            "description": "Get real-time GitHub activity (commits, pushes, etc.) from Walter's personal (amnotwallas) and work (notwallas) accounts.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
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
