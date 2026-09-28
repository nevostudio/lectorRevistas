import os
import stat
import tempfile

import pytest

from core import config


@pytest.fixture(autouse=True)
def temp_config(monkeypatch):
    d = tempfile.mkdtemp()
    path = os.path.join(d, "config.json")
    monkeypatch.setattr(config, "_CONFIG_DIR", d)
    monkeypatch.setattr(config, "_CONFIG_PATH", path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield


def test_guardar_y_leer_url():
    config.set_last_url("https://ejemplo.com/revista")
    assert config.last_url() == "https://ejemplo.com/revista"


def test_env_tiene_prioridad(monkeypatch):
    config.remember_api_key("sk-guardada")
    assert config.api_key() == "sk-guardada"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-entorno")
    assert config.api_key() == "sk-entorno"


def test_olvidar_clave_conserva_resto():
    config.set_last_url("https://x.com")
    config.remember_api_key("sk-x")
    config.forget_api_key()
    assert config.get("api_key") is None
    assert config.last_url() == "https://x.com"


def test_permisos_restrictivos():
    config.remember_api_key("sk-x")
    mode = stat.S_IMODE(os.stat(config._CONFIG_PATH).st_mode)
    assert mode == 0o600


def test_config_corrupta_no_rompe():
    with open(config._CONFIG_PATH, "w") as f:
        f.write("{ esto no es json valido")
    assert config.load() == {}
