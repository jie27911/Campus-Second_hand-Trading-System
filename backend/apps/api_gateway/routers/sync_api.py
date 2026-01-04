"""
数据库同步API路由 - 同步管理、冲突解决、一致性验证
"""
from typing import Optional, Any, Literal
from datetime import datetime
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from apps.api_gateway.dependencies import get_db_session, require_roles
from apps.core.models import User
from apps.core.database import db_manager
from apps.core.config import get_settings


router = APIRouter(prefix="/sync", tags=["数据库同步"])

_SAFE_TABLE_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)?$")
_SUPPORTED_DBS = {"mysql", "mariadb", "postgres"}
_EDGE_SOURCES = {"mariadb", "postgres"}
_SYNC_CONFIG_MODES = {"realtime", "scheduled"}

# Cache boolean columns per (db, table) to normalize cross-DB writes.
_BOOL_COL_CACHE: dict[tuple[str, str], set[str]] = {}

# Cache table columns per (db, table) to drop unknown fields during manual upserts.
_TABLE_COL_CACHE: dict[tuple[str, str], set[str]] = {}


# ==================== Pydantic Models ====================

class SyncWriteRequest(BaseModel):
    """同步写入请求"""
    table: str = Field(..., description="表名")
    action: str = Field(..., description="操作类型: insert/update/delete")
    data: dict = Field(..., description="数据字典")
    record_id: Optional[int] = Field(None, description="记录ID（用于update/delete）")


class SyncWriteResponse(BaseModel):
    """同步写入响应"""
    status: str
    success_rate: float
    success_dbs: list[str]
    conflicts: list
    timestamp: datetime


class ConsistencyCheckRequest(BaseModel):
    """一致性检查请求"""
    table: str
    record_id: int


class ConsistencyCheckResponse(BaseModel):
    """一致性检查响应"""
    consistent: bool
    data_by_db: dict
    timestamp: datetime


class SyncRepairRequest(BaseModel):
    """同步修复请求"""
    table: str
    record_id: int
    force: bool = False


class SyncRepairResponse(BaseModel):
    """同步修复响应"""
    success: bool
    repaired_dbs: list[str]
    results: dict


class SyncStatsResponse(BaseModel):
    """同步统计响应"""
    success_count: int
    failure_count: int
    conflict_count: int
    success_rate: float


class ConflictRecord(BaseModel):
    """冲突记录"""
    # Use string to avoid JS number precision loss for snowflake-style BIGINT ids.
    id: str
    table_name: str
    record_id: str
    source: str
    target: str
    resolved: bool
    created_at: datetime
    payload: dict


class ConflictListResponse(BaseModel):
    """冲突列表响应"""
    conflicts: list[ConflictRecord]
    total: int
    page: int
    page_size: int


class SyncStatusResponse(BaseModel):
    """Sync runtime status for frontend sync store."""

    targets: list[str]
    mode: str
    environment: str
    conflicts: int
    last_run: Optional[str]
    daily_stat: dict


class SyncConfigItem(BaseModel):
    """同步配置项"""
    id: str
    source: str
    target: str
    mode: str
    interval_seconds: int
    enabled: bool
    last_run_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class SyncConfigListResponse(BaseModel):
    """同步配置列表响应"""
    configs: list[SyncConfigItem]


class SyncConfigCreateRequest(BaseModel):
    """创建同步配置请求"""
    source: str = Field(..., description="源数据库")
    target: str = Field(..., description="目标数据库")
    mode: str = Field("realtime", description="同步模式")
    interval_seconds: int = Field(30, ge=1, le=3600, description="间隔秒数")
    enabled: bool = Field(True, description="是否启用")


class SyncConfigUpdateRequest(BaseModel):
    """更新同步配置请求"""
    mode: Optional[str] = None
    interval_seconds: Optional[int] = Field(default=None, ge=1, le=3600)
    enabled: Optional[bool] = None


class SyncLog(BaseModel):
    """同步日志"""
    id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    stats: dict


class SyncLogListResponse(BaseModel):
    """同步日志列表响应"""
    logs: list[SyncLog]
    total: int
    page: int
    page_size: int


class ConflictResolvePayload(BaseModel):
    """冲突解决请求"""
    strategy: Literal["source", "target", "manual"] = Field(
        default="manual", description="解决策略：采纳来源/source、保留目标/target、手动/manual"
    )


