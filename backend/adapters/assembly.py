from adapters.base import AdapterResult, ProviderAdapter
from config import get_settings


class AssemblyEngine(ProviderAdapter):
    name = "assembly"

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.shotstack_api_key) and settings.assembly_engine == "shotstack"

    def assemble(self, *, title: str, scene_uris: list[str]) -> AdapterResult:
        if self.is_configured():
            return self._shotstack_stub(title=title, scene_uris=scene_uris)
        slug = title.replace(" ", "-").lower()
        return AdapterResult(
            ok=True,
            provider="simulated",
            simulated=True,
            uri=f"local://simulated/assembly/{slug}.mp4",
            external_id=f"sim-assembly-{slug}",
            payload={"scenes": scene_uris, "note": "Shotstack not configured; simulated cut."},
            cost_usd=0.02,
        )

    def _shotstack_stub(self, *, title: str, scene_uris: list[str]) -> AdapterResult:
        # TODO: POST {shotstack_api_base}/{env}/render
        settings = get_settings()
        return AdapterResult(
            ok=True,
            provider="shotstack",
            simulated=True,
            uri=f"shotstack://todo/{title.replace(' ', '-')}",
            external_id="shotstack-todo",
            payload={
                "todo": True,
                "api_base": settings.shotstack_api_base,
                "env": settings.shotstack_env,
                "scenes": scene_uris,
            },
            cost_usd=0.08,
        )


def get_assembly_engine() -> AssemblyEngine:
    return AssemblyEngine()
