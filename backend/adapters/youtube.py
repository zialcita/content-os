from adapters.base import AdapterResult, ProviderAdapter
from config import get_settings


class YouTubeAdapter(ProviderAdapter):
    name = "youtube"

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.google_client_id and settings.youtube_refresh_token)

    def publish(self, *, title: str, uri: str) -> AdapterResult:
        if self.is_configured():
            # TODO: OAuth refresh + videos.insert
            return AdapterResult(
                ok=True,
                provider="youtube",
                simulated=True,
                uri="https://youtube.com/watch?v=TODO",
                external_id="yt-todo",
                payload={"todo": True, "title": title, "source_uri": uri},
                cost_usd=0.0,
            )
        slug = title.replace(" ", "-").lower()
        return AdapterResult(
            ok=True,
            provider="simulated",
            simulated=True,
            uri=f"https://youtube.com/watch?v=sim_{slug[:12]}",
            external_id=f"sim_{slug[:12]}",
            payload={"note": "YouTube credentials missing; simulated publish.", "source_uri": uri},
        )


def get_youtube_adapter() -> YouTubeAdapter:
    return YouTubeAdapter()
