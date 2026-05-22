from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from jinja2 import Environment, StrictUndefined, TemplateError

from orchestrator.models.call_state import CallState, ConversationState
from packs._schema.pack import IndustryPack

if TYPE_CHECKING:
    from orchestrator.services.objection_handler import ObjectionContext

_env = Environment(
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_system_prompt(pack: IndustryPack) -> str:
    """Render a pack's system_prompt_template into a final system prompt string."""
    try:
        template = _env.from_string(pack.system_prompt_template)
        return template.render(
            agent=pack.agent,
            product=pack.product,
            compliance=pack.compliance,
        ).strip()
    except TemplateError as exc:
        raise ValueError(f"Failed to render system prompt for pack '{pack.name}': {exc}") from exc


def render_runtime_context(pack: IndustryPack) -> str:
    """Inject current date, an explicit 7-day calendar, and hallucination guards."""
    sched = pack.scheduling
    try:
        now = datetime.now(ZoneInfo(sched.timezone))
    except Exception:
        now = datetime.now()

    today_full = now.strftime("%A, %B %d, %Y")

    # Build an explicit 7-day calendar so the LLM doesn't do date math
    calendar_lines = []
    for i in range(7):
        d = now + timedelta(days=i)
        weekday = d.strftime("%A")
        label = "TODAY" if i == 0 else ("Tomorrow" if i == 1 else weekday)
        date_str = d.strftime("%B %d, %Y")
        if weekday in sched.working_days:
            calendar_lines.append(f"  • {label}: {weekday}, {date_str}")
        else:
            calendar_lines.append(f"  • {label}: {weekday}, {date_str}  ✗ NON-WORKING — do not offer")
    calendar = "\n".join(calendar_lines)

    return (
        f"[RUNTIME CONTEXT]\n"
        f"Today is {today_full} ({sched.timezone}). Business hours: {sched.working_hours}.\n"
        f"\n"
        f"Use ONLY these upcoming dates when proposing times — never invent a weekday/date pairing:\n"
        f"{calendar}\n"
        f"\n"
        f"NEVER address the prospect by a name they haven't given you. If they haven't shared their "
        f"name, don't use one."
    )


def render_stage_instruction(
    pack: IndustryPack,
    state: CallState,
    objection_ctx: ObjectionContext | None = None,
) -> str:
    """Return a short stage-specific instruction appended to the system prompt."""
    stage = state.stage
    s = pack.stages

    match stage:
        case ConversationState.OPENER:
            return (
                f"[STAGE: OPENER]\n"
                f"Open the call with: \"{s.opener.strip()}\"\n"
                f"Then wait for the prospect to respond."
            )
        case ConversationState.PERMISSION:
            return (
                f"[STAGE: PERMISSION]\n"
                f"Ask for permission to continue: \"{s.permission.strip()}\"\n"
                f"If they push back, handle it warmly but don't persist past one attempt."
            )
        case ConversationState.DISCOVERY:
            remaining = [
                q for i, q in enumerate(s.discovery_questions)
                if i not in state.asked_question_indices
            ]
            next_q = remaining[0] if remaining else "Ask a relevant follow-up question."
            return (
                f"[STAGE: DISCOVERY — turn {state.discovery_turns + 1}]\n"
                f"Ask this question (one at a time): \"{next_q}\"\n"
                f"Listen carefully and acknowledge before asking the next one."
            )
        case ConversationState.PITCH:
            pitched = state.pitch_turns
            points = s.pitch_points
            next_point = points[pitched] if pitched < len(points) else points[-1]
            return (
                f"[STAGE: PITCH — turn {state.pitch_turns + 1}]\n"
                f"Naturally introduce this benefit: \"{next_point.strip()}\"\n"
                f"Keep it conversational — one benefit per turn."
            )
        case ConversationState.OBJECTION:
            if objection_ctx:
                retrieval_section = (
                    f"\nSupporting context from knowledge base:\n{objection_ctx.retrieved_context}"
                    if objection_ctx.retrieved_context
                    else ""
                )
                return (
                    f"[STAGE: OBJECTION — {objection_ctx.label} "
                    f"(strike {objection_ctx.strike_count}/{objection_ctx.max_strikes})]\n"
                    f"Suggested response (adapt naturally, don't read verbatim):\n"
                    f"\"{objection_ctx.suggested_response}\""
                    f"{retrieval_section}"
                )
            return (
                "[STAGE: OBJECTION]\n"
                "Acknowledge the prospect's concern empathetically, then offer a "
                "relevant response from the objection playbook. Don't be pushy.\n"
                f"Strikes so far: {sum(state.objection_strikes.values())}"
            )
        case ConversationState.CLOSE:
            return (
                f"[STAGE: CLOSE]\n"
                f"Go for the close: \"{s.close.strip()}\"\n"
                f"Offer two specific time options. Don't ask open-ended questions."
            )
        case ConversationState.SCHEDULE:
            if not state.collected_email:
                return (
                    "[STAGE: SCHEDULE — STEP 1 of 3: ASK FOR EMAIL]\n"
                    "Your entire next response MUST be a single short sentence asking for the "
                    "prospect's email address for the calendar invite. Example:\n"
                    "  \"Great. What's the best email for the calendar invite?\"\n"
                    "Do not ask for anything else. Do not say 'I'll send the invite' yet. "
                    "Do not invent a name."
                )
            if not state.collected_name:
                return (
                    "[STAGE: SCHEDULE — STEP 2 of 3: ASK FOR NAME]\n"
                    f"You already have the email: {state.collected_email}.\n"
                    "Your entire next response MUST be a single short sentence asking for the "
                    "prospect's name. Example:\n"
                    "  \"Got it. And what name should I put on the invite?\"\n"
                    "Do not say 'I'll send the invite' yet. Do not infer the name from the email."
                )
            return (
                "[STAGE: SCHEDULE — STEP 3 of 3: CONFIRM AND CLOSE]\n"
                f"You have: name={state.collected_name}, email={state.collected_email}.\n"
                "Briefly read these back to confirm, thank them, and end with the exact phrase: "
                "\"Have a great day, goodbye.\""
            )
        case ConversationState.END:
            return (
                "[STAGE: END]\n"
                "The call must end now. Say a brief, warm goodbye in under 15 words. "
                "End your message with the exact phrase \"Have a great day, goodbye.\" "
                "so the call disconnects cleanly."
            )
        case _:
            return f"[STAGE: {stage}]"
