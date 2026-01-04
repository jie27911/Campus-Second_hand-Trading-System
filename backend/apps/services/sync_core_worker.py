"""Sync Core 同步 Worker（Hub 侧）：基于触发器日志的跨库同步。

整体思路（High-level）
----------------------
本 Worker 实现的是“应用层跨数据库同步”，刻意不使用 MySQL/Postgres 的原生复制。
它的核心链路是：

1）Edge 侧触发器 -> 追加写入变更事件（append-only）
        - Edge 数据库（MariaDB/PostgreSQL）通过“轻量触发器”把行级变更快照写入
            `sync_log` 表。
        - 每条事件包含：table_name、data_id、operation、old_data/new_data、occurred_at。
        - 初始 status=0，表示未被 Hub 消费。

2）Hub 侧轮询 Worker -> 消费日志并写入目标库
        - Hub 运行本 Worker 作为消费者。
        - 对每个 origin（mariadb/postgres），Hub 的 `sync_worker_state` 保存一个游标：
            worker_name -> last_event_id，用于“可重启/断点续跑”。
        - 拉取边缘日志的典型 SQL：
                    SELECT ... FROM sync_log
                    WHERE status=0 AND log_id > cursor
                    ORDER BY log_id ASC
                    LIMIT batch_size

3）用向量时钟（v_clock）做冲突检测
        - 每条业务记录带一个 `v_clock` 字段（JSON 文本），表示跨 origin 的版本向量。
            MariaDB 本地写入会 bump "N" 分量，Postgres 本地写入会 bump "S" 分量。
        - 同步时比较 source v_clock 与 target 当前 v_clock：
                - dominates（支配/更新） -> 覆盖写入（UPSERT）
                - concurrent（并发） -> 写入 Hub `conflict_records`，不直接覆盖

4）回环抑制（trigger suppression）避免无限循环
        - 同步写入目标库时，必须禁止目标库触发器再次写 `sync_log`（否则会形成回环）。
        - MariaDB/MySQL：使用会话变量 `SET @sync_suppress = 1`。
        - Postgres：使用会话变量 `SET app.sync_suppress = '1'`。
        - Edge 侧触发器会检查这些标志，开启时跳过记录日志 / 跳过 v_clock bump。

关键语义（Important semantics）
------------------------------
- `sync_log.status` 目前是“按 origin 的已处理标记”（0/1），不是“按 target 的 ACK”。
    这让实现更简单，但意味着：一旦标记 processed，不会为了“新增 target”去重放。
- 定时同步（scheduled）通过 Hub 的 `sync_configs`（mode=scheduled）支持；
    Worker 会在 Hub 维护每条配置的 `last_run_at`。
"""

from __future__ import annotations

import json
import base64
import datetime as _dt
from decimal import Decimal
import os
import signal
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event
from typing import Any, Dict, Iterable, Optional, Tuple

from loguru import logger
from sqlalchemy import bindparam, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from apps.core.database import db_manager
from apps.core.models import ConflictRecord, DailyStat, SyncConfig, SyncLog, SyncWorkerState
from apps.services.notifications import email_notifier
from apps.core.config import get_settings
from apps.core.conflict_tokens import create_conflict_token


STOP_EVENT = Event()  # shared shutdown signal for the long-running loop


# === 同步拓扑配置（Replication topology constants）===
#
# EDGE_ORIGINS：将“逻辑 origin DB”映射到它负责 bump 的向量时钟分量。
# - MariaDB（主库/北区）负责 bump "N"
# - Postgres（分库/南区）负责 bump "S"
EDGE_ORIGINS: dict[str, str] = {
    "mariadb": "N",
    "postgres": "S",
}

# 只有这些表会被 Worker 同步。
# 其它表会被忽略（但对应的 edge 日志仍会被标记 processed，以推进队列）。
TRACKED_TABLES: set[str] = {
    "users",
    "user_profiles",
    "items",
    "item_images",
    "transactions",
    "messages",
    "favorites",
}


@dataclass(frozen=True)
class EdgeLogRow:
    """对 edge 侧 `sync_log` 行的统一结构化表示。

    说明：不同数据库对 JSON 快照的存储/返回类型不一致：
    - Postgres 通常是 JSONB（驱动可能直接返回 dict/list）
    - MariaDB 往往是 LONGTEXT（驱动返回 str/bytes）
    `_parse_json_maybe()` 会尽量把它们统一成 Python dict/list。
    """
    log_id: int
    table_name: str
    data_id: int
    operation: str
    old_data: Any
    new_data: Any
    occurred_at: Optional[datetime]


def _utc_now() -> datetime:
    """返回一个 UTC 的 aware datetime。

    约定：所有“定时/间隔”计算统一用 UTC，避免 tz/naive 混用导致的异常。
    """
    return datetime.now(timezone.utc)


def _as_utc_aware(value: Optional[datetime]) -> Optional[datetime]:
    """把 DB 驱动返回的时间统一成 UTC aware。

    一些 MySQL/MariaDB 驱动即使存的是“带时区语义”的时间，也可能返回 naive。
    这里约定：naive 一律按 UTC 解释，用于定时调度计算。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_json_maybe(value: Any) -> Any:
    """尽力解析 JSON（best-effort）。

    Edge 触发器写入的 old/new 快照，可能以如下形式被驱动返回：
    - dict/list（驱动已解析）
    - bytes
    - string
    该函数尽量把它们转换成 Python 对象；解析失败则原样返回。
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _parse_vclock(value: Any) -> dict[str, int]:
    """解析 v_clock，统一成包含 {"N","S"} 的 dict。

    v_clock 期望是类似 {"N": 3, "S": 1} 的 JSON 文本。
    缺失的分量默认按 0 处理。
    """
    parsed = _parse_json_maybe(value)
    if isinstance(parsed, dict):
        return {
            "N": int(parsed.get("N", 0) or 0),
            "S": int(parsed.get("S", 0) or 0),
        }
    if isinstance(parsed, str):
        # 异常情况：拿到一个普通字符串，按空 v_clock 处理
        return {"N": 0, "S": 0}
    return {"N": 0, "S": 0}

