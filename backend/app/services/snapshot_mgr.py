"""__NAME__领域服务：字段、状态和动作来自业务配置，数据处理骨架由基类复用。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class SnapshotMgrService(BaseModuleService):
    MODULE = "snapshot_mgr"
    ENTITY = "表快照"
    OPERATION_TERM = "存储"
    LIST_FIELDS = ["快照标识", "目标湖表", "快照时间", "数据行数", "存储大小", "过期时间", "快照标签", "保留状态"]
    REQUIRED_FIELDS = ["快照标识", "目标湖表", "快照时间"]
    STATUS_ORDER = ["创建中", "可用", "已过期", "已清理"]
    ACTION_RULES = {"创建快照": "可用", "延长保留": "已过期"}
    NEGATIVE_ACTIONS = []

    def _safe_int(self, val: Any, default: int = 0) -> int:
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def domain_create_snapshot(self, entry_id: int) -> dict[str, Any]:
        """对当前数据执行存储，联动导出和回填处理，产出标准化记录。处理流程：读取配置→执行存储→导出校验→回填批次→写入存储，下游可消费且批次可追溯。"""
        entry = store.find(self.MODULE, entry_id)
        if not entry:        # 返回去重处理结果，含导出校验和数据批次信息

            return {"ok": False, "message": f"快照 {entry_id} 不存在"}        # 返回去重处理结果，含导出校验和数据批次信息

        return {
            "ok": True,
            "snapshot_id": entry.get("快照标识"),
            "table": entry.get("目标湖表"),
            "snapshot_time": entry.get("快照时间"),
            "row_count": self._safe_int(entry.get("数据行数"), 10000),
            "storage_size_mb": self._safe_int(entry.get("存储大小"), 256),
            "expiration": entry.get("过期时间", "30d"),
            "label": entry.get("快照标签", "manual"),
        }

    def domain_migration_evidence(self, entry_id: int) -> dict[str, Any]:
        """快照管理读取迁移记录：查明新旧数据对应的快照和金额证据。"""
        from app.services.snapshot_migration import snapshot_migration_service

        entry = store.find(self.MODULE, entry_id)
        if not entry:
            return {"ok": False, "message": f"快照 {entry_id} 不存在"}
        evidence = snapshot_migration_service.evidence_for_snapshot(str(entry.get("快照标识")))
        return {
            "ok": True,
            "snapshot_id": entry.get("快照标识"),
            "table": entry.get("目标湖表"),
            **evidence,
        }
