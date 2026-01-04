"""Administrative operations endpoints for batch tooling and monitoring."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal

from loguru import logger
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import time
from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from apps.api_gateway.dependencies import get_db_session, get_hub_db_session, require_roles
from apps.api_gateway.routers.admin_tables import ALLOWED_TABLES
from apps.core.database import db_manager
from apps.core.models import (
    Item,
    Role,
    SystemSetting,
    SyncLog,
    Transaction,
    User,
    UserRole,
)
from apps.core.transaction import TransactionConfig
from apps.services.monitoring_simulator import monitoring_data_simulator, query_simulator
from apps.services.maintenance import MaintenanceTaskRunner

router = APIRouter(
    prefix="/admin/operations",
    tags=["Admin Operations"],
    dependencies=[Depends(require_roles("admin", "market_admin"))],
)


EXPORT_ROW_LIMIT = 2000
IMPORT_ROW_LIMIT = 500
SUPPORTED_DATABASES = {"mysql", "mariadb", "postgres"}
IMPORTABLE_TABLES = {"users", "items", "transactions", "messages"}
ARCHIVE_IMPORTABLE_TABLES = {
    "users",
    "user_profiles",
    "user_preferences",
    "categories",
    "campuses",
    "items",
    "item_images",
    "transactions",
    "messages",
}
ARCHIVE_IMPORT_ROW_LIMIT = 5000
UPLOAD_DIR = Path("/tmp/campuswap-admin")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class BatchUserOperation(BaseModel):
    """Payload for batch user instructions."""

    condition: Literal["inactive_30days", "not_verified", "low_credit", "banned"]
    action: Literal["delete", "remind", "demote", "reset_credit"]
    dry_run: bool = False


class BatchItemOperation(BaseModel):
    """Payload for batch item operations."""

    status: Literal["available", "sold", "deleted", "archived", "all"] = "available"
    days: int = Field(90, ge=1, le=365)
    action: Literal["archive", "delete", "remind_seller"]
    dry_run: bool = False


class TransactionCleanupPayload(BaseModel):
    """Transaction cleanup instructions."""

    statuses: List[str] = Field(default_factory=list)
    older_than_days: int = Field(30, ge=1, le=365)


class ExportPayload(BaseModel):
    """Data export payload."""

    tables: List[str] = Field(default_factory=list)
    format: Literal["json", "csv"] = "json"
    schedule_only: bool = False


class ImportArchivePayload(BaseModel):
    """Payload for importing an export archive (zip)."""

    mode: Literal["replace", "append", "update"] = "append"


class SqlPayload(BaseModel):
    """SQL runner payload."""

    database: Literal["mysql", "mariadb", "postgres"] = "mysql"
    query: str
    mode: Literal["run", "explain"] = "run"

class SqlBenchmarkPayload(BaseModel):
    """Benchmark two read-only SQL queries (baseline vs optimized)."""

    database: Literal["mysql", "mariadb", "postgres"] = "mysql"
    baseline_query: str = Field(..., description="优化前 SQL")
    optimized_query: str = Field(..., description="优化后 SQL")
    runs: int = Field(5, ge=1, le=30, description="每个 SQL 运行次数")
    mode: Literal["run", "explain", "explain_analyze"] = Field(
        default="run", description="run/explain/explain_analyze"
    )
    fetch_rows: int = Field(200, ge=0, le=2000, description="run 模式最多返回行数")


def _build_explain_statement(database: str, query: str, mode: str) -> str:
    q = query.strip().rstrip(";")
    if mode == "explain":
        if database == "mysql":
            return f"EXPLAIN {q}"
        if database == "mariadb":
            return f"EXPLAIN {q}"
        return f"EXPLAIN {q}"

    # explain_analyze
    if database == "postgres":
        return f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {q}"
    if database == "mysql":
        # MySQL 8+ supports EXPLAIN ANALYZE
        return f"EXPLAIN ANALYZE {q}"
    # MariaDB doesn't reliably support EXPLAIN ANALYZE across versions
    return f"EXPLAIN {q}"


def _run_one_statement(session: Session, *, statement: str, mode: str, fetch_rows: int) -> tuple[list[dict], int]:
    result = session.execute(text(statement))
    if mode == "run":
        rows = _serialize_rows(result.fetchmany(fetch_rows)) if fetch_rows else []
        return rows, len(rows)
    # explain/explain_analyze: fetch all plan rows (usually small)
    rows = _serialize_rows(result.fetchall())
    return rows, len(rows)


class AiAuditPayload(BaseModel):
    """Toggle AI audit mode payload."""

    enabled: bool


class MaintenanceTaskPayload(BaseModel):
    """Payload for system maintenance tasks triggered from the admin panel."""

    task: Literal[
        "cleanup_expired_sessions",
        "cleanup_deleted_records",
        "cleanup_temp_files",
        "vacuum_tables",
        "analyze_indexes",
        "rebuild_indexes",
        "suggest_indexes",
        "optimize_tables",
        "detect_anomalies",
        "lock_suspicious_users",
        "analyze_slow_queries",
        "cache_warming",
        "adjust_connection_pool",
        "auto_optimize",
        "create_backup",
        "view_backups",
        "restore_backup",
        "schedule_backup",
    ]


def current_admin_user(user: User = Depends(require_roles("admin", "market_admin"))) -> User:
    """Dependency that returns the current admin user."""

    return user


def _user_condition_expression(condition: str):
    now = datetime.utcnow()
    if condition == "inactive_30days":
        threshold = now - timedelta(days=30)
        return or_(User.last_login_at.is_(None), User.last_login_at < threshold)
    if condition == "not_verified":
        return User.is_verified.is_(False)
    if condition == "low_credit":
        return User.credit_score < 60
    if condition == "banned":
        return User.is_banned.is_(True)
    raise HTTPException(status_code=400, detail="不支持的用户筛选条件")


def _item_filter_expression(status: str, days: int):
    cutoff = datetime.utcnow() - timedelta(days=days)
    clauses = []
    if status != "all":
        clauses.append(Item.status == status)
    clauses.append(or_(Item.updated_at.is_(None), Item.updated_at < cutoff, Item.created_at < cutoff))
    return and_(*clauses)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _coerce_table_name(table: str) -> str:
    actual = ALLOWED_TABLES.get(table)
    if not actual:
        raise HTTPException(status_code=404, detail=f"表 {table} 不在允许导入/导出列表中")
    return actual


def _insert_notifications(session: Session, user_ids: Iterable[int], title: str, content: str) -> None:
    rows = [
        {
            "user_id": uid,
            "type": "system",
            "title": title,
            "content": content,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        for uid in user_ids
    ]
    if not rows:
        return
    session.execute(
        text(
            """
            INSERT INTO notifications (user_id, type, title, content, created_at, updated_at)
            VALUES (:user_id, :type, :title, :content, :created_at, :updated_at)
            """
        ),
        rows,
    )


@router.get("/users/estimate")
def estimate_users(
    condition: str = Query(..., description="inactive_30days/not_verified/low_credit/banned"),
    session: Session = Depends(get_db_session),
):
    """Return the number of users that match the batch condition."""

    expr = _user_condition_expression(condition)
    count = session.execute(select(func.count()).select_from(User).where(expr)).scalar() or 0
    return {"condition": condition, "count": count}


@router.post("/users/batch")
def batch_users(
    payload: BatchUserOperation,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(current_admin_user),
):
    """Execute batch user maintenance commands."""

    expr = _user_condition_expression(payload.condition)
    target_ids = (
        session.execute(select(User.id).where(expr).limit(2000)).scalars().all()
    )
    if payload.dry_run:
        return {"affected": len(target_ids), "preview": target_ids[:20]}

    if not target_ids:
        return {"affected": 0}

    affected = 0
    if payload.action == "delete":
        result = session.execute(
            update(User)
            .where(User.id.in_(target_ids))
            .values(is_active=False, is_banned=True, updated_at=datetime.utcnow())
        )
        affected = result.rowcount or len(target_ids)
    elif payload.action == "remind":
        _insert_notifications(session, target_ids, "账号活跃提醒", "您的账号长期未登录，请及时确认账户安全。")
        affected = len(target_ids)
    elif payload.action == "demote":
        role_ids = (
            session.execute(select(Role.id).where(Role.name.in_(["admin", "market_admin"])))
            .scalars()
            .all()
        )
        if role_ids:
            session.execute(
                delete(UserRole).where(
                    UserRole.user_id.in_(target_ids), UserRole.role_id.in_(role_ids)
                )
            )
        affected = len(target_ids)
    elif payload.action == "reset_credit":
        result = session.execute(
            update(User)
            .where(User.id.in_(target_ids))
            .values(credit_score=80, updated_at=datetime.utcnow())
        )
        affected = result.rowcount or len(target_ids)
    else:
        raise HTTPException(status_code=400, detail="不支持的批量操作")

    return {"affected": affected}


@router.get("/items/estimate")
def estimate_items(
    status: str = Query("available"),
    days: int = Query(90, ge=1, le=365),
    session: Session = Depends(get_db_session),
):
    """Return the estimated number of items affected."""

    expr = _item_filter_expression(status, days)
    count = session.execute(select(func.count()).select_from(Item).where(expr)).scalar() or 0
    return {"status": status, "days": days, "count": count}


@router.post("/items/batch")
def batch_items(
    payload: BatchItemOperation,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(current_admin_user),
):
    """Execute batch actions on items."""

    expr = _item_filter_expression(payload.status, payload.days)
    item_ids = (
        session.execute(select(Item.id).where(expr).limit(2000)).scalars().all()
    )
    if payload.dry_run:
        return {"affected": len(item_ids), "preview": item_ids[:20]}
    if not item_ids:
        return {"affected": 0}

    affected = 0
    if payload.action == "archive":
        result = session.execute(
            update(Item)
            .where(Item.id.in_(item_ids))
            .values(status="archived", updated_at=datetime.utcnow())
        )
        affected = result.rowcount or len(item_ids)
    elif payload.action == "delete":
        result = session.execute(
            update(Item)
            .where(Item.id.in_(item_ids))
            .values(status="deleted", updated_at=datetime.utcnow())
        )
        affected = result.rowcount or len(item_ids)
    elif payload.action == "remind_seller":
        seller_ids = (
            session.execute(select(Item.seller_id).where(Item.id.in_(item_ids))).scalars().all()
        )
        _insert_notifications(
            session,
            seller_ids,
            "商品下架提醒",
            "您的商品长时间未更新状态，请确认是否仍需上架。",
        )
        affected = len(seller_ids)
    else:
        raise HTTPException(status_code=400, detail="不支持的批量商品操作")

    return {"affected": affected}


@router.post("/transactions/cleanup")
def cleanup_transactions(
    payload: TransactionCleanupPayload,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(current_admin_user),
):
    """Cleanup stale transactions by marking them cancelled."""

    statuses = payload.statuses or ["pending", "cancelled", "timeout"]
    cutoff = datetime.utcnow() - timedelta(days=payload.older_than_days)
    stmt = (
        update(Transaction)
        .where(Transaction.status.in_(statuses))
        .where(or_(Transaction.updated_at.is_(None), Transaction.updated_at < cutoff))
        .values(status="cancelled", cancelled_at=datetime.utcnow())
    )
    result = session.execute(stmt)
    affected = result.rowcount or 0
    return {"affected": affected}


def _serialize_rows(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for row in rows:
        mapping = row._mapping if hasattr(row, "_mapping") else row
        serialized.append({key: _serialize_value(value) for key, value in dict(mapping).items()})
    return serialized


def _build_export_archive(session: Session, tables: List[str], fmt: str) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for table in tables:
            actual = _coerce_table_name(table)
            result = session.execute(text(f"SELECT * FROM {actual} LIMIT :limit"), {"limit": EXPORT_ROW_LIMIT})
            rows = _serialize_rows(result)
            filename = f"{actual}.{fmt}"
            if fmt == "json":
                payload = json.dumps(rows, ensure_ascii=False, indent=2)
            else:
                csv_buffer = io.StringIO()
                writer = None
                for row in rows:
                    if writer is None:
                        writer = csv.DictWriter(csv_buffer, fieldnames=list(row.keys()))
                        writer.writeheader()
                    writer.writerow(row)
                payload = csv_buffer.getvalue()
            archive.writestr(filename, payload)
    buffer.seek(0)
    return buffer


def _import_rows_into_table(session: Session, *, actual: str, rows: List[Dict[str, Any]], mode: str) -> int:
    if not rows:
        return 0

    if mode == "replace":
        session.execute(text(f"DELETE FROM {actual}"))

    inserted = 0
    for row in rows:
        clean_row = {key: value for key, value in row.items() if value not in (None, "")}
        if not clean_row:
            continue

        if mode == "update" and "id" in clean_row:
            stmt = update(text(actual)).where(text(f"{actual}.id = :id")).values(**clean_row)
            session.execute(stmt, clean_row)
        else:
            columns = ", ".join(clean_row.keys())
            placeholders = ", ".join([f":{key}" for key in clean_row.keys()])
            session.execute(text(f"INSERT INTO {actual} ({columns}) VALUES ({placeholders})"), clean_row)
        inserted += 1
    return inserted


def _parse_rows_from_bytes(filename: str, raw: bytes) -> List[Dict[str, Any]]:
    suffix = (Path(filename).suffix or "").lower()
    if suffix == ".json":
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, dict) and "items" in data:
            rows = data["items"]
        elif isinstance(data, list):
            rows = data
        else:
            raise HTTPException(status_code=400, detail=f"JSON 结构无法识别: {filename}")
        if not isinstance(rows, list):
            raise HTTPException(status_code=400, detail=f"JSON 数据格式错误: {filename}")
        return rows

    if suffix == ".csv":
        text_data = raw.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text_data))
        return list(reader)

    raise HTTPException(status_code=400, detail=f"仅支持 JSON/CSV: {filename}")


@router.post("/export")
def export_tables(
    payload: ExportPayload,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(current_admin_user),
):
    """Export whitelisted tables into a zipped archive."""

    if not payload.tables:
        raise HTTPException(status_code=400, detail="请选择至少一个数据表")

    unique_tables = sorted({table for table in payload.tables})
    if payload.schedule_only:
        return {"scheduled": True, "tables": unique_tables}

    archive = _build_export_archive(session, unique_tables, payload.format)
    filename = f"campuswap-export-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.zip"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(archive, media_type="application/zip", headers=headers)


async def _load_import_rows(file: UploadFile) -> List[Dict[str, Any]]:
    suffix = (Path(file.filename or "").suffix or "").lower()
    raw = await file.read()
    if suffix == ".json":
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, dict) and "items" in data:
            rows = data["items"]
        elif isinstance(data, list):
            rows = data
        else:
            raise HTTPException(status_code=400, detail="JSON 结构无法识别")
    elif suffix == ".csv":
        text_data = raw.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text_data))
        rows = list(reader)
    elif suffix == ".sql":
        target = UPLOAD_DIR / f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{file.filename}"
        target.write_bytes(raw)
        return []
    else:
        raise HTTPException(status_code=400, detail="仅支持 JSON/CSV/SQL 文件")
    if len(rows) > IMPORT_ROW_LIMIT:
        raise HTTPException(status_code=400, detail=f"单次导入最多 {IMPORT_ROW_LIMIT} 行")
    return rows


@router.post("/import")
async def import_table(
    table: str = Form(...),
    mode: Literal["replace", "append", "update"] = Form("append"),
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(current_admin_user),
):
    """Import structured data into allowed tables."""

    actual = _coerce_table_name(table)
    if actual not in IMPORTABLE_TABLES:
        raise HTTPException(status_code=400, detail="该表暂不支持后台导入")

    rows = await _load_import_rows(file)
    if not rows:
        return {"stored": True, "message": "SQL 文件已保存，请使用手动脚本执行"}

    if mode == "replace":
        session.execute(text(f"DELETE FROM {actual}"))

    inserted = 0
    for row in rows:
        clean_row = {key: value for key, value in row.items() if value not in (None, "")}
        if mode == "update" and "id" in clean_row:
            stmt = (
                update(text(actual))
                .where(text(f"{actual}.id = :id"))
                .values(**clean_row)
            )
            session.execute(stmt, clean_row)
        else:
            columns = ", ".join(clean_row.keys())
            placeholders = ", ".join([f":{key}" for key in clean_row.keys()])
            session.execute(text(f"INSERT INTO {actual} ({columns}) VALUES ({placeholders})"), clean_row)
        inserted += 1

    return {"imported": inserted, "table": actual}


@router.post("/import-archive")
async def import_archive(
    mode: Literal["replace", "append", "update"] = Form("append"),
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(current_admin_user),
):
    """Import a zipped archive created by /admin/operations/export."""

    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持 .zip 归档文件")

    raw = await file.read()
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw), "r")
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="ZIP 文件损坏或格式不正确") from exc

    extracted: Dict[str, List[Dict[str, Any]]] = {}
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename
        base = Path(name).name
        if base.startswith("."):
            continue

        table_key = (Path(base).stem or "").strip()
        if not table_key:
            continue

        actual = _coerce_table_name(table_key)
        if actual not in ARCHIVE_IMPORTABLE_TABLES:
            continue

        content = archive.read(info)
        rows = _parse_rows_from_bytes(base, content)
        if len(rows) > ARCHIVE_IMPORT_ROW_LIMIT:
            raise HTTPException(
                status_code=400,
                detail=f"单表导入最多 {ARCHIVE_IMPORT_ROW_LIMIT} 行: {actual}",
            )
        extracted[actual] = rows

    if not extracted:
        raise HTTPException(status_code=400, detail="归档中未找到可导入的数据表")

    # Best-effort: disable FK checks for bulk replace in MySQL/MariaDB.
    fk_disabled = False
    try:
        if mode == "replace":
            lowered = str(session.bind.dialect.name).lower() if session.bind is not None else ""
            if "mysql" in lowered:
                session.execute(text("SET FOREIGN_KEY_CHECKS=0"))
                fk_disabled = True

        total = 0
        per_table: Dict[str, int] = {}

        # Delete first (replace), then insert; use a stable order to reduce FK issues.
        if mode == "replace":
            delete_order = [
                "messages",
                "transactions",
                "item_images",
                "items",
                "user_preferences",
                "user_profiles",
                "users",
                "categories",
                "campuses",
            ]
            for actual in delete_order:
                if actual in extracted:
                    session.execute(text(f"DELETE FROM {actual}"))

        insert_order = [
            "campuses",
            "categories",
            "users",
            "user_profiles",
            "user_preferences",
            "items",
            "item_images",
            "transactions",
            "messages",
        ]
        for actual in insert_order:
            rows = extracted.get(actual)
            if not rows:
                continue
            inserted = _import_rows_into_table(session, actual=actual, rows=rows, mode="append" if mode == "replace" else mode)
            per_table[actual] = inserted
            total += inserted

        return {"imported": total, "tables": per_table, "mode": mode}
    finally:
        if fk_disabled:
            try:
                session.execute(text("SET FOREIGN_KEY_CHECKS=1"))
            except Exception:
                pass




def _assert_safe_sql(query: str) -> None:
    lowered = query.strip().lower()
    if not lowered:
        raise HTTPException(status_code=400, detail="SQL 语句不能为空")
    allowed_prefixes = ("select", "with", "show", "explain", "desc", "pragma")
    if not lowered.startswith(allowed_prefixes):
        raise HTTPException(status_code=400, detail="仅允许只读 SQL 语句")
    banned_tokens = ("drop ", "delete ", "truncate ", "update ", "insert ", "alter ", "create ")
    if any(token in lowered for token in banned_tokens):
        raise HTTPException(status_code=400, detail="SQL 包含危险操作")


@router.post("/sql")
def run_sql(
    payload: SqlPayload,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(current_admin_user),
):
    """Execute a read-only SQL query against a chosen database."""

    _assert_safe_sql(payload.query)
    if payload.database not in SUPPORTED_DATABASES:
        raise HTTPException(status_code=400, detail="不支持的数据库类型")

    with db_manager.session_scope(payload.database) as session:
        started = datetime.utcnow()
        try:
            statement = payload.query if payload.mode == "run" else f"EXPLAIN {payload.query}"
            result = session.execute(text(statement))
            rows = _serialize_rows(result.fetchmany(200))
        except ProgrammingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    duration = (datetime.utcnow() - started).total_seconds() * 1000
    return {"rows": rows, "rowcount": len(rows), "duration_ms": round(duration, 2)}

@router.post("/sql/benchmark")
def benchmark_sql(
    payload: SqlBenchmarkPayload,
    current_user: User = Depends(current_admin_user),
):
    """Benchmark baseline vs optimized SQL with timing + optional explain."""

    _assert_safe_sql(payload.baseline_query)
    _assert_safe_sql(payload.optimized_query)
    if payload.database not in SUPPORTED_DATABASES:
        raise HTTPException(status_code=400, detail="不支持的数据库类型")

    mode = payload.mode
    baseline_stmt = payload.baseline_query
    optimized_stmt = payload.optimized_query
    if mode != "run":
        baseline_stmt = _build_explain_statement(payload.database, payload.baseline_query, mode)
        optimized_stmt = _build_explain_statement(payload.database, payload.optimized_query, mode)

    results: dict[str, dict] = {
        "baseline": {"durations_ms": [], "rowcount": 0, "rows": []},
        "optimized": {"durations_ms": [], "rowcount": 0, "rows": []},
    }

    with db_manager.session_scope(payload.database) as session:
        # Interleave runs to make the comparison fairer w.r.t. cache warming.
        for i in range(int(payload.runs)):
            for name, stmt in (("baseline", baseline_stmt), ("optimized", optimized_stmt)):
                started = time.perf_counter()
                try:
                    rows, rc = _run_one_statement(session, statement=stmt, mode=mode if mode != "run" else "run", fetch_rows=int(payload.fetch_rows))
                except ProgrammingError as exc:
                    # Fallback: MySQL EXPLAIN ANALYZE might not be supported.
                    if mode == "explain_analyze" and payload.database in {"mysql", "mariadb"}:
                        fallback_stmt = _build_explain_statement(payload.database, payload.baseline_query if name == "baseline" else payload.optimized_query, "explain")
                        rows, rc = _run_one_statement(session, statement=fallback_stmt, mode="explain", fetch_rows=int(payload.fetch_rows))
                    else:
                        raise HTTPException(status_code=400, detail=str(exc)) from exc
                elapsed = (time.perf_counter() - started) * 1000
                results[name]["durations_ms"].append(round(elapsed, 3))
                # Return the last run's rows as a sample (plans are stable enough; data rows capped)
                results[name]["rows"] = rows
                results[name]["rowcount"] = rc

    for name in ("baseline", "optimized"):
        d = results[name]["durations_ms"]
        results[name]["summary"] = {
            "avg_ms": round(sum(d) / len(d), 3) if d else 0,
            "min_ms": min(d) if d else 0,
            "max_ms": max(d) if d else 0,
        }

    return {
        "database": payload.database,
        "mode": mode,
        "runs": payload.runs,
        "results": results,
    }


def _collect_running_queries(limit: int = 10) -> List[Dict[str, Any]]:
    running: List[Dict[str, Any]] = []
    try:
        with db_manager.session_scope("mysql") as session:
            rows = session.execute(text("SHOW FULL PROCESSLIST")).mappings().all()
        for row in rows:
            command = (row.get("Command") or "").lower()
            if command in {"sleep", "binlog dump"}:
                continue
            running.append(
                {
                    "id": str(row.get("Id")),
                    "database": row.get("db") or "mysql",
                    "query": row.get("Info") or "",
                    "status": row.get("State") or row.get("Command"),
                    "duration": int(row.get("Time") or 0) * 1000,
                }
            )
            if len(running) >= limit:
                break
    except Exception as exc:  # pragma: no cover - SHOW PROCESSLIST may need privileges
        logger.warning("Failed to read process list: %s", exc)
    if len(running) < limit:
        running.extend(query_simulator.snapshot(limit - len(running)))
    return running[:limit]


def _pool_snapshot(running_queries: List[Dict[str, Any]]):
    active = len(running_queries)
    max_pool = TransactionConfig.POOL_SIZE
    usage = min(100, int((active / max_pool) * 100)) if max_pool else 0
    idle = max(max_pool - active, 0)
    return {
        "active": active,
        "idle": idle,
        "max": max_pool,
        "waiting": max(active - max_pool, 0),
        "timeouts": 0,
        "usage": usage,
    }


@router.get("/performance/insights")
def performance_insights(session: Session = Depends(get_hub_db_session)):
    """Return aggregated monitoring data for AdminPerformanceView."""

    monitoring_data_simulator.ensure_baseline()
    running_queries = _collect_running_queries()
    pool = _pool_snapshot(running_queries)

    slow_queries: List[Dict[str, Any]] = []
    try:
        rows = session.execute(
            text(
                """
                SELECT id, db_name, metric_value, details, recorded_at
                FROM performance_metrics
                WHERE metric_type IN ('query_time', 'query_time_avg')
                ORDER BY recorded_at DESC
                LIMIT 10
                """
            )
        ).mappings().all()
        for row in rows:
            details = row.get("details") or {}
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except json.JSONDecodeError:
                    details = {}
            slow_queries.append(
                {
                    "id": f"Q{row['id']}",
                    "sql": details.get("sql") or f"SELECT * FROM {details.get('table', 'items')} LIMIT 50",
                    "count": details.get("count", 1),
                    "avgTime": float(row.get("metric_value") or 0),
                    "maxTime": float(details.get("max_time") or row.get("metric_value") or 0),
                    "rows": details.get("rows", 0),
                    "suggestion": details.get("suggestion") or "考虑为过滤列添加复合索引",
                }
            )
    except ProgrammingError:
        pass

    if not slow_queries:
        slow_queries = [
            {
                "id": "Q-items",
                "sql": "SELECT * FROM items WHERE status = 'available' ORDER BY updated_at DESC",
                "count": 120,
                "avgTime": 85,
                "maxTime": 230,
                "rows": 200,
                "suggestion": "为 status, updated_at 添加组合索引",
            }
        ]

    recent_window = datetime.utcnow() - timedelta(minutes=5)
    sync_runs = (
        session.execute(select(func.count()).select_from(SyncLog).where(SyncLog.started_at >= recent_window)).scalar()
        or 0
    )
    qps = round(sync_runs / (5 * 60), 2)
    avg_query_time = round(
        (sum(item["avgTime"] for item in slow_queries) / len(slow_queries)) if slow_queries else 12.0,
        2,
    )

    unresolved_conflicts = session.execute(
        text("SELECT COUNT(*) FROM conflict_records WHERE resolved = 0")
    ).scalar() or 0
    total_conflicts = session.execute(text("SELECT COUNT(*) FROM conflict_records")).scalar() or 1
    conflict_ratio = unresolved_conflicts / max(total_conflicts, 1)

    db_connection = max(50, 100 - max(pool["usage"] - 50, 0))
    query_speed = max(40, 100 - avg_query_time)
    sync_consistency = max(60, int((1 - conflict_ratio) * 100))
    resource_usage = min(95, pool["usage"] + 5)
    system_health = round(
        db_connection * 0.3
        + query_speed * 0.3
        + sync_consistency * 0.3
        + (100 - resource_usage) * 0.1,
        2,
    )

    connection_pools = {
        "mysql": pool,
        "postgres": {**pool, "usage": max(pool["usage"] - 10, 5)},
        "mariadb": {**pool, "usage": max(pool["usage"] - 5, 5)},
    }

    health = {
        "dbConnection": int(db_connection),
        "querySpeed": int(query_speed),
        "syncConsistency": int(sync_consistency),
        "resourceUsage": int(resource_usage),
        "score": system_health,
    }

    return {
        "slow_queries": slow_queries,
        "running_queries": running_queries,
        "connection_pools": connection_pools,
        "health": health,
        "stats": {"avg_query_time": avg_query_time, "qps": qps},
    }


@router.get("/performance/heatmap")
def performance_heatmap(days: int = Query(7, ge=1, le=14)):
    """Return recent sync activity heatmap data for analytics dashboards."""

    monitoring_data_simulator.ensure_baseline()
    data = monitoring_data_simulator.generate_heatmap(days)
    return {"days": days, "data": data}


@router.post("/maintenance")
def trigger_maintenance_task(
    payload: MaintenanceTaskPayload,
    session: Session = Depends(get_hub_db_session),
    current_user: User = Depends(current_admin_user),
):
    """Execute a maintenance task."""

    runner = MaintenanceTaskRunner(session)
    try:
        result = runner.run(payload.task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.get("/databases/{db_name}")
def database_details(db_name: str, session: Session = Depends(get_hub_db_session)):
    """Return last few sync logs for a database target."""

    if db_name not in SUPPORTED_DATABASES:
        raise HTTPException(status_code=404, detail="未知的数据库标识")
    rows = session.execute(
        text(
            """
            SELECT id, status, started_at, completed_at, stats
            FROM sync_logs
            WHERE JSON_UNQUOTE(JSON_EXTRACT(stats, '$.target')) = :target
            ORDER BY started_at DESC
            LIMIT 5
            """
        ),
        {"target": db_name},
    ).mappings().all()
    logs: List[Dict[str, Any]] = []
    for row in rows:
        stats = row.get("stats") or {}
        if isinstance(stats, str):
            try:
                stats = json.loads(stats)
            except json.JSONDecodeError:
                stats = {}
        logs.append(
            {
                "id": row["id"],
                "status": row["status"],
                "started_at": _serialize_value(row.get("started_at")),
                "completed_at": _serialize_value(row.get("completed_at")),
                "mode": stats.get("mode"),
            }
        )
    return {"database": db_name, "logs": logs}


@router.post("/queries/{query_id}/kill")
def kill_query(query_id: str, current_user: User = Depends(current_admin_user)):
    """Kill a running MySQL query."""

    try:
        numeric_id = int(query_id)
    except ValueError:
        numeric_id = None

    if numeric_id is not None:
        try:
            with db_manager.session_scope("mysql") as session:
                session.execute(text(f"KILL {numeric_id}"))
            return {"killed": numeric_id, "simulated": False}
        except Exception as exc:  # pragma: no cover - depends on DB privileges
            logger.warning("Failed to kill query %s: %s", query_id, exc)

    if query_simulator.kill(query_id):
        return {"killed": query_id, "simulated": True}

    raise HTTPException(status_code=404, detail="未找到正在运行的查询")


@router.get("/conflicts/export")
def export_conflicts(session: Session = Depends(get_hub_db_session)):
    """Export conflict records into a CSV file."""

    rows = session.execute(
        text(
            """
            SELECT id, table_name, record_id, source, target, status as conflict_type, created_at, resolution_note as resolution_strategy
            FROM conflict_records
            ORDER BY created_at DESC
            LIMIT 1000
            """
        )
    ).fetchall()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "table", "record_id", "source", "target", "type", "created_at", "strategy"])
    for row in rows:
        writer.writerow(row)
    buffer.seek(0)
    filename = f"conflicts-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(io.BytesIO(buffer.getvalue().encode("utf-8")), media_type="text/csv", headers=headers)


@router.post("/sync/replay")
def replay_stalled_sync() -> Dict[str, Any]:
    """Admin action endpoint.

    The Sync Core worker runs continuously (polling edge `sync_log`), so there is
    no separate replay queue to trigger here.
    """

    return {
        "success": True,
        "message": "Sync Core worker runs continuously; nothing to replay.",
    }


@router.get("/ai/audit-mode")
def get_ai_audit_mode(session: Session = Depends(get_db_session)):
    setting = session.execute(
        select(SystemSetting).where(SystemSetting.category == "ai", SystemSetting.key == "audit_mode")
    ).scalar_one_or_none()
    enabled = bool((setting.value or {}).get("enabled")) if setting else False
    return {"enabled": enabled, "updated_at": _serialize_value(setting.updated_at) if setting else None}


@router.post("/ai/audit-mode")
def update_ai_audit_mode(
    payload: AiAuditPayload,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(current_admin_user),
):
    setting = session.execute(
        select(SystemSetting).where(SystemSetting.category == "ai", SystemSetting.key == "audit_mode")
    ).scalar_one_or_none()
    value = {"enabled": payload.enabled, "updated_by": current_user.username, "updated_at": datetime.utcnow().isoformat()}
    if setting:
        setting.value = value
        setting.updated_by = current_user.id
    else:
        setting = SystemSetting(category="ai", key="audit_mode", value=value, updated_by=current_user.id)
        session.add(setting)
    return {"enabled": payload.enabled}


@router.get("/profile/insights")
def profile_insights(
    session: Session = Depends(get_hub_db_session),
    current_user: User = Depends(current_admin_user),
):
    """Expose aggregated profile data for AdminProfileView."""

    pending_reports = 0
    unresolved_conflicts = session.execute(
        text("SELECT COUNT(*) FROM conflict_records WHERE resolved = 0")
    ).scalar() or 0

    security_tips = []
    security_tips.append("举报/审计功能已移除，专注核心交易与同步演示。")
    if unresolved_conflicts:
        security_tips.append(f"同步模块存在 {unresolved_conflicts} 条待解决冲突，建议优先处理。")
    else:
        security_tips.append("同步冲突已全部处理，保持监控即可。")

    recent_actions = []

    return {
        "lastLoginAt": _serialize_value(current_user.last_login_at) if current_user.last_login_at else None,
        "pendingReports": pending_reports,
        "unresolvedConflicts": unresolved_conflicts,
        "securityTips": security_tips,
        "recentActions": recent_actions,
    }