def _vclock_dominates(a: dict[str, int], b: dict[str, int]) -> bool:
    """判断向量时钟 a 是否“支配（dominates）” b。

    支配的含义：a 的每个分量都不小于 b，且至少一个分量严格大于 b。
    """
    return (a["N"] >= b["N"] and a["S"] >= b["S"]) and (a["N"] > b["N"] or a["S"] > b["S"])

def _vclock_concurrent(a: dict[str, int], b: dict[str, int]) -> bool:
    """判断 a 和 b 是否并发（concurrent）：互不支配。"""
    if a == b:
        return False
    return not _vclock_dominates(a, b) and not _vclock_dominates(b, a)


def _strip_non_semantic_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """剔除不影响冲突语义的字段。

    用途：检测“异常更新”——业务字段变了，但 v_clock 没有变化。
    这种情况通常代表触发器未生效/绕过触发器（例如手工 SQL 修改），
    后续会触发 smart-fix：主动 bump origin 的 v_clock 分量。
    """
    # 用于 edge 侧“异常更新（external modification）”检测
    if not isinstance(payload, dict):
        return payload
    ignore = {"updated_at", "created_at", "sync_version"}
    return {k: v for k, v in payload.items() if k not in ignore}


def _ensure_sync_configs() -> None:
    """确保 Hub 侧存在一组“基线同步配置”（baseline）。

    这里把 Hub 的 `sync_configs` 作为同步拓扑表（source/target/mode/interval/enabled）。
    管理后台（AdminConsole）也会在运行期编辑这张表。
    """

    # Demo 默认拓扑（方便开箱即用）。
    # 注意：管理台会在运行期编辑 Hub 的 `sync_configs`。
    desired = (
        ("mariadb", "mysql", "realtime", 30, True),
        ("postgres", "mysql", "realtime", 30, True),
        ("mariadb", "postgres", "realtime", 30, True),
        ("postgres", "mariadb", "realtime", 30, True),
    )

    with db_manager.session_scope("mysql") as session:
        session.info["suppress_sync"] = True
        rows = session.execute(select(SyncConfig)).scalars().all()
        by_key: dict[tuple[str, str, str], SyncConfig] = {
            (str(r.source), str(r.target), str(r.mode or "realtime")): r for r in rows
        }

        # 以 (source,target,mode) 为键做 upsert，避免重复插入。
        for source, target, mode, interval_seconds, enabled in desired:
            key = (source, target, mode)
            existing = by_key.get(key)
            if existing is None:
                session.add(
                    SyncConfig(
                        source=source,
                        target=target,
                        mode=mode,
                        interval_seconds=int(interval_seconds),
                        enabled=bool(enabled),
                    )
                )
                continue

            changed = False
            if bool(existing.enabled) != bool(enabled):
                existing.enabled = bool(enabled)
                changed = True
            if int(existing.interval_seconds or 0) != int(interval_seconds):
                existing.interval_seconds = int(interval_seconds)
                changed = True
            if changed:
                session.add(existing)

def _load_cursor(worker_name: str) -> int:
    """读取指定 worker 的 edge 日志游标（last processed log_id）。"""
    with db_manager.session_scope("mysql") as session:
        session.info["suppress_sync"] = True
        state = (
            session.execute(select(SyncWorkerState).where(SyncWorkerState.worker_name == worker_name))
            .scalars()
            .one_or_none()
        )
        if state is None:
            state = SyncWorkerState(worker_name=worker_name, last_event_id=0)
            session.add(state)
            session.flush()
            return 0
        return int(state.last_event_id or 0)


def _store_cursor(worker_name: str, last_log_id: int) -> None:
    """把最新处理到的 log_id 游标持久化到 Hub。"""
    with db_manager.session_scope("mysql") as session:
        session.info["suppress_sync"] = True
        state = (
            session.execute(select(SyncWorkerState).where(SyncWorkerState.worker_name == worker_name))
            .scalars()
            .one_or_none()
        )
        if state is None:
            state = SyncWorkerState(worker_name=worker_name, last_event_id=int(last_log_id))
            session.add(state)
        else:
            state.last_event_id = int(last_log_id)
        session.flush()


def _fetch_edge_logs(origin_db: str, after_log_id: int, limit: int) -> list[EdgeLogRow]:
    """从 edge 拉取一批未处理的变更事件。

    关键点：查询同时依赖“游标”（log_id > after）与“状态位”（status=0）。
    因此 edge 侧建议有 (status, log_id) 的组合索引，否则批量轮询会很慢。
    """
    if origin_db == "postgres":
        sql = text(
            """
            SELECT log_id, table_name, data_id, operation, old_data, new_data, occurred_at
            FROM sync_log
            WHERE status = 0 AND log_id > :after
            ORDER BY log_id ASC
            LIMIT :limit
            """
        )
    else:
        # mariadb
        sql = text(
            """
            SELECT log_id, table_name, data_id, operation, old_data, new_data, occurred_at
            FROM sync_log
            WHERE status = 0 AND log_id > :after
            ORDER BY log_id ASC
            LIMIT :limit
            """
        )

    with db_manager.session_scope(origin_db) as session:
        rows = session.execute(sql, {"after": int(after_log_id), "limit": int(limit)}).all()

    result: list[EdgeLogRow] = []
    for row in rows:
        result.append(
            EdgeLogRow(
                log_id=int(row.log_id),
                table_name=str(row.table_name),
                data_id=int(row.data_id),
                operation=str(row.operation).upper(),
                old_data=_parse_json_maybe(row.old_data),
                new_data=_parse_json_maybe(row.new_data),
                occurred_at=row.occurred_at,
            )
        )
    return result


