"""Cross-campus item service for price comparison."""

from typing import Any, Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from apps.core.database import DatabaseManager
from apps.core.models import Item, ItemCrossCampus


class CrossCampusItemService:
    """Service for cross-campus item operations."""

    @staticmethod
    def get_cross_campus_prices(item_id: int, session: Session) -> Dict[str, Any]:
        """Get price information for an item across all campuses."""
        # Get the original item
        item = session.get(Item, item_id)
        if not item:
            return {}

        result = {
            item.campus: {
                "price": float(item.price),
                "title": item.title,
                "campus": item.campus,
                "item_id": item.id,
            }
        }

        # Get cross-campus mappings
        cross_items = (
            session.execute(select(ItemCrossCampus).where(ItemCrossCampus.item_id == item_id))
            .scalars()
            .all()
        )

        # For each cross-campus mapping, try to get the actual item from that campus
        for cross_item in cross_items:
            if cross_item.cross_item_id:
                # Try to get the item from the target campus database
                target_item = CrossCampusItemService._get_item_from_campus(
                    cross_item.campus, cross_item.cross_item_id
                )
                if target_item:
                    result[cross_item.campus] = {
                        "price": float(target_item["price"]),
                        "title": target_item["title"],
                        "campus": cross_item.campus,
                        "item_id": cross_item.cross_item_id,
                    }
                elif cross_item.cross_price:
                    # Fallback to stored price if item not found
                    result[cross_item.campus] = {
                        "price": float(cross_item.cross_price),
                        "title": f"{item.title} ({cross_item.campus})",
                        "campus": cross_item.campus,
                        "item_id": cross_item.cross_item_id,
                    }

        return result

    @staticmethod
    def _get_item_from_campus(campus: str, item_id: int) -> Optional[Dict[str, Any]]:
        """Get an item from a specific campus database."""
        try:
            db_manager = DatabaseManager()
            # Get the appropriate database connection for the campus
            if campus == "main":
                # MariaDB - 本部校区
                engine = db_manager.get_engine("mariadb")
            elif campus == "branch":
                # PostgreSQL - 分校区
                engine = db_manager.get_engine("postgres")
            elif campus == "hub":
                # MySQL - 价格情报中心
                engine = db_manager.get_engine("mysql")
            else:
                return None

            with engine.connect() as conn:
                # Query the item from the target database
                query = text(
                    """
                    SELECT id, title, price, campus
                    FROM items
                    WHERE id = :item_id AND status = 'available'
                """
                )
                result = conn.execute(query, {"item_id": item_id}).fetchone()
                if result:
                    return {
                        "id": result[0],
                        "title": result[1],
                        "price": result[2],
                        "campus": result[3],
                    }
        except Exception as e:
            print(f"Error getting item from {campus}: {e}")
            return None
        return None

    @staticmethod
    def find_similar_items_across_campuses(item: Item, session: Session) -> List[Dict[str, Any]]:
        """Find similar items across campuses based on title and category."""
        # Simple similarity based on title keywords and category
        category_id = item.category_id

        similar_items = []

        # Search in each campus database
        campuses = ["main", "branch", "hub"]
        db_manager = DatabaseManager()

        for campus in campuses:
            if campus == item.campus:
                continue  # Skip the same campus

            try:
                # Get the appropriate database connection
                if campus == "main":
                    engine = db_manager.get_engine("mariadb")
                elif campus == "branch":
                    engine = db_manager.get_engine("postgres")
                elif campus == "hub":
                    engine = db_manager.get_engine("mysql")
                else:
                    continue

                with engine.connect() as conn:
                    # Find similar items based on category and title keywords
                    query = text(
                        """
                        SELECT id, title, price, category_id
                        FROM items
                        WHERE status = 'available'
                        AND category_id = :category_id
                        AND id != :current_id
                        ORDER BY created_at DESC
                        LIMIT 5
                    """
                    )
                    results = conn.execute(
                        query,
                        {
                            "category_id": category_id,
                            "current_id": item.id if campus == item.campus else 0,
                        },
                    ).fetchall()

                    for result in results:
                        similarity = CrossCampusItemService._calculate_similarity(
                            item.title, result[1]
                        )
                        if similarity > 0.3:  # Minimum similarity threshold
                            similar_items.append(
                                {
                                    "campus": campus,
                                    "item_id": result[0],
                                    "title": result[1],
                                    "price": float(result[2]),
                                    "similarity_score": similarity,
                                }
                            )

            except Exception as e:
                print(f"Error searching {campus}: {e}")
                continue

        # Sort by similarity score
        similar_items.sort(key=lambda x: x["similarity_score"], reverse=True)
        return similar_items[:10]  # Return top 10

    @staticmethod
    def _calculate_similarity(title1: str, title2: str) -> float:
        """Calculate simple text similarity between two titles."""
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        if not union:
            return 0.0

        return len(intersection) / len(union)

    @staticmethod
    def sync_cross_campus_prices(session: Session) -> None:
        """Sync prices across campuses for all items."""
        # Get all items
        items = session.execute(select(Item)).scalars().all()

        for item in items:
            # Find similar items across campuses
            similar_items = CrossCampusItemService.find_similar_items_across_campuses(item, session)

            # Update or create cross-campus mappings
            for similar_item in similar_items:
                # Check if mapping already exists
                existing = session.execute(
                    select(ItemCrossCampus).where(
                        ItemCrossCampus.item_id == item.id,
                        ItemCrossCampus.campus == similar_item["campus"],
                    )
                ).scalar_one_or_none()

                if existing:
                    # Update existing mapping
                    existing.cross_item_id = similar_item["item_id"]
                    existing.cross_price = similar_item["price"]
                    existing.similarity_score = similar_item["similarity_score"]
                    existing.last_sync_at = session.execute(text("SELECT NOW()")).scalar()
                else:
                    # Create new mapping
                    cross_item = ItemCrossCampus(
                        item_id=item.id,
                        campus=similar_item["campus"],
                        cross_item_id=similar_item["item_id"],
                        cross_price=similar_item["price"],
                        similarity_score=similar_item["similarity_score"],
                    )
                    session.add(cross_item)

    @staticmethod
    def create_item_in_campus(
        campus: str,
        seller_id: int,
        title: str,
        description: str,
        price: float,
        category_name: str,
        images: List[str],
        status: str,
        condition: str,
    ) -> Optional[Dict[str, Any]]:
        """Create an item in a specific campus database."""
        try:
            db_manager = DatabaseManager()

            # Get the appropriate database connection
            if campus == "main":
                engine = db_manager.get_engine("mariadb")
            elif campus == "branch":
                engine = db_manager.get_engine("postgres")
            elif campus == "hub":
                engine = db_manager.get_engine("mysql")
            else:
                return None

            with engine.begin() as conn:
                # First, ensure category exists
                category_query = text(
                    """
                    SELECT id FROM categories WHERE name = :category_name LIMIT 1
                """
                )
                category_result = conn.execute(
                    category_query, {"category_name": category_name}
                ).fetchone()

                category_id = None
                if category_result:
                    category_id = category_result[0]
                else:
                    # Create category if it doesn't exist
                    insert_category = text(
                        """
                        INSERT INTO categories (name, slug) VALUES (:name, :slug)
                    """
                    )
                    conn.execute(
                        insert_category,
                        {"name": category_name, "slug": category_name.lower().replace(" ", "-")},
                    )
                    category_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()

                # Insert the item
                insert_item = text(
                    """
                    INSERT INTO items (seller_id, category_id, title, description, price, 
                                     condition_type, status, campus, created_at, updated_at)
                    VALUES (:seller_id, :category_id, :title, :description, :price,
                           :condition, :status, :campus, NOW(), NOW())
                """
                )

                conn.execute(
                    insert_item,
                    {
                        "seller_id": seller_id,
                        "category_id": category_id,
                        "title": title,
                        "description": description,
                        "price": price,
                        "condition": condition,
                        "status": status,
                        "campus": campus,
                    },
                )

                # Get the inserted item ID
                if campus == "branch":  # PostgreSQL
                    item_id = conn.execute(text("SELECT LASTVAL()")).scalar()
                else:  # MySQL/MariaDB
                    item_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()

                # Insert images if provided
                if images:
                    for image_url in images:
                        insert_image = text(
                            """
                            INSERT INTO item_images (item_id, image_url, sort_order)
                            VALUES (:item_id, :image_url, 0)
                        """
                        )
                        conn.execute(insert_image, {"item_id": item_id, "image_url": image_url})

                return {"id": item_id, "title": title, "price": price, "campus": campus}

        except Exception as e:
            print(f"Error creating item in {campus}: {e}")
            return None
