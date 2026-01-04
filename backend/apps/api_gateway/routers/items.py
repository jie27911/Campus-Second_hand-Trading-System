"""
实现完整的商品路由 - 使用业务逻辑服务
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api_gateway.dependencies import get_current_user, get_db_session, get_current_user_optional, get_user_campus_db_session
from apps.core.database import db_manager
from apps.core.models import User, Item, Category, ItemMedia
from apps.services.business_logic import ItemService, FavoriteService

router = APIRouter(prefix="/items", tags=["商品管理"])


# ==================== Pydantic Models ====================

class CampusPriceComparison(BaseModel):
    """跨校区价格比较（前端仅依赖部分字段，其他字段保持可选以兼容不同数据源）"""

    # Use string to avoid JS number precision loss for snowflake-style BIGINT ids.
    item_id: str
    title: str
    category: str
    prices: dict
    lowest_price: float
    lowest_campus: str
    price_diff: float
    updated_at: datetime
    seller_name: Optional[str] = None
    view_count: int = 0
    favorite_count: int = 0
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ItemCreateRequest(BaseModel):
    """创建商品请求"""
    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    price: float = Field(..., gt=0)
    category: str = Field(default="其他")
    campus: str = Field(default="main", pattern="^(main|south|north)$")
    images: List[str] = Field(default_factory=list)
    status: str = Field(default="available")
    condition: str = Field(default="good")

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_category(cls, value):
        return value or "其他"

    @field_validator("condition", mode="before")
    @classmethod
    def _coerce_condition(cls, value):
        # PublishItemView uses like-new/excellent; normalize for ItemService mapping
        if value == "like-new":
            return "like_new"
        if value == "excellent":
            return "very_good"
        return value or "good"


class ItemUpdateRequest(BaseModel):
    """更新商品请求"""
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    status: Optional[str] = None
    condition: Optional[str] = None


class ItemResponse(BaseModel):
    """商品响应"""
    # Use string to avoid JS number precision loss for snowflake-style BIGINT ids.
    id: str
    title: str
    description: str
    price: float
    category: str
    campus: str = "main"
    images: List[str]
    status: str
    condition: str = "good"
    # 注意：seller_id 是商品表里的卖家ID（校区库内的用户ID），不一定等于hub库用户ID。
    seller_id: str
    # seller_hub_id 用于跨库（hub）场景，比如聊天系统。
    seller_hub_id: Optional[str] = None
    seller_username: Optional[str] = None
    seller_name: str
    view_count: int = 0
    favorite_count: int = 0
    created_at: datetime
    updated_at: datetime
    # 多校区价格情报
    campus_prices: Optional[dict] = None  # {"main": 100, "branch1": 95, "branch2": 105}



class ItemListResponse(BaseModel):
    """商品列表响应"""
    items: List[ItemResponse]
    total: int
    page: int
    page_size: int


def _serialize_item(session: Session, item: Item) -> ItemResponse:
    """统一的商品序列化函数"""
    category = session.get(Category, item.category_id)
    seller = session.get(User, item.seller_id)
    medias = session.execute(
        select(ItemMedia).where(ItemMedia.item_id == item.id)
    ).scalars().all()
    
    # 获取校区信息
    campus_name = "main"  # 默认值
    if item.campus_id:
        from apps.core.models import Campus
        campus = session.get(Campus, item.campus_id)
        if campus:
            campus_name = campus.code
    
    return ItemResponse(
        id=str(item.id),
        title=item.title,
        description=item.description or "",
        price=float(item.price),
        category=category.name if category else "其他",
        campus=campus_name,
        images=[media.url for media in medias],
        status=item.status or "available",
        condition=item.condition,
        seller_id=str(item.seller_id),
        seller_name=seller.username if seller else "未知",
        view_count=item.view_count or 0,
        favorite_count=item.favorite_count or 0,
        created_at=item.created_at,
        updated_at=item.updated_at
    )


# ==================== API路由 ====================

@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: ItemCreateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_user_campus_db_session),
):
    """发布新商品"""
    # 需求：发布商品应写入“用户所属校区”的数据库，并且用户默认看到该库的数据。
    # 这里 session 来自 get_user_campus_db_session，会自动按用户 profile.campus 选择库。

    db_user = getattr(session, "_current_db_user", current_user)

    # 使用所属校区创建商品。payload.campus 仅用于写入 campus 字段/归属（由 ItemService 解析到 campus_id）。
    item = ItemService.create_item(
        session=session,
        seller_id=db_user.id,
        title=payload.title,
        description=payload.description,
        price=payload.price,
        category_name=payload.category,
        campus_code=payload.campus,
        images=payload.images,
        status=payload.status,
        condition=payload.condition,
    )
    # Ensure server defaults are loaded (created_at/updated_at).
    session.flush()
    try:
        session.refresh(item)
    except Exception:
        pass

    medias = session.execute(select(ItemMedia).where(ItemMedia.item_id == item.id)).scalars().all()
    category = session.get(Category, item.category_id)

    campus_name = "main"
    if item.campus_id:
        from apps.core.models import Campus
        campus = session.get(Campus, item.campus_id)
        if campus:
            campus_name = campus.code

    return ItemResponse(
        id=str(item.id),
        title=item.title,
        description=item.description or "",
        price=float(item.price),
        category=category.name if category else "其他",
        campus=campus_name,
        images=[m.url for m in medias],
        status=item.status,
        condition=item.condition,
        seller_id=str(db_user.id),
        seller_name=db_user.username,
        view_count=item.view_count or 0,
        favorite_count=item.favorite_count or 0,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
    # 从各个校区数据库获取价格信息
    comparisons = []
    
    # 这里简化实现，实际应该从各个数据库查询
    # 现在返回模拟数据
    mock_data = [
        {
            "item_id": 1,
            "title": "iPad Pro 12.9寸",
            "category": "数码产品",
            "prices": {"main": 5899, "branch": 5799, "hub": 5849},
            "lowest_price": 5799,
            "lowest_campus": "branch",
            "price_diff": 100,
            "updated_at": datetime.utcnow(),
            "seller_name": "本部商家",
            "view_count": 1250,
            "favorite_count": 89,
            "created_at": datetime.utcnow()
        },
        {
            "item_id": 2,
            "title": "MacBook Air M2",
            "category": "数码产品", 
            "prices": {"main": 8999, "branch": 8899, "hub": 8949},
            "lowest_price": 8899,
            "lowest_campus": "branch",
            "price_diff": 100,
            "updated_at": datetime.utcnow(),
            "seller_name": "分校商家",
            "view_count": 980,
            "favorite_count": 156,
            "created_at": datetime.utcnow()
        }
    ]
    
    return [CampusPriceComparison(**item) for item in mock_data]


@router.get("", response_model=ItemListResponse)
async def get_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None, description="商品分类"),
    condition: Optional[str] = Query(None, description="商品成色"),
    campus: Optional[str] = Query(None, description="校区筛选（默认使用当前用户所属校区）"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    min_price: Optional[float] = Query(None, ge=0, description="最低价格"),
    max_price: Optional[float] = Query(None, ge=0, description="最高价格"),
    item_status: str = Query("available", description="商品状态"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_user_campus_db_session),
):
    """获取商品列表"""

    # session 已按用户所属校区选择数据库。
    # campus 参数如果提供，仅允许等于用户所属校区（避免跨校区读取）。
    if campus is not None:
        valid_campuses = {"main", "south", "north", "hub"}
        if campus not in valid_campuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的校区代码: {campus}，有效值: {', '.join(sorted(valid_campuses))}",
            )
        session_campus = None
        try:
            session_campus = getattr(getattr(current_user, "profile", None), "campus", None)
        except Exception:
            session_campus = None
        # Normalize stored campus name/code.
        campus_name_to_code = {
            "本部校区": "main",
            "南校区": "south",
            "北校区": "north",
            "main": "main",
            "south": "south",
            "north": "north",
            "hub": "hub",
        }
        user_campus_code = campus_name_to_code.get(session_campus, "hub")
        if campus != user_campus_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"仅允许查看所属校区({user_campus_code})的数据",
            )

    items, total = ItemService.get_items(
        session=session,
        page=page,
        page_size=page_size,
        category=category,
        condition=condition,
        campus=campus,
        min_price=min_price,
        max_price=max_price,
        keyword=keyword,
        status=item_status,
    )
    items_data = [_serialize_item(session, item) for item in items]

    return ItemListResponse(
        items=items_data,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/my", response_model=ItemListResponse)
async def get_my_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="筛选商品状态"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_user_campus_db_session)
):
    """获取当前用户发布的商品"""
    db_user = getattr(session, "_current_db_user", current_user)

    status_map = {
        "selling": "available",
        "available": "available",
        "sold": "sold",
        "removed": "deleted",
        "draft": "draft"
    }
    normalized_status = status_map.get(status, status)
    items, total = ItemService.get_items(
        session=session,
        page=page,
        page_size=page_size,
        status=normalized_status,
        seller_id=db_user.id
    )
    items_data = [_serialize_item(session, item) for item in items]
    return ItemListResponse(
        items=items_data,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/campus-price-comparison", response_model=List[CampusPriceComparison])
async def campus_price_comparison(
    limit: int = Query(6, ge=1, le=20),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user_optional),
):
    """跨校区价格情报（用于 MarketplaceView 面板）。

    说明：当前实现优先返回 hub 中已有商品的对比信息；如果暂无数据则返回空数组。
    """

    items = (
        session.execute(select(Item).order_by(Item.view_count.desc()).limit(limit))
        .scalars()
        .all()
    )
    comparisons: List[CampusPriceComparison] = []
    for item in items:
        cat = session.get(Category, item.category_id) if item.category_id else None
        price = float(item.price or 0)
        comparisons.append(
            CampusPriceComparison(
                item_id=str(item.id),
                title=item.title or "",
                category=cat.name if cat else "未分类",
                prices={"hub": price},
                lowest_price=price,
                lowest_campus="hub",
                price_diff=0.0,
                updated_at=item.updated_at or item.created_at or datetime.utcnow(),
                seller_name=None,
                view_count=int(item.view_count or 0),
                favorite_count=int(item.favorite_count or 0),
                created_at=item.created_at,
            )
        )
    return comparisons


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item_detail(
    item_id: int,
    session: Session = Depends(get_user_campus_db_session),
    current_user=Depends(get_current_user_optional)
):
    """获取商品详情"""
    from apps.core.models import Category, User
    
    item = session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="商品不存在")
    
    # 增加浏览量
    item.view_count = (item.view_count or 0) + 1
    session.commit()
    
    # 获取关联数据
    seller = session.get(User, item.seller_id)
    category = session.get(Category, item.category_id) if item.category_id else None

    # 重要：聊天/会话属于hub库（mysql），前端需要 hub 的用户ID。
    seller_hub_id: Optional[str] = None
    seller_username: Optional[str] = None
    if seller:
        seller_username = seller.username
        try:
            with db_manager.session_scope("mysql") as hub_session:
                hub_user = hub_session.execute(
                    select(User).where(User.username == seller.username)
                ).scalar_one_or_none()
                if hub_user:
                    seller_hub_id = str(hub_user.id)
        except Exception:
            seller_hub_id = None
    
    # 获取图片
    images = []
    for media in item.medias:
        images.append(media.image_url)
    
    return ItemResponse(
        id=str(item.id),
        title=item.title,
        description=item.description or "",
        price=float(item.price),
        category=category.name if category else "其他",
        images=images,
        status=item.status or "available",
        condition=item.condition,  # ✅ 使用属性方法
        seller_id=str(item.seller_id),
        seller_hub_id=seller_hub_id,
        seller_username=seller_username,
        seller_name=seller.username if seller else "未知",
        view_count=item.view_count or 0,
        favorite_count=item.favorite_count or 0,
        created_at=item.created_at,
        updated_at=item.updated_at
    )


@router.put("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    payload: ItemUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """更新商品信息"""
    update_data = payload.dict(exclude_unset=True)
    item = ItemService.update_item(session, item_id, current_user.id, **update_data)
    
    if not item:
        raise HTTPException(status_code=404, detail="商品不存在或无权限")
    
    cat = session.get(Category, item.category_id)
    medias = session.execute(
        select(ItemMedia).where(ItemMedia.item_id == item.id)
    ).scalars().all()
    
    return ItemResponse(
        id=str(item.id),
        title=item.title,
        description=item.description,
        price=float(item.price),
        category=cat.name if cat else "其他",
        images=[m.url for m in medias],
        status=item.status,
        condition=item.condition,
        seller_id=str(item.seller_id),
        seller_name=current_user.username,
        view_count=item.view_count,
        favorite_count=0,
        created_at=item.created_at,
        updated_at=item.updated_at
    )


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """删除商品"""
    success = ItemService.delete_item(session, item_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="商品不存在或无权限")
    return None


@router.post("/{item_id}/favorite")
async def toggle_favorite(
    item_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """切换收藏状态"""
    result = FavoriteService.toggle_favorite(session, current_user.id, item_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.get("/my/favorites", response_model=ItemListResponse)
async def get_my_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """获取我的收藏"""
    items, total = FavoriteService.get_user_favorites(
        session, current_user.id, page, page_size
    )
    
    items_data = []
    for item in items:
        cat = session.get(Category, item.category_id)
        seller = session.get(User, item.seller_id)
        medias = session.execute(
            select(ItemMedia).where(ItemMedia.item_id == item.id)
        ).scalars().all()
        
        items_data.append(ItemResponse(
            id=str(item.id),
            title=item.title,
            description=item.description,
            price=float(item.price),
            category=cat.name if cat else "其他",
            images=[m.url for m in medias],
            status=item.status,
            condition=item.condition,
            seller_id=str(item.seller_id),
            seller_name=seller.username if seller else "未知",
            view_count=item.view_count,
            favorite_count=0,
            created_at=item.created_at,
            updated_at=item.updated_at
        ))
    
    return ItemListResponse(
        items=items_data,
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("/upload-image", response_model=dict)
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """上传商品图片"""
    import os
    import uuid
    from pathlib import Path
    
    # 检查文件类型
    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="只支持 JPG、PNG、GIF 格式的图片")
    
    # 检查文件大小 (5MB)
    file_content = await file.read()
    if len(file_content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片大小不能超过 5MB")
    
    # 生成唯一文件名
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    
    # 确保目录存在
    upload_dir = Path("/app/static/images/items")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存文件
    file_path = upload_dir / unique_filename
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # 返回图片URL
    image_url = f"/images/items/{unique_filename}"
    return {"url": image_url}