def _mark_edge_log_processed(origin_db: str, log_id: int) -> None:
    """把 edge 侧某条日志标记为已处理。

    当前语义：表示“Hub Worker 已消费该事件”。
    注意：这不是 per-target 的确认（ACK），而是 per-origin 的处理标记。
    """
    with db_manager.session_scope(origin_db) as session:
        session.execute(
            text("UPDATE sync_log SET status = 1, processed_at = CURRENT_TIMESTAMP WHERE log_id = :id"),
            {"id": int(log_id)},
        )


def _set_trigger_suppression(session, db_name: str) -> None:
    """在当前 DB session 中开启“触发器抑制”。

    目的：同步写入目标库时，不要再次生成 sync_log，也不要再 bump v_clock，
    以避免回环/无限同步。
    """
    if db_name in {"mysql", "mariadb"}:
        session.execute(text("SET @sync_suppress = 1"))
    elif db_name == "postgres":
        session.execute(text("SET app.sync_suppress = '1'"))


def _select_current_row(target_db: str, table_name: str, record_id: int) -> Optional[dict[str, Any]]:
    """读取目标库中某条记录的当前状态。

    返回：完整行 dict（列名 -> 值），不存在则返回 None。
    用途：读取 target 的 v_clock，与 source v_clock 比较后决定覆盖/跳过/记录冲突。
    """
    with db_manager.session_scope(target_db) as session:
        row = session.execute(
            text(f"SELECT * FROM {table_name} WHERE id = :id"),
            {"id": int(record_id)},
        ).mappings().first()
        return dict(row) if row is not None else None


def _select_edge_row(origin_db: str, table_name: str, record_id: int) -> Optional[dict[str, Any]]:
    """直接从 edge 库读取某条记录。

    用途：
    - 目标库缺失父表记录时进行补齐（backfill parent）
    - 通过唯一键（email/username/student_id 等）做跨库 ID 映射
    """
    with db_manager.session_scope(origin_db) as session:
        row = session.execute(
            text(f"SELECT * FROM {table_name} WHERE id = :id"),
            {"id": int(record_id)},
        ).mappings().first()
        return dict(row) if row is not None else None


def _is_mysql_fk_missing(exc: Exception) -> bool:
    """判断是否为 MySQL/MariaDB 外键约束失败（errno 1452）。"""
    if not isinstance(exc, IntegrityError):
        return False
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", None)
    if not args or not isinstance(args, tuple):
        return False
    # MySQL/MariaDB: 1452 = Cannot add or update a child row（外键失败）
    return len(args) >= 1 and args[0] == 1452


def _is_mysql_duplicate_key(exc: Exception) -> bool:
    """判断是否为 MySQL/MariaDB 唯一键冲突（errno 1062）。"""
    if not isinstance(exc, IntegrityError):
        return False
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", None)
    if not args or not isinstance(args, tuple):
        return False
    # MySQL/MariaDB: 1062 = Duplicate entry（唯一键冲突）
    return len(args) >= 1 and args[0] == 1062


def _is_postgres_unique_violation(exc: Exception) -> bool:
    """判断是否为 Postgres UNIQUE 约束冲突（SQLSTATE 23505）。"""
    if not isinstance(exc, IntegrityError):
        return False
    orig = getattr(exc, "orig", None)
    # psycopg: UniqueViolation 的 SQLSTATE 为 23505
    sqlstate = getattr(orig, "sqlstate", None)
    return sqlstate == "23505"


def _is_postgres_fk_missing(exc: Exception) -> bool:
    """判断是否为 Postgres 外键约束失败（SQLSTATE 23503）。"""
    if not isinstance(exc, IntegrityError):
        return False
    orig = getattr(exc, "orig", None)
    # psycopg: ForeignKeyViolation 的 SQLSTATE 为 23503
    sqlstate = getattr(orig, "sqlstate", None)
    return sqlstate == "23503"


def _map_user_id_by_unique(*, origin_db: str, target_db: str, origin_user_id: int) -> Optional[int]:
    """通过业务唯一键做“跨库 user.id 映射”。

    为什么需要：
    - 不同 edge 库可能为同一个“逻辑用户”生成不同的数值 ID。
    - 目标库可能已存在相同 email/student_id/username 的用户行。
    当写入/更新因为 UNIQUE 约束失败时，可以通过唯一键找到既有行并复用其 id。
    """
    origin_user = _select_edge_row(origin_db, "users", origin_user_id)
    if not isinstance(origin_user, dict):
        return None

    email = origin_user.get("email")
    student_id = origin_user.get("student_id")
    username = origin_user.get("username")

    candidates: list[tuple[str, Any]] = []
    if email:
        candidates.append(("email", email))
    if student_id:
        candidates.append(("student_id", student_id))
    if username:
        candidates.append(("username", username))

    if not candidates:
        return None

    with db_manager.session_scope(target_db) as session:
        for col, value in candidates:
            row = session.execute(
                text(f"SELECT id FROM users WHERE {col} = :v LIMIT 1"),
                {"v": value},
            ).first()
            if row is not None:
                return int(row[0])
    return None


def _select_profile_id_by_user_id(target_db: str, user_id: int) -> Optional[int]:
    """在目标库中通过 user_id 查找 user_profiles.id（存在则返回）。"""
    with db_manager.session_scope(target_db) as session:
        row = session.execute(
            text("SELECT id FROM user_profiles WHERE user_id = :uid LIMIT 1"),
            {"uid": int(user_id)},
        ).first()
        return int(row[0]) if row is not None else None