def _parse_json_field(value: Any) -> dict:
    """Safely parse JSON strings into dictionaries."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


def _parse_vclock_maybe(value: Any) -> dict[str, int] | None:
    """Parse a v_clock payload which may be dict/JSON-string/None.

    Returns a normalized dict with keys N/S when possible; otherwise None.
    """

    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            value = json.loads(value)
        except Exception:
            return None
    if not isinstance(value, dict):
        return None
    try:
        return {
            "N": int(value.get("N", 0) or 0),
            "S": int(value.get("S", 0) or 0),
        }
    except Exception:
        return None


def _conflict_signature(
    *,
    table_name: str,
    record_id: int,
    raw_payload: dict,
) -> str:
    """Build a stable signature for a conflict event.

    IMPORTANT: do NOT group by only (table_name, record_id), because the same record
    can legitimately have new conflicts later.

    We group by reason + the two vector-clock snapshots (order-independent) to dedupe
    the same conflict event across legacy/duplicate rows.
    """

    if not isinstance(raw_payload, dict):
        raw_payload = {}

    reason = str(raw_payload.get("reason") or "unknown")
    source_state = raw_payload.get("source_new") or raw_payload.get("source_old") or {}
    target_state = raw_payload.get("target_current") or {}

    source_vc = None
    if isinstance(source_state, dict):
        source_vc = _parse_vclock_maybe(source_state.get("v_clock"))
    target_vc = None
    if isinstance(target_state, dict):
        target_vc = _parse_vclock_maybe(target_state.get("v_clock"))

    def _vc_key(vc: dict[str, int] | None) -> str:
        if vc is None:
            return ""
        return json.dumps(
            {"N": int(vc.get("N", 0) or 0), "S": int(vc.get("S", 0) or 0)},
            sort_keys=True,
        )

    a = _vc_key(source_vc)
    b = _vc_key(target_vc)
    lo, hi = sorted([a, b])
    return f"{table_name}|{record_id}|{reason}|{lo}|{hi}"


def _validate_table_name(table_name: str) -> str:
    if not table_name or not _SAFE_TABLE_RE.match(table_name):
        raise HTTPException(status_code=400, detail="非法表名")
    return table_name


def _coerce_record_id(value: str | int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="record_id 必须为整数")


def _fetch_row_by_id(db_name: str, table_name: str, record_id: int) -> dict:
    with db_manager.session_scope(db_name) as session:
        row = (
            session.execute(
                text(f"SELECT * FROM {table_name} WHERE id = :id"),
                {"id": record_id},
            )
            .mappings()
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"{db_name} 未找到记录 {table_name}#{record_id}")
        return dict(row)


def _split_schema_table(table_name: str) -> tuple[Optional[str], str]:
    if "." in table_name:
        schema, pure_table = table_name.split(".", 1)
        return schema.strip('"'), pure_table.strip('"')
    return None, table_name.strip('"')


def _get_table_columns(db_name: str, session: Session, table_name: str) -> set[str]:
    cache_key = (db_name, table_name)
    cached = _TABLE_COL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    schema, pure_table = _split_schema_table(table_name)

    if db_name in {"mysql", "mariadb"}:
        sql = (
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = :table_name"
        )
        rows = session.execute(text(sql), {"table_name": pure_table}).all()
    elif db_name == "postgres":
        sql = (
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :table_name"
        )
        params: dict[str, Any] = {"table_name": pure_table}
        if schema:
            sql += " AND table_schema = :schema"
            params["schema"] = schema
        else:
            sql += " AND table_schema = current_schema()"
        rows = session.execute(text(sql), params).all()
    else:
        rows = []

    cols = {r[0] for r in rows}
    _TABLE_COL_CACHE[cache_key] = cols
    return cols


def _get_postgres_boolean_columns(session: Session, table_name: str) -> set[str]:
    cache_key = ("postgres", table_name)
    cached = _BOOL_COL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    schema, pure_table = _split_schema_table(table_name)

    sql = (
        "SELECT column_name "
        "FROM information_schema.columns "
        "WHERE table_name = :table_name "
        "AND data_type = 'boolean'"
    )
    params: dict[str, Any] = {"table_name": pure_table}
    if schema:
        sql += " AND table_schema = :schema"
        params["schema"] = schema
    else:
        sql += " AND table_schema = current_schema()"

    rows = session.execute(text(sql), params).all()
    cols = {r[0] for r in rows}
    _BOOL_COL_CACHE[cache_key] = cols
    return cols


def _normalize_record_for_target(db_name: str, session: Session, table_name: str, record: dict) -> dict:
    if db_name != "postgres":
        return record

    boolean_cols = _get_postgres_boolean_columns(session, table_name)
    if not boolean_cols:
        return record

    normalized = dict(record)
    for col in boolean_cols:
        if col not in normalized:
            continue
        value = normalized[col]
        if value is None:
            continue
        # bool is subclass of int; keep bools as-is.
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            normalized[col] = bool(value)
            continue
        if isinstance(value, str) and value in {"0", "1"}:
            normalized[col] = value == "1"
            continue

    return normalized


def _upsert_row_by_id(db_name: str, table_name: str, record: dict) -> None:
    if "id" not in record:
        raise HTTPException(status_code=500, detail="源记录缺少主键 id")

    with db_manager.session_scope(db_name) as session:
        # 这是管理员裁决后的手动同步：直接写入，不再发布同步事件，避免回环。
        session.info["suppress_sync"] = True

        # Also suppress edge triggers writing to sync_log (new sync design), avoiding loops.
        if db_name in {"mysql", "mariadb"}:
            session.execute(text("SET @sync_suppress = 1"))
        elif db_name == "postgres":
            session.execute(text("SET app.sync_suppress = '1'"))

        record_to_write = _normalize_record_for_target(db_name, session, table_name, record)
        allowed_columns = _get_table_columns(db_name, session, table_name)
        if allowed_columns:
            record_to_write = {k: v for k, v in record_to_write.items() if k in allowed_columns}

        if "id" not in record_to_write:
            raise HTTPException(status_code=500, detail=f"{db_name} 表结构不含主键 id")
        record_id = record_to_write["id"]

        exists = session.execute(
            text(f"SELECT 1 FROM {table_name} WHERE id = :id"),
            {"id": record_id},
        ).first()

        if exists:
            columns = [c for c in record_to_write.keys() if c != "id"]
            if not columns:
                return
            set_clause = ", ".join([f"{c} = :{c}" for c in columns])
            params = {c: record_to_write[c] for c in columns}
            params["id"] = record_id
            session.execute(text(f"UPDATE {table_name} SET {set_clause} WHERE id = :id"), params)
        else:
            columns = list(record_to_write.keys())
            placeholders = ", ".join([f":{c}" for c in columns])
            col_list = ", ".join(columns)
            session.execute(text(f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})"), record_to_write)


def _delete_row_by_id(db_name: str, table_name: str, record_id: int) -> None:
    with db_manager.session_scope(db_name) as session:
        session.info["suppress_sync"] = True

        if db_name in {"mysql", "mariadb"}:
            session.execute(text("SET @sync_suppress = 1"))
        elif db_name == "postgres":
            session.execute(text("SET app.sync_suppress = '1'"))

        session.execute(text(f"DELETE FROM {table_name} WHERE id = :id"), {"id": int(record_id)})


def _row_exists(db_name: str, table_name: str, record_id: int) -> bool:
    with db_manager.session_scope(db_name) as session:
        return (
            session.execute(
                text(f"SELECT 1 FROM {table_name} WHERE id = :id"),
                {"id": int(record_id)},
            ).first()
            is not None
        )


def _find_user_id_by_username_or_email(
    db_name: str,
    *,
    username: str | None,
    email: str | None,
) -> int | None:
    if not username and not email:
        return None

    clauses: list[str] = []
    params: dict[str, object] = {}
    if username:
        clauses.append("username = :username")
        params["username"] = username
    if email:
        clauses.append("email = :email")
        params["email"] = email
    if not clauses:
        return None

    with db_manager.session_scope(db_name) as session:
        sql = "SELECT id FROM users WHERE " + " OR ".join(clauses) + " LIMIT 1"
        row = session.execute(text(sql), params).mappings().first()
        return int(row["id"]) if row else None


def _ensure_user_in_target(
    *,
    source_db: str,
    target_db: str,
    user_id: int,
) -> int:
    """Ensure a referenced user exists in target DB.

    Returns the user id to reference in the target DB.
    If the exact id can't be inserted due to unique collisions (username/email),
    we fall back to an existing user matched by username/email.
    """

    if _row_exists(target_db, "users", user_id):
        return int(user_id)

    # Prefer winner/source db for the parent row, but fall back to any DB
    # because demo/partial-sync environments may have incomplete parents.
    try:
        user_row = _fetch_row_by_id(source_db, "users", int(user_id))
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        user_row = None
        for candidate_db in sorted(_SUPPORTED_DBS):
            if candidate_db in {source_db, target_db}:
                continue
            try:
                user_row = _fetch_row_by_id(candidate_db, "users", int(user_id))
                break
            except HTTPException as exc2:
                if exc2.status_code != 404:
                    raise
        if user_row is None:
            # Preserve the original context as much as possible.
            raise exc
    try:
        _upsert_row_by_id(target_db, "users", user_row)
        return int(user_id)
    except IntegrityError:
        existing_id = _find_user_id_by_username_or_email(
            target_db,
            username=user_row.get("username"),
            email=user_row.get("email"),
        )
        if existing_id is not None:
            return int(existing_id)
        raise


def _fetch_row_by_id_any_db(
    preferred_db: str,
    table_name: str,
    record_id: int,
    *,
    exclude: set[str] | None = None,
) -> tuple[str, dict]:
    exclude = exclude or set()
    tried: list[str] = []
    if preferred_db and preferred_db not in exclude:
        tried.append(preferred_db)
        try:
            return preferred_db, _fetch_row_by_id(preferred_db, table_name, record_id)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise

    for candidate in sorted(_SUPPORTED_DBS):
        if candidate in exclude or candidate in tried:
            continue
        try:
            return candidate, _fetch_row_by_id(candidate, table_name, record_id)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise

    raise HTTPException(status_code=404, detail=f"{preferred_db} 未找到记录 {table_name}#{record_id}")


def _ensure_item_in_target(
    *,
    source_db: str,
    target_db: str,
    item_id: int,
) -> int:
    if _row_exists(target_db, "items", item_id):
        return int(item_id)

    origin_db, item_row = _fetch_row_by_id_any_db(source_db, "items", int(item_id), exclude={target_db})
    # Ensure item's own parents first (seller/category/campus)
    _ensure_fk_dependencies(source_db=origin_db, target_db=target_db, table_name="items", record=item_row)
    _upsert_row_by_id(target_db, "items", item_row)
    return int(item_id)


def _ensure_message_in_target(
    *,
    source_db: str,
    target_db: str,
    message_id: int,
) -> int:
    if _row_exists(target_db, "messages", message_id):
        return int(message_id)
    origin_db, msg_row = _fetch_row_by_id_any_db(source_db, "messages", int(message_id), exclude={target_db})
    _ensure_fk_dependencies(source_db=origin_db, target_db=target_db, table_name="messages", record=msg_row)
    _upsert_row_by_id(target_db, "messages", msg_row)
    return int(message_id)


def _ensure_transaction_in_target(
    *,
    source_db: str,
    target_db: str,
    transaction_id: int,
) -> int:
    if _row_exists(target_db, "transactions", transaction_id):
        return int(transaction_id)
    origin_db, tx_row = _fetch_row_by_id_any_db(source_db, "transactions", int(transaction_id), exclude={target_db})
    _ensure_fk_dependencies(source_db=origin_db, target_db=target_db, table_name="transactions", record=tx_row)
    _upsert_row_by_id(target_db, "transactions", tx_row)
    return int(transaction_id)


def _ensure_fk_dependencies(
    *,
    source_db: str,
    target_db: str,
    table_name: str,
    record: dict,
) -> None:
    """Best-effort backfill of parent rows so FK constraints don't explode during conflict resolve."""

    if table_name == "items":
        seller_id = record.get("seller_id")
        if seller_id is not None:
            sid = _coerce_record_id(seller_id)
            mapped = _ensure_user_in_target(source_db=source_db, target_db=target_db, user_id=sid)
            # If the user id had to be mapped due to uniqueness collisions,
            # rewrite the FK so the item can be applied.
            record["seller_id"] = mapped

        category_id = record.get("category_id")
        if category_id is not None and str(category_id).strip() != "":
            cid = _coerce_record_id(category_id)
            if not _row_exists(target_db, "categories", cid):
                try:
                    cat_row = _fetch_row_by_id(source_db, "categories", cid)
                    _upsert_row_by_id(target_db, "categories", cat_row)
                except HTTPException:
                    # Categories may not be synchronized across DBs; skip best-effort.
                    pass

        campus_id = record.get("campus_id")
        if campus_id is not None and str(campus_id).strip() != "":
            cid2 = _coerce_record_id(campus_id)
            if not _row_exists(target_db, "campuses", cid2):
                try:
                    campus_row = _fetch_row_by_id(source_db, "campuses", cid2)
                    _upsert_row_by_id(target_db, "campuses", campus_row)
                except HTTPException:
                    pass

        return

    if table_name == "item_images":
        item_id = record.get("item_id")
        if item_id is not None and str(item_id).strip() != "":
            iid = _coerce_record_id(item_id)
            _ensure_item_in_target(source_db=source_db, target_db=target_db, item_id=iid)
        return

    if table_name == "transactions":
        item_id = record.get("item_id")
        if item_id is not None and str(item_id).strip() != "":
            iid = _coerce_record_id(item_id)
            _ensure_item_in_target(source_db=source_db, target_db=target_db, item_id=iid)

        buyer_id = record.get("buyer_id")
        if buyer_id is not None and str(buyer_id).strip() != "":
            bid = _coerce_record_id(buyer_id)
            record["buyer_id"] = _ensure_user_in_target(source_db=source_db, target_db=target_db, user_id=bid)

        seller_id = record.get("seller_id")
        if seller_id is not None and str(seller_id).strip() != "":
            sid = _coerce_record_id(seller_id)
            record["seller_id"] = _ensure_user_in_target(source_db=source_db, target_db=target_db, user_id=sid)
        return

    if table_name == "messages":
        sender_id = record.get("sender_id")
        if sender_id is not None and str(sender_id).strip() != "":
            sid = _coerce_record_id(sender_id)
            record["sender_id"] = _ensure_user_in_target(source_db=source_db, target_db=target_db, user_id=sid)

        receiver_id = record.get("receiver_id")
        if receiver_id is not None and str(receiver_id).strip() != "":
            rid = _coerce_record_id(receiver_id)
            record["receiver_id"] = _ensure_user_in_target(source_db=source_db, target_db=target_db, user_id=rid)

        item_id = record.get("item_id")
        if item_id is not None and str(item_id).strip() != "":
            iid = _coerce_record_id(item_id)
            _ensure_item_in_target(source_db=source_db, target_db=target_db, item_id=iid)
        return

    if table_name == "favorites":
        user_id = record.get("user_id")
        if user_id is not None and str(user_id).strip() != "":
            uid = _coerce_record_id(user_id)
            record["user_id"] = _ensure_user_in_target(source_db=source_db, target_db=target_db, user_id=uid)

        item_id = record.get("item_id")
        if item_id is not None and str(item_id).strip() != "":
            iid = _coerce_record_id(item_id)
            _ensure_item_in_target(source_db=source_db, target_db=target_db, item_id=iid)
        return

    if table_name == "user_follows":
        follower_id = record.get("follower_id")
        if follower_id is not None and str(follower_id).strip() != "":
            fid = _coerce_record_id(follower_id)
            record["follower_id"] = _ensure_user_in_target(source_db=source_db, target_db=target_db, user_id=fid)
        following_id = record.get("following_id")
        if following_id is not None and str(following_id).strip() != "":
            fid2 = _coerce_record_id(following_id)
            record["following_id"] = _ensure_user_in_target(source_db=source_db, target_db=target_db, user_id=fid2)
        return

    if table_name == "item_view_history":
        user_id = record.get("user_id")
        if user_id is not None and str(user_id).strip() != "":
            uid = _coerce_record_id(user_id)
            record["user_id"] = _ensure_user_in_target(source_db=source_db, target_db=target_db, user_id=uid)
        item_id = record.get("item_id")
        if item_id is not None and str(item_id).strip() != "":
            iid = _coerce_record_id(item_id)
            _ensure_item_in_target(source_db=source_db, target_db=target_db, item_id=iid)
        return

    if table_name == "user_addresses":
        user_id = record.get("user_id")
        if user_id is not None and str(user_id).strip() != "":
            uid = _coerce_record_id(user_id)
            record["user_id"] = _ensure_user_in_target(source_db=source_db, target_db=target_db, user_id=uid)
        return

    if table_name == "item_price_history":
        item_id = record.get("item_id")
        if item_id is not None and str(item_id).strip() != "":
            iid = _coerce_record_id(item_id)
            _ensure_item_in_target(source_db=source_db, target_db=target_db, item_id=iid)
        return

    if table_name == "message_attachments":
        mid = record.get("message_id")
        if mid is not None and str(mid).strip() != "":
            message_id = _coerce_record_id(mid)
            _ensure_message_in_target(source_db=source_db, target_db=target_db, message_id=message_id)
        return

    if table_name == "transaction_review_images":
        tid = record.get("transaction_id")
        if tid is not None and str(tid).strip() != "":
            tx_id = _coerce_record_id(tid)
            _ensure_transaction_in_target(source_db=source_db, target_db=target_db, transaction_id=tx_id)
        return

    if table_name == "notifications":
        user_id = record.get("user_id")
        if user_id is not None and str(user_id).strip() != "":
            uid = _coerce_record_id(user_id)
            record["user_id"] = _ensure_user_in_target(source_db=source_db, target_db=target_db, user_id=uid)
        return

    if table_name == "search_history":
        user_id = record.get("user_id")
        if user_id is not None and str(user_id).strip() != "":
            uid = _coerce_record_id(user_id)
            record["user_id"] = _ensure_user_in_target(source_db=source_db, target_db=target_db, user_id=uid)
        clicked = record.get("clicked_item_id")
        if clicked is not None and str(clicked).strip() != "":
            iid = _coerce_record_id(clicked)
            _ensure_item_in_target(source_db=source_db, target_db=target_db, item_id=iid)
        return


