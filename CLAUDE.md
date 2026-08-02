# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependency manager is `uv` (not pip directly).

```bash
make install                        # uv sync
make dev                            # uvicorn main:app --reload  (http://localhost:8000)
make test                           # uv run pytest tests/
PYTHONPATH=. uv run pytest tests/test_api.py::test_name -v   # single test
uv run python scripts/evaluator.py  # LLM-as-a-judge eval pipeline, needs GROQ_API_KEY/API_KEY, writes eval_report.md
make clean                          # rm .venv, __pycache__, .pytest_cache
```

Required env vars (`.env`, see `.env.example`): `API_KEY` (client auth secret), `GROQ_API_KEY` (default LLM provider), optional `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` if `app/config/config.yml`'s `llm.model` targets those providers instead. `app/core/config.py` validates the matching key is present at startup based on the `groq/`, `openai/`, or `anthropic/` prefix in `llm.model` (skipped under pytest unless `FORCE_ENV_VALIDATION=1`).

CI (`.github/workflows/llm-eval.yml`) runs the evaluator on every PR to `main`, monthly on a cron, and on manual dispatch — posts `eval_report.md` as a sticky PR comment.

## Architecture

Hexagonal (ports & adapters). Domain logic never imports FastAPI or infra directly:
- `app/domain/ports/` — abstract interfaces (`LLMPort`, `DataProviderPort`, `AuditPort`).
- `app/domain/services/agent.py` — `AgentService`, the orchestrator. Only depends on ports, injected via `app/core/dependencies.py`.
- `app/adapters/` — concrete implementations: `llm/litellm_adapter.py` (LiteLLM, swappable model provider), `data/json_loader.py` (singleton, mtime-cached loader of `app/data/data.json` into `PortfolioData`), `data/sqlite_audit.py` (conversation/tool-call audit log), `controllers/v1/*.py` (FastAPI routers).

**Agent loop** (`AgentService.get_response` / `get_streaming_response`, in `app/domain/services/agent.py`): ReAct-style loop, max `MAX_ITERATIONS = 5` rounds of tool calls, using `tool_registry.schemas` for function definitions. Tools live in `app/tools/cv_tools.py` and self-register via the `@tool_registry.tool(...)` decorator (`app/tools/registry.py`), which introspects the function signature to build the JSON schema automatically — add a new tool by decorating a function, no manual schema needed. The streaming and non-streaming response paths duplicate the tool-calling loop logic (SSE requires reconstructing tool-call deltas chunk-by-chunk into a `ToolCallProxy`); keep both in sync when changing agent behavior.

**Context injection**: the LLM never receives the full `data.json` in one shot. The system prompt (`app/core/prompts.py`) plus `_get_navigation_context()` inject only project slugs / experience company names + the frontend's current page (`ChatContext`) as `VALID_IDENTIFIERS`. Everything else (bio, full project detail, work history) is fetched on demand via tool calls against the singleton `data_provider`.

**Session memory is in-process and ephemeral**: `AgentService._sessions` is a plain class-level dict, not persisted or shared across workers/instances. History beyond the last 6 messages gets summarized via an extra LLM call (`_summarize_history`) rather than kept verbatim. This does not survive restarts or scale past a single instance.

**Guardrails** (`_check_input_guardrails` in `agent.py`): length cap (300 chars), bilingual regex patterns against prompt-injection/role-override/encoding requests, and a special-character density check — all before the query ever reaches the LLM. Blocked queries short-circuit with a canned refusal and log a `security_blocks_total` metric + audit event.

**Platform-conditional audit**: `app/core/dependencies.py` disables the SQLite audit adapter entirely when `VERCEL == "1"` (serverless filesystem is ephemeral there). `/api/v1/insights` (`app/adapters/controllers/v1/insights.py`) returns 503 when audit is `None`.

**Observability**: `prometheus-fastapi-instrumentator` auto-instruments HTTP metrics and exposes `/metrics`; `app/core/metrics.py` defines custom counters/gauges (`tool_calls_total`, `security_blocks_total`, `active_sessions`) referenced directly from `agent.py`. OpenTelemetry tracing is initialized in `main.py`'s lifespan (`init_telemetry`) and spans wrap each tool call when the `opentelemetry` package is importable (soft dependency — `agent.py` falls back to `trace = None` otherwise).

## 1. Context and Token Optimization Rules
*   **Output and Code Compression:** `caveman`, `caveman-commit`, `caveman-review`, `caveman-compress`, and `ponytail-*` below refer to an optional Claude Code plugin (compressed terse output + technical-debt tracking). If it isn't installed in your session, treat these bullets as "write concisely" / "track debt in a `TODO:`" and skip the literal skill invocation. When available: respond using token compression (skill `/caveman:caveman full`), removing filler words and unnecessary introductions without losing technical precision, applying the YAGNI ladder (stdlib and native features first).
*   **Commit Messages:** Commit messages must be extremely concise and describe the technical change directly (using the `/caveman:caveman-commit` skill, if available).
*   **Reading Context:** Before performing recursive searches across the repository or proposing any code changes, the agent must check the context mapping in `CLAUDE.md` and read the corresponding documentation file in `docs/context/[module].md`.

