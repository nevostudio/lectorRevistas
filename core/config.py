"""
config.py
---------
Configuracion persistente entre sesiones: recuerda la API key y la ultima URL
analizada para no tener que reescribirlas cada vez.

Se guarda en el HOME del usuario (no en el proyecto, para que no acabe en git)
con permisos restrictivos (solo el propietario puede leerlo). La variable de
entorno ANTHROPIC_API_KEY siempre tiene prioridad sobre el valor guardado.
"""

from __future__ import annotations

import os
import json
import stat

_CONFIG_DIR = os.path.expanduser("~/.config/nevo-revista")
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.json")


def _ensure_dir():
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    try:
        os.chmod(_CONFIG_DIR, stat.S_IRWXU)  # 0700
    except OSError:
        pass


def load() -> dict:
    """Lee la config. Devuelve {} si no existe o esta corrupta."""
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save(data: dict):
    """Escribe la config con permisos 0600 (solo el propietario)."""
    _ensure_dir()
    tmp = _CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _CONFIG_PATH)
    try:
        os.chmod(_CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


def get(key: str, default=None):
    return load().get(key, default)


def set(key: str, value):  # noqa: A003  (sombra de builtin a proposito)
    data = load()
    data[key] = value
    save(data)


def update(values: dict):
    data = load()
    data.update(values)
    save(data)


# --- Atajos especificos -------------------------------------------------- #
def api_key() -> str:
    """API key efectiva: variable de entorno > config guardada > ''."""
    return os.environ.get("ANTHROPIC_API_KEY") or get("api_key", "") or ""


def remember_api_key(key: str):
    set("api_key", key.strip())


def forget_api_key():
    data = load()
    data.pop("api_key", None)
    save(data)


def last_url() -> str:
    return get("last_url", "") or ""


def set_last_url(url: str):
    set("last_url", url.strip())
