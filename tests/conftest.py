import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_key() -> str:
    return "test-key"


@pytest.fixture
def client(tmp_path, monkeypatch, api_key):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("API_KEYS", f"{api_key},other-key")
    monkeypatch.setenv("DEFAULT_MODEL", "mock")
    monkeypatch.setenv("ENABLE_CATVTON_FLUX", "false")
    monkeypatch.setenv("FASHN_WEIGHTS_DIR", str(tmp_path / "missing-fashn-weights"))
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1000")
    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import create_app

    application = create_app()
    with TestClient(application) as test_client:
        yield test_client
    get_settings.cache_clear()