## 2. Development Workflow (Superpowers)
*   **Requirements Clarification:** If requirements are unclear or involve design decisions, the agent must initiate a clarification process using the `brainstorming` skill before drafting the plan.
*   **Mandatory Planning:** No code should be written or modified without first drawing up a detailed plan using the `writing-plans` skill.
*   **Isolation:** Any new feature development must be performed in an isolated git branch/worktree using `using-git-worktrees`.
*   **Delegation and Parallelism:** For plan execution, if there are tasks independent of each other, the `dispatching-parallel-agents` skill must be used to launch parallel subagents; if they are sequential, use the `subagent-driven-development` skill.
*   **Systematic Debugging:** In case of test failures or bugs, the agent must follow the `systematic-debugging` skill to diagnose the issue before proposing corrective code.
*   **Test-Driven Development:** Implement new features by writing the corresponding tests before implementing the code, following the `test-driven-development` skill.
*   **Verification Before Completion:** It is mandatory to run test suites or local validation commands (`verification-before-completion`) before claiming a task is complete.
*   **Code Review:** Upon completing development, request a code review using the `requesting-code-review` skill. In case of receiving feedback, follow the `receiving-code-review` skill rigorously.
*   **Execution in Separate Session:** To execute a plan in a distinct session with review checkpoints, use the `executing-plans` skill.
*   **Branch Completion:** When development in a worktree is complete, use the `finishing-a-development-branch` skill to decide how to integrate the work (merge, PR, or cleanup).
*   **Skill Creation:** To create or edit custom project skills, use the `writing-skills` skill before deploying.
*   **UI/UX Pro Max Usage:** For any task requiring interface design, layout, color palettes, logos, banners, slides, or frontend styling, the agent must use the skills from the UI/UX Pro Max plugin (`design`, `ui-styling`, `design-system`, `brand`, `slides`, `banner-design`, `ui-ux-pro-max`) before writing code.

## 3. Code Quality and Simplicity
*   **Avoid Complexity:** The agent must keep the code as simple as possible. Before each commit, perform a code review using the `caveman-review` skill (or `ponytail-review` as an alternative) to eliminate unnecessary abstractions and dead code.
*   **Technical Debt:** Use `ponytail-debt` to track and manage `ponytail:` comments as pending technical debt.

## 4. Context Persistence
*   **Documenting Changes:** If structural changes are made to a module during the session (APIs, database schema, signatures), the agent must update the `docs/context/[module].md` file and compress it using the `/caveman-compress <file>` command (or `caveman-compress` as an alternative) before finishing.

## 5. Native Slash Commands
*   **Long-Running Tasks:** Use `/goal` for objectives that require prolonged execution without interruption.
*   **Automation:** Use `/schedule` for recurring tasks (e.g., weekly `ponytail-audit`).
*   **Plan Alignment:** Use `/grill-me` as a complement to `brainstorming` for interactive interviews.
*   **Persistent Learning:** Use `/learn` after corrections so that the agent remembers the behavior in future sessions.

## 6. Git Control and File System
*   **Git Actions:** Do not execute `git add`, `git commit`, `git push`, `git merge`, or `git rebase` unless the user explicitly requests it in their current message. Suggesting a commit message is correct; executing it on your own is not.
*   **File System Security:** Do not delete, rename, or move files or directories without explicit confirmation.
*   **Configuration Modifications:** Do not modify critical configuration files (such as `.env`, `requirements.txt`, `package.json`, etc.) unless the task is directly related to them.
*   **Multi-File Confirmation:** If a change requires touching multiple files, list them first and wait for confirmation before proceeding.

## 7. Code Style and Best Practices
*   **Consistency:** Follow the existing patterns in the file you are modifying. Do not introduce new conventions halfway through the project.
*   **Typing:** Use type annotations (type hints/types) in all function signatures.
*   **No File Path Comments:** Do not place the file path as a comment on the first line of files (e.g., `# app/config.py`). Clean and self-documenting code is preferred.

## 8. Security and Cost Control (Guardrails)
*   **Authentication:** Do not remove or bypass authentication dependencies or API validation unless explicitly instructed.
*   **API Calls / RAG:** Always verify that data exists before sending requests or tokenizing towards paid LLM APIs. Avoid unnecessary calls to control costs.
*   **Running Tests:** Distinguish between unit tests (free execution) and integration tests (which consume external API credits). Do not run integration tests automatically.

**Tradeoff:** Sections 6-8 bias toward caution over speed. For trivial tasks, use judgment.

## 9. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 10. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 11. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 12. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

> [!TIP]
> Sections 6-8 above originated as a copyable template (Git, code style, security/cost boundaries) for reuse across other projects' `AGENTS.md` — they are active rules in this repo, not just an example.