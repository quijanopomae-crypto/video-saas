from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_repo_map_routes_exist_and_preserve_the_product_boundary():
    repo_map = yaml.safe_load((ROOT / "REPO_MAP.yaml").read_text(encoding="utf-8"))

    assert repo_map["authority"] == "navigation_only"

    routes = repo_map["routes"]
    for route_name, route in routes.items():
        assert route["paths"], route_name
        for mapped_path in route["paths"]:
            assert (ROOT / mapped_path).exists(), f"{route_name}: {mapped_path}"

    assert routes["backend"] == {
        "paths": ["apps/api/src/"],
        "role": "canonical_product_backend",
    }
    assert routes["root_src"] == {
        "paths": ["src/"],
        "role": "baseline_validation_support",
        "canonical_product": False,
    }

    recovery = repo_map["state_recovery"]
    assert recovery["read_first"][:4] == [
        "AGENTS.md",
        "REPO_MAP.yaml",
        "PROJECT_STATE.yaml",
        ".state/CURRENT.json",
    ]
    assert recovery["active_task_contract"] == "tasks/{active_task_id}.yaml"
    assert recovery["active_task_condition"] == "active_task_id != null"