def _ensure_parent_present(
    *,
    origin_db: str,
    target_db: str,
    parent_table: str,
    parent_id: int,
) -> bool:
    """确保目标库中存在父表记录。

    用于“外键顺序问题”的 best-effort 修复：子表先到、父表后到。
    这里会从 origin 读取父表行，并在 target 中 upsert 一次进行补齐。
    """
    if parent_id is None:
        return False
    existing = _select_current_row(target_db, parent_table, parent_id)
    if existing is not None:
        return True

    parent_payload = _select_edge_row(origin_db, parent_table, parent_id)
    if not isinstance(parent_payload, dict):
        return False
    try:
        _upsert_row(target_db, parent_table, parent_payload)
        return True
    except Exception:
        logger.exception(
            "Failed to backfill parent row",
            origin=origin_db,
            target=target_db,
            table=parent_table,
            record_id=parent_id,
        )
        return False


def _normalize_payload_for_target(target_db: str, payload: dict[str, Any]) -> dict[str, Any]:
    """修正常见的跨库类型不一致（best-effort）。

    - MariaDB/MySQL 常用 TINYINT(1) 表示布尔（0/1）
    - Postgres 使用 boolean
    """

    if target_db != "postgres":
        return payload

    normalized: dict[str, Any] = dict(payload)
    for key, value in list(normalized.items()):
        if key.startswith("is_") and isinstance(value, int) and value in (0, 1):
            normalized[key] = bool(value)
    return normalized


def _json_safe(value: Any) -> Any:
    """把常见的非 JSON 类型（如 Decimal、datetime）转换成可 JSON 序列化的值。"""
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Decimal):
        # Decimal 用字符串保存，避免精度丢失（例如价格）。
        return str(value)

    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()

    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]

    # 兜底：未知对象直接转字符串。
    return str(value)


def _upsert_row(target_db: str, table_name: str, payload: dict[str, Any]) -> None:
    """把一行数据 UPSERT 到目标库。

    约定：始终以主键 `id` 做 UPSERT，保证同步“幂等（idempotent）”。
    - Postgres：INSERT .. ON CONFLICT(id) DO UPDATE
    - MySQL/MariaDB：INSERT .. ON DUPLICATE KEY UPDATE
    同步写入时会开启 trigger suppression，避免目标库触发器再次记日志。
    """
    payload = _normalize_payload_for_target(target_db, payload)
    cols = [k for k in payload.keys() if k is not None]
    if "id" not in payload:
        raise ValueError("payload missing id")

    if target_db == "postgres":
        insert_cols = ", ".join(cols)
        insert_vals = ", ".join([f":{c}" for c in cols])
        update_cols = [c for c in cols if c != "id"]
        update_set = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])
        sql = text(
            f"INSERT INTO {table_name} ({insert_cols}) VALUES ({insert_vals}) "
            f"ON CONFLICT (id) DO UPDATE SET {update_set}"
        )
    else:
        insert_cols = ", ".join(cols)
        insert_vals = ", ".join([f":{c}" for c in cols])
        update_cols = [c for c in cols if c != "id"]
        update_set = ", ".join([f"{c} = VALUES({c})" for c in update_cols])
        sql = text(
            f"INSERT INTO {table_name} ({insert_cols}) VALUES ({insert_vals}) "
            f"ON DUPLICATE KEY UPDATE {update_set}"
        )

    with db_manager.session_scope(target_db) as session:
        _set_trigger_suppression(session, target_db)
        session.execute(sql, payload)


def _delete_row(target_db: str, table_name: str, record_id: int) -> None:
    """在目标库删除一条记录（写入前开启 trigger suppression）。"""
    with db_manager.session_scope(target_db) as session:
        _set_trigger_suppression(session, target_db)
        session.execute(text(f"DELETE FROM {table_name} WHERE id = :id"), {"id": int(record_id)})


