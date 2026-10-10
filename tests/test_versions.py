"""Release-metadata drift guard: the v0.1.4 failure mode (tag != pyproject)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from check_versions import check  # noqa: E402


def test_repo_metadata_is_consistent():
    assert check() == []


def test_tag_mismatch_is_caught():
    assert any("tag v9.9.9" in e for e in check("v9.9.9"))


def test_matching_tag_passes():
    import tomllib
    v = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert check(f"v{v}") == []


def test_script_exits_nonzero_on_bad_tag():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_versions.py"), "v9.9.9"],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "FAIL" in r.stdout


def test_server_json_matches_pyproject():
    import tomllib
    py = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    srv = json.loads((ROOT / "server.json").read_text())
    assert srv["version"] == py
