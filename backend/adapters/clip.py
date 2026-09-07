from adapters.base import AdapterResult, ProviderAdapter


class ClipEngine(ProviderAdapter):
    name = "clip"

    def is_configured(self) -> bool:
        return True

    def cut(self, *, title: str, duration_s: float = 60.0) -> list[AdapterResult]:
        windows = [(0.0, min(15.0, duration_s)), (max(duration_s - 20.0, 0.0), duration_s)]
        results: list[AdapterResult] = []
        for i, (start, end) in enumerate(windows, start=1):
            slug = title.replace(" ", "-").lower()
            results.append(
                AdapterResult(
                    ok=True,
                    provider="simulated",
                    simulated=True,
                    uri=f"local://simulated/clips/{slug}-{i}.mp4",
                    external_id=f"sim-clip-{i}",
                    payload={"start_s": start, "end_s": end, "title": f"{title} — clip {i}"},
                    cost_usd=0.0,
                )
            )
        return results


def get_clip_engine() -> ClipEngine:
    return ClipEngine()