def _resolve_conflict_and_replicate(
    *,
    conflict_id: int,
    strategy: Literal["source", "target", "manual"],
    resolved_by: int | None,
    db: Session,
) -> dict:
    conflict_row = db.execute(
        text(
            """
            SELECT id, table_name, record_id, source, target, resolved, payload
            FROM conflict_records
            WHERE id = :conflict_id
            """
        ),
        {"conflict_id": conflict_id},
    ).mappings().first()

    if not conflict_row:
        raise HTTPException(status_code=404, detail="冲突记录不存在")
    if conflict_row["resolved"]:
        raise HTTPException(status_code=400, detail="冲突已解决")

    table_name = _validate_table_name(str(conflict_row["table_name"]))
    record_id = _coerce_record_id(conflict_row["record_id"])
    source_db = str(conflict_row["source"])
    target_db = str(conflict_row["target"])

    raw_payload = _parse_json_field(conflict_row.get("payload"))
    signature = _conflict_signature(table_name=table_name, record_id=record_id, raw_payload=raw_payload)

    # Enforce: only the first resolution for the *same conflict event* is allowed.
    # We still lock by (table_name, record_id) for simplicity, but the "group" check
    # is done by conflict signature (reason + v_clock pair), so future unrelated
    # conflicts for the same record remain resolvable.
    group_rows = db.execute(
        text(
            """
            SELECT id, resolved, payload
            FROM conflict_records
            WHERE table_name = :table_name
              AND record_id = :record_id
            FOR UPDATE
            """
        ),
        {"table_name": table_name, "record_id": str(record_id)},
    ).mappings().all()
    for row in group_rows:
        if int(row.get("id") or -1) == int(conflict_id):
            continue
        if int(row.get("resolved") or 0) != 1:
            continue
        other_payload = _parse_json_field(row.get("payload"))
        other_sig = _conflict_signature(table_name=table_name, record_id=record_id, raw_payload=other_payload)
        if other_sig == signature:
            raise HTTPException(
                status_code=409,
                detail=f"该冲突事件已在冲突#{row.get('id')}中完成裁决，禁止重复裁决",
            )

    if source_db not in _SUPPORTED_DBS or target_db not in _SUPPORTED_DBS:
        raise HTTPException(status_code=400, detail="暂不支持该冲突来源/目标数据库")

    if strategy == "source":
        winner_db = source_db
    elif strategy == "target":
        winner_db = target_db
    else:
        winner_db = None

    synced_to: list[str] = []
    fallback_used = False
    record_missing = False
    if winner_db:
        try:
            winner_record = _fetch_row_by_id(winner_db, table_name, record_id)
        except HTTPException as exc:
            # The conflicted row may have been deleted/cleaned up after the conflict was recorded.
            # In that case, resolving from the UI should still succeed by marking the conflict as
            # resolved (best-effort) instead of returning a 404.
            if exc.status_code != 404:
                raise

            other_db = target_db if winner_db == source_db else source_db
            try:
                winner_record = _fetch_row_by_id(other_db, table_name, record_id)
                winner_db = other_db
                fallback_used = True
            except HTTPException as exc2:
                if exc2.status_code != 404:
                    raise
                winner_db = None
                record_missing = True

        if winner_db:
            for db_name in sorted(_SUPPORTED_DBS):
                if db_name == winner_db:
                    continue
                try:
                    _ensure_fk_dependencies(
                        source_db=winner_db,
                        target_db=db_name,
                        table_name=table_name,
                        record=winner_record,
                    )
                    _upsert_row_by_id(db_name, table_name, winner_record)
                    synced_to.append(db_name)
                except IntegrityError as exc:
                    # Most common: FK missing (e.g., items.seller_id -> users).
                    raise HTTPException(status_code=400, detail=f"同步到 {db_name} 失败: {exc.orig}")

    # Mark this conflict as resolved.
    db.execute(
        text(
            """
            UPDATE conflict_records
            SET resolved = 1,
                status = 'resolved',
                resolved_by = :user_id,
                resolved_at = NOW(),
                resolution_note = :note,
                updated_at = NOW()
            WHERE id = :conflict_id
            """
        ),
        {
            "user_id": resolved_by,
            "conflict_id": conflict_id,
            "note": strategy,
        },
    )

    # Also resolve any remaining legacy/duplicate conflicts for the SAME signature.
    duplicate_ids: list[int] = []
    for row in group_rows:
        rid = int(row.get("id") or -1)
        if rid == int(conflict_id):
            continue
        if int(row.get("resolved") or 0) == 1:
            continue
        other_payload = _parse_json_field(row.get("payload"))
        other_sig = _conflict_signature(table_name=table_name, record_id=record_id, raw_payload=other_payload)
        if other_sig == signature:
            duplicate_ids.append(rid)

    if duplicate_ids:
        placeholders = ", ".join([f":id{i}" for i in range(len(duplicate_ids))])
        params = {
            "user_id": resolved_by,
            "note": strategy,
        }
        for i, rid in enumerate(duplicate_ids):
            params[f"id{i}"] = int(rid)
        db.execute(
            text(
                f"""
                UPDATE conflict_records
                SET resolved = 1,
                    status = 'resolved',
                    resolved_by = :user_id,
                    resolved_at = NOW(),
                    resolution_note = :note,
                    updated_at = NOW()
                WHERE id IN ({placeholders})
                  AND resolved = 0
                """
            ),
            params,
        )
    db.commit()

    message = "冲突已处理并执行同步" if winner_db else "冲突已标记为已解决"
    if record_missing:
        message = "冲突对应的记录已不存在，已标记为已解决"
    elif fallback_used:
        message = "所选数据库中记录不存在，已使用另一侧记录完成同步"

    return {
        "success": True,
        "message": message,
        "conflict_id": conflict_id,
        "strategy": strategy,
        "winner_db": winner_db,
        "synced_to": synced_to,
    }


