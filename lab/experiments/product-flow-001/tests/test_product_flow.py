from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from product_flow_lab import ProjectRequest, run_product_flow


class ProductFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        payload = json.loads((ROOT / "fixtures" / "project_request.json").read_text(encoding="utf-8"))
        self.request = ProjectRequest.from_dict(payload)
        self.flow = run_product_flow(self.request)

    def test_duration_is_conserved_exactly(self) -> None:
        self.assertEqual(sum(scene.duration_sec for scene in self.flow.scene_graph), self.request.duration_sec)
        self.assertEqual(sum(shot.duration_sec for shot in self.flow.shot_contracts), self.request.duration_sec)
        self.assertEqual(self.flow.preview_plan.total_duration_sec, self.request.duration_sec)

    def test_ids_are_unique_and_references_are_valid(self) -> None:
        scene_ids = {scene.scene_id for scene in self.flow.scene_graph}
        shot_ids = {shot.shot_id for shot in self.flow.shot_contracts}
        self.assertEqual(len(scene_ids), len(self.flow.scene_graph))
        self.assertEqual(len(shot_ids), len(self.flow.shot_contracts))
        for shot in self.flow.shot_contracts:
            self.assertIn(shot.scene_id, scene_ids)
            self.assertIn(shot.scene_id, shot.continuity_refs)
            self.assertIn(self.flow.project_bible.project_id, shot.continuity_refs)

    def test_preview_is_contiguous(self) -> None:
        cursor = 0
        for segment in self.flow.preview_plan.segments:
            self.assertEqual(segment.start_sec, cursor)
            self.assertGreater(segment.end_sec, segment.start_sec)
            cursor = segment.end_sec
        self.assertEqual(cursor, self.request.duration_sec)

    def test_same_input_produces_same_output(self) -> None:
        again = run_product_flow(self.request)
        self.assertEqual(self.flow.to_dict(), again.to_dict())

    def test_planning_is_provider_independent(self) -> None:
        serialized = json.dumps(self.flow.to_dict(), ensure_ascii=False).lower()
        forbidden = ["api_key", "token", "runway", "vidu", "veo", "openai"]
        self.assertTrue(all(item not in serialized for item in forbidden))


if __name__ == "__main__":
    unittest.main()
