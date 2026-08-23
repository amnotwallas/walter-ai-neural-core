import json
import re
import time
import uuid
from typing import Optional
from app.domain.ports.llm import LLMPort
from app.domain.ports.data_provider import DataProviderPort
from app.domain.ports.audit import AuditPort
from app.tools.registry import tool_registry
import app.tools.cv_tools  # Trigger registration
from app.core.prompts import SYSTEM_PROMPT
from app.core.logger import get_logger, trace_id_var
from app.domain.models.schemas import AgentAction
import app.core.metrics as _metrics

try:
    from opentelemetry import trace
except ImportError:
    trace = None

logger = get_logger(__name__)


class AgentService:
    """
    Main orchestration service for WALTER-AI.
    Handles session management, tool execution, and LLM communication.
    """

    _sessions = {}
    MAX_ITERATIONS = 5

    def __init__(self, llm: LLMPort, data_provider: DataProviderPort, audit: Optional[AuditPort] = None):
        self.llm = llm
        self.data_provider = data_provider
        self.audit = audit

    # =========================
    # DATA CONTEXT
    # =========================

    @property
    def _project_data(self):
        return self.data_provider.get_data()

    def _get_project_context(self, slug: str) -> str:
        data = self._project_data
        if not slug or not data:
            return ""

        project = next((p for p in data.projects if p.slug == slug), None)
        if not project:
            return ""

        return (
            f"User is viewing project: {project.name}\n"
            f"Description: {project.description}\n"
            f"Stack: {', '.join(project.stack)}\n"
            "If user refers to 'this' or 'here', assume this project."
        )

    def _get_navigation_context(self, context_obj) -> str:
        data = self._project_data
        parts = []

        # 1. Site Map (Always present for ID precision)
        if data:
            project_slugs = [p.slug for p in data.projects]
            experience_ids = [w.company.upper() for w in data.work]
            parts.append(
                "VALID_IDENTIFIERS:\n"
                f"- Project Slugs: {', '.join(project_slugs)}\n"
                f"- Experience IDs: {', '.join(experience_ids)}"
            )

        # 2. Current Page State
        if context_obj:
            if context_obj.page == "home":
                parts.append("CURRENT_LOCATION: User is on the HOME page.")
            elif context_obj.page == "project_details":
                parts.append(f"CURRENT_LOCATION: User is already viewing the DETAILS of project: {context_obj.project_slug}")
            elif context_obj.page == "projects":
                parts.append("CURRENT_LOCATION: User is viewing the PROJECTS list.")
            elif context_obj.page == "experience":
                parts.append("CURRENT_LOCATION: User is viewing the EXPERIENCE section.")

            if context_obj.project_slug:
                project_info = self._get_project_context(context_obj.project_slug)
                if project_info:
                    parts.append(project_info)

        return "\n".join(parts)

    # =========================
    # MEMORY MANAGEMENT
    # =========================

    def _get_session_history(self, session_id: str) -> list:
        if not session_id:
            return []

        session = self._sessions.get(session_id)
        if not session:
            return []

        messages = []

        if session.get("summary"):
            messages.append({
                "role": "system",
                "content": f"Session summary: {session['summary']}"
            })

        messages.extend(session.get("recent", []))
        return messages

    async def _summarize_history(self, messages: list) -> str:
        if len(messages) < 8:
            return ""

        try:
            summary_prompt = [
                {"role": "system", "content": "Summarize the conversation focusing on intent and key context."},
                {"role": "user", "content": str(messages)}
            ]

            res = await self.llm.get_completion(messages=summary_prompt)
            return res.choices[0].message.content

        except Exception as e:
            logger.error(f"Summary failed: {e}")
            return ""

    async def _save_session_history(self, session_id: str, messages: list):
        if not session_id:
            return

        trimmed = messages[-6:]
        summary = ""

        if len(messages) > 10:
            summary = await self._summarize_history(messages[:-6])

        self._sessions[session_id] = {
            "recent": trimmed,
            "summary": summary
        }

    # =========================
    # TOOL EXECUTION
    # =========================

    async def _call_tool(self, tool_call, actions_list: list, conversation_id: str = None, tool_logs: list = None, session_id: str = None):
        function_name = tool_call.function.name
        tracer = trace.get_tracer("walter-ai") if trace is not None else None
        span_ctx = None
        if tracer is not None:
            span_ctx = tracer.start_as_current_span("agent_tool_call")
            span_ctx.__enter__()
            span = trace.get_current_span()
            if span:
                span.set_attribute("tool.name", function_name)

        try:
            raw_args = tool_call.function.arguments
            
            if isinstance(raw_args, dict):
                function_args = raw_args
            else:
                try:
                    function_args = json.loads(raw_args or "{}") if isinstance(raw_args, str) else {}
                    if not isinstance(function_args, dict):
                        function_args = {}
                except json.JSONDecodeError:
                    logger.warning(f"Malformed JSON args for {function_name}: {raw_args}")
                    function_args = {}

            logger.info(
                f"Tool execution started: {function_name}",
                extra={
                    "event": "tool_execution_started",
                    "session_id": session_id,
                    "tool_name": function_name,
                    "tool_status": "started",
                }
            )
            _metrics.tool_calls_total.labels(tool_name=function_name).inc()
            
            t0 = time.time()
            result = await tool_registry.execute(function_name, **function_args)
            latency_ms = (time.time() - t0) * 1000

            logger.info(
                f"Tool execution completed: {function_name}",
                extra={
                    "event": "tool_execution_completed",
                    "session_id": session_id,
                    "tool_name": function_name,
                    "tool_status": "success",
                    "tool_latency_ms": latency_ms,
                }
            )

            if self.audit:
                log_data = {
                    "id": str(uuid.uuid4()),
                    "conversation_id": conversation_id,
                    "tool_name": function_name,
                    "args": str(function_args),
                    "result": str(result)[:500],
                    "latency_ms": round(latency_ms, 2),
                }
                if tool_logs is not None:
                    tool_logs.append(log_data)
            
            # Post-process for structured actions
            try:
                parsed_result = json.loads(result)
                if isinstance(parsed_result, dict) and "__action__" in parsed_result:
                    action_model = AgentAction(**parsed_result["__action__"])
                    actions_list.append(action_model.model_dump())
                    return f"Action {action_model.type} executed successfully."
                elif isinstance(parsed_result, list):
                    count = 0
                    for item in parsed_result:
                        if isinstance(item, dict) and "__action__" in item:
                            action_model = AgentAction(**item["__action__"])
                            actions_list.append(action_model.model_dump())
                            count += 1
                    if count:
                        return f"Tour executed: {count} actions queued."
            except Exception as e:
                logger.warning(f"Validation failed for action payload from tool: {e}")

            return result

        except Exception as e:
            logger.error(
                f"Error executing tool '{function_name}': {str(e)}",
                extra={
                    "event": "tool_execution_failed",
                    "session_id": session_id,
                    "tool_name": function_name,
                    "tool_status": "failed",
                    "error_type": type(e).__name__,
                }
            )
            return f"Error: The action '{function_name}' failed."
        finally:
            if span_ctx is not None:
                span_ctx.__exit__(None, None, None)

    # =========================
    # CONVERSATION PREP
    # =========================

    async def _check_input_guardrails(self, query: str) -> bool:
        """
        Validates user input against common prompt injection, system override attempts,
        excessive lengths, and format injection anomalies.
        Returns True if the query is safe, False otherwise.
        """
        if not query:
            return True

        # 1. Length guardrail (portfolio questions should be relatively brief)
        if len(query) > 300:
            logger.warning("GUARDRAIL_TRIGGERED: Query blocked due to excessive length.")
            _metrics.security_blocks_total.labels(reason="length").inc()
            if self.audit:
                await self.audit.log_security_event(
                    id=str(uuid.uuid4()),
                    reason="length",
                    query_snippet=query[:100]
                )
            return False

        query_lower = query.lower()

        # 2. Bilingual semantic patterns (verb + control noun combinations)
        suspicious_patterns = [
            r"\b(forget|olvid[a-z]*|ignor[a-z]*|bypass|salt[a-z]*|evad[a-z]*|override)\b.*\b(instruc[a-z]*|regla[a-z]*|rule[a-z]*|prompt[a-z]*|directiv[a-z]*|limit[a-z]*|guideline[a-z]*)\b",
            r"\b(system|sistem[a-z]*)\b.*\b(prompt[a-z]*|context[a-z]*|regla[a-z]*|rule[a-z]*|instruc[a-z]*)\b",
            r"\b(act|actu[a-z]*|desempeñ[a-z]*|represent[a-z]*|now you are|ahora eres)\b.*\b(as|como|role|papel|un|a)\b",
            r"\b(translate|traduc[a-z]*|encode|codific[a-z]*|base64|hex|rot13|binary|binario)\b"
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, query_lower):
                logger.warning(f"GUARDRAIL_TRIGGERED: Blocked by pattern match '{pattern}'")
                _metrics.security_blocks_total.labels(reason="injection").inc()
                if self.audit:
                    await self.audit.log_security_event(
                        id=str(uuid.uuid4()),
                        reason="injection",
                        query_snippet=query[:100]
                    )
                return False

        # 3. Formatting anomaly detection (prevents template injection payloads)
        special_chars_count = len(re.findall(r"[{}\[\]<>/\\#*_]", query))
        if special_chars_count > 10:
            logger.warning("GUARDRAIL_TRIGGERED: Too many formatting/structured characters.")
            _metrics.security_blocks_total.labels(reason="format").inc()
            if self.audit:
                await self.audit.log_security_event(
                    id=str(uuid.uuid4()),
                    reason="format",
                    query_snippet=query[:100]
                )
            return False

        return True

    def _prepare_conversation(self, user_query: str, history: list, session_id: str, context: any):
        user_query = user_query or "Hola"
        history = history or []

        saved_history = self._get_session_history(session_id)
        current_history = saved_history if session_id and not history else history

        is_first = " (First Message)" if not current_history else ""
        logger.info(f"New Query{is_first}: '{user_query}' | Session: {session_id or 'Anonymous'}")

        context_info = self._get_navigation_context(context)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        if context_info:
            messages.append({
                "role": "system",
                "content": context_info
            })

        messages.extend(current_history)

        messages.append({
            "role": "user",
            "content": user_query
        })

        return messages, current_history

    # =========================
    # MAIN RESPONSE
    # =========================

    async def get_response(self, user_query: str, history: list = None, session_id: str = None, context=None, trace_id: Optional[str] = None) -> dict:
        if trace_id:
            trace_id_var.set(trace_id)

        if not await self._check_input_guardrails(user_query):
            return {
                "message": "Solo puedo hablar sobre el portafolio de Walter. ¿Te puedo mostrar algo de su trabajo? 😄",
                "actions": []
            }

        _metrics.active_sessions.inc()
        conv_id = str(uuid.uuid4())
        tool_logs = []
        try:
            messages, current_history = self._prepare_conversation(user_query, history, session_id, context)
            actions = []
            iterations = 0

            try:
                while iterations < self.MAX_ITERATIONS:
                    response = await self.llm.get_completion(
                        messages=messages,
                        tools=tool_registry.schemas,
                        tool_choice="auto"
                    )

                    response_message = response.choices[0].message
                    tool_calls = response_message.tool_calls

                    if not tool_calls:
                        full_response = response_message.content or ""
                        break

                    messages.append(response_message)
                    for tool_call in tool_calls:
                        function_response = await self._call_tool(tool_call, actions, conv_id, tool_logs=tool_logs, session_id=session_id)
                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": tool_call.function.name,
                            "content": function_response,
                        })
                    
                    iterations += 1
                else:
                    logger.warning("Max tool iterations reached")
                    full_response = "I'm sorry, I encountered an internal loop while processing your request."

                if session_id:
                    formatted_history = self._format_history(current_history)
                    formatted_history.append({"role": "user", "content": user_query})
                    formatted_history.append({"role": "assistant", "content": full_response})
                    await self._save_session_history(session_id, formatted_history)

                if self.audit:
                    await self.audit.log_conversation(
                        id=conv_id,
                        session_id=session_id or "anonymous",
                        query=user_query,
                        response=full_response,
                    )
                    for log in tool_logs:
                        await self.audit.log_tool_execution(**log)

                return {
                    "message": full_response,
                    "actions": actions
                }

            except Exception as e:
                logger.error(f"Error in AgentService.get_response: {str(e)}")
                return {
                    "message": f"Sorry, I'm having trouble connecting: {str(e)}",
                    "actions": []
                }
        finally:
            _metrics.active_sessions.dec()

    # =========================
    # STREAMING
    # =========================

    async def get_streaming_response(self, user_query: str, history: list = None, session_id: str = None, action: str = "chat", context=None, trace_id: Optional[str] = None):
        if trace_id:
            trace_id_var.set(trace_id)

        history = history or []

        if action == "init":
            if session_id in self._sessions:
                del self._sessions[session_id]

            logger.info(f"NEW_CONVERSATION_STARTED: Session ID: {session_id or 'Anonymous'}")
            yield "data: {\"message\": \"WALTER-AI_READY\", \"actions\": []}\n\n"
            return

        if not await self._check_input_guardrails(user_query):
            yield f"data: {json.dumps({'message': 'Solo puedo hablar sobre el portafolio de Walter. ¿Te puedo mostrar algo de su trabajo? 😄', 'actions': []})}\n\n"
            return

        _metrics.active_sessions.inc()
        conv_id = str(uuid.uuid4())
        tool_logs = []
        try:
            messages, current_history = self._prepare_conversation(user_query, history, session_id, context)
            actions = []
            full_response = ""
            iterations = 0

            try:
                while iterations < self.MAX_ITERATIONS:
                    stream = await self.llm.get_streaming_completion(
                        messages=messages,
                        tools=tool_registry.schemas,
                        tool_choice="auto"
                    )

                    tool_calls_data = []
                    is_tool_call = False
                    current_chunk_response = ""

                    async for chunk in stream:
                        delta = chunk.choices[0].delta

                        if delta.tool_calls:
                            is_tool_call = True
                            for tc in delta.tool_calls:
                                index = tc.index
                                while len(tool_calls_data) <= index:
                                    tool_calls_data.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                                if tc.id: tool_calls_data[index]["id"] = tc.id
                                if tc.function:
                                    if tc.function.name: tool_calls_data[index]["function"]["name"] += tc.function.name
                                    if tc.function.arguments: tool_calls_data[index]["function"]["arguments"] += tc.function.arguments

                        elif delta.content:
                            content = delta.content
                            current_chunk_response += content
                            full_response += content
                            yield f"data: {json.dumps({'message': content, 'actions': []})}\n\n"

                    if not is_tool_call:
                        break

                    # Execute tools
                    messages.append({"role": "assistant", "tool_calls": tool_calls_data})
                    logger.debug(f"Executing {len(tool_calls_data)} tool calls: {[tc['function']['name'] for tc in tool_calls_data]}")
                    
                    for tc_data in tool_calls_data:
                        class ToolCallProxy:
                            def __init__(self, data):
                                self.id = data["id"]
                                self.function = type('FunctionProxy', (object,), data["function"])

                        proxy = ToolCallProxy(tc_data)
                        logger.debug(f"Calling tool {tc_data['function']['name']} with args: {tc_data['function']['arguments']}")
                        prev_len = len(actions)
                        function_response = await self._call_tool(proxy, actions, conv_id, tool_logs=tool_logs, session_id=session_id)
                        if len(actions) > prev_len:
                            yield f"data: {json.dumps({'message': '', 'actions': actions[prev_len:]})}\n\n"
                        messages.append({
                            "tool_call_id": tc_data["id"],
                            "role": "tool",
                            "name": tc_data["function"]["name"],
                            "content": function_response,
                        })
                    
                    iterations += 1

                if session_id:
                    formatted_history = self._format_history(current_history)
                    formatted_history.append({"role": "user", "content": user_query})
                    formatted_history.append({"role": "assistant", "content": full_response})
                    await self._save_session_history(session_id, formatted_history)

                if self.audit:
                    await self.audit.log_conversation(
                        id=conv_id,
                        session_id=session_id or "anonymous",
                        query=user_query,
                        response=full_response,
                    )
                    for log in tool_logs:
                        await self.audit.log_tool_execution(**log)

            except Exception as e:
                error_msg = str(e)
                if "failed_generation" in error_msg:
                    logger.error(f"GROQ_TOOL_CALL_ERROR: {error_msg}")
                    yield f"data: {json.dumps({'message': 'I encountered a technical glitch while trying to use my tools. Let me try again without them.', 'actions': []})}\n\n"
                else:
                    logger.error(f"SYSTEM_FAILURE: {error_msg}")
                    yield f"data: {json.dumps({'message': f'ERROR: {error_msg}', 'actions': []})}\n\n"
        finally:
            _metrics.active_sessions.dec()

    # =========================
    # UTILS
    # =========================

    def _format_history(self, history: list) -> list:
        formatted = []
        for m in history:
            if hasattr(m, "model_dump"):
                formatted.append(m.model_dump())
            elif isinstance(m, dict):
                formatted.append(m)
        return formatted
