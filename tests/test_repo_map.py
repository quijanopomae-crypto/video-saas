from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_repo_map_routes_exist_and_preserve_the_product_boundary():
    repo_map = yaml.safe_load((ROOT / "REPO_MAP.yaml").read_text(encoding="utf-8"))

    assert repo_map["authority"] == "navigation_only"

    expected_routes = {
        "backend": {
            "paths": ["apps/api/src/"],
            "role": "canonical_product_backend",
        },
        "frontend": {
            "paths": ["apps/web/src/"],
            "role": "canonical_product_frontend",
        },
        "control_plane": {
            "paths": ["projectctl/", "PROJECT_STATE.yaml", ".state/", "tasks/"],
            "role": "canonical_repository_control",
        },
        "laboratory": {
            "paths": ["lab/"],
            "role": "noncanonical_experimentation",
        },
        "tests": {
            "paths": [
                "tests/",
                "apps/api/tests/",
                "apps/web/tests/",
                "lab/experiments/product-flow-001/tests/",
            ],
            "role": "validation_by_boundary",
        },
        "manifests_evidence": {
            "paths": ["manifests/", "evidence/"],
            "role": "frozen_baseline_and_execution_proof",
        },
        "root_src": {
            "paths": ["src/"],
            "role": "baseline_validation_support",
            "canonical_product": False,
        },
    }

    routes = repo_map["routes"]
    assert routes == expected_routes
    for route_name, route in routes.items():
        for mapped_path in route["paths"]:
            assert (ROOT / mapped_path).exists(), f"{route_name}: {mapped_path}"

    recovery = repo_map["state_recovery"]
    assert recovery["read_first"][:4] == [
        "AGENTS.md",
        "REPO_MAP.yaml",
        "PROJECT_STATE.yaml",
        ".state/CURRENT.json",
    ]
    assert recovery["active_task_contract"] == "tasks/{active_task_id}.yaml"
    assert recovery["active_task_condition"] == "active_task_id != null"
