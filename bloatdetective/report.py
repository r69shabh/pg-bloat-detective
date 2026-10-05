"""Markdown report + thin HTML dashboard (inline SVG, zero deps)."""
from __future__ import annotations
import sqlite3

def render(findings: list[dict], before_after: tuple | None = None) -> str:
    lines = ["# Bloat report", "", "| table | verdict | dead | live | evidence |", "|---|---|---|---|---|"]
    for f in findings:
        lines.append(f"| {f['table']} | **{f['verdict']}** | {f['dead']} | {f['live']} | {f['evidence']} |")
    if before_after:
        b, a = before_after
        lines += ["", f"## Proof: dead tuples {b} → {a} ({(b - a) / max(b, 1) * 100:.0f}% reclaimed)"]
    lines += ["", "_Sources: pg_stat_user_tables, pg_stat_activity.backend_xmin, pg_replication_slots, pg_prepared_xacts, pgstattuple_approx._"]
    return "\n".join(lines) + "\n"

def _sparkline(points: list[int], w: int = 200, h: int = 36) -> str:
    if not points:
        return ""
    mx = max(points) or 1
    step = w / max(len(points) - 1, 1)
    pts = " ".join(f"{i * step:.0f},{h - (v / mx) * (h - 4) - 2:.0f}" for i, v in enumerate(points))
    return f'<svg width="{w}" height="{h}"><polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="2"/></svg>'

def render_html(db_path: str, findings: list[dict]) -> str:
    con = sqlite3.connect(db_path)
    tables = [r[0] for r in con.execute("SELECT DISTINCT tbl FROM snapshots ORDER BY tbl")]
    series = {t: [r[0] for r in con.execute("SELECT dead FROM snapshots WHERE tbl=? ORDER BY ts", (t,))] for t in tables}
    blockers = con.execute("SELECT ts, kind, pid, xact_age, query, slot FROM blockers ORDER BY ts DESC LIMIT 20").fetchall()
    con.close()
    colors = {"normal": "green", "vacuum-starved": "orange", "needs-rewrite": "red"}
    rows = "\n".join(
        f'<tr><td>{f["table"]}</td><td style="color:{colors.get(f["verdict"], "red")};font-weight:bold">{f["verdict"]}</td>'
        f"<td>{_sparkline(series.get(f['table'], []))}</td><td>{f['dead']}</td><td>{f['evidence']}</td></tr>"
        for f in findings)
    blocks = "\n".join(f"<li><b>{k}</b> pid={p} age={a} q={q} slot={s}</li>" for _, k, p, a, q, s in blockers) or "<li>none</li>"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Bloat report</title>
<style>body{{font-family:system-ui;max-width:900px;margin:2em auto}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:6px}}</style>
</head><body><h1>Bloat report</h1>
<table><tr><th>table</th><th>verdict</th><th>dead-tuple timeline</th><th>dead</th><th>evidence</th></tr>{rows}</table>
<h2>Blockers (latest)</h2><ul>{blocks}</ul></body></html>"""
