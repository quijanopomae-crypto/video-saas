from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.modules.planning import ProjectRequest, run_product_flow


PAYLOAD = {
    "title": "Como funciona una fabrica multimodelo de video",
    "idea": "Explicar de forma visual como una solicitud se convierte en escenas, shots y un video final coordinando diferentes capacidades.",
    "duration_sec": 60,
    "aspect_ratio": "16:9",
    "audience": "creadores y equipos de producto",
    "tone": "claro y tecnologico",
    "language": "es",
}


def _flow():
    return run_product_flow(ProjectRequest.from_dict(PAYLOAD))


def test_duration_is_conserved_exactly() -> None:
    flow = _flow()
    assert sum(scene.duration_sec for scene in flow.scene_graph) == 60
    assert sum(shot.duration_sec for shot in flow.shot_contracts) == 60
    assert flow.preview_plan.total_duration_sec == 60


def test_ids_are_unique_and_references_are_valid() -> None:
    flow = _flow()
    scene_ids = {scene.scene_id for scene in flow.scene_graph}
    shot_ids = {shot.shot_id for shot in flow.shot_contracts}
    assert len(scene_ids) == len(flow.scene_graph)
    assert len(shot_ids) == len(flow.shot_contracts)
    for shot in flow.shot_contracts:
        assert shot.scene_id in scene_ids
        assert shot.scene_id in shot.continuity_refs
        assert flow.project_bible.project_id in shot.continuity_refs


def test_preview_is_contiguous() -> None:
    flow = _flow()
    cursor = 0
    for segment in flow.preview_plan.segments:
        assert segment.start_sec == cursor
        assert segment.end_sec > segment.start_sec
        cursor = segment.end_sec
    assert cursor == 60


def test_same_input_produces_same_output() -> None:
    assert _flow().to_dict() == _flow().to_dict()


def test_planning_is_provider_independent_and_lab_free() -> None:
    flow_text = json.dumps(_flow().to_dict(), ensure_ascii=False).lower()
    forbidden = ["api_key", "token", "runway", "vidu", "veo", "openai"]
    assert all(item not in flow_text for item in forbidden)

    module_root = Path(__file__).resolve().parents[1] / "src" / "modules" / "planning"
    source = "\n".join(path.read_text(encoding="utf-8") for path in module_root.glob("*.py"))
    assert "product_flow_lab" not in source
    assert "from lab" not in source
    assert "import lab" not in source


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({**PAYLOAD, "title": " "}, "title is required"),
        ({**PAYLOAD, "idea": " "}, "idea is required"),
        ({**PAYLOAD, "duration_sec": 4}, "duration_sec must be between 5 and 600"),
        ({**PAYLOAD, "aspect_ratio": "4:3"}, "unsupported aspect_ratio"),
    ],
)
def test_invalid_requests_are_rejected(payload: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ProjectRequest.from_dict(payload)
