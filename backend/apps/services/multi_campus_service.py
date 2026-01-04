"""
多校区商品服务
负责在不同校区数据库间协调商品操作
"""
from typing import List, Optional
from sqlalchemy.orm import Session

from apps.core.database import db_manager
from apps.services.business_logic import ItemService


class MultiCampusItemService:
    """多校区商品服务"""

    @staticmethod
    def create_item_in_campus(
        campus_code: str,
        seller_id: int,
        title: str,
        description: str,
        price: float,
        category_name: str,
        images: List[str] = None,
        status: str = "available",
        condition: str = "good"
    ):
        """
        在指定校区创建商品

        Args:
            campus_code: 校区代码 (main, south, north)
            seller_id: 卖家ID
            title: 商品标题
            description: 商品描述
            price: 价格
            category_name: 分类名称
            images: 图片URL列表
            status: 商品状态
            condition: 商品成色
        """
        # 数据库间已实时同步：不再按校区切换数据库，只写入默认数据库。
        with db_manager.session_scope("mysql") as session:
            return ItemService.create_item(
                session=session,
                seller_id=seller_id,
                title=title,
                description=description,
                price=price,
                category_name=category_name,
                campus_code=campus_code,
                images=images or [],
                status=status,
                condition=condition
            )

    @staticmethod
    def get_items_by_campus(campus_code: str, limit: int = 50, offset: int = 0):
        """
        获取指定校区的商品列表
        """
        with db_manager.session_scope("mysql") as session:
            return ItemService.get_items(session, limit=limit, offset=offset, campus=campus_code)

    @staticmethod
    def get_all_campuses_items():
        """
        获取所有校区的商品汇总（合并各校区数据库中的商品）
        返回 (items, total)
        """
        campus_codes = ["main", "south", "north", "hub"]
        all_items = []
        total = 0

        # 为简单起见：从每个校区取足够多的记录，然后合并、排序并分页
        # 这在数据量大时需要优化（使用跨库索引或集中库），但足以解决当前显示遗漏的问题。
        for code in campus_codes:
            db_name_map = {
                "hub": "mysql",
                "main": "mariadb",
                "south": "postgres",
                "north": "mysql",
            }
            db_name = db_name_map.get(code, "mysql")
            try:
                with db_manager.session_scope(db_name) as session:
                    # 获取足够多的记录（取前 200 条以保证合并结果的正确性）
                    items, sub_total = ItemService.get_items(
                        session=session,
                        page=1,
                        page_size=200,
                        category=None,
                        condition=None,
                        campus=None,
                        min_price=None,
                        max_price=None,
                        keyword=None,
                        status="available",
                    )

                    # 将每个 item 序列化为轻量字典，包含来源校区标识，避免跨会话访问已关闭对象
                    for it in items:
                        # 获取图片
                        medias = session.execute(
                            __import__('sqlalchemy').sql.select(
                                __import__('apps.core.models', fromlist=['ItemMedia']).ItemMedia
                            ).where(__import__('apps.core.models', fromlist=['ItemMedia']).ItemMedia.item_id == it.id)
                        ).scalars().all()
                        images = [m.url for m in medias]

                        # 获取分类和卖家名称
                        cat = session.get(__import__('apps.core.models', fromlist=['Category']).Category, it.category_id) if it.category_id else None
                        seller = session.get(__import__('apps.core.models', fromlist=['User']).User, it.seller_id)

                        item_dict = {
                            "id": int(it.id),
                            "title": it.title or "",
                            "description": it.description or "",
                            "price": float(it.price or 0),
                            "category": cat.name if cat else "其他",
                            "campus": code,
                            "images": images,
                            "status": it.status or "available",
                            "condition": it.condition,
                            "seller_id": it.seller_id,
                            "seller_name": seller.username if seller else "未知",
                            "view_count": int(it.view_count or 0),
                            "favorite_count": int(it.favorite_count or 0),
                            "created_at": it.created_at,
                            "updated_at": it.updated_at,
                        }
                        all_items.append(item_dict)
                    total += sub_total
            except Exception:
                # 忽略单个校区出现的错误，继续合并其他校区
                continue

        # 根据创建时间降序排序
        all_items.sort(key=lambda x: x["created_at"] or x["id"], reverse=True)
        return all_items, total