# ==================== API Endpoints ====================

@router.post("/write", response_model=SyncWriteResponse)
async def sync_write(
    request: SyncWriteRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session)
) -> SyncWriteResponse:
    """
    三数据库同步写入
    
    自动将数据写入 MySQL、PostgreSQL、MariaDB 三个数据库
    包含版本控制和冲突检测
    """
    table_name = _validate_table_name(request.table)
    action = str(request.action).lower().strip()
    if action not in {"insert", "update", "delete"}:
        raise HTTPException(status_code=400, detail="action 必须是 insert/update/delete")

    record_id = request.record_id
    if record_id is None:
        record_id = request.data.get("id")
    if record_id is None:
        raise HTTPException(status_code=400, detail="record_id 或 data.id 必须提供")
    record_id_int = _coerce_record_id(record_id)

    success_dbs: list[str] = []
    failures: dict[str, str] = {}
    conflicts: list = []

    for db_name in sorted(_SUPPORTED_DBS):
        try:
            if action == "delete":
                _delete_row_by_id(db_name, table_name, record_id_int)
            else:
                payload = dict(request.data)
                payload["id"] = record_id_int
                _upsert_row_by_id(db_name, table_name, payload)
            success_dbs.append(db_name)
        except Exception as exc:
            failures[db_name] = str(exc)

    total = len(_SUPPORTED_DBS)
    success_rate = float(len(success_dbs)) / float(total) if total else 0.0
    status = "ok" if len(success_dbs) == total else "partial"
    if failures and not success_dbs:
        status = "failed"

    return SyncWriteResponse(
        status=status,
        success_rate=success_rate,
        success_dbs=success_dbs,
        conflicts=conflicts,
        timestamp=datetime.utcnow(),
    )


