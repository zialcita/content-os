"""Run only the owned legacy slice with no inherited settings or outbound network."""
import os
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[4]
BACKEND = REPO / "backend"

with TemporaryDirectory(prefix="contentos-runtime-pytest-") as directory:
    os.environ.clear()
    os.environ.update({
        "APP_ENV": "test", "RUNTIME_MODE": "simulation",
        "DATABASE_URL": f"sqlite:///{directory}/test.db",
        "LOCAL_STORAGE_DIR": directory, "SPEND_LIMIT_USD": "25",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    })
    sys.path.insert(0, str(BACKEND))
    from config import Settings, get_settings
    Settings.model_config["env_file"] = None
    get_settings.cache_clear()

    def forbidden_network(*args, **kwargs):
        raise AssertionError("Network access forbidden in legacy simulation test run")

    socket.socket.connect = forbidden_network
    socket.create_connection = forbidden_network
    import pytest
    raise SystemExit(pytest.main([
        str(BACKEND / "tests/test_pipeline.py"),
        str(BACKEND / "tests/test_runtime_safety.py"),
        "-v", "-p", "no:cacheprovider",
        f"--junitxml={Path(__file__).parent / 'pytest.xml'}",
    ]))
