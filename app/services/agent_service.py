import json
from app.providers.llm_provider import LLMProvider
from app.tools.cv_tools import TOOLS_SCHEMA, AVAILABLE_TOOLS
from app.core.prompts import SYSTEM_PROMPT, build_secure_message
from app.core.logger import get_logger
from app.services.quality_service import QualityGuard

logger = get_logger(__name__)

class AgentService:
    """
    Main orchestration service for WALTER_AI.
    Handles session management, tool execution, and LLM communication.
    """
    # Session Memory: {session_id: [messages]}
    _sessions = {}

    def __init__(self):
        self.llm = LLMProvider()

    def _get_session_history(self, session_id: str) -> list:
        """Retrieves history for a given session."""
        if not session_id: return []
        return self._sessions.get(session_id, [])

    def _save_session_history(self, session_id: str, messages: list):
        """Persists the last 6 messages of a session to optimize memory."""
        if session_id:
            self._sessions[session_id] = messages[-6:]

    async def _call_tool(self, tool_call):
        """Dynamically executes a tool based on the LLM's request (asynchronous)."""
        function_name = tool_call.function.name
        try:
            function_args = json.loads(tool_call.function.arguments)
            function_to_call = AVAILABLE_TOOLS[function_name]
            
            logger.info(f"Executing Tool: {function_name} | Args: {function_args}")
            
            # Since all tools are now async, we await them
            if function_args:
                result = await function_to_call(**function_args)
            else:
                result = await function_to_call()
            
            return result
        except Exception as e:
            logger.error(f"Error executing tool '{function_name}': {str(e)}")
            return f"Error: The action '{function_name}' could not be completed correctly."

    async def get_response(self, user_query: str, history: list = [], session_id: str = None) -> str:
        """
        Asynchronous method to get a full response from the agent.
        """
        saved_history = self._get_session_history(session_id)
        current_history = saved_history if session_id and not history else history
        
        secure_content = build_secure_message(user_query)
        messages = [*current_history, {"role": "user", "content": secure_content}]
        
        try:
            # 1. First LLM pass to decide on tool usage
            response = await self.llm.get_completion(
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # 2. Execute tools if required
            if tool_calls:
                messages.append(response_message)
                for tool_call in tool_calls:
                    function_response = await self._call_tool(tool_call)
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": function_response,
                    })
                
                # Generate final response with tool results
                final_response = await self.llm.get_completion(messages=messages)
                full_response = final_response.choices[0].message.content
            else:
                full_response = response_message.content

            # Quality assessment
            QualityGuard.evaluate(user_query, full_response)

            # Persist in memory
            if session_id:
                formatted_history = self._format_history(current_history)
                formatted_history.append({"role": "user", "content": user_query})
                formatted_history.append({"role": "assistant", "content": full_response})
                self._save_session_history(session_id, formatted_history)
                
            return full_response
        except Exception as e:
            logger.error(f"Error in AgentService.get_response: {str(e)}")
            return f"ERROR_SYSTEM_FAILURE: {str(e)}"

    def _format_history(self, history: list) -> list:
        """Normalizes history entries to dictionary format."""
        formatted = []
        for m in history:
            if hasattr(m, "dict"): formatted.append(m.dict())
            elif isinstance(m, dict): formatted.append(m)
        return formatted

    async def get_streaming_response(self, user_query: str, history: list = [], session_id: str = None, action: str = "chat"):
        """
        Asynchronous generator for streaming the agent's response.
        """
        # Handle session initialization
        if action == "init":
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Session {session_id} reset successfully.")
            
            logger.info(f"NEW_CONVERSATION_STARTED: Session ID: {session_id or 'Anonymous'}")
            yield "data: [SYSTEM_READY]: WALTER_AI_CORE_ESTABLISHED. How can I help you today?\n\n"
            return

        saved_history = self._get_session_history(session_id)
        current_history = saved_history if session_id and not history else history
        
        if not current_history:
            logger.info(f"FIRST_MESSAGE_RECEIVED: Session ID: {session_id or 'Anonymous'} | Query: {user_query}")

        secure_content = build_secure_message(user_query)
        messages = [*current_history, {"role": "user", "content": secure_content}]
        
        logger.info(f"New Query: {user_query} | Session: {session_id or 'Anonymous'}")
        
        try:
            # 1. Decision phase
            response = await self.llm.get_completion(
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # 2. Tool execution and final streaming
            if tool_calls:
                messages.append(response_message)
                for tool_call in tool_calls:
                    function_response = await self._call_tool(tool_call)
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": function_response,
                    })
                
                logger.info("Generating final response based on tool data...")
                stream = await self.llm.get_streaming_completion(messages=messages)
            else:
                logger.info("Direct response initiated")
                stream = await self.llm.get_streaming_completion(messages=messages)

            full_response = ""
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    full_response += content
                    yield f"data: {content}\n\n"
            
            # Final quality assessment
            QualityGuard.evaluate(user_query, full_response)

            # Persist session
            if session_id:
                formatted_history = self._format_history(current_history)
                formatted_history.append({"role": "user", "content": user_query})
                formatted_history.append({"role": "assistant", "content": full_response})
                self._save_session_history(session_id, formatted_history)

        except Exception as e:
            logger.error(f"Critical error in AgentService: {str(e)}")
            yield f"data: ERROR_SYSTEM_FAILURE: {str(e)}\n\n"
