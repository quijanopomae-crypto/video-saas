from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "apps/api/src/main.py",
    "apps/api/src/core/config.py",
    "apps/api/src/core/db.py",
    "apps/api/src/adapters/storage.py",
    "apps/api/src/adapters/queue.py",
    "apps/api/src/adapters/workflow.py",
    "apps/api/src/workers/render.py",
    "apps/api/alembic.ini",
    "apps/api/migrations/versions/0001_infra_meta.py",
    "apps/web/package.json",
    "apps/web/src/app/page.tsx",
    "apps/web/src/app/api/health/route.ts",
    "apps/web/src/features/system-health/HealthCard.tsx",
    ".github/workflows/product-ci.yml",
    "docker-compose.yml",
    ".env.example",
    "scripts/dev.ps1",
    "scripts/test.ps1",
]

def test_required_development_infrastructure_files_exist():
    missing = [path for path in REQUIRED if not (ROOT / path).exists()]
    assert not missing, missing

def test_provider_operations_remain_disabled():
    state = yaml.safe_load((ROOT / "PROJECT_STATE.yaml").read_text(encoding="utf-8"))
    assert state["provider_preflight_allowed"] is False
    assert state["paid_provider_requests_allowed"] is False

def test_root_business_src_is_not_repurposed():
    state = yaml.safe_load((ROOT / "PROJECT_STATE.yaml").read_text(encoding="utf-8"))
    assert state["repository_control_plane"]["root_business_src"] == "FORBIDDEN"
    assert (ROOT / "src").exists()

def test_frontend_has_pinned_framework_versions():
    pkg = json.loads((ROOT / "apps/web/package.json").read_text(encoding="utf-8"))
    assert pkg["dependencies"]["next"] == "16.3.5"
    assert pkg["dependencies"]["react"] == "19.3.0"

def test_env_example_contains_no_provider_credentials():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    forbidden = ["OPENAI_API_KEY", "RUNWAY_API_KEY", "VIDU_API_KEY", "GOOGLE_API_KEY", "CLOUDFLARE_API_TOKEN"]
    assert all(name not in text for name in forbidden)
