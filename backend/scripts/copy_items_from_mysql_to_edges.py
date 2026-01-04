"""Copy marketplace items from Hub MySQL into edge databases.

This is a pragmatic, ops-style script for cases where you want to ensure MariaDB
and Postgres contain the same item rows as Hub MySQL.

It copies:
- items
- item_images

It does NOT attempt to backfill referenced FK rows (users/categories/campuses).
Instead, it validates that required parent rows exist in the target DB and fails
fast with a readable error.

Run inside docker:
  docker compose exec gateway python scripts/copy_items_from_mysql_to_edges.py --item-id 123

Examples:
  # Upsert one item (overwrite fields to match MySQL)
  docker compose exec gateway python scripts/copy_items_from_mysql_to_edges.py --item-id 265...

  # Copy latest 10 items (upsert)
  docker compose exec gateway python scripts/copy_items_from_mysql_to_edges.py --latest 10

  # Only insert missing rows (do not overwrite existing item row)
  docker compose exec gateway python scripts/copy_items_from_mysql_to_edges.py --latest 10 --missing-only
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.inspection import inspect as sa_inspect

# Ensure the project root is importable when running as a script.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from apps.core.database import db_manager, get_all_engines
from apps.core.models.inventory import Campus, Category, Item, ItemMedia
from apps.core.models.users import User


SUPPORTED_TARGETS = ("mariadb", "postgres")

# Keep output readable: disable SQLAlchemy echo for this process.
for _engine in get_all_engines().values():
    _engine.echo = False


@dataclass(frozen=True)
class ItemSnapshot:
    item: dict[str, Any]
    medias: list[dict[str, Any]]


def _model_to_dict(model_cls: type, instance: Any) -> dict[str, Any]:
    mapper = sa_inspect(model_cls)
    data: dict[str, Any] = {}
    # Use mapped attribute keys (important for renamed columns like User.hashed_password).
    for attr in mapper.column_attrs:
        data[attr.key] = getattr(instance, attr.key)
    return data


def _load_fk_rows_from_mysql(snapshot: ItemSnapshot) -> dict[str, dict[str, Any] | None]:
    item = snapshot.item
    seller_id = item.get("seller_id")
    category_id = item.get("category_id")
    campus_id = item.get("campus_id")

    with db_manager.session_scope("mysql") as session:
        seller = session.get(User, int(seller_id)) if seller_id is not None else None
        category = session.get(Category, int(category_id)) if category_id is not None else None
        campus = session.get(Campus, int(campus_id)) if campus_id is not None else None

        return {
            "seller": _model_to_dict(User, seller) if seller is not None else None,
            "category": _model_to_dict(Category, category) if category is not None else None,
            "campus": _model_to_dict(Campus, campus) if campus is not None else None,
        }


def _find_user_unique_conflicts(session, user_row: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []
    user_id = int(user_row["id"])

    username = user_row.get("username")
    email = user_row.get("email")
    student_id = user_row.get("student_id")

    if username:
        other = session.scalar(select(User).where(User.username == username))
        if other is not None and int(other.id) != user_id:
            conflicts.append(f"username={username} held by users.id={other.id}")
    if email:
        other = session.scalar(select(User).where(User.email == email))
        if other is not None and int(other.id) != user_id:
            conflicts.append(f"email={email} held by users.id={other.id}")
    if student_id:
        other = session.scalar(select(User).where(User.student_id == student_id))
        if other is not None and int(other.id) != user_id:
            conflicts.append(f"student_id={student_id} held by users.id={other.id}")

    return conflicts


def _make_placeholder_user_row(user_id: int, *, target: str) -> dict[str, Any]:
    # Keep within length constraints (username 50, email 100)
    base = f"ghost_{user_id}"
    username = base[:50]
    email_local = (base + f"_{target}")[:64]
    email = f"{email_local}@example.invalid"[:100]

    return {
        "id": int(user_id),
        "username": username,
        "email": email,
        "student_id": None,
        # Column name in DB is password_hash; ORM attribute is hashed_password
        "hashed_password": "placeholder-password-hash",
        "phone": None,
        "avatar_url": None,
        "real_name": None,
        "is_active": True,
        "is_verified": False,
        "is_banned": False,
        "v_clock": None,
        "sync_version": 1,
    }


def _find_category_unique_conflicts(session, category_row: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []
    category_id = int(category_row["id"])
    slug = category_row.get("slug")
    if slug:
        other = session.scalar(select(Category).where(Category.slug == slug))
        if other is not None and int(other.id) != category_id:
            conflicts.append(f"slug={slug} held by categories.id={other.id}")
    return conflicts


def _find_campus_unique_conflicts(session, campus_row: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []
    campus_id = int(campus_row["id"])
    code = campus_row.get("code")
    if code:
        other = session.scalar(select(Campus).where(Campus.code == code))
        if other is not None and int(other.id) != campus_id:
            conflicts.append(f"code={code} held by campuses.id={other.id}")
    return conflicts


def _ensure_fk_rows(
    target: str,
    snapshot: ItemSnapshot,
    *,
    include_fk: bool,
    create_placeholder_users: bool,
) -> list[str]:
    """Ensure FK parents exist in target.

    Returns a list of missing/failed FK descriptions. Empty means ready.
    """

    item = snapshot.item
    seller_id = item.get("seller_id")
    category_id = item.get("category_id")
    campus_id = item.get("campus_id")

    fk_rows = _load_fk_rows_from_mysql(snapshot) if include_fk else {}
    missing: list[str] = []

    with db_manager.session_scope(target) as session:
        # users
        if seller_id is not None and session.get(User, int(seller_id)) is None:
            if not include_fk:
                missing.append(f"users.id={seller_id} (items.seller_id)")
            else:
                user_row = fk_rows.get("seller")
                if not user_row:
                    if create_placeholder_users:
                        placeholder = _make_placeholder_user_row(int(seller_id), target=target)
                        conflicts = _find_user_unique_conflicts(session, placeholder)
                        if conflicts:
                            missing.append(
                                f"users.id={seller_id} (items.seller_id) [placeholder unique conflict: {'; '.join(conflicts)}]"
                            )
                        else:
                            session.merge(User(**placeholder))
                    else:
                        missing.append(f"users.id={seller_id} (items.seller_id) [not found in mysql]")
                else:
                    conflicts = _find_user_unique_conflicts(session, user_row)
                    if conflicts:
                        missing.append(
                            f"users.id={seller_id} (items.seller_id) [unique conflict: {'; '.join(conflicts)}]"
                        )
                    else:
                        session.merge(User(**user_row))

        # categories
        if category_id is not None and session.get(Category, int(category_id)) is None:
            if not include_fk:
                missing.append(f"categories.id={category_id} (items.category_id)")
            else:
                category_row = fk_rows.get("category")
                if not category_row:
                    missing.append(
                        f"categories.id={category_id} (items.category_id) [not found in mysql]"
                    )
                else:
                    conflicts = _find_category_unique_conflicts(session, category_row)
                    if conflicts:
                        missing.append(
                            f"categories.id={category_id} (items.category_id) [unique conflict: {'; '.join(conflicts)}]"
                        )
                    else:
                        session.merge(Category(**category_row))

        # campuses
        if campus_id is not None and session.get(Campus, int(campus_id)) is None:
            if not include_fk:
                missing.append(f"campuses.id={campus_id} (items.campus_id)")
            else:
                campus_row = fk_rows.get("campus")
                if not campus_row:
                    missing.append(f"campuses.id={campus_id} (items.campus_id) [not found in mysql]")
                else:
                    conflicts = _find_campus_unique_conflicts(session, campus_row)
                    if conflicts:
                        missing.append(
                            f"campuses.id={campus_id} (items.campus_id) [unique conflict: {'; '.join(conflicts)}]"
                        )
                    else:
                        session.merge(Campus(**campus_row))

        # After possible backfill, re-check to ensure required rows are now present.
        if seller_id is not None and session.get(User, int(seller_id)) is None:
            missing.append(f"users.id={seller_id} (items.seller_id)")
        if category_id is not None and session.get(Category, int(category_id)) is None:
            missing.append(f"categories.id={category_id} (items.category_id)")
        if campus_id is not None and session.get(Campus, int(campus_id)) is None:
            missing.append(f"campuses.id={campus_id} (items.campus_id)")

    # de-dup while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for entry in missing:
        if entry in seen:
            continue
        seen.add(entry)
        result.append(entry)
    return result


def _load_item_snapshot_from_mysql(item_id: int) -> ItemSnapshot:
    with db_manager.session_scope("mysql") as session:
        item = session.scalar(select(Item).where(Item.id == item_id))
        if item is None:
            raise SystemExit(f"MySQL: item not found: {item_id}")

        medias = list(
            session.scalars(
                select(ItemMedia)
                .where(ItemMedia.item_id == item_id)
                .order_by(ItemMedia.sort_order.asc(), ItemMedia.id.asc())
            )
        )

        item_dict = _model_to_dict(Item, item)
        medias_dicts = [_model_to_dict(ItemMedia, media) for media in medias]

        return ItemSnapshot(item=item_dict, medias=medias_dicts)


def _upsert_into_target(target: str, snapshot: ItemSnapshot, *, missing_only: bool) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "target": target,
        "item_upserted": False,
        "item_skipped": False,
        "medias_upserted": 0,
        "medias_skipped": 0,
    }

    with db_manager.session_scope(target) as session:
        existing_item = session.get(Item, int(snapshot.item["id"]))

        if missing_only and existing_item is not None:
            stats["item_skipped"] = True
        else:
            session.merge(Item(**snapshot.item))
            stats["item_upserted"] = True

        if missing_only:
            existing_media_ids = {
                int(row)
                for row in session.scalars(
                    select(ItemMedia.id).where(ItemMedia.item_id == int(snapshot.item["id"]))
                ).all()
            }
            for media in snapshot.medias:
                if int(media["id"]) in existing_media_ids:
                    stats["medias_skipped"] += 1
                    continue
                session.merge(ItemMedia(**media))
                stats["medias_upserted"] += 1
        else:
            for media in snapshot.medias:
                session.merge(ItemMedia(**media))
                stats["medias_upserted"] += 1

    return stats


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy items from Hub MySQL to MariaDB/Postgres")
    parser.add_argument(
        "--item-id",
        action="append",
        default=[],
        help="Item ID to copy (repeatable).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Copy ALL items from MySQL (uses batched pagination).",
    )
    parser.add_argument(
        "--latest",
        type=int,
        default=0,
        help="Copy latest N items by created_at from MySQL.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Batch size for --all pagination.",
    )
    parser.add_argument(
        "--targets",
        default=",".join(SUPPORTED_TARGETS),
        help=f"Comma-separated targets from {SUPPORTED_TARGETS}. Default: all.",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only insert rows that are missing (do not overwrite existing item row).",
    )
    parser.add_argument(
        "--include-fk",
        action="store_true",
        help="When a target is missing FK parents, copy needed users/categories/campuses from MySQL first.",
    )
    parser.add_argument(
        "--create-placeholder-users",
        action="store_true",
        help="If an item references a seller user missing in MySQL, create a placeholder user in the target DB.",
    )
    parser.add_argument(
        "--strict-fk",
        action="store_true",
        help="Fail fast when FK parents are missing in a target DB (default: skip that target for the item).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-item details (default prints periodic progress).",
    )
    return parser.parse_args(argv)


def _resolve_item_ids(args: argparse.Namespace) -> list[int]:
    item_ids: set[int] = set()

    for raw in args.item_id:
        try:
            item_ids.add(int(raw))
        except ValueError as exc:
            raise SystemExit(f"Invalid --item-id value: {raw}") from exc

    if args.latest and args.latest > 0:
        with db_manager.session_scope("mysql") as session:
            rows = session.scalars(
                select(Item.id).order_by(Item.created_at.desc()).limit(int(args.latest))
            ).all()
        item_ids.update(int(x) for x in rows)

    if args.all:
        raise SystemExit("Use --all without --item-id/--latest")

    if not item_ids:
        raise SystemExit("Provide --item-id or --latest")

    return sorted(item_ids)


def _iter_all_item_ids(batch_size: int) -> list[list[int]]:
    """Yield item_id batches ordered by (created_at DESC, id DESC) using keyset pagination."""

    if batch_size <= 0:
        raise SystemExit("--batch-size must be > 0")

    batches: list[list[int]] = []
    last_created_at = None
    last_id = None

    while True:
        with db_manager.session_scope("mysql") as session:
            stmt = select(Item.id, Item.created_at).order_by(Item.created_at.desc(), Item.id.desc()).limit(
                int(batch_size)
            )
            if last_created_at is not None and last_id is not None:
                stmt = stmt.where(
                    (Item.created_at < last_created_at)
                    | ((Item.created_at == last_created_at) & (Item.id < last_id))
                )

            rows = session.execute(stmt).all()

        if not rows:
            break

        batch_ids = [int(row[0]) for row in rows]
        batches.append(batch_ids)

        last_created_at = rows[-1][1]
        last_id = int(rows[-1][0])

        if len(rows) < int(batch_size):
            break

    return batches


def _resolve_targets(raw: str) -> list[str]:
    targets = [t.strip() for t in (raw or "").split(",") if t.strip()]
    invalid = [t for t in targets if t not in SUPPORTED_TARGETS]
    if invalid:
        raise SystemExit(f"Invalid targets: {invalid}. Supported: {SUPPORTED_TARGETS}")
    if not targets:
        raise SystemExit("No targets selected")
    return targets


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    targets = _resolve_targets(args.targets)

    if args.all and (args.item_id or (args.latest and args.latest > 0)):
        raise SystemExit("Do not combine --all with --item-id/--latest")

    if args.all:
        batches = _iter_all_item_ids(int(args.batch_size))
        item_ids = [item_id for batch in batches for item_id in batch]
    else:
        item_ids = _resolve_item_ids(args)

    print(
        f"Copy plan: items={len(item_ids)} targets={targets} mode={'missing-only' if args.missing_only else 'upsert'} "
        f"include_fk={bool(args.include_fk)} placeholder_users={bool(args.create_placeholder_users)}"
    )

    processed = 0

    for item_id in item_ids:
        snapshot = _load_item_snapshot_from_mysql(item_id)

        title = snapshot.item.get("title")
        if args.verbose:
            print(f"\nItem {item_id} ({title})")

        for target in targets:
            missing_fk = _ensure_fk_rows(
                target,
                snapshot,
                include_fk=bool(args.include_fk),
                create_placeholder_users=bool(args.create_placeholder_users),
            )
            if missing_fk:
                if args.verbose:
                    msg = f"  -> {target}: skip (missing FK: {', '.join(missing_fk)})"
                    print(msg)
                if args.strict_fk:
                    raise SystemExit(f"{target}: missing FK(s): {', '.join(missing_fk)}")
                continue
            stats = _upsert_into_target(target, snapshot, missing_only=args.missing_only)
            if args.verbose:
                print(
                    f"  -> {target}: item={'upsert' if stats['item_upserted'] else 'skip'} "
                    f"medias_upserted={stats['medias_upserted']} medias_skipped={stats['medias_skipped']}"
                )

        processed += 1
        if not args.verbose and (processed % 50 == 0):
            print(f"Progress: {processed}/{len(item_ids)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
