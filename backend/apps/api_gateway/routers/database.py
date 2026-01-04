"""
数据库初始化管理端点
提供手动触发数据库脚本执行和验证的 API
"""
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from apps.api_gateway.dependencies import require_roles
from apps.core.models.users import User
from apps.services.db_initializer import get_initializer

router = APIRouter(prefix="/admin/database", tags=["Database Admin"])


def _engine_db_type(engine: Engine) -> str:
    # SQLAlchemy dialect names are stable across drivers: "mysql" / "postgresql" / "sqlite"...
    return str(getattr(engine, "dialect", None).name or "unknown")


def _check_engine(engine: Engine) -> Dict[str, Any]:
    """Return a lightweight status snapshot without raising."""

    errors: list[str] = []
    latency_ms: int | None = None
    connected = False
    object_count = 0
    active_connections: int | None = None

    start = time.time()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        connected = True
    except Exception as exc:
        errors.append(str(exc))
    finally:
        latency_ms = int((time.time() - start) * 1000)

    try:
        object_count = len(inspect(engine).get_table_names())
    except Exception as exc:
        errors.append(f"inspect failed: {exc}")

    try:
        checkedout = getattr(getattr(engine, "pool", None), "checkedout", None)
        if callable(checkedout):
            active_connections = int(checkedout())
    except Exception as exc:
        errors.append(f"pool status failed: {exc}")

    return {
        "db_type": _engine_db_type(engine),
        "connected": connected,
        "latency": latency_ms,
        "active_connections": active_connections,
        "object_count": object_count,
        "errors": errors,
    }


@router.post("/initialize", response_model=Dict[str, Dict])
def initialize_all_databases(
    _: User = Depends(require_roles("admin", "market_admin"))
) -> Dict[str, Dict]:
    """
    初始化所有数据库（执行触发器、存储过程、函数脚本）
    
    需要管理员权限
    """
    try:
        initializer = get_initializer()
        results = initializer.initialize_all_databases()
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库初始化失败: {str(e)}")


@router.post("/initialize/{db_name}", response_model=Dict[str, Any])
def initialize_single_database(
    db_name: str,
    _: User = Depends(require_roles("admin", "market_admin"))
) -> Dict[str, Any]:
    """
    初始化单个数据库
    
    参数:
    - db_name: mysql, mariadb, postgres
    """
    try:
        initializer = get_initializer()
        
        if db_name not in initializer.engines:
            raise HTTPException(status_code=404, detail=f"数据库 {db_name} 不存在")
        
        engine = initializer.engines[db_name]
        result = initializer.initialize_database(db_name, engine)
        return {"db_type": _engine_db_type(engine), **result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"初始化失败: {str(e)}")


@router.get("/verify/{db_name}", response_model=Dict[str, Any])
def verify_database_objects(
    db_name: str,
    _: User = Depends(require_roles("admin", "market_admin"))
) -> Dict[str, Any]:
    """
    验证数据库对象（触发器、存储过程、函数、视图）是否创建成功
    
    参数:
    - db_name: mysql, mariadb, postgres
    """
    try:
        initializer = get_initializer()
        
        if db_name not in initializer.engines:
            raise HTTPException(status_code=404, detail=f"数据库 {db_name} 不存在")
        
        engine = initializer.engines[db_name]
        return _check_engine(engine)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")


@router.get("/status", response_model=Dict[str, Dict])
def get_database_status(
    _: User = Depends(require_roles("admin", "market_admin"))
) -> Dict[str, Dict]:
    """
    获取所有数据库的对象创建状态
    """
    try:
        initializer = get_initializer()
        status: Dict[str, Dict[str, Any]] = {}
        for db_name, engine in initializer.engines.items():
            # Never fail the whole endpoint because one DB is down/misconfigured.
            status[db_name] = _check_engine(engine)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")
