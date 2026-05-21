from jinja2 import Environment, StrictUndefined, TemplateError

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
