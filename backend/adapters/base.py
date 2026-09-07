from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdapterResult:
    ok: bool
    provider: str
    simulated: bool
    uri: str = ""
    external_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    cost_usd: float = 0.0


class ProviderAdapter:
    name = "base"

    def is_configured(self) -> bool:
        return False
