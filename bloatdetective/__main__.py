"""CLI: collect | analyze | report [--html|--json --out] | serve [--port]."""
import argparse
import json
from .collector import collect
from .analyze import analyze
from .report import render, render_html, export_json
from .exporter import serve

def main() -> None:
    p = argparse.ArgumentParser(prog="bloatdetective")
    p.add_argument("cmd", choices=["collect", "analyze", "report", "serve"])
    p.add_argument("--dsn", default="dbname=bloatdemo user=postgres password=postgres host=localhost port=5433")
    p.add_argument("--db", default=None, action="append")  # repeat for multi-DB serve: --db a.db --db b.db
    p.add_argument("--html", action="store_true")
    p.add_argument("--json", action="store_true")  # data feed for dashboard/: --out data.json
    p.add_argument("--out", default="report.html")
    p.add_argument("--port", type=int, default=9187)
    a = p.parse_args()
    dbs = a.db or ["timeline.db"]
    if a.cmd == "collect":
        collect(a.dsn, dbs[0])
        print(f"snapshot saved to {dbs[0]}")
    elif a.cmd == "serve":
        serve(dbs, a.port)
    else:
        findings = analyze(dbs[0])
        if a.cmd == "analyze":
            for f in findings:
                print(f"{f['table']}: {f['verdict']} — {f['evidence']}")
        elif a.html:
            open(a.out, "w").write(render_html(dbs[0], findings))
            print(f"dashboard written to {a.out}")
        elif a.json:
            open(a.out, "w").write(json.dumps(export_json(dbs[0], findings)))
            print(f"data written to {a.out}")
        else:
            print(render(findings), end="")

if __name__ == "__main__":
    main()
