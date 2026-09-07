import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT.parent / "data"
DATA.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DATA / 'test.db'}")
os.environ.setdefault("SPEND_LIMIT_USD", "25")
os.environ.setdefault("SCHEDULER_INTERVAL_SECONDS", "60")

from config import get_settings  # noqa: E402

get_settings.cache_clear()

from database import Base, engine, init_db  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _key(client: TestClient) -> str:
    res = client.post("/v1/workspaces", json={"name": "Demo Studio"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["api_key"].startswith("cos_")
    return body["api_key"]


def test_health(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_simulated_pipeline(client: TestClient):
    key = _key(client)
    headers = {"X-API-Key": key}

    persona = client.post(
        "/v1/personas",
        headers=headers,
        json={"name": "Founder", "tone": "crisp"},
    )
    assert persona.status_code == 200

    video = client.post(
        "/v1/videos",
        headers=headers,
        json={"title": "Ship the cut", "topic": "content systems", "persona_id": persona.json()["id"]},
    )
    assert video.status_code == 200, video.text
    assert video.json()["status"] == "script_ready"
    assert "Scene 1" in video.json()["script_draft"]
    video_id = video.json()["id"]

    edited = client.patch(
        f"/v1/videos/{video_id}/script",
        headers=headers,
        json={"script": "# Edited\n\n## Scene 1 — Hook\nSCRIPT: Hello.\nBROLL: city night\n"},
    )
    assert edited.status_code == 200
    assert edited.json()["script_draft"].startswith("# Edited")

    approved = client.post(f"/v1/videos/{video_id}/approve-script", headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "avatar_ready"

    broll = client.post(f"/v1/videos/{video_id}/resolve-broll", headers=headers)
    assert broll.status_code == 200
    assert broll.json()["status"] == "resolving_broll"
    assert broll.json()["scenes"][0]["broll_asset_id"]

    cut = client.post(f"/v1/videos/{video_id}/assemble", headers=headers)
    assert cut.status_code == 200
    assert cut.json()["status"] == "in_review"

    final = client.post(f"/v1/videos/{video_id}/approve", headers=headers)
    assert final.status_code == 200
    assert final.json()["status"] == "approved"

    published = client.post(f"/v1/videos/{video_id}/publish", headers=headers)
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["published_url"]

    clips = client.get(f"/v1/videos/{video_id}/clips", headers=headers)
    assert clips.status_code == 200
    assert len(clips.json()) >= 1

    me = client.get("/v1/workspaces/me", headers=headers)
    assert me.json()["spend_usd"] > 0


def test_spend_gate(client: TestClient, monkeypatch):
    from services import spend as spend_mod

    key = _key(client)
    headers = {"X-API-Key": key}

    def refuse(*_args, **_kwargs):
        from models.entities import Workspace
        from database import SessionLocal

        db = SessionLocal()
        ws = db.query(Workspace).first()
        ws.spend_usd = 25.0
        db.commit()
        db.close()

    refuse()
    res = client.post("/v1/videos", headers=headers, json={"title": "Over budget"})
    assert res.status_code == 402
    assert spend_mod  # keep import used
