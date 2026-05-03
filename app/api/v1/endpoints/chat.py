from fastapi import APIRouter, Depends, Security
from fastapi.responses import StreamingResponse
from app.models.schemas import ChatRequest, ChatResponse
from app.services.agent_service import AgentService
from app.core.security import validate_api_key, limiter
from fastapi import Request

router = APIRouter()
@router.post("/chat", response_model=ChatResponse, dependencies=[Security(validate_api_key)])
@limiter.limit("5/minute")
async def chat(
    request_data: ChatRequest, 
    request: Request,
    agent: AgentService = Depends()
):
    """
    Standard chat endpoint. Returns the full response at once.
    """
    response = await agent.get_response(
        request_data.query, 
        request_data.history, 
        request_data.session_id,
        request_data.context
    )
    return ChatResponse(response=response)

@router.post("/chat/stream", dependencies=[Security(validate_api_key)])
@limiter.limit("5/minute")
async def chat_stream(
    request_data: ChatRequest, 
    request: Request,
    agent: AgentService = Depends()
):
    """
    Streaming chat endpoint. Returns a Server-Sent Events (SSE) stream.
    """
    return StreamingResponse(
        agent.get_streaming_response(
            request_data.query, 
            request_data.history, 
            request_data.session_id,
            request_data.action,
            request_data.context
        ),
        media_type="text/event-stream"
    )

