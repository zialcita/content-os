from sqlalchemy.orm import Session

from adapters.base import AdapterResult, ProviderAdapter
from config import get_settings
from models.entities import MediaAsset
from models.enums import AssetKind, AssetSource


class BrollEngine(ProviderAdapter):
    name = "broll"

    def is_configured(self) -> bool:
        settings = get_settings()
        if settings.broll_engine == "pexels":
            return bool(settings.pexels_api_key)
        if settings.broll_engine == "higgsfield":
            return bool(settings.higgsfield_api_key)
        if settings.broll_engine == "library":
            return True
        return False

    def resolve(
        self,
        db: Session,
        workspace_id: str,
        *,
        query: str,
    ) -> AdapterResult:
        library = self._from_library(db, workspace_id, query)
        if library:
            return library

        settings = get_settings()
        if settings.pexels_api_key:
            return self._pexels_stub(query)
        if settings.higgsfield_api_key:
            return self._higgsfield_stub(query)

        slug = query.replace(" ", "-").lower()[:48] or "broll"
        return AdapterResult(
            ok=True,
            provider="simulated",
            simulated=True,
            uri=f"local://simulated/broll/{slug}.mp4",
            external_id=f"sim-broll-{slug}",
            payload={"query": query, "waterfall": ["library", "pexels", "higgsfield", "simulated"]},
            cost_usd=0.0,
        )

    def _from_library(self, db: Session, workspace_id: str, query: str) -> AdapterResult | None:
        q = query.lower()
        assets = (
            db.query(MediaAsset)
            .filter(
                MediaAsset.workspace_id == workspace_id,
                MediaAsset.kind == AssetKind.BROLL.value,
                MediaAsset.source == AssetSource.LIBRARY.value,
            )
            .all()
        )
        for asset in assets:
            hay = f"{asset.title} {asset.uri}".lower()
            if q and q in hay:
                return AdapterResult(
                    ok=True,
                    provider="library",
                    simulated=False,
                    uri=asset.uri,
                    external_id=asset.id,
                    payload={"asset_id": asset.id, "title": asset.title},
                    cost_usd=0.0,
                )
        return None

    def _pexels_stub(self, query: str) -> AdapterResult:
        # TODO: GET https://api.pexels.com/videos/search?query=...
        return AdapterResult(
            ok=True,
            provider="pexels",
            simulated=True,
            uri=f"pexels://todo/{query.replace(' ', '-')}",
            external_id="pexels-todo",
            payload={"todo": True, "query": query},
            cost_usd=0.0,
        )

    def _higgsfield_stub(self, query: str) -> AdapterResult:
        # TODO: POST Higgsfield generate with HIGGSFIELD_API_KEY
        settings = get_settings()
        return AdapterResult(
            ok=True,
            provider="higgsfield",
            simulated=True,
            uri=f"higgsfield://todo/{query.replace(' ', '-')}",
            external_id="higgsfield-todo",
            payload={"todo": True, "api_base": settings.higgsfield_api_base, "query": query},
            cost_usd=0.15,
        )


def get_broll_engine() -> BrollEngine:
    return BrollEngine()
