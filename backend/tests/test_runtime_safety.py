"""Legacy boundary regressions; no provider access or inherited deployment config.

Integration checks run in separate processes with synthetic environment and a
private SQLite path. .env loading is disabled before ANY application import.
"""

import os
from pathlib import Path
import subprocess
import sys
import textwrap
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import Settings  # noqa: E402
from services.runtime_policy import RuntimeSafetyError, require_legacy_simulation  # noqa: E402


BOOTSTRAP = """
import os
import socket
import sys
from config import Settings, get_settings
Settings.model_config['env_file'] = None
get_settings.cache_clear()
def forbid_network(*args, **kwargs):
    raise AssertionError('Network access is forbidden in runtime-safety tests')
socket.socket.connect = forbid_network
socket.create_connection = forbid_network
"""


def isolated_run(tmp_path, source, **overrides):
    env = {
        "APP_ENV": "test", "RUNTIME_MODE": "simulation",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'isolated.db'}",
        "LOCAL_STORAGE_DIR": str(tmp_path), "SPEND_LIMIT_USD": "25",
        "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.update(overrides)
    result = subprocess.run(
        [sys.executable, "-c", BOOTSTRAP + textwrap.dedent(source)],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def settings(**kwargs):
    # Unlike _env_file=None alone, this also excludes inherited shell values.
    with patch.dict(os.environ, {}, clear=True):
        return Settings(_env_file=None, **kwargs)


def assert_safety_error(config, code):
    with pytest.raises(RuntimeSafetyError) as caught:
        require_legacy_simulation(config)
    assert caught.value.status_code == 503
    assert caught.value.detail["code"] == code
    assert caught.value.detail["retryable"] is False
    assert caught.value.detail["correlation_id"]


def test_default_is_blocked_production_with_zero_budget():
    config = settings()
    assert config.app_env == "production"
    assert config.runtime_mode == "blocked"
    assert config.spend_limit_usd == 0
    assert_safety_error(config, "LEGACY_PRODUCTION_DISABLED")


@pytest.mark.parametrize("mode", ["blocked", "simulation", "live"])
def test_production_never_unlocks(mode):
    assert_safety_error(settings(app_env="production", runtime_mode=mode), "LEGACY_PRODUCTION_DISABLED")


@pytest.mark.parametrize("env", ["prod", "Production", "staging", "preview", "", "test ", "development\n"])
def test_unknown_environment_cannot_bypass_production(env):
    assert_safety_error(settings(app_env=env, runtime_mode="simulation"), "UNSUPPORTED_ENVIRONMENT")


@pytest.mark.parametrize("env", ["test", "development"])
@pytest.mark.parametrize("mode", ["blocked", "live", "", "simulated"])
def test_nonproduction_requires_exact_explicit_simulation(env, mode):
    assert_safety_error(settings(app_env=env, runtime_mode=mode), "SIMULATION_OPT_IN_REQUIRED")


@pytest.mark.parametrize("env", ["test", "development"])
def test_explicit_simulation_is_allowed(env):
    require_legacy_simulation(settings(app_env=env, runtime_mode="simulation"))


@pytest.mark.parametrize("field,value", [
    ("avatar_engine", "heygen"), ("assembly_engine", "shotstack"),
    ("broll_engine", "pexels"), ("storage_backend", "r2"),
    ("ai_api_key", "synthetic-not-a-key"), ("heygen_api_key", "synthetic-not-a-key"),
    ("pexels_api_key", "synthetic-not-a-key"), ("higgsfield_api_key", "synthetic-not-a-key"),
    ("shotstack_api_key", "synthetic-not-a-key"), ("s3_access_key_id", "synthetic-not-a-key"),
    ("s3_secret_access_key", "synthetic-not-a-key"), ("google_client_id", "synthetic-id"),
    ("google_client_secret", "synthetic-not-a-key"), ("youtube_refresh_token", "synthetic-not-a-key"),
    ("youtube_channel_id", "synthetic-id"),
])
def test_no_configured_stub_or_provider_fallback(field, value):
    config = settings(app_env="test", runtime_mode="simulation", **{field: value})
    assert_safety_error(config, "LIVE_CONFIGURATION_FORBIDDEN")
    with pytest.raises(RuntimeSafetyError) as caught:
        require_legacy_simulation(config)
    assert value not in str(caught.value.detail)  # no secret echo


@pytest.mark.parametrize("env,mode,code", [
    ("production", "simulation", "LEGACY_PRODUCTION_DISABLED"),
    ("production", "blocked", "LEGACY_PRODUCTION_DISABLED"),
    ("prod", "simulation", "UNSUPPORTED_ENVIRONMENT"),
    ("test", "blocked", "SIMULATION_OPT_IN_REQUIRED"),
    ("development", "blocked", "SIMULATION_OPT_IN_REQUIRED"),
])
def test_import_refuses_before_database_routes_or_scheduler(tmp_path, env, mode, code):
    isolated_run(tmp_path, f"""
        from services.runtime_policy import RuntimeSafetyError
        try:
            import main
        except RuntimeSafetyError as exc:
            assert exc.code == {code!r}
        else:
            raise AssertionError('unsafe app imported')
        assert 'database' not in sys.modules
        assert 'services.scheduler' not in sys.modules
        assert not any(name.startswith('routers.') for name in sys.modules)
        assert not os.path.exists({str(tmp_path / 'isolated.db')!r})
    """, APP_ENV=env, RUNTIME_MODE=mode,
        V6_READY="true", OIDC_READY="true", MIGRATIONS_READY="true", WORKERS_READY="true")


@pytest.mark.parametrize("env", ["test", "development"])
def test_startup_simulation_has_labels_and_no_scheduler(tmp_path, env):
    isolated_run(tmp_path, """
        from fastapi.testclient import TestClient
        from main import app
        with TestClient(app) as client:
            response = client.get('/health')
            assert response.status_code == 200
            assert response.headers['X-ContentOS-Mode'] == 'simulation'
            assert response.headers['X-ContentOS-Usage'] == 'simulation-not-provider-spend'
            body = response.json()
            assert body['runtime_mode'] == 'simulation'
            assert body['production_ready'] is False
            assert body['publication_kind'] == 'simulation_not_live'
            assert body['usage_kind'] == 'simulation_not_provider_spend'
        assert 'services.scheduler' not in sys.modules
    """, APP_ENV=env)


def test_lifespan_rechecks_before_create_all(tmp_path):
    isolated_run(tmp_path, """
        import main
        from fastapi.testclient import TestClient
        from services.runtime_policy import RuntimeSafetyError
        def forbidden_init():
            raise AssertionError('init_db must not run')
        main.init_db = forbidden_init
        get_settings().app_env = 'production'
        try:
            with TestClient(main.app):
                pass
        except RuntimeSafetyError as exc:
            assert exc.code == 'LEGACY_PRODUCTION_DISABLED'
        else:
            raise AssertionError('production lifespan allowed')
    """)


@pytest.mark.parametrize("env", ["production", "staging"])
def test_requests_without_lifespan_cannot_bypass_guard(tmp_path, env):
    isolated_run(tmp_path, f"""
        from fastapi.testclient import TestClient
        from main import app
        get_settings().app_env = {env!r}
        client = TestClient(app)  # intentionally no lifespan
        for path in ['/v1/workspaces', '/v1/jobs/tick', '/v1/videos']:
            response = client.post(path, json={{'name': 'must not exist'}})
            assert response.status_code == 503
            assert response.json()['detail']['code'] in {{'LEGACY_PRODUCTION_DISABLED', 'UNSUPPORTED_ENVIRONMENT'}}
        assert not os.path.exists({str(tmp_path / 'isolated.db')!r})
    """)


@pytest.mark.parametrize("env", ["test", "development"])
def test_tick_disabled_for_two_workspaces_with_no_global_advancement(tmp_path, env):
    isolated_run(tmp_path, """
        from fastapi.testclient import TestClient
        from main import app
        from database import SessionLocal
        from models.entities import Workspace, VideoProject, RenderJob, CostLedger
        with TestClient(app) as client:
            keys = [client.post('/v1/workspaces', json={'name': name}).json()['api_key']
                    for name in ['Workspace A', 'Workspace B']]
            with SessionLocal() as db:
                for ws in db.query(Workspace).all():
                    video = VideoProject(workspace_id=ws.id, title='Queued fixture', status='script_approved')
                    db.add(video)
                    db.flush()
                    db.add(RenderJob(workspace_id=ws.id, video_id=video.id, job_type='avatar', status='queued'))
                db.commit()
                before_jobs = [(j.id, j.status, j.result_payload) for j in db.query(RenderJob).order_by(RenderJob.id)]
                before_videos = [(v.id, v.status) for v in db.query(VideoProject).order_by(VideoProject.id)]
            for headers in [{}, {'X-API-Key': 'invalid'}, *[{'X-API-Key': k} for k in keys]]:
                response = client.post('/v1/jobs/tick', headers=headers)
                assert response.status_code == 503
                assert response.json()['detail']['code'] == 'GLOBAL_TICK_DISABLED'
            with SessionLocal() as db:
                assert before_jobs == [(j.id, j.status, j.result_payload) for j in db.query(RenderJob).order_by(RenderJob.id)]
                assert before_videos == [(v.id, v.status) for v in db.query(VideoProject).order_by(VideoProject.id)]
                assert db.query(CostLedger).count() == 0
                assert all(ws.spend_usd == 0 for ws in db.query(Workspace))
        assert 'services.scheduler' not in sys.modules
    """, APP_ENV=env)


def test_zero_workspace_budget_does_not_fall_back_to_25(tmp_path):
    isolated_run(tmp_path, """
        from types import SimpleNamespace
        from services.spend import assert_can_spend, SpendLimitExceeded
        ws = SimpleNamespace(spend_usd=0.0, spend_limit_usd=0.0)
        assert get_settings().spend_limit_usd == 25
        assert_can_spend(ws, 0)
        try:
            assert_can_spend(ws, 0.001)
        except SpendLimitExceeded as exc:
            assert exc.status_code == 402
            assert exc.detail['code'] == 'BUDGET_EXCEEDED'
            assert exc.detail['limit_usd'] == 0
        else:
            raise AssertionError('zero fell back to a positive budget')
    """)


def test_zero_default_api_blocks_fixture_usage_and_rolls_back(tmp_path):
    isolated_run(tmp_path, """
        from fastapi.testclient import TestClient
        from main import app
        from database import SessionLocal
        from models.entities import CostLedger, VideoProject, RenderJob
        with TestClient(app) as client:
            created = client.post('/v1/workspaces', json={'name': 'Zero cap'}).json()
            assert created['spend_limit_usd'] == 0
            headers = {'X-API-Key': created['api_key']}
            response = client.post('/v1/videos', headers=headers, json={'title': 'No paid allowance'})
            assert response.status_code == 402
            assert response.json()['detail']['code'] == 'BUDGET_EXCEEDED'
            with SessionLocal() as db:
                assert db.query(CostLedger).count() == 0
                assert db.query(VideoProject).count() == 0
                assert db.query(RenderJob).count() == 0
    """, SPEND_LIMIT_USD="0")


def test_fixture_ledger_is_explicitly_simulation_not_real_spend(tmp_path):
    isolated_run(tmp_path, """
        from fastapi.testclient import TestClient
        from main import app
        from database import SessionLocal
        from models.entities import CostLedger
        with TestClient(app) as client:
            key = client.post('/v1/workspaces', json={'name': 'Fixture'}).json()['api_key']
            response = client.post('/v1/videos', headers={'X-API-Key': key}, json={'title': 'Fixture'})
            assert response.status_code == 200
            with SessionLocal() as db:
                entries = db.query(CostLedger).all()
                assert len(entries) == 1
                assert entries[0].provider == 'simulated'
                assert entries[0].operation == 'simulation.script.generate'
                assert entries[0].amount_usd > 0  # fixture accounting only
    """)


@pytest.mark.parametrize("amount", ["-1", "float('nan')", "float('inf')"])
def test_invalid_usage_cannot_bypass_cap(tmp_path, amount):
    isolated_run(tmp_path, f"""
        from types import SimpleNamespace
        from services.spend import assert_can_spend
        from services.runtime_policy import RuntimeSafetyError
        try:
            assert_can_spend(SimpleNamespace(spend_usd=0.0, spend_limit_usd=25.0), {amount})
        except RuntimeSafetyError as exc:
            assert exc.code == 'INVALID_BUDGET'
        else:
            raise AssertionError('invalid amount allowed')
    """)


def test_real_provider_cannot_settle_in_legacy_ledger(tmp_path):
    isolated_run(tmp_path, """
        from types import SimpleNamespace
        from services.spend import record_spend
        from services.runtime_policy import RuntimeSafetyError
        try:
            record_spend(None, SimpleNamespace(spend_usd=0.0, spend_limit_usd=25.0),
                         provider='heygen', operation='avatar.render', amount_usd=0.1)
        except RuntimeSafetyError as exc:
            assert exc.code == 'LIVE_SPEND_DISABLED'
        else:
            raise AssertionError('real spend allowed')
    """)


def test_dotenv_and_inherited_provider_database_are_not_loaded(tmp_path, monkeypatch):
    # Deliberately hostile synthetic parent values, not real secrets or endpoints.
    monkeypatch.setenv('AI_API_KEY', 'synthetic-parent-key')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://synthetic.invalid/must-not-connect')
    (tmp_path / '.env').write_text('AI_API_KEY=synthetic-dotenv-key\nAPP_ENV=production\nDATABASE_URL=postgresql://synthetic.invalid/no\n')
    isolated_run(tmp_path, """
        import main
        config = get_settings()
        assert config.app_env == 'test'
        assert config.ai_api_key == ''
        assert config.database_url.startswith('sqlite:///')
        assert config.model_config['env_file'] is None
    """)
