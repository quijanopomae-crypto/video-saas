from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from typing import Any, Callable, Literal

from ..planning import ProductFlow


AssetKind = Literal["image", "video", "audio", "subtitle", "other"]
QAStatus = Literal["pending", "pass", "fail"]
LockState = Literal["unlocked", "locked"]


@dataclass(frozen=True)
class AssetRecord:
    asset_id: str
    shot_id: str
    kind: AssetKind
    uri: str
    source: str
    source_ref: str | None = None
    version: int = 1
    cost_usd: str = "0.00"

    def validate(self, shot_ids: set[str]) -> None:
        if self.shot_id not in shot_ids:
            raise ValueError("asset references unknown shot")
        if not self.asset_id or not self.uri or not self.source:
            raise ValueError("asset identity, uri and source are required")
        if self.version < 1:
            raise ValueError("asset version must be positive")
        if Decimal(self.cost_usd) < 0:
            raise ValueError("asset cost cannot be negative")


@dataclass(frozen=True)
class QAFinding:
    finding_id: str
    shot_id: str
    status: QAStatus
    code: str
    message: str
    patch_intent: str | None = None


@dataclass(frozen=True)
class TimelineItem:
    shot_id: str
    start_sec: int
    end_sec: int
    asset_id: str | None = None
    lock_state: LockState = "unlocked"
    clip_in_sec: int = 0
    clip_out_sec: int | None = None
    caption_text: str | None = None
    overlay_x: float | None = None
    overlay_y: float | None = None
    patch_intent: str | None = None

    @property
    def duration_sec(self) -> int:
        return self.end_sec - self.start_sec

    def validate_edit_state(self) -> None:
        effective_out = self.duration_sec if self.clip_out_sec is None else self.clip_out_sec
        if self.clip_in_sec < 0 or effective_out <= self.clip_in_sec or effective_out > self.duration_sec:
            raise ValueError("clip trim must remain inside shot duration")
        if (self.overlay_x is None) != (self.overlay_y is None):
            raise ValueError("overlay position requires both x and y")
        if self.overlay_x is not None and not (0.0 <= self.overlay_x <= 1.0 and 0.0 <= self.overlay_y <= 1.0):
            raise ValueError("overlay position must be normalized between 0 and 1")


