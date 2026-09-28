"""
library.py
----------
Biblioteca local (SQLite) de revistas analizadas. Convierte el extractor en
una herramienta de inteligencia competitiva: cada analisis se guarda y luego
se pueden comparar numeros, ver el historico de un anunciante o el reparto
por sector (share of voice).

No requiere servidor: es un unico fichero .db portable.
"""

from __future__ import annotations

import os
import json
import sqlite3
import datetime

from core.detector import canonical_brand
from core.sectors import normalize_sector

# Ubicacion por defecto de la base de datos (junto al proyecto, carpeta data/).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(_PROJECT_ROOT, "data", "biblioteca.db")


SCHEMA = """
CREATE TABLE IF NOT EXISTS issues (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo          TEXT,
    numero          TEXT,
    url             TEXT,
    fecha_analisis  TEXT,
    paginas         INTEGER,
    modo            TEXT,
    coste_usd       REAL,
    n_anunciantes   INTEGER
);

CREATE TABLE IF NOT EXISTS advertisers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id    INTEGER NOT NULL,
    brand        TEXT,
    canonical    TEXT,
    sector       TEXT,
    sector_group TEXT,
    pages        TEXT,
    website     TEXT,
    email       TEXT,
    phone       TEXT,
    ad_size     TEXT,
    confidence  REAL,
    method      TEXT,
    FOREIGN KEY (issue_id) REFERENCES issues(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_adv_issue ON advertisers(issue_id);
CREATE INDEX IF NOT EXISTS idx_adv_canon ON advertisers(canonical);
"""


def _as_dict(advertiser) -> dict:
    return advertiser if isinstance(advertiser, dict) else advertiser.__dict__


