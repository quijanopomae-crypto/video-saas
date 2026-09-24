from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from typing import Any, Literal

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

    @property
    def duration_sec(self) -> int:
        return self.end_sec - self.start_sec


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
    timeline: list[TimelineItem] = []
    found = False
    for item in project.timeline:
        if item.shot_id == shot_id:
            found = True
            if item.lock_state == "locked":
                raise ValueError("quality-locked shot must be unlocked before mutation")
            item = replace(item, asset_id=asset_id)
        timeline.append(item)
    if not found:
        raise ValueError("unknown shot")
    updated = replace(project, timeline=tuple(timeline))
    updated.validate()
    return updated


def set_quality_lock(project: VideoProject, shot_id: str, locked: bool) -> VideoProject:
    timeline: list[TimelineItem] = []
    found = False
    for item in project.timeline:
        if item.shot_id == shot_id:
            found = True
            item = replace(item, lock_state="locked" if locked else "unlocked")
        timeline.append(item)
    if not found:
        raise ValueError("unknown shot")
    updated = replace(project, timeline=tuple(timeline))
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
