from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)))


def render_prompt(name: str, **variables: str) -> tuple[str, str]:
    """Render a prompt pair.

    Reads ``{name}.system.html`` for the system prompt and
    ``{name}.user.html`` for the user prompt. Both receive the same
    template variables.

    Returns (system_prompt, user_prompt).
    """
    system_template = _env.get_template(f"{name}.system.html")
    user_template = _env.get_template(f"{name}.user.html")
    return system_template.render(**variables).strip(), user_template.render(**variables).strip()