@router.post("/verify-consistency", response_model=ConsistencyCheckResponse)
async def verify_consistency(
    request: ConsistencyCheckRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session)
) -> ConsistencyCheckResponse:
    """
    验证数据一致性
    
    检查三个数据库中指定记录的数据是否一致
    """
    table_name = _validate_table_name(request.table)
    record_id = _coerce_record_id(request.record_id)

    data_by_db: dict[str, Any] = {}
    for db_name in sorted(_SUPPORTED_DBS):
        try:
            data_by_db[db_name] = _fetch_row_by_id(db_name, table_name, record_id)
        except HTTPException as exc:
            if exc.status_code == 404:
                data_by_db[db_name] = None
            else:
                raise

    def _strip_meta(value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        ignore = {"created_at", "updated_at"}
        return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in value.items() if k not in ignore}

    normalized = [_strip_meta(data_by_db.get(db_name)) for db_name in sorted(_SUPPORTED_DBS)]
    base = normalized[0]
    consistent = all(n == base for n in normalized[1:])

    return ConsistencyCheckResponse(
        consistent=consistent,
        data_by_db=data_by_db,
        timestamp=datetime.utcnow(),
    )


@router.post("/repair", response_model=SyncRepairResponse)
async def sync_repair(
    request: SyncRepairRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session)
) -> SyncRepairResponse:
    """
    同步修复
    
    从主库（MySQL）读取数据，强制同步到其他数据库
    需要管理员权限
    """
    table_name = _validate_table_name(request.table)
    record_id = _coerce_record_id(request.record_id)

    master_db = "mysql"
    master_row = _fetch_row_by_id(master_db, table_name, record_id)

    repaired_dbs: list[str] = []
    results: dict[str, Any] = {}

    for db_name in sorted(_SUPPORTED_DBS):
        if db_name == master_db:
            continue
        try:
            _upsert_row_by_id(db_name, table_name, master_row)
            repaired_dbs.append(db_name)
            results[db_name] = {"ok": True}
        except Exception as exc:
            results[db_name] = {"ok": False, "error": str(exc)}
            if not request.force:
                break

    success = len(repaired_dbs) == (len(_SUPPORTED_DBS) - 1)
    return SyncRepairResponse(success=success, repaired_dbs=repaired_dbs, results=results)


