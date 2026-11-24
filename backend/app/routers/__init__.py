"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。"""
from __future__ import annotations

from app.routers import resource, chains, snapshot_migration

# resource 含 /api/{module} 动态段，必须放在固定前缀路由之后注册。
ROUTERS = [chains, snapshot_migration, resource]
