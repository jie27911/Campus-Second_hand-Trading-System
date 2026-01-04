"""Seed demo data into Hub(MySQL) for Advanced Query demos.

Usage (docker):
  docker compose exec -T gateway python /app/scripts/seed_demo_data.py --users 200 --items 1000 --transactions 800 --messages 2000

Notes:
- Writes to Hub/MySQL only. This is intentional because the Advanced Query page runs SQL against mysql.
- Uses fixed bcrypt hash identical to the built-in admin seed, so demo users can share a known password if needed.
"""

from __future__ import annotations

import argparse
import random
import string
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import text

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from apps.core.database import db_manager


DEMO_BCRYPT_HASH = "$2b$12$KLysJ85PhtqHTQGptnrr6.c1yOdB51s1j65u8dsOPtiVssLJKi/De"


def _ensure_categories_and_campuses(session) -> tuple[list[int], list[int]]:
    category_ids = session.execute(text("SELECT id FROM categories ORDER BY id")).scalars().all()
    if not category_ids:
        categories = [
            {"id": 1001, "name": "数码", "slug": "digital", "description": "数码产品", "sort_order": 1, "is_active": 1},
            {"id": 1002, "name": "书籍", "slug": "books", "description": "教材/课外书", "sort_order": 2, "is_active": 1},
            {"id": 1003, "name": "生活", "slug": "life", "description": "生活用品", "sort_order": 3, "is_active": 1},
            {"id": 1004, "name": "运动", "slug": "sports", "description": "运动器材", "sort_order": 4, "is_active": 1},
        ]
        session.execute(
            text(
                """
                INSERT INTO categories (id, name, slug, description, sort_order, is_active)
                VALUES (:id, :name, :slug, :description, :sort_order, :is_active)
                """
            ),
            categories,
        )
        category_ids = [c["id"] for c in categories]

    campus_ids = session.execute(text("SELECT id FROM campuses ORDER BY id")).scalars().all()
    if not campus_ids:
        campuses = [
            {"id": 2001, "name": "本部", "code": "main", "address": "主校区", "description": "本部校区", "sort_order": 1, "is_active": 1},
            {"id": 2002, "name": "南校区", "code": "south", "address": "南校区", "description": "南校区", "sort_order": 2, "is_active": 1},
        ]
        session.execute(
            text(
                """
                INSERT INTO campuses (id, name, code, address, description, sort_order, is_active)
                VALUES (:id, :name, :code, :address, :description, :sort_order, :is_active)
                """
            ),
            campuses,
        )
        campus_ids = [c["id"] for c in campuses]

    return list(category_ids), list(campus_ids)


