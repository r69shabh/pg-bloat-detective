"""Markdown report + thin HTML dashboard (inline SVG, zero deps) + JSON export (shadcn dashboard feed)."""
from __future__ import annotations
import sqlite3
import time

def render(findings: list[dict], before_after: tuple | None = None) -> str:
    lines = ["# Bloat report", "", "| table | verdict | dead | live | evidence |", "|---|---|---|---|---|"]
    for f in findings:
        lines.append(f"| {f['table']} | **{f['verdict']}** | {f['dead']} | {f['live']} | {f['evidence']} |")
    if before_after:
        b, a = before_after
        lines += ["", f"## Proof: dead tuples {b} → {a} ({(b - a) / max(b, 1) * 100:.0f}% reclaimed)"]
    lines += ["", "_Sources: pg_stat_user_tables, pg_stat_activity.backend_xmin, pg_replication_slots, pg_prepared_xacts, pgstattuple_approx, pgstatindex._"]
    return "\n".join(lines) + "\n"

def _sparkline(points: list[int], w: int = 200, h: int = 36) -> str:
    if not points:
        return ""
    mx = max(points) or 1
    step = w / max(len(points) - 1, 1)
    pts = " ".join(f"{i * step:.0f},{h - (v / mx) * (h - 4) - 2:.0f}" for i, v in enumerate(points))
    return f'<svg width="{w}" height="{h}"><polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="2"/></svg>'

def export_json(db_path: str, findings: list[dict]) -> dict:
    """Machine-readable feed for the shadcn dashboard: findings + per-table series + blockers."""
    try:
        con = sqlite3.connect(db_path)
    except Exception:
        return {"generated_at": int(time.time()), "findings": findings, "series": {},
                "approx": {}, "index_bloat": {}, "index_scans": {}, "blockers": []}
    try:
        try:
            tables = [r[0] for r in con.execute("SELECT DISTINCT tbl FROM snapshots ORDER BY tbl")]
        except Exception:
            tables = []
        series = {t: [{"ts": ts, "live": lv, "dead": d} for ts, lv, d in
                  con.execute("SELECT ts, live, dead FROM snapshots WHERE tbl=? ORDER BY ts", (t,))] for t in tables}
        try:
            approx = {t: [{"ts": ts, "dead_pct": p} for ts, p in
                    con.execute("SELECT ts, dead_pct FROM approx WHERE tbl=? AND idx IS NULL ORDER BY ts", (t,))] for t in tables}
        except Exception:
            approx = {}
        try:
            idx_names = [r[0] for r in con.execute("SELECT DISTINCT idx FROM approx WHERE idx IS NOT NULL ORDER BY idx")]
            index_bloat = {i: [{"ts": ts, "bloat_pct": p} for ts, p in
                        con.execute("SELECT ts, idx_bloat_pct FROM approx WHERE idx=? AND idx_bloat_pct IS NOT NULL ORDER BY ts", (i,))] for i in idx_names}
        except Exception:
            index_bloat = {}
        try:
            scan_names = [r[0] for r in con.execute("SELECT DISTINCT idx FROM index_stats ORDER BY idx")]
            index_scans = {i: [{"ts": ts, "scans": s} for ts, s in
                        con.execute("SELECT ts, scans FROM index_stats WHERE idx=? ORDER BY ts", (i,))] for i in scan_names}
        except Exception:
            index_scans = {}  # old DBs without index_stats: feed stays heap-only
        try:
            blockers = [{"ts": ts, "kind": k, "pid": p, "age": a, "query": q, "slot": s} for ts, k, p, a, q, s in
                    con.execute("SELECT ts, kind, pid, xact_age, query, slot FROM blockers ORDER BY ts DESC LIMIT 20")]
        except Exception:
            blockers = []
        return {"generated_at": int(time.time()), "findings": findings, "series": series,
                "approx": approx, "index_bloat": index_bloat, "index_scans": index_scans,
                "blockers": blockers}
    finally:
        try:
            con.close()
        except Exception:
            pass

def render_html(db_path: str, findings: list[dict]) -> str:
    con = sqlite3.connect(db_path)
    tables = [r[0] for r in con.execute("SELECT DISTINCT tbl FROM snapshots ORDER BY tbl")]
    series = {t: [r[0] for r in con.execute("SELECT dead FROM snapshots WHERE tbl=? ORDER BY ts", (t,))] for t in tables}
    blockers = con.execute("SELECT ts, kind, pid, xact_age, query, slot FROM blockers ORDER BY ts DESC LIMIT 20").fetchall()
    con.close()
    colors = {"normal": "green", "vacuum-starved": "orange", "needs-rewrite": "red",
              "index-bloated": "red", "index-unused": "orange"}
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
