"""Prometheus exporter (stdlib only): serves SQLite timelines + live verdicts on /metrics."""
from __future__ import annotations
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from .analyze import analyze, _age_secs

def _label(path: str, multi: bool) -> str:
    return f'db="{os.path.splitext(os.path.basename(path))[0]}",' if multi else ""

def collect_metrics(db_path: str, label: str = "") -> str:
    lines = []
    for f in analyze(db_path):
        t = f["table"]
        lines.append(f'pgbloat_dead_tuples{{{label}table="{t}",verdict="{f["verdict"]}"}} {f["dead"]}')
        lines.append(f'pgbloat_live_tuples{{{label}table="{t}"}} {f["live"]}')
    try:
        con = sqlite3.connect(db_path)
        try:
            for (t, pct) in con.execute("SELECT tbl, dead_pct FROM approx WHERE tbl IS NOT NULL AND (tbl, ts) IN (SELECT tbl, max(ts) FROM approx WHERE tbl IS NOT NULL GROUP BY tbl)"):
                lines.append(f'pgbloat_approx_dead_pct{{{label}table="{t}"}} {pct}')
        except Exception:
            pass
        try:
            for (idx, pct) in con.execute("SELECT idx, idx_bloat_pct FROM approx WHERE idx IS NOT NULL AND idx_bloat_pct IS NOT NULL AND (idx, ts) IN (SELECT idx, max(ts) FROM approx WHERE idx IS NOT NULL GROUP BY idx)"):
                lines.append(f'pgbloat_index_bloat_pct{{{label}index="{idx}"}} {pct}')
        except Exception:
            pass
        try:
            for (idx, tbl, scans) in con.execute('SELECT idx, tbl, scans FROM index_stats WHERE (idx, ts) IN (SELECT idx, max(ts) FROM index_stats GROUP BY idx)'):
                lines.append(f'pgbloat_index_scans{{{label}index="{idx}",table="{tbl}"}} {scans or 0}')
        except Exception:
            pass  # old DBs without index_stats keep serving heap metrics
        for (kind, pid, age, q) in con.execute("SELECT kind, pid, xact_age, query FROM blockers ORDER BY ts DESC LIMIT 20"):
            secs = _age_secs(age or "")
            if secs >= 0:
                lines.append(f'pgbloat_xmin_holder_age_seconds{{{label}kind="{kind}",pid="{pid}",query="{(q or "")[:60]}"}} {secs}')
        con.close()
    except Exception:
        pass
    return "\n".join(lines) + "\n"

def collect_all(db_paths: list[str]) -> str:
    multi = len(db_paths) > 1
    return "".join(collect_metrics(p, _label(p, multi)) for p in db_paths)

def make_handler(db_paths):
    paths = [db_paths] if isinstance(db_paths, str) else list(db_paths)
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = collect_all(paths).encode() if self.path == "/metrics" else b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a):
            pass
    return H

def serve(db_paths, port: int = 9187) -> None:
    paths = [db_paths] if isinstance(db_paths, str) else list(db_paths)
    print(f"serving {paths} on :{port}/metrics")
    HTTPServer(("0.0.0.0", port), make_handler(paths)).serve_forever()
