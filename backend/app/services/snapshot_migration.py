"""快照字段迁移领域服务：历史快照金额字段 amount_cents → amount_decimal。

业务规则：
- 迁移记录登记上线依赖和数据库兼容范围，保存为快照字段迁移记录，全程可查；
- 上线切换前在生产环境重演历史快照：旧快照仍按原来的分读取，
  新读者使用实际发布的元及换算版本；
- 迁移确认结果同步到快照审计清单；更正查询入口可查原值、换算版本和待处理更正；
- 旧格式发生更正时原值和更正来源都留存；并发确认与断线恢复幂等：
  一笔更正不会被算两次，也不会覆盖已发布的历史读取口径。
"""
from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.store import store

MIGRATION_TABLE = "snapshot_field_migration"
CORRECTION_TABLE = "snapshot_correction"
CHECKLIST_TABLE = "snapshot_audit_checklist"

STATUS_ORDER = ["已登记", "待确认", "已发布"]
CONVERSION_RULE = "amount_cents ÷ 100 → amount_decimal（保留2位小数）"


def to_decimal_yuan(cents: Any) -> str:
    """分 → 元，固定两位小数，返回字符串避免浮点误差。"""
    return str((Decimal(int(cents)) / Decimal(100)).quantize(Decimal("0.01")))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _bump_version(version: Any) -> str:
    """换算版本递进：v1 → v2；无法解析时追加修订号。"""
    head, sep, tail = str(version).rpartition("v")
    if sep and tail.isdigit():
        return f"{head}v{int(tail) + 1}"
    return f"{version}-r2"


