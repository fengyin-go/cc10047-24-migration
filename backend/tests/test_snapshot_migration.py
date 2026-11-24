"""快照字段迁移测试：amount_cents → amount_decimal 的登记、重演、确认、双格式读取与幂等。

场景主线（S19）：250 分已转换为 2.50 元，正式发布前原来源补报 275 分更正；
停在迁移确认前补报，恢复后确认，重试一次核对金额、版本和更正次数。
"""
from __future__ import annotations

import sys
import threading

sys.path.insert(0, '.')

from fastapi.testclient import TestClient

from app.main import app
from app.services import service_for
from app.services.snapshot_migration import snapshot_migration_service

client = TestClient(app)


def _register(snapshot_key: str, cents: int) -> dict:
    resp = client.post("/api/snapshot-migrations", json={
        "snapshot_key": snapshot_key,
        "table": "fact_orders",
        "amount_cents": cents,
        "deploy_deps": "reader-sdk>=2.3.0",
        "db_compat": "delta-lake>=2.4,<3.0",
    })
    return resp.json()


class TestRegisterMigration:
    def test_register_saves_dependencies_and_compat(self):
        data = _register("S100", 12345)
        assert data["ok"] is True
        mig = data["migration"]
        assert mig["上线依赖"] == "reader-sdk>=2.3.0"
        assert mig["数据库兼容范围"] == "delta-lake>=2.4,<3.0"
        assert mig["源字段"] == "amount_cents"
        assert mig["目标字段"] == "amount_decimal"
        assert mig["原值分"] == 12345
        assert mig["原值元"] == "123.45"
        assert mig["换算版本"] == "v1"
        assert mig["status"] == "已登记"

    def test_register_requires_deps_and_compat(self):
        resp = client.post("/api/snapshot-migrations", json={
            "snapshot_key": "S101",
            "table": "fact_orders",
            "amount_cents": 100,
            "deploy_deps": "",
            "db_compat": "",
        })
        assert resp.json()["ok"] is False

    def test_duplicate_snapshot_rejected(self):
        assert _register("S102", 100)["ok"] is True
        assert _register("S102", 200)["ok"] is False

    def test_list_migrations_reads_records(self):
        resp = client.get("/api/snapshot-migrations")
        data = resp.json()
        assert data["ok"] is True
        keys = [item["迁移标识"] for item in data["items"]]
        assert "MIG-S19" in keys and "MIG-S100" in keys


class TestReplay:
    def test_replay_generates_evidence_and_moves_to_pending(self):
        # 种子记录 MIG-S20（id=2）：已登记 → 重演 → 待确认
        result = client.post("/api/snapshot-migrations/2/replay").json()
        assert result["ok"] is True
        evidence = result["evidence"]
        assert evidence["环境"] == "生产预演"
        assert evidence["原值分"] == 9900
        assert evidence["换算后元"] == "99.00"
        assert evidence["换算版本"] == "v1"
        assert result["migration"]["status"] == "待确认"

    def test_original_snapshot_is_replayable_repeatedly(self):
        first = client.post("/api/snapshot-migrations/2/replay").json()
        second = client.post("/api/snapshot-migrations/2/replay").json()
        assert first["ok"] is True and second["ok"] is True
        assert second["evidence"]["重演序号"] == first["evidence"]["重演序号"] + 1


class TestDualFormatRead:
    def test_decimal_read_requires_publish(self):
        resp = client.get("/api/snapshot-migrations/2/read", params={"format": "decimal"})
        assert resp.json()["ok"] is False

    def test_cents_read_always_available(self):
        resp = client.get("/api/snapshot-migrations/2/read", params={"format": "cents"})
        data = resp.json()
        assert data["ok"] is True
        assert data["amount_cents"] == 9900
        assert data["可重演"] is True


