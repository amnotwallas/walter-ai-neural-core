import json
from app.providers.llm_provider import LLMProvider
from app.tools.cv_tools import TOOLS_SCHEMA, AVAILABLE_TOOLS
from app.core.prompts import SYSTEM_PROMPT
from app.core.logger import get_logger
from app.services.quality_service import QualityGuard

logger = get_logger(__name__)

class AgentService:
    # Memoria de sesiones: {session_id: [messages]}
    _sessions = {}

    def __init__(self):
        self.llm = LLMProvider()

    def _get_session_history(self, session_id: str) -> list:
        if not session_id: return []
        return self._sessions.get(session_id, [])

    def _save_session_history(self, session_id: str, messages: list):
        if session_id:
            # Solo guardamos los últimos 10 mensajes para ahorrar memoria
            self._sessions[session_id] = messages[-10:]

    def _call_tool(self, tool_call):
        function_name = tool_call.function.name
        try:
            function_args = json.loads(tool_call.function.arguments)
            function_to_call = AVAILABLE_TOOLS[function_name]
            
            logger.info(f"Executing Tool: {function_name} | Args: {function_args}")
            
            if function_args:
                result = function_to_call(**function_args)
            else:
                result = function_to_call()
            
            return result
        except Exception as e:
            logger.error(f"Error executing tool '{function_name}': {str(e)}")
            return f"Error: No se pudo ejecutar la acción '{function_name}' correctamente."

    def get_streaming_response(self, user_query: str, history: list = [], session_id: str = None, action: str = "chat"):
        # 0. Si la acción es 'init', limpiamos la sesión y saludamos
        if action == "init":
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Session {session_id} reset successfully.")
            
            logger.info(f"NEW_CONVERSATION_STARTED: Session ID: {session_id or 'Anonymous'}")
            yield "data: [SYSTEM_READY]: WALTER_AI_CORE_ESTABLISHED. Cómo puedo ayudarte hoy?\n\n"
            return

       
        saved_history = self._get_session_history(session_id)
       
        current_history = saved_history if session_id and not history else history
        
        
        if not current_history:
            logger.info(f"FIRST_MESSAGE_RECEIVED: Session ID: {session_id or 'Anonymous'} | Query: {user_query}")

        wrapped_query = f"<user_input>\n{user_query}\n</user_input>"
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *current_history, {"role": "user", "content": wrapped_query}]
        
        logger.info(f"New Query: {user_query} | Session: {session_id or 'Anonymous'}")
        
        try:
            # 1. El Maestro decide
            response = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # 2. Si hay herramientas, las ejecutamos
            if tool_calls:
                messages.append(response_message)
                for tool_call in tool_calls:
                    function_response = self._call_tool(tool_call)
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": function_response,
                    })
                
                logger.info("Generating final response based on tool data...")
                stream = self.llm.client.chat.completions.create(
                    model=self.llm.model,
                    messages=messages,
                    stream=True
                )
            else:
                logger.info("Direct response initiated")
                stream = self.llm.client.chat.completions.create(
                    model=self.llm.model,
                    messages=messages,
                    stream=True
                )

            full_response = ""
            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    full_response += content
                    yield f"data: {content}\n\n"
            
            # Evaluación de calidad al terminar el stream
            QualityGuard.evaluate(user_query, full_response)

            # 3. Persistir en memoria
            if session_id:
                # Normalizar historial a formato diccionario
                formatted_history = []
                for m in current_history:
                    if hasattr(m, "dict"): formatted_history.append(m.dict())
                    elif isinstance(m, dict): formatted_history.append(m)
                
                formatted_history.append({"role": "user", "content": user_query})
                formatted_history.append({"role": "assistant", "content": full_response})
                self._save_session_history(session_id, formatted_history)

        except Exception as e:
            logger.error(f"Critical error in AgentService: {str(e)}")
            yield f"data: ERROR_SYSTEM_FAILURE: {str(e)}\n\n"