def _record_conflict(
    table_name: str,
    record_id: int,
    source: str,
    target: str,
    payload: dict[str, Any],
) -> int:
    """在 Hub 记录一条冲突，并（尽力）发送通知。

    冲突的定义：source 与 target 的 v_clock 互为 concurrent（并发）。
    我们会保存足够的快照 payload，方便后续人工排查/合并。
    """
    def _load_runtime_notification_email_config() -> dict[str, Any]:
        try:
            from apps.core.models import SystemSetting

            with db_manager.session_scope("mysql") as session:
                session.info["suppress_sync"] = True
                row = (
                    session.query(SystemSetting)
                    .filter(SystemSetting.category == "notification", SystemSetting.key == "email")
                    .one_or_none()
                )
                if row and isinstance(row.value, dict):
                    return row.value
        except Exception:
            # best-effort：运行期配置读取失败就回退到默认
            return {}
        return {}

    def _fmt_value(value: Any, max_len: int = 140) -> str:
        try:
            if isinstance(value, (dict, list)):
                text_value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            else:
                text_value = str(value)
        except Exception:
            text_value = repr(value)
        if len(text_value) > max_len:
            return text_value[: max_len - 3] + "..."
        return text_value

    def _summarize_payload(payload_obj: dict[str, Any]) -> str:
        reason = payload_obj.get("reason") or "unknown"
        source_state = payload_obj.get("source_new") or payload_obj.get("source_old") or {}
        target_state = payload_obj.get("target_current") or {}

        lines: list[str] = []
        lines.append(f"Reason: {reason}")

        source_vc = source_state.get("v_clock") if isinstance(source_state, dict) else None
        target_vc = target_state.get("v_clock") if isinstance(target_state, dict) else None
        if source_vc is not None or target_vc is not None:
            lines.append(f"v_clock(source): {_fmt_value(source_vc)}")
            lines.append(f"v_clock(target): {_fmt_value(target_vc)}")

        diffs: list[tuple[str, Any, Any]] = []
        if isinstance(source_state, dict) and isinstance(target_state, dict):
            keys = sorted(set(source_state.keys()) | set(target_state.keys()))
            for key in keys:
                if key in {"created_at", "updated_at"}:
                    continue
                if source_state.get(key) != target_state.get(key):
                    diffs.append((key, source_state.get(key), target_state.get(key)))

        if diffs:
            lines.append("")
            lines.append("Key differences (source vs target):")
            for key, s_val, t_val in diffs[:12]:
                lines.append(f"- {key}: { _fmt_value(s_val) }  |  { _fmt_value(t_val) }")
            if len(diffs) > 12:
                lines.append(f"(… {len(diffs) - 12} more fields differ)")

        return "\n".join(lines)

    payload = _json_safe(payload)
    with db_manager.session_scope("mysql") as session:
        session.info["suppress_sync"] = True
        row = ConflictRecord(
            table_name=table_name,
            record_id=int(record_id),
            source=source,
            target=target,
            status="pending",
            resolved=False,
            payload=payload,
        )
        session.add(row)
        session.flush()
        conflict_id = int(row.id)

    # best-effort：邮件通知失败不影响主流程
    try:
        runtime_email = _load_runtime_notification_email_config()
        if runtime_email.get("notify_conflicts") is False:
            return conflict_id

        settings = get_settings()
        token = create_conflict_token(conflict_id, purpose="admin_ui")
        ui_base = settings.frontend_base_url.rstrip("/")
        ui_link = f"{ui_base}/admin/console?conflictId={conflict_id}&token={token}"

        subject = f"[CampuSwap] Sync conflict: {table_name}#{record_id} (id={conflict_id})"
        auth_note = (
            "Authentication: This email contains a signed magic-login link (no password required).\n"
            f"Token purpose=admin_ui, expires in ~{int(settings.conflict_token_expire_minutes)} minutes.\n"
            "Do NOT forward this email.\n"
        )

        summary = _summarize_payload(payload)

        payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(payload_text) > 6000:
            payload_text = payload_text[:6000] + "\n... (truncated)\n"

        body = (
            f"Conflict ID: {conflict_id}\n"
            f"Table: {table_name}\n"
            f"Record: {record_id}\n"
            f"Source: {source}\n"
            f"Target: {target}\n\n"
            f"{auth_note}\n"
            f"Summary:\n{summary}\n\n"
            f"Links:\n"
            f"- Open in system (magic-login): {ui_link}\n"
            "\n"
            f"Payload (full snapshot):\n{payload_text}\n"
        )
        email_notifier.send(subject, body)
    except Exception as exc:  # pragma: no cover
        logger.debug("Email notify failed: %s", exc)

    return conflict_id


def _bump_daily_stat(field: str) -> None:
    """Hub 侧每日统计计数器 +1。

    用于管理后台/监控展示。该逻辑是 best-effort：统计失败不应阻塞同步。
    """
    today = _utc_now().date()
    with db_manager.session_scope("mysql") as session:
        session.info["suppress_sync"] = True
        row = session.execute(select(DailyStat).where(DailyStat.stat_date == today)).scalar_one_or_none()
        if row is None:
            row = DailyStat(stat_date=today)
            session.add(row)
            session.flush()
        current = int(getattr(row, field) or 0)
        setattr(row, field, current + 1)


