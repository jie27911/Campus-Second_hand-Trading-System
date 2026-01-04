"""
校区管理路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api_gateway.dependencies import get_hub_db_session
from apps.core.models import Campus

router = APIRouter(prefix="/campuses", tags=["校区管理"])


# ==================== Pydantic Models ====================

class CampusResponse(BaseModel):
    """校区响应"""
    id: int
    name: str
    code: str
    address: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    sort_order: int


# ==================== API路由 ====================

@router.get("/", response_model=List[CampusResponse])
@router.get("", response_model=List[CampusResponse])
def get_campuses(session: Session = Depends(get_hub_db_session)):
    """获取所有校区列表"""
    from sqlalchemy import select

    campuses = session.execute(
        select(Campus).where(Campus.is_active == True).order_by(Campus.sort_order)
    ).scalars().all()

    return [
        CampusResponse(
            id=campus.id,
            name=campus.name,
            code=campus.code,
            address=campus.address,
            description=campus.description,
            is_active=campus.is_active,
            sort_order=campus.sort_order
        )
        for campus in campuses
    ]