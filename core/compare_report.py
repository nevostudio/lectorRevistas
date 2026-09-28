"""
compare_report.py
-----------------
Genera un informe HTML (con la marca Nevo) que compara dos numeros de una
revista: anunciantes nuevos, perdidos y recurrentes, ademas de un indice de
fidelidad. Es el entregable de "inteligencia competitiva" de la Fase 4.

Usa los datos que devuelve Library.compare_issues().
"""

from __future__ import annotations

import os
import html
import datetime

_FONT_LINK = (
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Big+Shoulders:opsz,wght@10..72,700;10..72,900&'
    'family=Instrument+Sans:wght@400;500&'
    'family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">'
)


def _issue_label(issue: dict | None) -> str:
    if not issue:
        return "—"
    titulo = issue.get("titulo", "Revista") or "Revista"
    numero = issue.get("numero", "")
    return f"{titulo} #{numero}" if numero else titulo


def _rows(items: list[dict], kind: str) -> str:
    """kind: 'nuevo' | 'perdido' | 'recurrente' (para el color del punto)."""
    if not items:
        return ('<tr><td colspan="4" class="empty">'
                'Sin anunciantes en esta categoria.</td></tr>')
    out = []
    for a in items:
        brand = html.escape(a.get("brand", "") or "—")
        sector = html.escape(a.get("sector", "") or "—")
        pages = html.escape(str(a.get("pages", "") or "—"))
        web = a.get("website", "") or ""
        web_cell = (f'<a href="https://{html.escape(web)}" target="_blank">'
                    f'{html.escape(web)}</a>' if web
                    else '<span class="vacio">—</span>')
        out.append(
            f'<tr><td class="marca"><span class="dot {kind}"></span>'
            f'{brand}</td><td>{sector}</td>'
            f'<td class="paginas">{pages}</td><td>{web_cell}</td></tr>')
    return "".join(out)