def _process_edge_row(origin_db: str, origin_key: str, row: EdgeLogRow, targets: Iterable[str]) -> bool:
    """处理一条 edge `sync_log` 事件，并同步到多个 target。

    对每个 target 的决策流程：
    1）读取 target 当前行（可能不存在）
    2）比较 source v_clock 与 target v_clock
       - source dominates（或相等）-> 执行覆盖（UPSERT/DELETE）
       - target dominates -> 跳过（target 更新）
       - concurrent -> 记录冲突（conflict_records），不直接覆盖

    返回值语义：
    - True：认为该事件“已处理”，会把 origin 上的这条日志标记 processed
    - False：遇到未知/暂时性错误，调用方会停止本批处理，等待下次重试
    """
    table_name = row.table_name
    if table_name not in TRACKED_TABLES:
        # 不同步的表：直接推进 edge 队列（标记 processed），避免队列卡死。
        _mark_edge_log_processed(origin_db, row.log_id)
        return True

    source_payload = row.new_data if row.operation in {"INSERT", "UPDATE"} else row.old_data
    if not isinstance(source_payload, dict):
        # 触发器捕获到非 dict 的异常快照：为避免“毒化队列”，直接跳过并推进。
        _mark_edge_log_processed(origin_db, row.log_id)
        return True

    # 解析并规范化 v_clock
    v_clock = _parse_vclock(source_payload.get("v_clock"))

    # Smart-fix：检测到业务字段变了但 v_clock 没变（可能绕过触发器），则补 bump
    if row.operation in {"INSERT", "UPDATE"}:
        old_payload = row.old_data if isinstance(row.old_data, dict) else None
        new_payload = row.new_data if isinstance(row.new_data, dict) else None

        needs_fix = False
        if old_payload is not None and new_payload is not None:
            old_v = _parse_vclock(old_payload.get("v_clock"))
            new_v = _parse_vclock(new_payload.get("v_clock"))
            if old_v == new_v and _strip_non_semantic_fields(old_payload) != _strip_non_semantic_fields(new_payload):
                needs_fix = True
        elif row.operation == "INSERT":
            if int(v_clock.get(origin_key, 0) or 0) <= 0:
                needs_fix = True

        if needs_fix:
            # 一些写入可能绕过触发器（手工 SQL、批量导入等）。
            # 若业务字段变化但 v_clock 未变化，会破坏冲突检测的“单调性”。
            # 因此这里补 bump origin 分量以恢复正确语义。
            fixed = dict(v_clock)
            fixed[origin_key] = int(fixed.get(origin_key, 0) or 0) + 1
            fixed_text = json.dumps(fixed, ensure_ascii=False, separators=(",", ":"))
            try:
                with db_manager.session_scope(origin_db) as session:
                    _set_trigger_suppression(session, origin_db)
                    session.execute(
                        text(f"UPDATE {table_name} SET v_clock = :v WHERE id = :id"),
                        {"v": fixed_text, "id": int(row.data_id)},
                    )
                source_payload["v_clock"] = fixed_text
                v_clock = fixed
                logger.warning(
                    "Smart-fixed missing v_clock increment",
                    origin=origin_db,
                    table=table_name,
                    record_id=row.data_id,
                    v_clock=fixed,
                )
            except SQLAlchemyError as exc:
                logger.warning("Smart-fix failed", error=str(exc), origin=origin_db, table=table_name)

    # 对每个 target 逐一同步（基于向量时钟比较）
    for target_db in targets:
        if target_db == origin_db:
            continue

        try:
            # 读取 target 当前状态，用 v_clock 决定“覆盖/跳过/冲突”。
            current = _select_current_row(target_db, table_name, row.data_id)
            current_v = _parse_vclock((current or {}).get("v_clock"))

            if row.operation == "DELETE":
                # DELETE 的生效条件：source delete 必须 dominates（或相等）于 target
                if current is None or _vclock_dominates(v_clock, current_v) or v_clock == current_v:
                    _delete_row(target_db, table_name, row.data_id)
                    _bump_daily_stat("sync_success_count")
                elif _vclock_concurrent(v_clock, current_v):
                    # 并发：delete vs update => 记录冲突，保留 target 当前值
                    _record_conflict(
                        table_name,
                        row.data_id,
                        source=origin_db,
                        target=target_db,
                        payload={
                            "reason": "vector_clock_conflict_delete",
                            "origin": origin_db,
                            "target": target_db,
                            "table": table_name,
                            "record_id": row.data_id,
                            "edge_log_id": row.log_id,
                            "source_v_clock": v_clock,
                            "target_v_clock": current_v,
                            "source_old": row.old_data,
                            "target_current": current,
                        },
                    )
                    _bump_daily_stat("sync_conflict_count")
                continue

            # INSERT/UPDATE
            if current is None or _vclock_dominates(v_clock, current_v) or v_clock == current_v:
                _upsert_row(target_db, table_name, source_payload)
                _bump_daily_stat("sync_success_count")
            elif _vclock_dominates(current_v, v_clock):
                # target 更新：跳过
                continue
            else:
                # 并发更新：记录冲突，保留 target 当前值
                _record_conflict(
                    table_name,
                    row.data_id,
                    source=origin_db,
                    target=target_db,
                    payload={
                        "reason": "vector_clock_conflict",
                        "origin": origin_db,
                        "target": target_db,
                        "table": table_name,
                        "record_id": row.data_id,
                        "edge_log_id": row.log_id,
                        "operation": row.operation,
                        "source_v_clock": v_clock,
                        "target_v_clock": current_v,
                        "source_old": row.old_data,
                        "source_new": row.new_data,
                        "target_current": current,
                    },
                )
                _bump_daily_stat("sync_conflict_count")
        except Exception as exc:
            # === 常见跨库异常的 best-effort 修复分支 ===
            #
            # 我们的 UPSERT 策略是“按主键 id”保证幂等。
            # 代价是：无法天然处理“跨库唯一键冲突”（如 email 相同但 id 不同）
            # 以及“外键顺序问题”（子表先到父表后到）。
            # 下方分支属于工程化的补丁修复：提升 demo 稳定性。

            # Postgres target FK missing: child arrives but parent user id doesn't exist there.
            if (
                target_db == "postgres"
                and table_name == "user_profiles"
                and row.operation in {"INSERT", "UPDATE"}
                and _is_postgres_fk_missing(exc)
            ):
                parent_id = source_payload.get("user_id")
                if parent_id is not None:
                    # 先尝试通过唯一键把 parent user 映射到 target 的 id，再重试。
                    mapped = _map_user_id_by_unique(
                        origin_db=origin_db,
                        target_db=target_db,
                        origin_user_id=int(parent_id),
                    )
                    if mapped is not None:
                        patched_profile = dict(source_payload)
                        patched_profile["user_id"] = int(mapped)
                        logger.warning(
                            "Mapped user_profiles.user_id by unique fields",
                            origin=origin_db,
                            target=target_db,
                            table=table_name,
                            record_id=row.data_id,
                            origin_user_id=int(parent_id),
                            mapped_user_id=int(mapped),
                        )
                        try:
                            _upsert_row(target_db, table_name, patched_profile)
                            _bump_daily_stat("sync_success_count")
                            continue
                        except Exception as exc2:
                            # Retry may still fail due to UNIQUE(user_id); fall through to the
                            # dedicated handler below.
                            exc = exc2

            # Postgres target can also fail on UNIQUE(user_id) for user_profiles because UPSERT
            # is keyed by (id) only. If a profile already exists for that user_id, update it.
            if (
                target_db == "postgres"
                and table_name == "user_profiles"
                and row.operation in {"INSERT", "UPDATE"}
                and _is_postgres_unique_violation(exc)
            ):
                raw_uid = source_payload.get("user_id")
                if raw_uid is not None:
                    uid = int(raw_uid)
                    # If the referenced user id isn't present, map it first.
                    if _select_current_row(target_db, "users", uid) is None:
                        mapped_uid = _map_user_id_by_unique(
                            origin_db=origin_db,
                            target_db=target_db,
                            origin_user_id=uid,
                        )
                        if mapped_uid is not None:
                            uid = int(mapped_uid)

                    # 如果该 user 已存在 profile，则更新那条 profile（而不是用 edge 的 id）。
                    existing_profile_id = _select_profile_id_by_user_id(target_db, uid)
                    if existing_profile_id is not None:
                        patched_profile = dict(source_payload)
                        patched_profile["user_id"] = uid
                        patched_profile["id"] = int(existing_profile_id)
                        logger.warning(
                            "Mapped user_profiles.id by user_id",
                            origin=origin_db,
                            target=target_db,
                            table=table_name,
                            record_id=row.data_id,
                            user_id=uid,
                            mapped_profile_id=int(existing_profile_id),
                        )
                        try:
                            _upsert_row(target_db, table_name, patched_profile)
                            _bump_daily_stat("sync_success_count")
                            continue
                        except Exception as exc2:
                            logger.exception(
                                "Replication retry failed",
                                origin=origin_db,
                                target=target_db,
                                table=table_name,
                                record_id=row.data_id,
                                error=str(exc2),
                            )
                            return False

            # Postgres target can fail on UNIQUE(username/email/student_id) because our UPSERT
            # is keyed by (id). If a logically same user already exists in target under a
            # different id, map by unique fields and retry.
            if (
                target_db == "postgres"
                and table_name == "users"
                and row.operation in {"INSERT", "UPDATE"}
                and _is_postgres_unique_violation(exc)
            ):
                # 同一个“逻辑用户”在不同 DB 里可能有不同数值 id。
                # 若 UNIQUE(email/student_id/username) 触发，说明 target 已有该用户：
                # 复用 target 既有行的 id，并把更新写到那一行。
                mapped = _map_user_id_by_unique(
                    origin_db=origin_db,
                    target_db=target_db,
                    origin_user_id=int(row.data_id),
                )
                if mapped is not None:
                    patched_user = dict(source_payload)
                    patched_user["id"] = int(mapped)
                    logger.warning(
                        "Mapped user.id by unique fields",
                        origin=origin_db,
                        target=target_db,
                        table=table_name,
                        origin_user_id=int(row.data_id),
                        mapped_user_id=int(mapped),
                    )
                    try:
                        _upsert_row(target_db, table_name, patched_user)
                        _bump_daily_stat("sync_success_count")
                        continue
                    except Exception as exc2:
                        logger.exception(
                            "Replication retry failed",
                            origin=origin_db,
                            target=target_db,
                            table=table_name,
                            record_id=row.data_id,
                            error=str(exc2),
                        )
                        return False

            # If a child row arrives before its parent on the target (or the parent was skipped
            # previously), backfill the parent from origin and retry once.
            if _is_mysql_fk_missing(exc) and row.operation in {"INSERT", "UPDATE"}:
                if table_name == "items":
                    seller_id = source_payload.get("seller_id")
                    if seller_id is not None:
                        # items.seller_id 外键指向 users。
                        # 若跨库 user.id 不一致，则通过唯一键映射后再重试写入。
                        mapped = _map_user_id_by_unique(
                            origin_db=origin_db,
                            target_db=target_db,
                            origin_user_id=int(seller_id),
                        )
                        if mapped is not None:
                            patched_item = dict(source_payload)
                            patched_item["seller_id"] = int(mapped)
                            logger.warning(
                                "Mapped items.seller_id by unique fields",
                                origin=origin_db,
                                target=target_db,
                                table=table_name,
                                record_id=row.data_id,
                                origin_seller_id=int(seller_id),
                                mapped_seller_id=int(mapped),
                            )
                            try:
                                _upsert_row(target_db, table_name, patched_item)
                                _bump_daily_stat("sync_success_count")
                                continue
                            except Exception as exc2:
                                logger.exception(
                                    "Replication retry failed",
                                    origin=origin_db,
                                    target=target_db,
                                    table=table_name,
                                    record_id=row.data_id,
                                    error=str(exc2),
                                )
                                return False

                if table_name == "user_profiles":
                    parent_id = source_payload.get("user_id")
                    if parent_id is not None:
                        logger.warning(
                            "FK missing; attempting to repair",
                            origin=origin_db,
                            target=target_db,
                            table=table_name,
                            record_id=row.data_id,
                            parent_table="users",
                            parent_id=int(parent_id),
                        )

                        if _ensure_parent_present(
                            origin_db=origin_db,
                            target_db=target_db,
                            parent_table="users",
                            parent_id=int(parent_id),
                        ):
                            try:
                                _upsert_row(target_db, table_name, source_payload)
                                _bump_daily_stat("sync_success_count")
                                continue
                            except Exception as exc2:
                                # Fall through to mapping attempt below.
                                exc = exc2

                        # 若 parent 的数值 id 不一致，则通过唯一键映射。
                        mapped = _map_user_id_by_unique(
                            origin_db=origin_db,
                            target_db=target_db,
                            origin_user_id=int(parent_id),
                        )
                        if mapped is not None:
                            patched = dict(source_payload)
                            patched["user_id"] = int(mapped)
                            logger.warning(
                                "Mapped user_id by unique fields",
                                origin=origin_db,
                                target=target_db,
                                table=table_name,
                                record_id=row.data_id,
                                origin_user_id=int(parent_id),
                                mapped_user_id=int(mapped),
                            )
                            try:
                                _upsert_row(target_db, table_name, patched)
                                _bump_daily_stat("sync_success_count")
                                continue
                            except Exception as exc3:
                                logger.exception(
                                    "Replication retry failed",
                                    origin=origin_db,
                                    target=target_db,
                                    table=table_name,
                                    record_id=row.data_id,
                                    error=str(exc3),
                                )
                                return False

            logger.exception(
                "Replication error",
                origin=origin_db,
                target=target_db,
                table=table_name,
                record_id=row.data_id,
                error=str(exc),
            )
            return False

    # 只有当“所有 targets 都处理完”后，才把 origin 的日志标记 processed。
    _mark_edge_log_processed(origin_db, row.log_id)
    return True