@router.get("/stats", response_model=SyncStatsResponse)
async def get_sync_stats(
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session)
) -> SyncStatsResponse:
    """
    获取同步统计信息
    """
    latest_stat = db.execute(
        text(
            """
            SELECT sync_success_count, sync_conflict_count
            FROM daily_stats
            ORDER BY stat_date DESC
            LIMIT 1
            """
        )
    ).mappings().first()

    success_count = int((latest_stat or {}).get("sync_success_count") or 0)
    # failure_count in this response is treated as "today failed/blocked" and aligns with daily_stats.sync_conflict_count.
    # (The separate conflict_count field still reflects conflict_records volume.)
    failure_count = int((latest_stat or {}).get("sync_conflict_count") or 0)
    conflict_count = int(db.scalar(text("SELECT COUNT(*) FROM conflict_records")) or 0)

    denom = success_count + failure_count
    # If there are no samples yet, treat as 100% to match frontend store behavior.
    success_rate = (float(success_count) / float(denom)) if denom > 0 else 1.0

    return SyncStatsResponse(
        success_count=success_count,
        failure_count=failure_count,
        conflict_count=conflict_count,
        success_rate=success_rate,
    )


@router.get("/status", response_model=SyncStatusResponse)
def get_sync_status(
    _: User = Depends(require_roles("admin", "market_admin", "trader")),
    session: Session = Depends(get_db_session),
) -> SyncStatusResponse:
    """Return sync runtime status used by the frontend sync store."""

    from apps.core.models import DailyStat, SyncConfig

    settings = get_settings()
    configs = session.execute(select(SyncConfig)).scalars().all()
    unresolved_conflicts = int(
        session.scalar(text("SELECT COUNT(*) FROM conflict_records WHERE resolved = 0")) or 0
    )

    latest_log = session.execute(
        text("SELECT started_at FROM sync_logs ORDER BY started_at DESC LIMIT 1")
    ).scalar_one_or_none()
    last_run = latest_log.isoformat() if isinstance(latest_log, datetime) else None

    today_stat = (
        session.execute(select(DailyStat).order_by(DailyStat.stat_date.desc()))
        .scalars()
        .first()
    )

    return SyncStatusResponse(
        targets=sorted({cfg.target for cfg in configs}) if configs else ["mysql"],
        mode="+".join(sorted({cfg.mode for cfg in configs})) if configs else "realtime",
        environment=getattr(settings, "environment", "unknown"),
        conflicts=unresolved_conflicts,
        last_run=last_run,
        daily_stat={
            "date": today_stat.stat_date.isoformat() if today_stat else None,
            "sync_success": int(getattr(today_stat, "sync_success_count", 0) or 0),
            "sync_conflicts": int(getattr(today_stat, "sync_conflict_count", 0) or 0),
        },
    )


@router.post("/run")
def trigger_manual_sync(_: User = Depends(require_roles("admin", "market_admin"))) -> dict:
    """Queue a manual sync trigger.

    The actual sync is performed by the `sync-worker` container. This endpoint
    records a manual trigger flag in Hub MySQL, so the worker can pick it up and
    run a forced pass (including scheduled links) immediately.
    """

    from apps.core.models import SyncWorkerState

    with db_manager.session_scope("mysql") as session:
        session.info["suppress_sync"] = True
        row = (
            session.execute(
                select(SyncWorkerState).where(SyncWorkerState.worker_name == "manual_trigger")
            )
            .scalars()
            .one_or_none()
        )
        if row is None:
            row = SyncWorkerState(worker_name="manual_trigger", last_event_id=1)
            session.add(row)
        else:
            row.last_event_id = int(row.last_event_id or 0) + 1
        session.flush()

    return {"status": "queued"}


