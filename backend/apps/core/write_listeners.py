"""SQLAlchemy session listeners for application-layer IDs.

We keep these concerns in the app layer:
- Snowflake IDs (global uniqueness across multi-master)

Vector clocks (v_clock) are maintained by DB triggers on edge databases.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, sessionmaker

from .snowflake import Snowflake


_generators: dict[str, Snowflake] = {
    "mariadb": Snowflake(int(1)),
    "postgres": Snowflake(int(2)),
    "mysql": Snowflake(int(0)),
}


def _get_generator(db_name: str) -> Snowflake:
    # Allow override via env, without reworking config objects.
    # Defaults follow the design: N=1, S=2.
    if db_name == "mariadb":
        worker_id = int(__import__("os").getenv("SNOWFLAKE_WORKER_ID_N", "1"))
    elif db_name == "postgres":
        worker_id = int(__import__("os").getenv("SNOWFLAKE_WORKER_ID_S", "2"))
    elif db_name == "mysql":
        worker_id = int(__import__("os").getenv("SNOWFLAKE_WORKER_ID_H", "0"))
    else:
        worker_id = int(__import__("os").getenv("SNOWFLAKE_WORKER_ID", "0"))

    existing = _generators.get(db_name)
    if existing is None or getattr(existing, "_worker_id", None) != worker_id:
        _generators[db_name] = Snowflake(worker_id)
    return _generators[db_name]


def register_write_listeners(factory: sessionmaker[Session]) -> None:
    event.listen(factory, "before_flush", _before_flush)


def _before_flush(session: Session, _flush_context: Any, _instances: Any) -> None:
    db_name = session.info.get("db_name")
    if not isinstance(db_name, str):
        return
    if db_name not in {"mysql", "mariadb", "postgres"}:
        return

    now = datetime.now(timezone.utc)

    for obj in list(session.new):
        _ensure_id(db_name, obj)
        _touch_updated_at(obj, now)

    for obj in list(session.dirty):
        state = inspect(obj)
        if state.deleted or not state.modified:
            continue

        if not _has_meaningful_changes(state):
            continue
        _touch_updated_at(obj, now)


def _ensure_id(db_name: str, obj: Any) -> None:
    if not hasattr(obj, "id"):
        return
    current = getattr(obj, "id", None)
    if current is None or int(current) == 0:
        setattr(obj, "id", _get_generator(db_name).next_id())


def _touch_updated_at(obj: Any, now: datetime) -> None:
    if hasattr(obj, "updated_at"):
        try:
            setattr(obj, "updated_at", now)
        except Exception:
            return


def _has_meaningful_changes(state) -> bool:
    # ignore pure timestamp or sync metadata updates
    ignore = {"updated_at", "created_at", "sync_version", "v_clock"}
    for attr in state.attrs:
        if attr.key in ignore:
            continue
        if attr.history.has_changes():
            return True
    return False