class SnapshotMigrationService:
    """快照字段迁移引擎：登记 → 生产重演 →（暂停/恢复）→ 迁移确认 → 双格式读取。"""

    def __init__(self) -> None:
        # 确认与更正采用必须串行，保证并发确认不会把一笔更正算两次。
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 表句柄
    # ------------------------------------------------------------------
    def _migrations(self) -> list[dict[str, Any]]:
        return store.rows(MIGRATION_TABLE)

    def _corrections(self) -> list[dict[str, Any]]:
        return store.rows(CORRECTION_TABLE)

    def _checklist(self) -> list[dict[str, Any]]:
        return store.rows(CHECKLIST_TABLE)

    def _find(self, migration_id: int) -> dict[str, Any] | None:
        for row in self._migrations():
            if int(row.get("id", 0)) == migration_id:
                return row
        return None

    def _pending_corrections(self, migration_key: str) -> list[dict[str, Any]]:
        return [
            corr for corr in self._corrections()
            if corr.get("迁移标识") == migration_key and corr.get("status") == "待处理"
        ]

    def _corrections_of(self, migration_key: str) -> list[dict[str, Any]]:
        return [corr for corr in self._corrections() if corr.get("迁移标识") == migration_key]

    # ------------------------------------------------------------------
    # 视图组装
    # ------------------------------------------------------------------
    def _detail(self, mig: dict[str, Any]) -> dict[str, Any]:
        """快照详情：区分原值、候选新值和本次允许采用的金额。"""
        pending = self._pending_corrections(mig["迁移标识"])
        candidate = pending[-1] if pending else None
        published = mig.get("status") == "已发布"
        adopt_cents = int(candidate["更正值分"]) if candidate else int(mig["原值分"])
        return {
            **mig,
            "原值元": to_decimal_yuan(mig["原值分"]),
            "候选新值分": int(candidate["更正值分"]) if candidate else None,
            "候选新值元": to_decimal_yuan(candidate["更正值分"]) if candidate else None,
            "本次允许采用分": int(mig["已发布分"]) if published else adopt_cents,
            "本次允许采用元": mig["已发布元"] if published else to_decimal_yuan(adopt_cents),
            "待处理更正数": len(pending),
            "重演次数": len(mig.get("重演证据", [])),
            "更正记录": [dict(corr) for corr in self._corrections_of(mig["迁移标识"])],
        }

    # ------------------------------------------------------------------
    # 登记迁移记录
    # ------------------------------------------------------------------
    def register_migration(
        self,
        *,
        snapshot_key: str,
        table: str,
        amount_cents: Any,
        deploy_deps: str,
        db_compat: str,
        migration_key: str | None = None,
        base_version: str = "v1",
    ) -> dict[str, Any]:
        """登记快照字段迁移记录：上线依赖和数据库兼容范围一并保存。"""
        snapshot_key = str(snapshot_key or "").strip()
        table = str(table or "").strip()
        deploy_deps = str(deploy_deps or "").strip()
        db_compat = str(db_compat or "").strip()
        if not snapshot_key or not table:
            return {"ok": False, "message": "快照标识和目标湖表不能为空"}
        try:
            cents = int(amount_cents)
        except (TypeError, ValueError):
            return {"ok": False, "message": "原值分必须是非负整数"}
        if cents < 0:
            return {"ok": False, "message": "原值分必须是非负整数"}
        if not deploy_deps or not db_compat:
            return {"ok": False, "message": "必须登记上线依赖和数据库兼容范围"}
        key = (migration_key or f"MIG-{snapshot_key}").strip()
        with self._lock:
            if any(row.get("迁移标识") == key for row in self._migrations()):
                return {"ok": False, "message": f"迁移标识 {key} 已存在"}
            if any(row.get("快照标识") == snapshot_key for row in self._migrations()):
                return {"ok": False, "message": f"快照 {snapshot_key} 已登记迁移记录"}
            row = {
                "id": max((int(r.get("id", 0)) for r in self._migrations()), default=0) + 1,
                "迁移标识": key,
                "快照标识": snapshot_key,
                "目标湖表": table,
                "源字段": "amount_cents",
                "目标字段": "amount_decimal",
                "原值分": cents,
                "初始换算版本": base_version,
                "换算版本": base_version,
                "换算规则": CONVERSION_RULE,
                "上线依赖": deploy_deps,
                "数据库兼容范围": db_compat,
                "status": "已登记",
                "已暂停确认": False,
                "已发布分": None,
                "已发布元": None,
                "更正次数": 0,
                "确认单号": None,
                "确认时间": None,
                "重演证据": [],
            }
            self._migrations().append(row)
        return {"ok": True, "message": "快照字段迁移记录已登记", "migration": self._detail(row)}

    def list_migrations(self) -> dict[str, Any]:
        """快照管理读取迁移记录：列出全部迁移记录及金额对应关系。"""
        items = [self._detail(row) for row in self._migrations()]
        return {"ok": True, "items": items, "total": len(items)}

    def get_migration(self, migration_id: int) -> dict[str, Any]:
        mig = self._find(migration_id)
        if mig is None:
            return {"ok": False, "message": f"迁移记录 {migration_id} 不存在"}
        return {"ok": True, "migration": self._detail(mig)}

    # ------------------------------------------------------------------
    # 生产环境重演
    # ------------------------------------------------------------------
    def replay(self, migration_id: int) -> dict[str, Any]:
        """上线切换前在生产环境重演历史快照，产出新旧数据对应的金额证据。

        原快照可随时重演：重演只追加证据，不改动已发布的历史读取口径。
        """
        with self._lock:
            mig = self._find(migration_id)
            if mig is None:
                return {"ok": False, "message": f"迁移记录 {migration_id} 不存在"}
            evidence = {
                "重演序号": len(mig.setdefault("重演证据", [])) + 1,
                "环境": "生产预演",
                "快照标识": mig["快照标识"],
                "目标湖表": mig["目标湖表"],
                "源字段": mig["源字段"],
                "目标字段": mig["目标字段"],
                "原值分": int(mig["原值分"]),
                "换算后元": to_decimal_yuan(mig["原值分"]),
                "换算版本": mig["初始换算版本"],
                "重演时间": _now(),
            }
            mig["重演证据"].append(evidence)
            if mig["status"] == "已登记":
                mig["status"] = "待确认"
            return {
                "ok": True,
                "message": "历史快照已在生产环境重演，旧快照仍按分读取",
                "evidence": evidence,
                "migration": self._detail(mig),
            }

    # ------------------------------------------------------------------
    # 暂停 / 恢复（停在迁移确认前，补报更正后再恢复）
    # ------------------------------------------------------------------
    def pause(self, migration_id: int) -> dict[str, Any]:
        mig = self._find(migration_id)
        if mig is None:
            return {"ok": False, "message": f"迁移记录 {migration_id} 不存在"}
        if mig.get("status") != "待确认":
            return {"ok": False, "message": "只有待确认状态可以停在迁移确认前"}
        mig["已暂停确认"] = True
        return {"ok": True, "message": "已停在迁移确认前，可补报更正", "migration": self._detail(mig)}

    def resume(self, migration_id: int) -> dict[str, Any]:
        mig = self._find(migration_id)
        if mig is None:
            return {"ok": False, "message": f"迁移记录 {migration_id} 不存在"}
        if not mig.get("已暂停确认"):
            return {"ok": False, "message": "迁移确认未处于暂停状态"}
        mig["已暂停确认"] = False
        return {"ok": True, "message": "已恢复，可执行迁移确认", "migration": self._detail(mig)}

    # ------------------------------------------------------------------
    # 补报更正（旧格式更正：原值和更正来源都留存）
    # ------------------------------------------------------------------
    def submit_correction(
        self,
        migration_id: int,
        *,
        corrected_cents: Any,
        source: str,
        correction_key: str | None = None,
    ) -> dict[str, Any]:
        mig = self._find(migration_id)
        if mig is None:
            return {"ok": False, "message": f"迁移记录 {migration_id} 不存在"}
        try:
            cents = int(corrected_cents)
        except (TypeError, ValueError):
            return {"ok": False, "message": "更正值分必须是非负整数"}
        if cents < 0:
            return {"ok": False, "message": "更正值分必须是非负整数"}
        source = str(source or "").strip()
        if not source:
            return {"ok": False, "message": "更正来源不能为空"}
        # 未提供更正标识时按内容派生确定性标识：同一笔更正重试会被幂等去重。
        if correction_key and correction_key.strip():
            key = correction_key.strip()
        else:
            digest = hashlib.md5(
                f"{mig['迁移标识']}|{cents}|{source}".encode()
            ).hexdigest()[:8]
            key = f"CORR-{mig['迁移标识']}-{digest}"
        with self._lock:
            for corr in self._corrections():
                if corr.get("更正标识") == key:
                    return {
                        "ok": True,
                        "deduplicated": True,
                        "message": "更正已登记，幂等去重不重复计数",
                        "correction": dict(corr),
                        "migration": self._detail(mig),
                    }
            correction = {
                "id": max((int(c.get("id", 0)) for c in self._corrections()), default=0) + 1,
                "更正标识": key,
                "迁移标识": mig["迁移标识"],
                "快照标识": mig["快照标识"],
                "原值分": int(mig["原值分"]),
                "原值元": to_decimal_yuan(mig["原值分"]),
                "更正值分": cents,
                "换算后元": to_decimal_yuan(cents),
                "更正来源": source,
                "status": "待处理",
                "补报时间": _now(),
                "采用时间": None,
            }
            self._corrections().append(correction)
        if mig.get("status") == "已发布":
            message = "迁移已发布：更正留存原值与更正来源，不覆盖已发布的历史读取口径"
        else:
            message = "更正在正式发布前补报，迁移确认时作为候选新值采用"
        return {
            "ok": True,
            "deduplicated": False,
            "message": message,
            "correction": dict(correction),
            "migration": self._detail(mig),
        }

    # ------------------------------------------------------------------
    # 迁移确认（幂等）→ 同步快照审计清单
    # ------------------------------------------------------------------
    def confirm(self, migration_id: int, *, confirm_no: str | None = None) -> dict[str, Any]:
        with self._lock:
            mig = self._find(migration_id)
            if mig is None:
                return {"ok": False, "message": f"迁移记录 {migration_id} 不存在"}
            if mig.get("status") == "已发布":
                # 并发确认 / 断线恢复重试：直接返回已发布口径，
                # 不重复采用更正、不重复计数、不覆盖已发布口径。
                return {
                    "ok": True,
                    "idempotent": True,
                    "message": "迁移已确认，重试返回已发布口径，不产生重复变更",
                    "migration": self._detail(mig),
                }
            if mig.get("已暂停确认"):
                return {"ok": False, "message": "迁移确认已暂停，请先恢复再确认"}
            if mig.get("status") != "待确认":
                return {"ok": False, "message": "请先完成生产环境重演再执行迁移确认"}
            pending = self._pending_corrections(mig["迁移标识"])
            adopted_candidate: dict[str, Any] | None = None
            if pending:
                adopted_candidate = pending[-1]
                for corr in pending:
                    corr["status"] = "已采用"
                    corr["采用时间"] = _now()
                mig["更正次数"] = int(mig.get("更正次数", 0)) + len(pending)
                mig["已发布分"] = int(adopted_candidate["更正值分"])
                mig["换算版本"] = _bump_version(mig["换算版本"])
            else:
                mig["已发布分"] = int(mig["原值分"])
            mig["已发布元"] = to_decimal_yuan(mig["已发布分"])
            mig["status"] = "已发布"
            mig["确认单号"] = (confirm_no or f"CONF-{mig['迁移标识']}").strip()
            mig["确认时间"] = _now()
            audit_entry = self._sync_checklist(mig, adopted_candidate)
            return {
                "ok": True,
                "idempotent": False,
                "message": "迁移确认完成，结果已同步到快照审计清单",
                "migration": self._detail(mig),
                "audit_entry": audit_entry,
            }

    def _sync_checklist(
        self,
        mig: dict[str, Any],
        adopted_candidate: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """迁移确认结果同步到快照审计清单（按迁移标识幂等更新）。"""
        entry = {
            "迁移标识": mig["迁移标识"],
            "快照标识": mig["快照标识"],
            "目标湖表": mig["目标湖表"],
            "原值分": int(mig["原值分"]),
            "原值元": to_decimal_yuan(mig["原值分"]),
            "候选新值分": int(adopted_candidate["更正值分"]) if adopted_candidate else None,
            "候选新值元": to_decimal_yuan(adopted_candidate["更正值分"]) if adopted_candidate else None,
            "本次采用分": int(mig["已发布分"]),
            "本次采用元": mig["已发布元"],
            "换算版本": mig["换算版本"],
            "确认结果": "已确认",
            "更正次数": int(mig.get("更正次数", 0)),
            "确认单号": mig.get("确认单号"),
            "同步时间": _now(),
        }
        for row in self._checklist():
            if row.get("迁移标识") == mig["迁移标识"]:
                row.update(entry)
                return dict(row)
        entry["id"] = max((int(r.get("id", 0)) for r in self._checklist()), default=0) + 1
        self._checklist().append(entry)
        return dict(entry)

    # ------------------------------------------------------------------
    # 双格式读取：旧快照按分读取，新读者用已发布的元及换算版本
    # ------------------------------------------------------------------
    def read_snapshot(self, migration_id: int, fmt: str) -> dict[str, Any]:
        mig = self._find(migration_id)
        if mig is None:
            return {"ok": False, "message": f"迁移记录 {migration_id} 不存在"}
        if fmt == "cents":
            return {
                "ok": True,
                "format": "cents",
                "迁移标识": mig["迁移标识"],
                "快照标识": mig["快照标识"],
                "amount_cents": int(mig["原值分"]),
                "读取口径": "原始快照（分）",
                "初始换算版本": mig["初始换算版本"],
                "可重演": True,
            }
        if fmt == "decimal":
            if mig.get("status") != "已发布":
                return {"ok": False, "message": "元格式口径尚未发布，请先完成迁移确认"}
            return {
                "ok": True,
                "format": "decimal",
                "迁移标识": mig["迁移标识"],
                "快照标识": mig["快照标识"],
                "amount_decimal": mig["已发布元"],
                "来源分": int(mig["已发布分"]),
                "换算版本": mig["换算版本"],
                "读取口径": "已发布元格式",
            }
        return {"ok": False, "message": f"未知读取格式：{fmt}，仅支持 cents / decimal"}

    # ------------------------------------------------------------------
    # 查询入口
    # ------------------------------------------------------------------
    def audit_checklist(self) -> dict[str, Any]:
        """快照审计清单：迁移确认结果。"""
        items = [dict(row) for row in self._checklist()]
        return {"ok": True, "items": items, "total": len(items)}

    def corrections_view(self, status: str | None = None) -> dict[str, Any]:
        """更正查询入口：可查原值、换算版本和待处理更正。"""
        version_by_key = {mig["迁移标识"]: mig["换算版本"] for mig in self._migrations()}
        items = []
        for corr in self._corrections():
            if status and corr.get("status") != status:
                continue
            items.append({**corr, "换算版本": version_by_key.get(corr.get("迁移标识"))})
        return {
            "ok": True,
            "items": items,
            "total": len(items),
            "待处理数": sum(1 for item in items if item.get("status") == "待处理"),
        }

    def evidence_for_snapshot(self, snapshot_key: str) -> dict[str, Any]:
        """快照管理读取迁移记录：查明新旧数据对应的快照和金额证据。"""
        migs = [mig for mig in self._migrations() if mig.get("快照标识") == snapshot_key]
        return {
            "ok": True,
            "快照标识": snapshot_key,
            "迁移记录数": len(migs),
            "金额证据": [
                {
                    "迁移标识": mig["迁移标识"],
                    "源字段": mig["源字段"],
                    "目标字段": mig["目标字段"],
                    "原值分": int(mig["原值分"]),
                    "原值元": to_decimal_yuan(mig["原值分"]),
                    "已发布分": mig.get("已发布分"),
                    "已发布元": mig.get("已发布元"),
                    "换算版本": mig["换算版本"],
                    "状态": mig["status"],
                    "更正次数": int(mig.get("更正次数", 0)),
                    "重演次数": len(mig.get("重演证据", [])),
                }
                for mig in migs
            ],
        }


snapshot_migration_service = SnapshotMigrationService()