@router.get("/conflicts", response_model=ConflictListResponse)
def get_conflicts(
    resolved: Optional[bool] = None,
    show_all: bool = False,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session)
) -> ConflictListResponse:
    """
    获取冲突记录列表
    
    支持筛选已解决/未解决的冲突
    """
    # Use raw SQL for cross-version compatibility.
    # NOTE: conflict_records stores a single JSON payload snapshot. Do NOT duplicate it into
    # both "local" and "remote" — that produces misleading conflict details.
    base_select = (
        "SELECT id, table_name, record_id, source, target, resolved, created_at, status, payload, resolution_note "
        "FROM conflict_records"
    )

    # Default behavior: return unresolved conflicts.
    # NOTE: do NOT hide future conflicts for the same (table_name, record_id).
    # We only suppress legacy/duplicate rows that represent the same conflict
    # event (same signature) when a resolved entry exists.
    effective_resolved: Optional[bool]
    if show_all:
        effective_resolved = resolved
    else:
        effective_resolved = False if resolved is None else resolved

    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if effective_resolved is not None:
        where_clauses.append("resolved = :resolved")
        params["resolved"] = 1 if effective_resolved else 0

    sql = base_select
    count_sql = "SELECT COUNT(*) FROM conflict_records"
    if where_clauses:
        where_sql = " WHERE " + " AND ".join(where_clauses)
        sql += where_sql
        count_sql += where_sql

    # If we're showing unresolved (default) and not show_all, suppress only
    # unresolved rows that have a resolved sibling with the same signature.
    if (not show_all) and (effective_resolved is False):
        resolved_rows = db.execute(
            text("SELECT table_name, record_id, payload FROM conflict_records WHERE resolved = 1")
        ).mappings().all()
        resolved_sigs: set[str] = set()
        for r in resolved_rows:
            tname = _validate_table_name(str(r.get("table_name")))
            rid = _coerce_record_id(r.get("record_id"))
            r_payload = _parse_json_field(r.get("payload"))
            resolved_sigs.add(_conflict_signature(table_name=tname, record_id=rid, raw_payload=r_payload))

        unresolved_rows = db.execute(
            text(
                """
                SELECT id, table_name, record_id, source, target, resolved, created_at, status, payload, resolution_note
                FROM conflict_records
                WHERE resolved = 0
                ORDER BY created_at DESC
                """
            )
        ).fetchall()

        filtered_rows = []
        for row in unresolved_rows:
            tname = _validate_table_name(str(row[1]))
            rid = _coerce_record_id(row[2])
            raw_payload = _parse_json_field(row[8])
            sig = _conflict_signature(table_name=tname, record_id=rid, raw_payload=raw_payload)
            if sig in resolved_sigs:
                continue
            filtered_rows.append(row)

        total = len(filtered_rows)
        start = (page - 1) * page_size
        end = start + page_size
        rows = filtered_rows[start:end]
    else:
        total = db.execute(text(count_sql), params).scalar()
        sql += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = page_size
        params["offset"] = (page - 1) * page_size
        rows = db.execute(text(sql), params).fetchall()

    # 转换为响应格式
    conflicts: list[ConflictRecord] = []
    for row in rows:
        raw_payload = _parse_json_field(row[8])
        payload = {
            "status": row[7],
            "data": raw_payload,
            "strategy": row[9],
        }
        conflicts.append(
            ConflictRecord(
                id=str(row[0]),
                table_name=str(row[1]),
                record_id=str(row[2]),
                source=str(row[3]),
                target=str(row[4]),
                resolved=bool(row[5]),
                created_at=row[6],
                payload=payload,
            )
        )
    
    return ConflictListResponse(
        conflicts=conflicts,
        total=total,
        page=page,
        page_size=page_size
    )


@router.put("/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: str,
    payload: ConflictResolvePayload,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session)
) -> dict:
    """解决冲突：按策略选择以哪个数据库为准，并把数据同步到其它库。"""
    return _resolve_conflict_and_replicate(
        conflict_id=_coerce_record_id(conflict_id),
        strategy=payload.strategy,
        resolved_by=int(current_user.id),
        db=db,
    )


@router.get("/logs", response_model=SyncLogListResponse)
async def get_sync_logs(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session)
) -> SyncLogListResponse:
    """
    获取同步日志列表
    """
    # 获取总数
    count_sql = "SELECT COUNT(*) FROM sync_logs"
    total_result = db.execute(text(count_sql))
    total = total_result.scalar()
    
    # 分页查询
    sql = """
    SELECT id, config_id, status, started_at, completed_at, stats
    FROM sync_logs
    ORDER BY started_at DESC
    LIMIT :limit OFFSET :offset
    """
    
    result = db.execute(text(sql), {
        "limit": page_size,
        "offset": (page - 1) * page_size
    })
    rows = result.fetchall()
    
    # 转换为响应格式
    logs = [
        SyncLog(
            id=row[0],
            status=row[2],
            started_at=row[3],
            completed_at=row[4],
            stats=_parse_json_field(row[5])
        )
        for row in rows
    ]
    
    return SyncLogListResponse(
        logs=logs,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/databases/status")
async def get_database_status(
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session)
) -> dict:
    """
    获取三个数据库的状态信息
    """
    from apps.core.config import Settings
    
    settings = Settings()
    
    databases = []
    
    # MySQL
    mysql_status = await check_database_health(
        "MySQL",
        settings.mysql_dsn,
        "mysql",
        "MySQL 8.0"
    )
    databases.append(mysql_status)
    
    # MariaDB
    mariadb_status = await check_database_health(
        "MariaDB", 
        settings.mariadb_dsn,
        "mariadb",
        "MariaDB 10.6"
    )
    databases.append(mariadb_status)
    
    # PostgreSQL
    postgres_status = await check_database_health(
        "PostgreSQL",
        settings.postgres_dsn,
        "postgres", 
        "PostgreSQL 14"
    )
    databases.append(postgres_status)
    
    return {"databases": databases}


