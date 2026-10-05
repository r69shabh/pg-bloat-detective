"""Prometheus exporter (stdlib only): serves the SQLite timeline + live verdicts on /metrics."""
from __future__ import annotations
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from .analyze import analyze, _age_secs

def collect_metrics(db_path: str) -> str:
    lines = []
    for f in analyze(db_path):
        t = f["table"]
        lines.append(f'pgbloat_dead_tuples{{table="{t}",verdict="{f["verdict"]}"}} {f["dead"]}')
        lines.append(f'pgbloat_live_tuples{{table="{t}"}} {f["live"]}')
    try:
        con = sqlite3.connect(db_path)
        for (t, pct) in con.execute("SELECT tbl, dead_pct FROM approx WHERE (tbl, ts) IN (SELECT tbl, max(ts) FROM approx GROUP BY tbl)"):
            lines.append(f'pgbloat_approx_dead_pct{{table="{t}"}} {pct}')
        for (kind, pid, age, q) in con.execute("SELECT kind, pid, xact_age, query FROM blockers ORDER BY ts DESC LIMIT 20"):
            secs = _age_secs(age or "")
            if secs >= 0:
                lines.append(f'pgbloat_xmin_holder_age_seconds{{kind="{kind}",pid="{pid}",query="{(q or "")[:60]}"}} {secs}')
        con.close()
    except Exception:
        pass
    return "\n".join(lines) + "\n"

def make_handler(db_path: str):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = collect_metrics(db_path).encode() if self.path == "/metrics" else b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a):
            pass
    return H

def serve(db_path: str, port: int = 9187) -> None:
    print(f"serving {db_path} on :{port}/metrics")
    HTTPServer(("0.0.0.0", port), make_handler(db_path)).serve_forever()
