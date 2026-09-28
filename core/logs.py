"""
logs.py
-------
Registro a fichero de cada ejecucion. Deja un rastro de lo que paso (util para
soporte y para diagnosticar una revista que fallo) sin estorbar a la interfaz:
cada mensaje de progreso se escribe ademas en logs/nevo_<fecha>.log.

No depende de nada externo. Si por lo que sea no se puede escribir el log, la
ejecucion continua igual (el log nunca debe romper el flujo principal).
"""

from __future__ import annotations

import os
import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")


def log_path(when: datetime.date | None = None) -> str:
    day = (when or datetime.date.today()).strftime("%Y%m%d")
    return os.path.join(LOG_DIR, f"nevo_{day}.log")


def log_line(msg: str):
    """Anade una linea con marca de tiempo al log del dia. Nunca lanza."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(f"{ts}  {msg}\n")
    except OSError:
        pass


def tee(progress=None):
    """Envuelve un callback de progreso para que ademas escriba al log.

    Si `progress` es None, solo escribe al log. Devuelve un callable nuevo.
    """
    def _emit(msg: str):
        if progress is not None:
            progress(msg)
        log_line(msg)
    return _emit
