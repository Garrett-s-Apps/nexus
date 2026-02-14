"""
NEXUS Haiku-based Intake Module

Replaces the regex-based intent classifier + CEO interpreter with a single
Haiku tool-use call. The Haiku model classifies intent AND can execute
lightweight operations via tool calls.

For engineering work, it calls start_directive to hand off to the orchestrator.
"""

import logging
from dataclasses import dataclass

import anthropic

from src.config import get_key
from src.cost.tracker import cost_tracker

logger = logging.getLogger("nexus.haiku_intake")

# Anthropic tool schema for intake operations
INTAKE_TOOLS = [
    {
        "name": "query_org",
        "description": "Query the organization structure, agent details, reporting tree, or teams. Use this to answer questions about who works here, what agents exist, and how the org is structured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["full_org", "agent_detail", "team", "reporting_tree"],
                    "description": "Type of org query to perform",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent ID (required for agent_detail queries)",
                },
            },
            "required": ["query_type"],
        },
    },
    {
        "name": "mutate_org",
        "description": "Make organizational changes: hire new agents, fire agents, promote/demote agents, or reassign reporting lines. Use this when Garrett wants to change the org structure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["hire", "fire", "promote", "reassign", "update_model"],
                    "description": "The organizational action to take",
                },
                "agent_id": {
                    "type": "string",
                    "description": "The agent ID to act on (required for fire, promote, reassign, update_model)",
                },
                "params": {
                    "type": "object",
                    "description": "Additional parameters for the action (hire: full agent spec; promote/update_model: new_model; reassign: new_manager)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "query_status",
        "description": "Get current system status: active directive, recent events, running services, agent activity. Use this to answer 'what's happening right now' questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "detail_level": {
                    "type": "string",
                    "enum": ["summary", "detailed"],
                    "description": "Level of detail to return",
                },
            },
            "required": ["detail_level"],
        },
    },
    {
        "name": "query_cost",
        "description": "Query cost metrics and budget status for different time periods.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["session", "today", "month", "all_time"],
                    "description": "Time scope for cost query",
                },
            },
            "required": ["scope"],
        },
    },
    {
        "name": "query_kpi",
        "description": "Get KPI dashboard and metrics: productivity, quality, cost, security metrics, and trends.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["all", "productivity", "quality", "cost", "security", "trends"],
                    "description": "KPI category to query",
                },
            },
            "required": ["category"],
        },
    },
    {
        "name": "query_ml",
        "description": "Query the ML system: model status, similar past directives, agent performance stats.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["status", "similar_directives", "agent_stats"],
                    "description": "Type of ML query",
                },
                "text": {
                    "type": "string",
                    "description": "Query text (required for similar_directives)",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent ID (required for agent_stats)",
                },
            },
            "required": ["query_type"],
        },
    },
    {
        "name": "start_directive",
        "description": "Start a new engineering directive. This hands off to the orchestrator to spawn Claude Code sessions and execute the work. Use this for any request that involves building, coding, refactoring, testing, deploying, or any other engineering work.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directive_text": {
                    "type": "string",
                    "description": "The directive text describing what to build/do",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "Priority level (default: medium)",
                },
                "context": {
                    "type": "string",
                    "description": "Any additional context or constraints",
                },
            },
            "required": ["directive_text"],
        },
    },
    {
        "name": "generate_document",
        "description": "Generate a document (Word, PowerPoint, PDF): reports, presentations, memos, specifications.",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_type": {
                    "type": "string",
                    "enum": ["docx", "pptx", "pdf"],
                    "description": "Type of document to generate",
                },
                "description": {
                    "type": "string",
                    "description": "What the document should contain",
                },
            },
            "required": ["document_type", "description"],
        },
    },
    {
        "name": "talk_to_agent",
        "description": "Send a direct message to a specific agent. Use this when Garrett wants to communicate with a specific team member.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The agent ID to message",
                },
                "message": {
                    "type": "string",
                    "description": "The message to send",
                },
            },
            "required": ["agent_id", "message"],
        },
    },
    {
        "name": "query_database",
        "description": "Query NEXUS internal databases: directives, events, sessions, memory. Use this when Garrett asks about data stored in NEXUS — past directives, event history, active sessions, conversation logs, or any stored records.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "enum": ["directives", "events", "sessions", "memory", "task_outcomes", "cost_log"],
                    "description": "Which database table to query",
                },
                "filter": {
                    "type": "string",
                    "description": "Optional filter: 'recent' (last 24h), 'active', 'all', or a search term",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return (default 20)",
                },
            },
            "required": ["table"],
        },
    },
]

INTAKE_SYSTEM_PROMPT = """You are the intake coordinator for NEXUS, an autonomous software engineering organization.
Your job is to understand what the CEO (Garrett) wants and route his request to the right system.

CRITICAL: Garrett is the CEO. Every request he makes is a valid directive. NEXUS builds whatever
Garrett asks for — personal projects, client apps, internal tools, websites, anything. Never refuse
work, never suggest he go elsewhere, never gatekeep. If he says build it, you hand it off to
start_directive. No exceptions.

You have access to tools that let you either answer questions directly (org queries, status checks,
cost lookups, KPI dashboards, ML stats, database queries) or hand off engineering work to the
orchestrator (which spawns Claude Code CLI sessions to write code, run tests, build features).

Guidelines:
- For ANY engineering work (build, refactor, deploy, test, fix, create apps, make websites,
  personal projects, tools, scripts — anything involving code), use start_directive immediately.
  Include any context you can infer from the message.
- For simple data queries (org structure, cost, status, KPIs, database lookups), use the
  appropriate query tool and respond conversationally with the results.
- For document requests (reports, decks, memos), use generate_document.
- For direct agent communication ("tell the tech lead...", "@frontend-dev..."), use talk_to_agent.
- For org changes (hire, fire, promote), use mutate_org.
- For conversational messages (greetings, thank yous, general chat), respond naturally without
  using any tools. Keep it SHORT — 2-4 sentences max. Be a sharp, chill coworker.

ROUTING BIAS — when in doubt, use start_directive. Garrett expects action, not conversation.
If a message could be either a question or a request to do work, treat it as work. Examples:
- "fix the nana tracker" → start_directive (not a question)
- "add dark mode" → start_directive (not a question)
- "the login is broken" → start_directive (implicit request to fix)
- "can you update the API?" → start_directive (yes, and do it)
- "what's the cost?" → query_cost (pure data question)
- "how many agents?" → query_org (pure data question)

FOLLOW-UP CONTEXT: {thread_context}

Current org summary:
{org_summary}

Current system status:
{system_status_brief}
"""


