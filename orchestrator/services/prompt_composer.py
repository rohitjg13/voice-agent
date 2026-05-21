from jinja2 import Environment, StrictUndefined, TemplateError

from orchestrator.models.call_state import CallState, ConversationState
from packs._schema.pack import IndustryPack

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


def render_stage_instruction(pack: IndustryPack, state: CallState) -> str:
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
            return (
                f"[STAGE: SCHEDULE]\n"
                f"\"{s.schedule.strip()}\"\n"
                f"Confirm the meeting details and end on a warm, positive note."
            )
        case ConversationState.END:
            return (
                "[STAGE: END]\n"
                "Wrap up the call politely. Thank them for their time. Keep it brief."
            )
        case _:
            return f"[STAGE: {stage}]"
