import groq
from app.core.config import get_settings
from typing import List, Optional, Any

class LLMProvider:
    """
    Provider class for LLM interactions using AsyncGroq SDK.
    Handles client initialization and asynchronous completion requests.
    """
    def __init__(self):
        settings = get_settings()
        self.client = groq.AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.model = settings.MODEL_NAME

    async def get_completion(
        self, 
        messages: List[dict], 
        tools: Optional[List[dict]] = None, 
        tool_choice: str = "auto",
        temperature: float = 0.5
    ) -> Any:
        """
        Generates a non-streaming asynchronous completion.
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        return await self.client.chat.completions.create(**kwargs)

    async def get_streaming_completion(
        self, 
        messages: List[dict], 
        temperature: float = 0.5
    ) -> Any:
        """
        Generates a streaming asynchronous completion.
        """
        return await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            stream=True
        )