class TestS19CorrectionScenario:
    """S19：250 分 → 2.50 元已转换，正式发布前补报 275 分更正。"""

    def test_full_scenario(self):
        # 初始：S19 已从 250 分转换为 2.50，等待迁移确认
        detail = client.get("/api/snapshot-migrations/1").json()["migration"]
        assert detail["快照标识"] == "S19"
        assert detail["status"] == "待确认"
        assert detail["原值分"] == 250
        assert detail["原值元"] == "2.50"
        assert detail["换算版本"] == "v1"

        # 停在迁移确认前
        paused = client.post("/api/snapshot-migrations/1/pause").json()
        assert paused["ok"] is True
        assert paused["migration"]["已暂停确认"] is True

        # 暂停期间不允许确认
        blocked = client.post("/api/snapshot-migrations/1/confirm", json={}).json()
        assert blocked["ok"] is False

        # 原来源补报 275 分的更正：原值和更正来源都留存
        corr = client.post("/api/snapshot-migrations/1/corrections", json={
            "corrected_cents": 275,
            "source": "origin-source",
            "correction_key": "CORR-S19-001",
        }).json()
        assert corr["ok"] is True
        assert corr["correction"]["原值分"] == 250
        assert corr["correction"]["更正来源"] == "origin-source"
        assert corr["correction"]["status"] == "待处理"

        # 快照详情区分原值、候选新值和本次允许采用的金额
        detail = client.get("/api/snapshot-migrations/1").json()["migration"]
        assert detail["原值元"] == "2.50"
        assert detail["候选新值分"] == 275
        assert detail["候选新值元"] == "2.75"
        assert detail["本次允许采用元"] == "2.75"
        assert detail["待处理更正数"] == 1

        # 恢复并执行迁移确认
        resumed = client.post("/api/snapshot-migrations/1/resume").json()
        assert resumed["ok"] is True
        confirmed = client.post(
            "/api/snapshot-migrations/1/confirm", json={"confirm_no": "CONF-S19-001"},
        ).json()
        assert confirmed["ok"] is True
        mig = confirmed["migration"]
        assert mig["status"] == "已发布"
        assert mig["已发布元"] == "2.75"
        assert mig["换算版本"] == "v2"
        assert mig["更正次数"] == 1

        # 迁移确认结果同步到快照审计清单：区分原值、候选新值、本次采用
        checklist = client.get("/api/snapshot-migrations/audit-checklist").json()
        entry = [e for e in checklist["items"] if e["迁移标识"] == "MIG-S19"][0]
        assert entry["原值元"] == "2.50"
        assert entry["候选新值元"] == "2.75"
        assert entry["本次采用元"] == "2.75"
        assert entry["换算版本"] == "v2"
        assert entry["确认结果"] == "已确认"
        assert entry["更正次数"] == 1

        # 分别读取原快照和元格式快照
        cents = client.get("/api/snapshot-migrations/1/read", params={"format": "cents"}).json()
        assert cents["amount_cents"] == 250  # 已发布的历史读取口径不被覆盖
        decimal = client.get("/api/snapshot-migrations/1/read", params={"format": "decimal"}).json()
        assert decimal["amount_decimal"] == "2.75"
        assert decimal["换算版本"] == "v2"

        # 重试一次迁移确认：金额、版本和更正次数不变
        retry = client.post(
            "/api/snapshot-migrations/1/confirm", json={"confirm_no": "CONF-S19-001"},
        ).json()
        assert retry["ok"] is True
        assert retry["idempotent"] is True
        mig = retry["migration"]
        assert mig["已发布元"] == "2.75"
        assert mig["换算版本"] == "v2"
        assert mig["更正次数"] == 1

        # 同一笔更正重复补报：幂等去重，更正次数仍为 1
        dup = client.post("/api/snapshot-migrations/1/corrections", json={
            "corrected_cents": 275,
            "source": "origin-source",
            "correction_key": "CORR-S19-001",
        }).json()
        assert dup["deduplicated"] is True
        detail = client.get("/api/snapshot-migrations/1").json()["migration"]
        assert detail["更正次数"] == 1
        assert detail["待处理更正数"] == 0


