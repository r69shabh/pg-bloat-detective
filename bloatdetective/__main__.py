"""CLI: collect | analyze | report [--html --out]."""
import argparse
from .collector import collect
from .analyze import analyze
from .report import render, render_html

def main() -> None:
    p = argparse.ArgumentParser(prog="bloatdetective")
    p.add_argument("cmd", choices=["collect", "analyze", "report"])
    p.add_argument("--dsn", default="dbname=bloatdemo user=postgres password=postgres host=localhost port=5433")
    p.add_argument("--db", default="timeline.db")
    p.add_argument("--html", action="store_true")
    p.add_argument("--out", default="report.html")
    a = p.parse_args()
    if a.cmd == "collect":
        collect(a.dsn, a.db)
        print(f"snapshot saved to {a.db}")
    else:
        findings = analyze(a.db)
        if a.cmd == "analyze":
            for f in findings:
                print(f"{f['table']}: {f['verdict']} — {f['evidence']}")
        elif a.html:
            open(a.out, "w").write(render_html(a.db, findings))
            print(f"dashboard written to {a.out}")
        else:
            print(render(findings), end="")

if __name__ == "__main__":
    main()
