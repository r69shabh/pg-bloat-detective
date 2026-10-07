"""Serve-loop entrypoint for the docker exporter service: pip-installs nothing, serves the mounted timeline.db."""
import os
from .exporter import serve

if __name__ == "__main__":
    serve([os.environ.get("BLOAT_DB", "/app/timeline.db")], int(os.environ.get("BLOAT_PORT", "9187")))