def seed_demo_data(*, users: int, items: int, transactions: int, messages: int, seed: int, dry_run: bool) -> dict:
    rng = random.Random(seed)
    now_tag = datetime.utcnow().strftime("%Y%m%d%H%M%S")

    with db_manager.session_scope("mysql") as session:
        category_ids, campus_ids = _ensure_categories_and_campuses(session)

        existing_user_ids = session.execute(text("SELECT id FROM users ORDER BY id LIMIT 2000")).scalars().all()

        new_user_rows: List[Dict[str, Any]] = []
        for i in range(users):
            suffix = "".join(rng.choices(string.ascii_lowercase + string.digits, k=6))
            username = f"demo_{now_tag}_{i}_{suffix}"
            email = f"{username}@demo.local"
            new_user_rows.append(
                {
                    "id": int(3_000_000_000_000 + rng.randrange(1_000_000_000)),
                    "username": username,
                    "email": email,
                    "password_hash": DEMO_BCRYPT_HASH,
                    "is_active": 1,
                    "is_verified": 1,
                    "credit_score": rng.randint(60, 100),
                }
            )

        if new_user_rows and not dry_run:
            session.execute(
                text(
                    """
                    INSERT INTO users (id, username, email, password_hash, is_active, is_verified, credit_score)
                    VALUES (:id, :username, :email, :password_hash, :is_active, :is_verified, :credit_score)
                    """
                ),
                new_user_rows,
            )

        user_ids = list(existing_user_ids) + [row["id"] for row in new_user_rows]
        if not user_ids:
            raise RuntimeError("No users found; ensure DB init ran and admin exists")

        item_ids: List[int] = []
        item_rows: List[Dict[str, Any]] = []
        condition_types = ["全新", "99新", "95新", "9成新", "二手"]
        # MySQL/MariaDB init schema defines `items.status` as:
        # ENUM('available', 'reserved', 'sold', 'deleted')
        # Keep most items available so Advanced Query demos have enough results.
        statuses = ["available"] * 8 + ["reserved", "sold"]
        for i in range(items):
            item_id = int(4_000_000_000_000 + rng.randrange(2_000_000_000))
            item_ids.append(item_id)
            seller_id = rng.choice(user_ids)
            price = round(rng.uniform(5, 999), 2)
            original_price = round(price * rng.uniform(1.05, 1.8), 2)
            item_rows.append(
                {
                    "id": item_id,
                    "seller_id": seller_id,
                    "category_id": rng.choice(category_ids),
                    "campus_id": rng.choice(campus_ids),
                    "title": f"演示商品 #{i} ({now_tag})",
                    "description": f"用于高级查询演示的数据。随机种子={seed}",
                    "price": price,
                    "original_price": original_price,
                    "condition_type": rng.choice(condition_types),
                    "location": rng.choice(["教学楼", "宿舍区", "图书馆", "食堂"]),
                    "contact_info": rng.choice(["微信:demo", "电话:13800000000", "站内私信"]),
                    "status": rng.choice(statuses),
                    "is_negotiable": 1 if rng.random() < 0.3 else 0,
                    "is_shipped": 1 if rng.random() < 0.2 else 0,
                    "view_count": rng.randint(0, 5000),
                    "favorite_count": rng.randint(0, 500),
                    "inquiry_count": rng.randint(0, 300),
                }
            )

        if item_rows and not dry_run:
            session.execute(
                text(
                    """
                    INSERT INTO items (
                        id, seller_id, category_id, campus_id,
                        title, description, price, original_price,
                        condition_type, location, contact_info,
                        status, is_negotiable, is_shipped,
                        view_count, favorite_count, inquiry_count
                    ) VALUES (
                        :id, :seller_id, :category_id, :campus_id,
                        :title, :description, :price, :original_price,
                        :condition_type, :location, :contact_info,
                        :status, :is_negotiable, :is_shipped,
                        :view_count, :favorite_count, :inquiry_count
                    )
                    """
                ),
                item_rows,
            )

        # Build candidate items for generating transactions.
        planned_items = [(row["id"], int(row["seller_id"]), float(row["price"])) for row in item_rows]
        existing_items = (
            session.execute(
                text("SELECT id, seller_id, price FROM items ORDER BY id DESC LIMIT 2000")
            )
            .mappings()
            .all()
        )
        existing_items_tuples = [
            (int(r["id"]), int(r["seller_id"]), float(r["price"]))
            for r in existing_items
            if r.get("id") is not None and r.get("seller_id") is not None and r.get("price") is not None
        ]
        candidate_items = planned_items + existing_items_tuples

        tx_rows: List[Dict[str, Any]] = []
        tx_statuses = ["completed", "completed", "completed", "pending", "cancelled"]
        for i in range(transactions):
            if not candidate_items:
                break
            item_id, seller_id, item_price = rng.choice(candidate_items)
            buyer_candidates = [uid for uid in user_ids if uid != int(seller_id)]
            buyer_id = rng.choice(buyer_candidates or user_ids)
            final_amount = float(item_price) * rng.uniform(0.9, 1.0)
            tx_rows.append(
                {
                    "id": int(5_000_000_000_000 + rng.randrange(2_000_000_000)),
                    "item_id": item_id,
                    "buyer_id": buyer_id,
                    "seller_id": int(seller_id),
                    "item_price": item_price,
                    "final_amount": round(final_amount, 2),
                    "status": rng.choice(tx_statuses),
                    "buyer_contact": "demo@buyer",
                    "seller_contact": "demo@seller",
                    "meeting_location": rng.choice(["图书馆门口", "食堂门口", "宿舍楼下"]),
                }
            )

        if tx_rows and not dry_run:
            session.execute(
                text(
                    """
                    INSERT INTO transactions (
                        id, item_id, buyer_id, seller_id,
                        item_price, final_amount, status,
                        buyer_contact, seller_contact, meeting_location
                    ) VALUES (
                        :id, :item_id, :buyer_id, :seller_id,
                        :item_price, :final_amount, :status,
                        :buyer_contact, :seller_contact, :meeting_location
                    )
                    """
                ),
                tx_rows,
            )

        msg_rows: List[Dict[str, Any]] = []
        for i in range(messages):
            sender = rng.choice(user_ids)
            receiver = rng.choice([uid for uid in user_ids if uid != sender] or user_ids)
            msg_rows.append(
                {
                    "id": int(6_000_000_000_000 + rng.randrange(2_000_000_000)),
                    "sender_id": sender,
                    "receiver_id": receiver,
                    "item_id": rng.choice(item_ids) if item_ids else None,
                    "content": f"演示消息 {i} - {now_tag}",
                    "is_read": 1 if rng.random() < 0.6 else 0,
                    "is_deleted_by_sender": 0,
                    "is_deleted_by_receiver": 0,
                    "sync_version": 1,
                    "v_clock": None,
                }
            )

        if msg_rows and not dry_run:
            session.execute(
                text(
                    """
                    INSERT INTO messages (
                        id, sender_id, receiver_id, item_id, content,
                        is_read, is_deleted_by_sender, is_deleted_by_receiver,
                        sync_version, v_clock
                    ) VALUES (
                        :id, :sender_id, :receiver_id, :item_id, :content,
                        :is_read, :is_deleted_by_sender, :is_deleted_by_receiver,
                        :sync_version, :v_clock
                    )
                    """
                ),
                msg_rows,
            )

        return {
            "seed": seed,
            "dry_run": dry_run,
            "inserted": {
                "users": len(new_user_rows),
                "items": len(item_rows),
                "transactions": len(tx_rows),
                "messages": len(msg_rows),
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data into Hub/MySQL")
    parser.add_argument("--users", type=int, default=200)
    parser.add_argument("--items", type=int, default=1000)
    parser.add_argument("--transactions", type=int, default=800)
    parser.add_argument("--messages", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true", help="Do not write, only print planned counts")
    args = parser.parse_args()

    result = seed_demo_data(
        users=max(args.users, 0),
        items=max(args.items, 0),
        transactions=max(args.transactions, 0),
        messages=max(args.messages, 0),
        seed=max(args.seed, 0),
        dry_run=bool(args.dry_run),
    )

    inserted = result["inserted"]
    print(
        "seed_demo_data done: "
        f"users={inserted['users']}, items={inserted['items']}, "
        f"transactions={inserted['transactions']}, messages={inserted['messages']}, "
        f"dry_run={result['dry_run']}"
    )


if __name__ == "__main__":
    main()
