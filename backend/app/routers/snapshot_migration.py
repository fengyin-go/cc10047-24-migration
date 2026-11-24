"""快照字段迁移接口：登记、生产重演、迁移确认、双格式读取、审计清单和更正查询。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.snapshot_migration import snapshot_migration_service

router = APIRouter(prefix="/api/snapshot-migrations", tags=["快照字段迁移"])


class MigrationPayload(BaseModel):
    snapshot_key: str
    table: str
    amount_cents: Any
    deploy_deps: str
    db_compat: str
    migration_key: str | None = None


class CorrectionPayload(BaseModel):
    corrected_cents: Any
    source: str
    correction_key: str | None = None


class ConfirmPayload(BaseModel):
    confirm_no: str | None = None


@router.get("")
def list_migrations() -> dict[str, Any]:
    """快照管理读取迁移记录：查明新旧数据对应的快照和金额证据。"""
    return snapshot_migration_service.list_migrations()


@router.post("")
def register_migration(payload: MigrationPayload) -> dict[str, Any]:
    """登记快照字段迁移记录：上线依赖和数据库兼容范围一并保存。"""
    return snapshot_migration_service.register_migration(
        snapshot_key=payload.snapshot_key,
        table=payload.table,
        amount_cents=payload.amount_cents,
        deploy_deps=payload.deploy_deps,
        db_compat=payload.db_compat,
        migration_key=payload.migration_key,
    )


@router.get("/audit-checklist")
def audit_checklist() -> dict[str, Any]:
    """快照审计清单：迁移确认结果。"""
    return snapshot_migration_service.audit_checklist()


@router.get("/corrections")
def corrections(status: str | None = Query(default=None)) -> dict[str, Any]:
    """更正查询入口：可查原值、换算版本和待处理更正。"""
    return snapshot_migration_service.corrections_view(status=status)


@router.get("/{migration_id}")
def get_migration(migration_id: int) -> dict[str, Any]:
    """快照详情：区分原值、候选新值和本次允许采用的金额。"""
    return snapshot_migration_service.get_migration(migration_id)


@router.post("/{migration_id}/replay")
def replay_migration(migration_id: int) -> dict[str, Any]:
    """上线切换前在生产环境重演历史快照。"""
    return snapshot_migration_service.replay(migration_id)


@router.post("/{migration_id}/pause")
def pause_migration(migration_id: int) -> dict[str, Any]:
    """停在迁移确认前。"""
    return snapshot_migration_service.pause(migration_id)


@router.post("/{migration_id}/resume")
def resume_migration(migration_id: int) -> dict[str, Any]:
    """恢复迁移确认。"""
    return snapshot_migration_service.resume(migration_id)


@router.post("/{migration_id}/corrections")
def submit_correction(migration_id: int, payload: CorrectionPayload) -> dict[str, Any]:
    """补报更正：原值和更正来源都留存。"""
    return snapshot_migration_service.submit_correction(
        migration_id,
        corrected_cents=payload.corrected_cents,
        source=payload.source,
        correction_key=payload.correction_key,
    )


@router.post("/{migration_id}/confirm")
def confirm_migration(migration_id: int, payload: ConfirmPayload | None = None) -> dict[str, Any]:
    """迁移确认（幂等）：结果同步到快照审计清单。"""
    confirm_no = payload.confirm_no if payload else None
    return snapshot_migration_service.confirm(migration_id, confirm_no=confirm_no)


@router.get("/{migration_id}/read")
def read_snapshot(
    migration_id: int,
    format: str = Query(default="cents"),
) -> dict[str, Any]:
    """双格式读取：旧快照按分读取，新读者用已发布的元及换算版本。"""
    return snapshot_migration_service.read_snapshot(migration_id, format)