def _resolve_targets(origin: str, mode: str = "realtime") -> list[str]:
    """根据 origin 与 mode 获取启用的 target 列表。

    说明：这是一个“简单查询器”（可能被脚本/旧逻辑使用）。
    主循环会用 `_resolve_targets_and_due_scheduled()` 来统一处理 realtime + scheduled。
    """
    with db_manager.session_scope("mysql") as session:
        targets = (
            session.execute(
                select(SyncConfig.target).where(
                    SyncConfig.enabled.is_(True),
                    SyncConfig.source == origin,
                    SyncConfig.mode == mode,
                    SyncConfig.target.is_not(None),
                    SyncConfig.target != origin,
                )
            )
            .scalars()
            .all()
        )
    return list(targets)


def _load_manual_trigger_counter() -> int:
    """读取 Hub 上的“手动触发计数器”。

    API 会递增 SyncWorkerState(worker_name='manual_trigger').last_event_id。
    Worker 通过检测该计数器是否变化，来“强制执行一次 scheduled 链路”。
    """

    with db_manager.session_scope("mysql") as session:
        session.info["suppress_sync"] = True
        row = (
            session.execute(
                select(SyncWorkerState).where(SyncWorkerState.worker_name == "manual_trigger")
            )
            .scalars()
            .one_or_none()
        )
        return int(row.last_event_id or 0) if row is not None else 0


