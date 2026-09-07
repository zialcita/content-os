from config import get_settings
from adapters.base import AdapterResult, ProviderAdapter


class AvatarEngine(ProviderAdapter):
    name = "avatar"

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.heygen_api_key) and settings.avatar_engine == "heygen"

    def render(self, *, script: str, avatar_id: str, title: str) -> AdapterResult:
        settings = get_settings()
        if self.is_configured():
            return self._heygen_stub(script=script, avatar_id=avatar_id, title=title)
        return AdapterResult(
            ok=True,
            provider="simulated",
            simulated=True,
            uri=f"local://simulated/aroll/{title.replace(' ', '-').lower()}.mp4",
            external_id=f"sim-avatar-{avatar_id or 'default'}",
            payload={
                "engine": settings.avatar_engine,
                "note": "HeyGen not configured; simulated A-roll.",
                "script_chars": len(script),
            },
            cost_usd=0.01,
        )

    def _heygen_stub(self, *, script: str, avatar_id: str, title: str) -> AdapterResult:
        # TODO: POST {heygen_api_base}/v2/video/generate with HEYGEN_API_KEY
        settings = get_settings()
        return AdapterResult(
            ok=True,
            provider="heygen",
            simulated=True,
            uri=f"heygen://pending/{title.replace(' ', '-').lower()}",
            external_id=f"heygen-todo-{avatar_id or 'default'}",
            payload={
                "todo": True,
                "api_base": settings.heygen_api_base,
                "script_chars": len(script),
            },
            cost_usd=0.25,
        )


def get_avatar_engine() -> AvatarEngine:
    return AvatarEngine()
