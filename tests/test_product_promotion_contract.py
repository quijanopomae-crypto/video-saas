from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_product_promotion_contract_is_narrow_and_safe():
    project = yaml.safe_load((ROOT / "PROJECT_STATE.yaml").read_text(encoding="utf-8"))
    task = yaml.safe_load((ROOT / "tasks" / "TASK-PRODUCT-PROMOTE-001.yaml").read_text(encoding="utf-8"))

    assert project["product_promotion"]["task_id"] == "TASK-PRODUCT-PROMOTE-001"
    assert project["product_promotion"]["implementation_status"] == "PASS"
    assert project["provider_preflight_allowed"] is False
    assert project["paid_provider_requests_allowed"] is False
    assert task["approval"]["explicit_user_approval"] is True
    assert "apps/web/**" in task["scope"]["forbidden_paths"]
    assert "manifests/**" in task["scope"]["forbidden_paths"]
    assert "projectctl/**" in task["scope"]["forbidden_paths"]


def test_canonical_runtime_does_not_import_lab():
    offenders = []
    runtime_root = ROOT / "apps" / "api" / "src"
    for path in runtime_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "product_flow_lab" in text or "from lab" in text or "import lab" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