def _resolve_targets_and_due_scheduled(origin: str, *, force_scheduled: bool) -> tuple[list[str], list[int]]:
    """解析同步目标，并在 scheduled 到期（或手动触发）时包含 scheduled 链路。

    返回：(targets, scheduled_config_ids_to_touch)
    - targets：本轮要同步到的目标库列表
    - scheduled_config_ids_to_touch：本轮触发的 scheduled 配置 id，用于更新 last_run_at
    """

    now = _utc_now()
    targets: set[str] = set()
    scheduled_ids: list[int] = []

    with db_manager.session_scope("mysql") as session:
        session.info["suppress_sync"] = True
        configs = (
            session.execute(
                select(SyncConfig).where(
                    SyncConfig.enabled.is_(True),
                    SyncConfig.source == origin,
                    SyncConfig.target.is_not(None),
                    SyncConfig.target != origin,
                )
            )
            .scalars()
            .all()
        )

        for cfg in configs:
            target = str(cfg.target)
            mode = str(cfg.mode or "realtime")
            if mode == "realtime":
                targets.add(target)
                continue
            if mode != "scheduled":
                continue

            if force_scheduled:
                # 手动触发：无视 last_run_at/interval，立即执行 scheduled
                targets.add(target)
                scheduled_ids.append(int(cfg.id))
                continue

            # 正常 scheduled：当 now - last_run_at >= interval 才算到期
            last = _as_utc_aware(cfg.last_run_at)
            interval = int(cfg.interval_seconds or 300)
            due = last is None or (now - last).total_seconds() >= float(interval)
            if due:
                targets.add(target)
                scheduled_ids.append(int(cfg.id))

    return sorted(targets), scheduled_ids


def _touch_scheduled_last_run(config_ids: Iterable[int]) -> None:
    """更新本轮执行过的 scheduled 配置的 `last_run_at`。

    注意：即使本轮没有任何 edge 事件可同步，也会 touch 一次 last_run_at。
    这样管理后台能观察到“定时轮询是活着的”。
    """
    ids = [int(i) for i in config_ids]
    if not ids:
        return
    now = _utc_now()
    with db_manager.session_scope("mysql") as session:
        session.info["suppress_sync"] = True
        stmt = text("UPDATE sync_configs SET last_run_at = :now WHERE id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        )
        session.execute(stmt, {"now": now, "ids": ids})


def _handle_shutdown(signum: int, _frame: object) -> None:  # pragma: no cover
    logger.warning("Sync Core received shutdown", signal=signum)
    STOP_EVENT.set()


def run_forever(batch_size: int = 100, idle_sleep: float = 0.5) -> None:
    """主循环：持续轮询 edge 日志并同步。

    对每个 origin edge DB：
    - 解析 targets：realtime 永远参与；scheduled 到期/手动触发时参与
    - 按 origin 专属游标拉取一批未处理日志
    - 按 log_id 顺序处理；遇到失败立刻停（保持顺序一致性，等待下次重试）
    - 写回游标，并更新 scheduled 的 last_run_at
    """
    _ensure_sync_configs()

    hostname = socket.gethostname()
    logger.info("Sync Core started", worker=hostname)

    last_manual_counter = _load_manual_trigger_counter()

    while not STOP_EVENT.is_set():
        progressed = False

        manual_counter = _load_manual_trigger_counter()
        force_scheduled = manual_counter > last_manual_counter
        if force_scheduled:
            last_manual_counter = manual_counter

        for origin_db, origin_key in EDGE_ORIGINS.items():
            cursor_name = f"edge_sync_log:{origin_db}"
            last = _load_cursor(cursor_name)
            targets, scheduled_ids = _resolve_targets_and_due_scheduled(
                origin_db, force_scheduled=force_scheduled
            )

            if not targets:
                continue

            rows = _fetch_edge_logs(origin_db, after_log_id=last, limit=batch_size)
            if not rows:
                # Even if there's nothing to replicate, scheduled runs still count as a poll.
                _touch_scheduled_last_run(scheduled_ids)
                continue

            progressed = True
            max_committed = last
            for row in rows:
                ok = _process_edge_row(origin_db, origin_key, row, targets)
                if not ok:
                    # 失败就提前停止：游标停在上一次 committed 的位置，等待下次重试。
                    break
                max_committed = max(max_committed, int(row.log_id))

            _store_cursor(cursor_name, max_committed)
            _touch_scheduled_last_run(scheduled_ids)

        if not progressed:
            time.sleep(idle_sleep)


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    batch_size = int(os.getenv("SYNC_EDGE_BATCH", "100"))
    idle_sleep = float(os.getenv("SYNC_EDGE_IDLE_SLEEP", "0.5"))
    run_forever(batch_size=batch_size, idle_sleep=idle_sleep)


if __name__ == "__main__":
    main()
