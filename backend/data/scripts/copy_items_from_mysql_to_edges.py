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
  docker compose exec gateway python data/scripts/copy_items_from_mysql_to_edges.py --item-id 123

Examples:
  # Upsert one item (overwrite fields to match MySQL)
  docker compose exec gateway python data/scripts/copy_items_from_mysql_to_edges.py --item-id 265...

  # Copy latest 10 items (upsert)
  docker compose exec gateway python data/scripts/copy_items_from_mysql_to_edges.py --latest 10

  # Only insert missing rows (do not overwrite existing item row)
  docker compose exec gateway python data/scripts/copy_items_from_mysql_to_edges.py --latest 10 --missing-only
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.inspection import inspect as sa_inspect

from apps.core.database import db_manager
from apps.core.models.inventory import Campus, Category, Item, ItemMedia
from apps.core.models.users import User


SUPPORTED_TARGETS = ("mariadb", "postgres")


@dataclass(frozen=True)
class ItemSnapshot:
    item: dict[str, Any]
    medias: list[dict[str, Any]]


def _model_to_dict(model_cls: type, instance: Any) -> dict[str, Any]:
    mapper = sa_inspect(model_cls)
    return {col.key: getattr(instance, col.key) for col in mapper.columns}


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


def _require_fk_rows_exist(target: str, snapshot: ItemSnapshot) -> None:
    item = snapshot.item
    seller_id = item.get("seller_id")
    category_id = item.get("category_id")
    campus_id = item.get("campus_id")

    with db_manager.session_scope(target) as session:
        if seller_id is not None and session.get(User, int(seller_id)) is None:
            raise SystemExit(
                f"{target}: missing FK users.id={seller_id} required by items.seller_id"
            )
        if category_id is not None and session.get(Category, int(category_id)) is None:
            raise SystemExit(
                f"{target}: missing FK categories.id={category_id} required by items.category_id"
            )
        if campus_id is not None and session.get(Campus, int(campus_id)) is None:
            raise SystemExit(
                f"{target}: missing FK campuses.id={campus_id} required by items.campus_id"
            )


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
        "--latest",
        type=int,
        default=0,
        help="Copy latest N items by created_at from MySQL.",
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

    if not item_ids:
        raise SystemExit("Provide --item-id or --latest")

    return sorted(item_ids)


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
    item_ids = _resolve_item_ids(args)

    print(
        f"Copy plan: items={len(item_ids)} targets={targets} mode={'missing-only' if args.missing_only else 'upsert'}"
    )

    for item_id in item_ids:
        snapshot = _load_item_snapshot_from_mysql(item_id)

        title = snapshot.item.get("title")
        print(f"\nItem {item_id} ({title})")

        for target in targets:
            _require_fk_rows_exist(target, snapshot)
            stats = _upsert_into_target(target, snapshot, missing_only=args.missing_only)
            print(
                f"  -> {target}: item={'upsert' if stats['item_upserted'] else 'skip'} "
                f"medias_upserted={stats['medias_upserted']} medias_skipped={stats['medias_skipped']}"
            )

    print("\nDone.")


if __name__ == "__main__":
    main()
