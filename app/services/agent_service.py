import json
from app.providers.llm_provider import LLMProvider
from app.tools.registry import tool_registry
import app.tools.cv_tools  # Trigger registration
from app.core.prompts import SYSTEM_PROMPT, build_secure_message
from app.core.logger import get_logger
from app.services.quality_service import QualityGuard

from app.core.data_loader import data_provider

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

    @property
    def _project_data(self):
        """Getter for portfolio data, always fresh from data_provider."""
        return data_provider.get_data()

    def _get_project_context(self, slug: str) -> str:
        """Retrieves and formats context for a specific project."""
        data = self._project_data
        if not slug or not data:
            return ""
        
        projects = data.get("projects", [])
        project = next((p for p in projects if p.get("slug") == slug), None)
        
        if not project:
            return ""
        
        context = (
            f"User is currently viewing project: {project.get('name')}\n"
            f"Description: {project.get('long_description', project.get('description'))}\n"
            f"Stack: {', '.join(project.get('stack', []))}\n"
            f"Status: {project.get('metadata', {}).get('status', 'N/A')}\n"
            "If user uses 'this', 'here', 'this project' or similar, refer to these details."
        )
        return context

    def _get_navigation_context(self, context_obj) -> str:
        """Constructs context string based on navigation state."""
        if not context_obj:
            return ""
        
        parts = []
        if context_obj.page == "home":
            parts.append("User is on the HOME page. Greet them and mention they can explore projects below.")
        
        if context_obj.project_slug:
            project_info = self._get_project_context(context_obj.project_slug)
            if project_info:
                parts.append(project_info)
        
        return "\n".join(parts)

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
            logger.info(f"Executing Tool: {function_name} | Args: {function_args}")
            
            # Use ToolRegistry for execution
            result = await tool_registry.execute(function_name, **function_args)
            return result
        except Exception as e:
            logger.error(f"Error executing tool '{function_name}': {str(e)}")
            return f"Error: The action '{function_name}' could not be completed correctly."

    async def get_response(self, user_query: str, history: list = [], session_id: str = None, context = None) -> str:
        """
        Asynchronous method to get a full response from the agent.
        """
        saved_history = self._get_session_history(session_id)
        current_history = saved_history if session_id and not history else history
        
        context_info = self._get_navigation_context(context)
        secure_content = build_secure_message(user_query, context_info)
        
        # Inject SYSTEM_PROMPT as a dedicated system message for efficiency
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *current_history, 
            {"role": "user", "content": secure_content}
        ]
        
        try:
            # 1. First LLM pass to decide on tool usage
            response = await self.llm.get_completion(
                messages=messages,
                tools=tool_registry.schemas,
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

    async def get_streaming_response(self, user_query: str, history: list = [], session_id: str = None, action: str = "chat", context = None):
        """
        Asynchronous generator for streaming the agent's response with Early Streaming optimization.
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

        context_info = self._get_navigation_context(context)
        secure_content = build_secure_message(user_query, context_info)
        
        # Inject SYSTEM_PROMPT as a dedicated system message for efficiency
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *current_history, 
            {"role": "user", "content": secure_content}
        ]
        
        logger.info(f"New Query: {user_query} | Session: {session_id or 'Anonymous'}")
        
        try:
            # 1. First Pass (Streaming Decision)
            first_pass_stream = await self.llm.get_streaming_completion(
                messages=messages,
                tools=tool_registry.schemas,
                tool_choice="auto"
            )

            full_response = ""
            tool_calls_data = [] 
            is_tool_call = False
            
            async for chunk in first_pass_stream:
                delta = chunk.choices[0].delta
                
                # Detect and accumulate tool calls
                if delta.tool_calls:
                    is_tool_call = True
                    for tc in delta.tool_calls:
                        index = tc.index
                        while len(tool_calls_data) <= index:
                            tool_calls_data.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        
                        if tc.id:
                            tool_calls_data[index]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_data[index]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_data[index]["function"]["arguments"] += tc.function.arguments
                
                # If it's regular content, yield it immediately (Early Streaming)
                elif delta.content:
                    content = delta.content
                    full_response += content
                    yield f"data: {content}\n\n"

            # 2. If tools were detected, execute them and perform second pass
            if is_tool_call:
                # Append assistant message with tool calls to history for context
                assistant_message = {"role": "assistant", "tool_calls": tool_calls_data}
                messages.append(assistant_message)
                
                # Execute each accumulated tool
                for tc_data in tool_calls_data:
                    # Create a proxy object that matches the expected tool_call interface (.id, .function.name, .function.arguments)
                    class ToolCallProxy:
                        def __init__(self, data):
                            self.id = data["id"]
                            self.function = type('FunctionProxy', (object,), data["function"])
                    
                    proxy = ToolCallProxy(tc_data)
                    function_response = await self._call_tool(proxy)
                    
                    messages.append({
                        "tool_call_id": tc_data["id"],
                        "role": "tool",
                        "name": tc_data["function"]["name"],
                        "content": function_response,
                    })
                
                logger.info("Executing tools and generating final response...")
                final_stream = await self.llm.get_streaming_completion(messages=messages)
                
                async for chunk in final_stream:
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
            error_str = str(e)
            if "failed_generation" in error_str:
                logger.warning("RESCUE_ACTIVE: Processing failed_generation")
                try:
                    import re
                    # 1. Extract the raw generated content
                    content_match = re.search(r"failed_generation':\s*'(.*?)'\}", error_str, re.DOTALL)
                    raw = content_match.group(1) if content_match else error_str
                    
                    # 2. Extract potential UI tokens before cleaning
                    tokens = re.findall(r'\[NAV:.*?\]|\[HIGHLIGHT:.*?\]', raw)
                    
                    # 3. If it looks like a navigation call, synthesize the token if missing
                    if "trigger_navigation" in raw and not any("NAV" in t for t in tokens):
                        target_match = re.search(r'"target":\s*"(.*?)"', raw)
                        if target_match:
                            tokens.append(f"[NAV:{target_match.group(1).upper()}]")

                    # 4. Clean prose: remove XML tags and JSON
                    clean = re.sub(r'<function.*?>.*?(?:</function>|\[/function\]|<function>|\[function\]|$)', '', raw, flags=re.DOTALL | re.IGNORECASE)
                    clean = re.sub(r'\{.*\}', '', clean).replace("\\n", "\n").replace("\\'", "'").strip()
                    
                    # 5. Build final response
                    final_output = clean
                    if tokens:
                        # Append tokens only if not already present in clean text
                        for token in tokens:
                            if token not in final_output:
                                final_output += f" {token}"
                    
                    final_output = final_output.strip()
                    if len(final_output) > 2:
                        yield f"data: {final_output}\n\n"
                        return
                except Exception as inner_e:
                    logger.error(f"RESCUE_FAILED: {inner_e}")
            
            logger.error(f"SYSTEM_FAILURE: {error_str}")
            yield f"data: ERROR_SYSTEM_FAILURE: {error_str}\n\n"
