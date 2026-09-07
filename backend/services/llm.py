from adapters.base import AdapterResult
from config import get_settings


def _template_script(title: str, topic: str, persona_tone: str) -> str:
    tone = persona_tone or "direct and useful"
    body = topic or title
    return (
        f"# {title}\n\n"
        f"## Scene 1 — Hook\n"
        f"SCRIPT: You are watching this because {body} actually matters.\n"
        f"BROLL: speaker close-up, then kinetic text\n\n"
        f"## Scene 2 — Point\n"
        f"SCRIPT: Here is the one idea to steal: treat {body} as a system, not a one-off post.\n"
        f"BROLL: desk workflow, notes, timeline\n\n"
        f"## Scene 3 — Close\n"
        f"SCRIPT: If this helped, approve the cut and ship it. Tone: {tone}.\n"
        f"BROLL: end card, channel logo\n"
    )


def generate_script(*, title: str, topic: str, persona_tone: str = "") -> AdapterResult:
    settings = get_settings()
    script = _template_script(title, topic, persona_tone)
    if settings.ai_api_key:
        # TODO: POST {AI_BASE_URL}/chat/completions with AI_API_KEY / AI_MODEL
        return AdapterResult(
            ok=True,
            provider="openai-compatible",
            simulated=True,
            payload={
                "todo": True,
                "script": script,
                "base_url": settings.ai_base_url,
                "model": settings.ai_model,
            },
            cost_usd=0.01,
        )
    return AdapterResult(
        ok=True,
        provider="simulated",
        simulated=True,
        payload={"script": script, "model": "simulated"},
        cost_usd=0.001,
    )