def export_comparison_html(cmp: dict, path: str) -> str:
    """Escribe el informe comparativo en `path`. Devuelve la ruta."""
    issue_a = cmp.get("issue_a")
    issue_b = cmp.get("issue_b")
    nuevos = cmp.get("nuevos", [])
    perdidos = cmp.get("perdidos", [])
    recurrentes = cmp.get("recurrentes", [])
    fidelidad = cmp.get("fidelidad", 0.0)

    label_a = _issue_label(issue_a)
    label_b = _issue_label(issue_b)
    fecha = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    n_new = len(nuevos)
    n_lost = len(perdidos)
    n_rec = len(recurrentes)
    total_b = n_new + n_rec

    doc = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEVO · Comparativa — {html.escape(label_b)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
{_FONT_LINK}
<style>
  :root {{
    --bg:#ffffff; --ink:#0a0a0a; --orange:#ff4b00;
    --gray-50:#f4f4f2; --gray-100:#ececea; --gray-400:#9a9a97;
    --gray-800:#2a2a28;
    --green:#1f7a4d; --red:#b8430f;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  ::selection{{background:var(--orange);color:#fff}}
  body{{
    background:var(--bg); color:var(--ink);
    font-family:'Instrument Sans',ui-sans-serif,system-ui,sans-serif;
    -webkit-font-smoothing:antialiased; padding:56px 28px;
  }}
  .lienzo{{max-width:1240px;margin:0 auto}}
  .nevo-bar{{display:flex;align-items:center;gap:12px;margin-bottom:32px}}
  .nevo-mono{{
    width:36px;height:36px;background:var(--ink);border-radius:8px;
    display:grid;place-items:center;color:#fff;
    font-family:'Big Shoulders',sans-serif;font-weight:900;font-size:24px;
    font-stretch:75%;letter-spacing:-.04em;line-height:1;
  }}
  .nevo-word{{
    font-family:'Big Shoulders',sans-serif;font-weight:900;font-size:28px;
    font-stretch:75%;letter-spacing:-.02em;line-height:1;
    text-transform:uppercase;position:relative;display:inline-block;
  }}
  .nevo-word .e{{position:relative}}
  .nevo-word .e::after{{
    content:"";position:absolute;left:0;right:.08em;bottom:-.08em;
    height:.12em;background:var(--orange);
  }}
  .nevo-tag{{
    margin-left:auto;font-family:'Geist Mono',ui-monospace,monospace;
    font-size:11px;letter-spacing:.1em;text-transform:uppercase;
    color:var(--gray-400);
  }}
  header.hero{{
    border-top:1px solid var(--gray-100);
    border-bottom:1px solid var(--gray-100);
    padding:36px 0;margin-bottom:8px;
  }}
  .kicker{{
    font-family:'Geist Mono',ui-monospace,monospace;font-weight:500;
    font-size:11px;letter-spacing:.1em;text-transform:uppercase;
    color:var(--gray-400);margin-bottom:14px;
  }}
  .kicker .d{{color:var(--orange)}}
  h1{{
    font-family:'Big Shoulders',sans-serif;font-weight:900;font-stretch:75%;
    font-size:clamp(2.4rem,5vw,4rem);line-height:.92;
    letter-spacing:-.02em;text-transform:uppercase;
  }}
  .vs{{
    margin-top:14px;font-family:'Geist Mono',ui-monospace,monospace;
    font-size:13px;color:var(--gray-800);letter-spacing:.02em;
  }}
  .vs b{{color:var(--ink)}}
  .vs .arrow{{color:var(--orange);margin:0 8px}}

  .stats{{
    display:grid;grid-template-columns:repeat(4,1fr);gap:0;
    margin:40px 0 36px;border:1px solid var(--gray-100);
  }}
  .stat{{padding:24px 26px;border-right:1px solid var(--gray-100)}}
  .stat:last-child{{border-right:none}}
  .stat .n{{
    font-family:'Big Shoulders',sans-serif;font-weight:900;font-stretch:75%;
    font-size:3.2rem;line-height:1;letter-spacing:-.02em;
  }}
  .stat .l{{
    font-family:'Geist Mono',ui-monospace,monospace;font-weight:500;
    font-size:11px;letter-spacing:.1em;text-transform:uppercase;
    color:var(--gray-400);margin-top:10px;
  }}
  .stat.new .n{{color:var(--green)}}
  .stat.lost .n{{color:var(--red)}}
  .stat.rec .n{{color:var(--ink)}}
  .stat.fid .n{{color:var(--orange)}}

  section.bloque{{margin-bottom:40px}}
  .bloque h2{{
    font-family:'Big Shoulders',sans-serif;font-weight:900;font-stretch:75%;
    font-size:1.8rem;text-transform:uppercase;letter-spacing:-.01em;
    margin-bottom:4px;display:flex;align-items:center;gap:12px;
  }}
  .bloque h2 .count{{
    font-family:'Geist Mono',ui-monospace,monospace;font-size:13px;
    font-weight:500;color:#fff;background:var(--ink);
    padding:3px 10px;border-radius:4px;letter-spacing:.02em;
  }}
  .bloque .sub{{
    font-size:13.5px;color:var(--gray-400);margin-bottom:16px;
  }}
  table{{
    width:100%;border-collapse:collapse;background:#fff;
    border:1px solid var(--gray-100);
  }}
  thead th{{
    background:var(--ink);color:#fff;
    font-family:'Geist Mono',ui-monospace,monospace;font-weight:500;
    font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
    padding:13px 16px;text-align:left;
  }}
  tbody tr{{border-bottom:1px solid var(--gray-100)}}
  tbody tr:last-child{{border-bottom:none}}
  tbody tr:hover{{background:var(--gray-50)}}
  tbody td{{padding:13px 16px;font-size:13.5px;vertical-align:middle}}
  .marca{{font-weight:500;display:flex;align-items:center;gap:10px}}
  .dot{{width:9px;height:9px;border-radius:50%;flex-shrink:0}}
  .dot.nuevo{{background:var(--green)}}
  .dot.perdido{{background:var(--red)}}
  .dot.recurrente{{background:var(--gray-400)}}
  .paginas{{font-family:'Geist Mono',ui-monospace,monospace;
           color:var(--gray-400);font-size:12.5px}}
  td a{{color:var(--ink);text-decoration:none;
        border-bottom:1px solid var(--gray-100)}}
  td a:hover{{border-bottom-color:var(--orange)}}
  .vacio{{color:var(--gray-100)}}
  .empty{{text-align:center;padding:30px;color:var(--gray-400);
          font-size:13px}}

  footer{{
    margin-top:32px;font-family:'Geist Mono',ui-monospace,monospace;
    font-size:11px;color:var(--gray-400);
    border-top:1px solid var(--gray-100);padding-top:20px;
    display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;
    text-transform:uppercase;letter-spacing:.08em;
  }}
  footer a{{color:var(--ink);text-decoration:none;
           border-bottom:1px solid var(--orange);text-transform:none}}
  @media(max-width:900px){{.stats{{grid-template-columns:repeat(2,1fr)}}}}
  @media(max-width:640px){{
    body{{padding:28px 14px}}.stats{{grid-template-columns:1fr}}
    table{{display:block;overflow-x:auto}}
  }}
</style>
</head>
<body>
<div class="lienzo">
  <div class="nevo-bar">
    <div class="nevo-mono">N</div>
    <div class="nevo-word">N<span class="e">E</span>VO</div>
    <div class="nevo-tag">Comparativa de numeros · {fecha}</div>
  </div>

  <header class="hero">
    <div class="kicker"><span class="d">●</span> &nbsp;Inteligencia competitiva</div>
    <h1>{html.escape(label_b)}</h1>
    <div class="vs">Comparado con <b>{html.escape(label_a)}</b>
      <span class="arrow">→</span> {html.escape(label_b)}</div>
  </header>

  <div class="stats">
    <div class="stat new"><div class="n">{n_new}</div>
      <div class="l">Nuevos</div></div>
    <div class="stat lost"><div class="n">{n_lost}</div>
      <div class="l">Perdidos</div></div>
    <div class="stat rec"><div class="n">{n_rec}</div>
      <div class="l">Recurrentes</div></div>
    <div class="stat fid"><div class="n">{fidelidad:.0%}</div>
      <div class="l">Fidelidad</div></div>
  </div>

  <section class="bloque">
    <h2>Nuevos anunciantes <span class="count">{n_new}</span></h2>
    <p class="sub">Aparecen en {html.escape(label_b)} pero no estaban en
       {html.escape(label_a)}. Son oportunidades comerciales recientes.</p>
    <table><thead><tr><th>Marca</th><th>Sector</th><th>Paginas</th>
      <th>Web</th></tr></thead>
      <tbody>{_rows(nuevos, "nuevo")}</tbody></table>
  </section>

  <section class="bloque">
    <h2>Anunciantes perdidos <span class="count">{n_lost}</span></h2>
    <p class="sub">Estaban en {html.escape(label_a)} y ya no aparecen en
       {html.escape(label_b)}. Posible fuga de inversion.</p>
    <table><thead><tr><th>Marca</th><th>Sector</th><th>Paginas</th>
      <th>Web</th></tr></thead>
      <tbody>{_rows(perdidos, "perdido")}</tbody></table>
  </section>

  <section class="bloque">
    <h2>Recurrentes <span class="count">{n_rec}</span></h2>
    <p class="sub">Presentes en ambos numeros. Fidelidad sobre el total de
       {label_b}: <b>{fidelidad:.0%}</b> ({n_rec} de {total_b}).</p>
    <table><thead><tr><th>Marca</th><th>Sector</th><th>Paginas</th>
      <th>Web</th></tr></thead>
      <tbody>{_rows(recurrentes, "recurrente")}</tbody></table>
  </section>

  <footer>
    <span>NEVO · Comparativa de anunciantes</span>
    <span><a href="https://nevo.studio">nevo.studio</a></span>
  </footer>
</div>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path