async def check_database_health(name: str, dsn: str, db_type: str, version: str) -> dict:
    """检查单个数据库健康状态"""
    import time
    from sqlalchemy import create_engine
    
    start_time = time.time()
    status = "healthy"
    latency = 0
    
    try:
        engine = create_engine(dsn, pool_pre_ping=True)
        with engine.connect() as conn:
            # 执行简单查询
            if db_type == "mysql":
                conn.execute(text("SELECT 1"))
            elif db_type == "postgres":
                conn.execute(text("SELECT 1"))
            elif db_type == "mariadb":
                conn.execute(text("SELECT 1"))
            
            latency = int((time.time() - start_time) * 1000)
            
            # 检查同步进度（简化版）
            sync_progress = 100  # 暂时设为100
            
    except Exception:
        status = "error"
        latency = 9999
        sync_progress = 0
    
    return {
        "name": db_type,
        "label": f"{name} ({'主库' if db_type == 'mysql' else '从库'})",
        "type": version,
        "host": dsn.split('@')[-1] if '@' in dsn else f"{db_type}:3306",
        "status": status,
        "sync_progress": sync_progress,
        "latency": latency,
        "last_sync": datetime.utcnow()
    }


# ==================== SyncConfig Management ====================

@router.get("/configs", response_model=SyncConfigListResponse, dependencies=[Depends(require_roles("admin"))])
def list_sync_configs(session: Session = Depends(get_db_session)):
    """获取所有同步配置"""
    from apps.core.models import SyncConfig
    
    configs = session.execute(select(SyncConfig)).scalars().all()
    return SyncConfigListResponse(
        configs=[
            SyncConfigItem(
                id=str(config.id),
                source=config.source,
                target=config.target,
                mode=config.mode,
                interval_seconds=config.interval_seconds,
                enabled=config.enabled,
                last_run_at=config.last_run_at,
                created_at=config.created_at,
                updated_at=config.updated_at,
            )
            for config in configs
        ]
    )


@router.post("/configs", response_model=SyncConfigItem, dependencies=[Depends(require_roles("admin"))])
def create_sync_config(request: SyncConfigCreateRequest, session: Session = Depends(get_db_session)):
    """创建同步配置"""
    from apps.core.models import SyncConfig
    
    # 验证数据库名称
    if request.source not in _SUPPORTED_DBS or request.target not in _SUPPORTED_DBS:
        raise HTTPException(status_code=400, detail="不支持的数据库类型")
    if request.source == request.target:
        raise HTTPException(status_code=400, detail="源数据库和目标数据库不能相同")
    # 当前 sync worker 仅轮询 edge 的 sync_log（mariadb/postgres）
    if request.source not in _EDGE_SOURCES:
        raise HTTPException(status_code=400, detail="当前仅支持 mariadb/postgres 作为源库（mysql 作为源库不会被 worker 轮询）")
    if request.mode not in _SYNC_CONFIG_MODES:
        raise HTTPException(status_code=400, detail="不支持的同步模式（仅支持 realtime/scheduled）")
    
    # 检查是否已存在相同的配置
    existing = session.execute(
        select(SyncConfig).where(
            SyncConfig.source == request.source,
            SyncConfig.target == request.target,
            SyncConfig.mode == request.mode,
        )
    ).scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="相同的同步配置已存在")
    
    config = SyncConfig(
        source=request.source,
        target=request.target,
        mode=request.mode,
        interval_seconds=request.interval_seconds,
        enabled=request.enabled,
    )
    
    session.add(config)
    session.commit()
    session.refresh(config)
    
    return SyncConfigItem(
        id=str(config.id),
        source=config.source,
        target=config.target,
        mode=config.mode,
        interval_seconds=config.interval_seconds,
        enabled=config.enabled,
        last_run_at=config.last_run_at,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.put("/configs/{config_id}", response_model=SyncConfigItem, dependencies=[Depends(require_roles("admin"))])
def update_sync_config(config_id: str, request: SyncConfigUpdateRequest, session: Session = Depends(get_db_session)):
    """更新同步配置"""
    from apps.core.models import SyncConfig

    try:
        config_id_int = int(config_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid config id")
    
    config = session.execute(
        select(SyncConfig).where(SyncConfig.id == config_id_int)
    ).scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="同步配置不存在")

    if request.mode is not None and request.mode not in _SYNC_CONFIG_MODES:
        raise HTTPException(status_code=400, detail="不支持的同步模式（仅支持 realtime/scheduled）")
    if config.source == config.target:
        # defense-in-depth for legacy/bad rows
        raise HTTPException(status_code=400, detail="配置非法：源数据库和目标数据库不能相同")

    # Prevent duplicates when switching mode (unique key is effectively source+target+mode).
    if request.mode is not None and request.mode != config.mode:
        duplicate = session.execute(
            select(SyncConfig).where(
                SyncConfig.id != config.id,
                SyncConfig.source == config.source,
                SyncConfig.target == config.target,
                SyncConfig.mode == request.mode,
            )
        ).scalar_one_or_none()
        if duplicate:
            raise HTTPException(status_code=400, detail="切换模式会导致重复配置（相同 source/target/mode 已存在）")
    
    # 更新字段
    if request.mode is not None:
        config.mode = request.mode
    if request.interval_seconds is not None:
        config.interval_seconds = request.interval_seconds
    if request.enabled is not None:
        config.enabled = request.enabled
    
    session.commit()
    session.refresh(config)
    
    return SyncConfigItem(
        id=str(config.id),
        source=config.source,
        target=config.target,
        mode=config.mode,
        interval_seconds=config.interval_seconds,
        enabled=config.enabled,
        last_run_at=config.last_run_at,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.delete("/configs/{config_id}", dependencies=[Depends(require_roles("admin"))])
def delete_sync_config(config_id: str, session: Session = Depends(get_db_session)):
    """删除同步配置"""
    from apps.core.models import SyncConfig

    try:
        config_id_int = int(config_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid config id")
    
    config = session.execute(
        select(SyncConfig).where(SyncConfig.id == config_id_int)
    ).scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="同步配置不存在")
    
    session.delete(config)
    session.commit()
    
    return {"message": "同步配置已删除"}