@dataclass
class IntakeResult:
    """Result from Haiku intake processing."""

    tool_called: str | None  # Which tool was invoked (None = pure conversation)
    tool_input: dict | None  # The tool's input parameters
    response_text: str  # Haiku's conversational response
    directive_id: str | None = None  # Set by dispatcher after processing
    tokens_in: int = 0
    tokens_out: int = 0


async def run_haiku_intake(
    message: str,
    thread_history: list[dict] | None = None,
    org_summary: str = "",
    system_status_brief: str = "",
    thread_context: str = "",
) -> IntakeResult:
    """
    Run Haiku intake on a message.

    Args:
        message: The user's message
        thread_history: Previous conversation context (last 10 messages)
        org_summary: Current organization summary
        system_status_brief: Current system status
        thread_context: Context about whether this thread has active work

    Returns:
        IntakeResult with tool call info and response text
    """
    api_key = get_key("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("No ANTHROPIC_API_KEY found")
        return IntakeResult(
            tool_called=None,
            tool_input=None,
            response_text="Error: ANTHROPIC_API_KEY not configured",
        )

    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Build message history - type annotations for mypy
    messages: list[dict] = []
    if thread_history:
        # Take last 10 messages for context
        for msg in thread_history[-10:]:
            messages.append({"role": msg["role"], "content": msg.get("content") or msg.get("text", "")})

    # Add current message
    messages.append({"role": "user", "content": message})

    # Format system prompt
    system_prompt = INTAKE_SYSTEM_PROMPT.format(
        org_summary=org_summary or "Organization not yet initialized",
        system_status_brief=system_status_brief or "No active work",
        thread_context=thread_context or "New conversation — no prior thread context.",
    )

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            system=system_prompt,
            messages=messages,  # type: ignore[arg-type]
            tools=INTAKE_TOOLS,  # type: ignore[arg-type]
        )

        # Track cost
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        cost_tracker.record(
            model="haiku",
            agent_name="haiku_intake",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

        # Parse response
        tool_called = None
        tool_input = None
        response_text = ""

        for block in response.content:
            if block.type == "tool_use":
                tool_called = block.name
                tool_input = block.input
            elif block.type == "text":
                response_text += block.text

        return IntakeResult(
            tool_called=tool_called,
            tool_input=tool_input,
            response_text=response_text.strip(),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    except anthropic.APIError as e:
        logger.error(f"Anthropic API error in haiku_intake: {e}")
        return IntakeResult(
            tool_called=None,
            tool_input=None,
            response_text=f"API error: {e}",
        )
    except Exception as e:
        logger.exception(f"Unexpected error in haiku_intake: {e}")
        return IntakeResult(
            tool_called=None,
            tool_input=None,
            response_text=f"Internal error: {e}",
        )


async def format_with_tool_result(
    original_result: IntakeResult,
    tool_output: str,
    thread_history: list[dict] | None = None,
) -> str:
    """
    Send tool result back to Haiku for natural language formatting.

    After a tool executes and returns raw data, this function sends that data
    back to Haiku to format it into a natural, conversational response.

    Args:
        original_result: The original IntakeResult from run_haiku_intake
        tool_output: The raw output from the tool execution
        thread_history: Previous conversation context

    Returns:
        Natural language formatted response from Haiku
    """
    api_key = get_key("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("No ANTHROPIC_API_KEY found")
        return tool_output  # Fall back to raw output

    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Build the continuation conversation with original user message for context
    messages: list = []
    if thread_history:
        for msg in thread_history[-10:]:
            messages.append({"role": msg["role"], "content": msg.get("content") or msg.get("text", "")})

    # Ensure original user message is present so Haiku has context for formatting
    has_recent_user_msg = thread_history and any(
        msg.get("role") == "user" and msg.get("content") == original_result.response_text
        for msg in (thread_history or [])[-3:]
    )
    if not has_recent_user_msg and (not messages or messages[-1]["role"] != "user"):
        messages.append({"role": "user", "content": original_result.response_text or "query"})

    # The tool result needs to be formatted as a tool_result content block
    messages.append({
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_format_001",  # Dummy ID for formatting
                "name": original_result.tool_called or "unknown",
                "input": original_result.tool_input or {},
            }
        ],
    })

    messages.append({
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_format_001",
                "content": tool_output,
            }
        ],
    })

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=messages,  # type: ignore[arg-type]
        )

        # Track cost
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        cost_tracker.record(
            model="haiku",
            agent_name="haiku_intake_format",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

        # Extract text response
        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text += block.text

        return response_text.strip() or tool_output

    except anthropic.APIError as e:
        logger.error(f"Anthropic API error in format_with_tool_result: {e}")
        return tool_output  # Fall back to raw output
    except Exception as e:
        logger.exception(f"Unexpected error in format_with_tool_result: {e}")
        return tool_output  # Fall back to raw output