class TestSnapshotMgrEvidence:
    def test_snapshot_mgr_reads_migration_evidence(self):
        """快照管理读取迁移记录，查明新旧数据对应的快照和金额证据。"""
        svc = service_for("snapshot_mgr")
        result = svc.domain_migration_evidence(4)  # S19
        assert result["ok"] is True
        assert result["快照标识"] == "S19"
        assert result["迁移记录数"] == 1
        evidence = result["金额证据"][0]
        assert evidence["源字段"] == "amount_cents"
        assert evidence["目标字段"] == "amount_decimal"
        assert evidence["原值分"] == 250
        assert evidence["原值元"] == "2.50"
        # S19 场景已确认发布：新口径为 2.75 / v2
        assert evidence["已发布元"] == "2.75"
        assert evidence["换算版本"] == "v2"
        assert evidence["更正次数"] == 1


class TestCorrectionsEntry:
    def test_corrections_view_shows_original_version_and_pending(self):
        """另一个入口：可查原值、换算版本和待处理更正。"""
        mig = _register("S300", 100)["migration"]
        mid = mig["id"]
        client.post(f"/api/snapshot-migrations/{mid}/replay")
        client.post(f"/api/snapshot-migrations/{mid}/corrections", json={
            "corrected_cents": 999,
            "source": "billing-replay",
            "correction_key": "CORR-S300-001",
        })
        resp = client.get("/api/snapshot-migrations/corrections", params={"status": "待处理"})
        data = resp.json()
        assert data["ok"] is True
        assert data["待处理数"] >= 1
        item = [i for i in data["items"] if i["更正标识"] == "CORR-S300-001"][0]
        assert item["原值分"] == 100
        assert item["原值元"] == "1.00"
        assert item["更正值分"] == 999
        assert item["换算后元"] == "9.99"
        assert item["更正来源"] == "billing-replay"
        assert item["换算版本"] == "v1"
        assert item["status"] == "待处理"


class TestConcurrentConfirm:
    def test_concurrent_confirm_counts_correction_once(self):
        """并发确认与断线恢复：一笔更正只算一次，已发布口径不被覆盖。"""
        mig = _register("S200", 100)["migration"]
        mid = mig["id"]
        client.post(f"/api/snapshot-migrations/{mid}/replay")
        client.post(f"/api/snapshot-migrations/{mid}/corrections", json={
            "corrected_cents": 150,
            "source": "src",
            "correction_key": "CORR-S200-001",
        })
        results = []

        def worker():
            results.append(snapshot_migration_service.confirm(mid, confirm_no="CONF-S200"))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert all(r["ok"] for r in results)
        publishes = [r for r in results if not r.get("idempotent")]
        assert len(publishes) == 1  # 只发布一次，其余为幂等重试
        detail = client.get(f"/api/snapshot-migrations/{mid}").json()["migration"]
        assert detail["更正次数"] == 1
        assert detail["已发布元"] == "1.50"
        assert detail["换算版本"] == "v2"


class TestPostPublishCorrection:
    def test_correction_after_publish_retained_without_overwrite(self):
        """已发布后旧格式更正：原值和更正来源留存，已发布口径不被覆盖。"""
        resp = client.post("/api/snapshot-migrations/1/corrections", json={
            "corrected_cents": 300,
            "source": "late-source",
            "correction_key": "CORR-S19-002",
        }).json()
        assert resp["ok"] is True
        assert resp["correction"]["status"] == "待处理"
        assert resp["correction"]["原值分"] == 250
        assert resp["correction"]["更正来源"] == "late-source"

        # 已发布口径不变
        decimal = client.get("/api/snapshot-migrations/1/read", params={"format": "decimal"}).json()
        assert decimal["amount_decimal"] == "2.75"
        assert decimal["换算版本"] == "v2"
        # 原快照仍按原来的分读取
        cents = client.get("/api/snapshot-migrations/1/read", params={"format": "cents"}).json()
        assert cents["amount_cents"] == 250
        # 待处理更正可在更正入口查到
        pending = client.get("/api/snapshot-migrations/corrections", params={"status": "待处理"}).json()
        assert any(i["更正标识"] == "CORR-S19-002" for i in pending["items"])
