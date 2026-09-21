from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SHA_REF = re.compile(r"uses:\s+[^\s#]+@([0-9a-f]{40})(?:\s+#\s+v\d+)?\s*$")


def test_all_external_actions_are_pinned_to_full_commit_sha():
    violations = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith("- uses:"):
                continue
            if "uses: ./" in stripped:
                continue
            if not SHA_REF.search(stripped):
                violations.append(f"{path.name}:{number}:{stripped}")
    assert violations == []


def test_product_ci_uses_locked_installs_and_production_server():
    workflow = (WORKFLOWS / "product-ci.yml").read_text(encoding="utf-8")
    assert "npm ci --no-audit --no-fund" in workflow
    assert "npm install --no-audit --no-fund" not in workflow
    assert "npm run build" in workflow
    assert "npm run start -- --hostname 127.0.0.1 --port 3000" in workflow
    assert "npm run dev" not in workflow
    assert "requirements.lock.txt" in workflow
    assert "WEB_PRODUCTION_TO_API_TO_POSTGRES_SMOKE_OK" in workflow
    assert "http://127.0.0.1:3000/api/ready" in workflow


def test_node_lockfile_is_versioned_and_consistent_with_package_manifest():
    package = json.loads((ROOT / "apps" / "web" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "apps" / "web" / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["lockfileVersion"] == 3
    assert lock["name"] == package["name"]
    assert lock["version"] == package["version"]
    root_package = lock["packages"][""]
    assert root_package["dependencies"] == package["dependencies"]
    assert root_package["devDependencies"] == package["devDependencies"]


def test_python_direct_and_resolved_dependencies_are_exactly_pinned():
    requirements = (ROOT / "apps" / "api" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    lock = (ROOT / "apps" / "api" / "requirements.lock.txt").read_text(encoding="utf-8").splitlines()

    direct = [line.strip() for line in requirements if line.strip() and not line.startswith("#")]
    resolved = [line.strip() for line in lock if line.strip() and not line.startswith("#")]

    assert direct
    assert resolved
    assert all("==" in line and ">=" not in line and "<" not in line for line in direct)
    assert all("==" in line for line in resolved)


def test_local_validation_uses_same_locked_install_strategy():
    script = (ROOT / "scripts" / "test.ps1").read_text(encoding="utf-8")
    assert "requirements.lock.txt" in script
    assert "npm ci --no-audit --no-fund" in script
    assert "npm install --no-audit --no-fund" not in script