class Library:
    """Acceso a la biblioteca de revistas analizadas."""

    def __init__(self, db_path: str = DEFAULT_DB):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        """Migraciones para bases de datos creadas con un esquema anterior."""
        cols = {r["name"] for r in self.conn.execute(
            "PRAGMA table_info(advertisers)")}
        if "sector_group" not in cols:
            self.conn.execute(
                "ALTER TABLE advertisers ADD COLUMN sector_group TEXT")
        # Rellena el grupo en filas que aun no lo tengan.
        pending = self.conn.execute(
            "SELECT id, sector FROM advertisers "
            "WHERE sector_group IS NULL OR sector_group = ''").fetchall()
        for r in pending:
            self.conn.execute(
                "UPDATE advertisers SET sector_group = ? WHERE id = ?",
                (normalize_sector(r["sector"] or ""), r["id"]))

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------ #
    # Guardar
    # ------------------------------------------------------------------ #
    def save_issue(self, meta: dict, advertisers: list) -> int:
        """Guarda una revista analizada y sus anunciantes. Devuelve el id."""
        cur = self.conn.cursor()
        cur.execute(
            """INSERT INTO issues
               (titulo, numero, url, fecha_analisis, paginas, modo,
                coste_usd, n_anunciantes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                meta.get("titulo", "Revista"),
                str(meta.get("numero", "") or ""),
                meta.get("url", ""),
                datetime.datetime.now().isoformat(timespec="seconds"),
                int(meta.get("paginas") or 0) if str(
                    meta.get("paginas") or "").isdigit() else None,
                meta.get("modo", ""),
                float(meta.get("coste_usd") or 0) or None,
                len(advertisers),
            ),
        )
        issue_id = cur.lastrowid
        for a in advertisers:
            d = _as_dict(a)
            cur.execute(
                """INSERT INTO advertisers
                   (issue_id, brand, canonical, sector, sector_group, pages,
                    website, email, phone, ad_size, confidence, method)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    issue_id,
                    d.get("brand", ""),
                    canonical_brand(d.get("brand", "")),
                    d.get("sector", ""),
                    normalize_sector(d.get("sector", "")),
                    ", ".join(str(p) for p in d.get("pages", [])),
                    d.get("website", ""),
                    d.get("email", ""),
                    d.get("phone", ""),
                    d.get("ad_size", ""),
                    float(d.get("confidence") or 0),
                    d.get("method", ""),
                ),
            )
        self.conn.commit()
        return issue_id

    # ------------------------------------------------------------------ #
    # Consultar
    # ------------------------------------------------------------------ #
    def list_issues(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT * FROM issues ORDER BY fecha_analisis DESC, id DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_issue(self, issue_id: int) -> dict | None:
        r = self.conn.execute(
            "SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
        return dict(r) if r else None

    def get_advertisers(self, issue_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM advertisers WHERE issue_id = ? ORDER BY brand",
            (issue_id,)).fetchall()
        return [dict(r) for r in rows]

    def delete_issue(self, issue_id: int):
        self.conn.execute("DELETE FROM advertisers WHERE issue_id = ?",
                          (issue_id,))
        self.conn.execute("DELETE FROM issues WHERE id = ?", (issue_id,))
        self.conn.commit()

    # ------------------------------------------------------------------ #
    # Inteligencia
    # ------------------------------------------------------------------ #
    def compare_issues(self, id_a: int, id_b: int) -> dict:
        """Compara dos numeros (A = anterior, B = actual).

        Devuelve nuevos (en B, no en A), perdidos (en A, no en B) y
        recurrentes (en ambos), comparando por marca canonica.
        """
        a = self.get_advertisers(id_a)
        b = self.get_advertisers(id_b)
        map_a = {x["canonical"]: x for x in a if x["canonical"]}
        map_b = {x["canonical"]: x for x in b if x["canonical"]}
        keys_a = set(map_a)
        keys_b = set(map_b)

        nuevos = [map_b[k] for k in sorted(keys_b - keys_a,
                                           key=lambda k: map_b[k]["brand"])]
        perdidos = [map_a[k] for k in sorted(keys_a - keys_b,
                                             key=lambda k: map_a[k]["brand"])]
        recurrentes = [map_b[k] for k in sorted(keys_a & keys_b,
                                                key=lambda k: map_b[k]["brand"])]

        total_b = len(keys_b)
        fidelidad = (len(recurrentes) / total_b) if total_b else 0.0
        return {
            "issue_a": self.get_issue(id_a),
            "issue_b": self.get_issue(id_b),
            "nuevos": nuevos,
            "perdidos": perdidos,
            "recurrentes": recurrentes,
            "fidelidad": fidelidad,
        }

    def advertiser_history(self, brand: str) -> list[dict]:
        """Numeros en los que ha aparecido una marca (por su canonica)."""
        canon = canonical_brand(brand)
        rows = self.conn.execute(
            """SELECT i.id, i.titulo, i.numero, i.fecha_analisis,
                      adv.brand, adv.pages, adv.sector, adv.ad_size
               FROM advertisers adv
               JOIN issues i ON i.id = adv.issue_id
               WHERE adv.canonical = ?
               ORDER BY i.fecha_analisis""",
            (canon,)).fetchall()
        return [dict(r) for r in rows]

    def share_of_voice(self, issue_id: int) -> list[tuple[str, int]]:
        """Reparto de anunciantes por categoria amplia (mayor primero).

        Agrupa por la categoria normalizada (sector_group), no por el sector
        libre de la IA, para que el reparto sea legible.
        """
        rows = self.conn.execute(
            """SELECT COALESCE(NULLIF(TRIM(sector_group), ''),
                               'Sin sector') AS sec,
                      COUNT(*) AS n
               FROM advertisers WHERE issue_id = ?
               GROUP BY sec ORDER BY n DESC, sec""",
            (issue_id,)).fetchall()
        return [(r["sec"], r["n"]) for r in rows]


def save_analysis(meta: dict, advertisers: list,
                  db_path: str = DEFAULT_DB) -> int:
    """Atajo: abre la biblioteca, guarda un analisis y cierra."""
    with Library(db_path) as lib:
        return lib.save_issue(meta, advertisers)