@dataclass(frozen=True)
class VideoProject:
    project_id: str
    planning: dict[str, Any]
    timeline: tuple[TimelineItem, ...]
    assets: tuple[AssetRecord, ...] = ()
    qa_findings: tuple[QAFinding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def total_cost_usd(self) -> Decimal:
        return sum((Decimal(asset.cost_usd) for asset in self.assets), Decimal("0.00"))

    def validate(self) -> None:
        shot_ids = {item.shot_id for item in self.timeline}
        if len(shot_ids) != len(self.timeline):
            raise ValueError("timeline shot ids must be unique")
        cursor = 0
        for item in self.timeline:
            if item.start_sec != cursor or item.end_sec <= item.start_sec:
                raise ValueError("timeline must be positive and contiguous")
            item.validate_edit_state()
            cursor = item.end_sec
        for asset in self.assets:
            asset.validate(shot_ids)
        asset_ids = {asset.asset_id for asset in self.assets}
        if len(asset_ids) != len(self.assets):
            raise ValueError("asset ids must be unique")
        for item in self.timeline:
            if item.asset_id is not None and item.asset_id not in asset_ids:
                raise ValueError("timeline references unknown asset")
        for finding in self.qa_findings:
            if finding.shot_id not in shot_ids:
                raise ValueError("QA finding references unknown shot")


def from_product_flow(flow: ProductFlow) -> VideoProject:
    timeline = tuple(
        TimelineItem(
            shot_id=segment.shot_id,
            start_sec=segment.start_sec,
            end_sec=segment.end_sec,
        )
        for segment in flow.preview_plan.segments
    )
    project = VideoProject(
        project_id=flow.project_bible.project_id,
        planning=flow.to_dict(),
        timeline=timeline,
    )
    project.validate()
    return project


def _mutate_shot(
    project: VideoProject,
    shot_id: str,
    operation: Callable[[TimelineItem], TimelineItem],
    *,
    allow_locked: bool = False,
) -> VideoProject:
    project.validate()
    timeline: list[TimelineItem] = []
    found = False
    for item in project.timeline:
        if item.shot_id == shot_id:
            found = True
            if item.lock_state == "locked" and not allow_locked:
                raise ValueError("quality-locked shot must be unlocked before mutation")
            item = operation(item)
        timeline.append(item)
    if not found:
        raise ValueError("unknown shot")
    updated = replace(project, timeline=tuple(timeline))
    updated.validate()
    return updated


def _shot_ids_for_scene(project: VideoProject, scene_id: str) -> tuple[str, ...]:
    contracts = project.planning.get("shot_contracts") or []
    shot_ids = tuple(
        item["shot_id"]
        for item in contracts
        if isinstance(item, dict) and item.get("scene_id") == scene_id and item.get("shot_id")
    )
    if not shot_ids:
        raise ValueError("unknown scene")
    return shot_ids


def attach_asset(project: VideoProject, asset: AssetRecord) -> VideoProject:
    project.validate()
    shot_ids = {item.shot_id for item in project.timeline}
    asset.validate(shot_ids)
    if any(existing.asset_id == asset.asset_id for existing in project.assets):
        raise ValueError("asset id already exists")
    updated = replace(project, assets=project.assets + (asset,))
    updated.validate()
    return updated


def select_asset(project: VideoProject, shot_id: str, asset_id: str) -> VideoProject:
    project.validate()
    asset = next((item for item in project.assets if item.asset_id == asset_id), None)
    if asset is None or asset.shot_id != shot_id:
        raise ValueError("asset is not available for shot")
    return _mutate_shot(project, shot_id, lambda item: replace(item, asset_id=asset_id))


def replace_asset(project: VideoProject, shot_id: str, asset_id: str) -> VideoProject:
    return select_asset(project, shot_id, asset_id)


def trim_clip(project: VideoProject, shot_id: str, clip_in_sec: int, clip_out_sec: int) -> VideoProject:
    if type(clip_in_sec) is not int or type(clip_out_sec) is not int:
        raise TypeError("clip trim values must be integers")
    return _mutate_shot(
        project,
        shot_id,
        lambda item: replace(item, clip_in_sec=clip_in_sec, clip_out_sec=clip_out_sec),
    )


def move_overlay(project: VideoProject, shot_id: str, x: float, y: float) -> VideoProject:
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise TypeError("overlay coordinates must be numbers")
    return _mutate_shot(project, shot_id, lambda item: replace(item, overlay_x=float(x), overlay_y=float(y)))


def change_caption(project: VideoProject, shot_id: str, caption: str) -> VideoProject:
    if not isinstance(caption, str):
        raise TypeError("caption must be a string")
    normalized = caption.strip()
    if not normalized or len(normalized) > 2000:
        raise ValueError("caption must be between 1 and 2000 characters")
    return _mutate_shot(project, shot_id, lambda item: replace(item, caption_text=normalized))


def patch_scene(project: VideoProject, scene_id: str, patch_intent: str) -> VideoProject:
    if not isinstance(patch_intent, str):
        raise TypeError("patch_intent must be a string")
    normalized = patch_intent.strip()
    if not normalized:
        raise ValueError("patch_intent is required")
    project.validate()
    shot_ids = set(_shot_ids_for_scene(project, scene_id))
    if any(item.shot_id in shot_ids and item.lock_state == "locked" for item in project.timeline):
        raise ValueError("quality-locked scene must be unlocked before mutation")
    timeline = tuple(
        replace(item, patch_intent=normalized) if item.shot_id in shot_ids else item
        for item in project.timeline
    )
    updated = replace(project, timeline=timeline)
    updated.validate()
    return updated


def set_quality_lock(project: VideoProject, shot_id: str, locked: bool) -> VideoProject:
    return _mutate_shot(
        project,
        shot_id,
        lambda item: replace(item, lock_state="locked" if locked else "unlocked"),
        allow_locked=True,
    )


def lock_scene(project: VideoProject, scene_id: str) -> VideoProject:
    shot_ids = set(_shot_ids_for_scene(project, scene_id))
    timeline = tuple(
        replace(item, lock_state="locked") if item.shot_id in shot_ids else item
        for item in project.timeline
    )
    updated = replace(project, timeline=timeline)
    updated.validate()
    return updated


def unlock_scene(project: VideoProject, scene_id: str) -> VideoProject:
    shot_ids = set(_shot_ids_for_scene(project, scene_id))
    timeline = tuple(
        replace(item, lock_state="unlocked") if item.shot_id in shot_ids else item
        for item in project.timeline
    )
    updated = replace(project, timeline=timeline)
    updated.validate()
    return updated


def add_qa_finding(project: VideoProject, finding: QAFinding) -> VideoProject:
    project.validate()
    if finding.shot_id not in {item.shot_id for item in project.timeline}:
        raise ValueError("QA finding references unknown shot")
    if any(item.finding_id == finding.finding_id for item in project.qa_findings):
        raise ValueError("QA finding id already exists")
    updated = replace(project, qa_findings=project.qa_findings + (finding,))
    updated.validate()
    return updated
