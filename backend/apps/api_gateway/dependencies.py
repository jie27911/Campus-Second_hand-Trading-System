"""API Gateway 依赖注入模块
提供数据库会话、用户认证等依赖
"""
from typing import Callable, Generator, Iterable, Optional

from fastapi import Depends, HTTPException, status, Header, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from jose import JWTError

from apps.core.config import Settings, get_settings
from apps.core.database import db_manager
from apps.core.models import User, UserProfile
from apps.core.security import decode_access_token

# OAuth2 认证 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_db_session(campus_code: str = "hub") -> Generator[Session, None, None]:
    """
    根据校区获取对应的数据库会话
    
    数据库映射:
    - hub: MySQL (中央汇总)
    - main: MariaDB (本部校区)
    - south: PostgreSQL (南校区)  
    - north: MySQL (北校区; 数据已同步)
    """
    campus_to_db = {
        "hub": "mysql",      # 中央汇总
        "main": "mariadb",   # 本部校区
        "south": "postgres", # 南校区
        "north": "mysql",    # 北校区(与中央库一致)
    }
    
    db_name = campus_to_db.get(campus_code, "mysql")  # 默认使用中央数据库
    with db_manager.session_scope(db_name) as session:
        yield session


def get_campus_db_session(campus_code: str = "main") -> Generator[Session, None, None]:
    """
    获取指定校区的数据库会话
    """
    return get_db_session(campus_code)


def get_hub_db_session() -> Generator[Session, None, None]:
    """
    获取中央汇总数据库会话
    """
    yield from get_db_session("hub")


def get_multi_campus_session(campus_code: Optional[str] = None) -> Generator[Session, None, None]:
    """
    获取多校区会话
    如果指定校区，使用对应数据库；否则使用中央数据库
    """
    if campus_code:
        yield from get_db_session(campus_code)
    else:
        yield from get_hub_db_session()




def get_current_settings() -> Settings:
    """获取应用配置"""
    return get_settings()


def get_current_token(token: str = Depends(oauth2_scheme)) -> str:
    """获取当前 JWT Token"""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_db_session)
) -> User:
    """
    获取当前登录用户
    从 JWT Token 中解析并返回用户对象
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = decode_access_token(token)
        if payload is None:
            raise credentials_exception
        
        # 尝试从 payload 中获取用户标识
        user_id = payload.get("user_id")
        email = payload.get("sub")
        
        if user_id:
            user = session.execute(
                select(User).options(joinedload(User.profile)).where(User.id == int(user_id))
            ).scalar_one_or_none()
        elif email:
            user = session.execute(
                select(User).options(joinedload(User.profile)).where(User.email == email)
            ).scalar_one_or_none()
        else:
            raise credentials_exception
            
    except (JWTError, ValueError):
        raise credentials_exception
    
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用"
        )
    
    return user




async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    session: Session = Depends(get_db_session)
) -> Optional[User]:
    """
    获取当前用户（可选）
    如果没有提供 token 或 token 无效，返回 None 而不是抛出异常
    """
    if not authorization:
        return None
    
    try:
        # 提取 Bearer token
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            return None
        
        # 验证 token
        payload = decode_access_token(token)
        if payload is None:
            return None
        
        # 尝试从 payload 中获取用户标识
        user_id = payload.get("user_id")
        email = payload.get("sub")
        
        if user_id:
            user = session.execute(
                select(User).options(joinedload(User.profile)).where(User.id == int(user_id))
            ).scalar_one_or_none()
        elif email:
            user = session.execute(
                select(User).options(joinedload(User.profile)).where(User.email == email)
            ).scalar_one_or_none()
        else:
            return None
        
        return user
        
    except (JWTError, ValueError):
        return None


def require_roles(*roles: str) -> Callable[[User], User]:
    """
    生成一个依赖，确保当前用户拥有至少一个所需角色
    """
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not roles:
            return user
        user_roles = {role.name for role in user.roles}
        required: Iterable[str] = set(roles)
        if user_roles.intersection(required):
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )

    return dependency


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """获取当前活跃用户"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用"
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """获取当前管理员用户"""
    if not getattr(current_user, 'is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return current_user


def get_user_campus_db_session(current_user: User = Depends(get_current_user)) -> Generator[Session, None, None]:
    """
    根据当前用户的校区自动选择数据库会话，并确保用户在该数据库中存在
    
    数据库映射:
    - 本部校区: MariaDB
    - 南校区: PostgreSQL  
    - 北校区: MySQL (数据已同步)
    - 默认: MySQL (中央汇总)
    """
    # 直接使用已加载的用户profile信息
    campus_code = "hub"  # 默认使用中央数据库
    if current_user.profile and current_user.profile.campus:
        # 根据校区名称/代码映射到统一代码
        campus_name_to_code = {
            # 中文名称
            "本部校区": "main",
            "南校区": "south",
            "北校区": "north",
            # 兼容直接存 code
            "main": "main",
            "south": "south",
            "north": "north",
            "hub": "hub",
        }
        campus_code = campus_name_to_code.get(current_user.profile.campus, "hub")
    
    # 使用对应的数据库
    campus_to_db = {
        "hub": "mysql",
        "main": "mariadb", 
        "south": "postgres",
        "north": "mysql",
    }
    db_name = campus_to_db.get(campus_code, "mysql")
    
    with db_manager.session_scope(db_name) as session:
        # 在当前数据库中查找用户（通过用户名或邮箱）
        db_user = session.execute(
            select(User).options(joinedload(User.profile)).where(
                (User.username == current_user.username) | (User.email == current_user.email)
            )
        ).scalar_one_or_none()
        
        if not db_user:
            # 如果用户不存在，尝试通过student_id查找
            db_user = session.execute(
                select(User).options(joinedload(User.profile)).where(
                    User.student_id == current_user.student_id
                )
            ).scalar_one_or_none()
        
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户在目标数据库中不存在，请联系管理员"
            )
        
        # 将数据库中的用户对象替换到上下文中
        # 注意：这里我们不能修改current_user，但后续代码需要使用正确的用户ID
        # 我们在session中添加一个特殊属性来传递正确的用户ID
        session._current_db_user = db_user
        
        yield session


def get_campus_db_session_by_code(campus_code: str, current_user: User = Depends(get_current_user)) -> Session:
    """
    根据指定的校区代码获取数据库会话，并确保用户在该数据库中存在
    
    Args:
        campus_code: 校区代码 ("hub", "main", "south", "north")
        
    Returns:
        数据库会话对象
    """
    # 使用对应的数据库
    campus_to_db = {
        "hub": "mysql",
        "main": "mariadb", 
        "south": "postgres",
        "north": "mysql",
    }
    db_name = campus_to_db.get(campus_code, "mysql")
    
    # 创建session
    session_factory = db_manager._sessions[db_name]
    session = session_factory()
    session.info.setdefault("db_name", db_name)
    
    try:
        # 在当前数据库中查找用户（通过用户名或邮箱）
        db_user = session.execute(
            select(User).options(joinedload(User.profile)).where(
                (User.username == current_user.username) | (User.email == current_user.email)
            )
        ).scalar_one_or_none()
        
        if not db_user:
            # 如果用户不存在，尝试通过student_id查找
            db_user = session.execute(
                select(User).options(joinedload(User.profile)).where(
                    User.student_id == current_user.student_id
                )
            ).scalar_one_or_none()

        if not db_user:
            # 如果用户在目标库不存在，尝试创建本地副本以便跨校区发布（复制必要字段）
            try:
                # 在创建副本时禁用同步事件以避免回环
                session.info["suppress_sync"] = True
                new_user = User(
                    username=current_user.username,
                    email=current_user.email,
                    student_id=current_user.student_id,
                    hashed_password=getattr(current_user, "hashed_password", getattr(current_user, "password_hash", "")),
                    phone=getattr(current_user, "phone", None),
                    avatar_url=getattr(current_user, "avatar_url", None),
                    real_name=getattr(current_user, "real_name", None),
                    is_active=True,
                    is_verified=getattr(current_user, "is_verified", False),
                )
                session.add(new_user)
                session.flush()

                display_name = None
                if getattr(current_user, "profile", None):
                    display_name = getattr(current_user.profile, "display_name", None)
                display_name = display_name or current_user.username

                campus_name_map = {
                    "main": "本部校区",
                    "south": "南校区",
                    "north": "北校区",
                    "hub": "中央库",
                }
                profile = UserProfile(user_id=new_user.id, display_name=display_name, campus=campus_name_map.get(campus_code, campus_code))
                session.add(profile)
                session.flush()

                # 恢复同步设置
                session.info.pop("suppress_sync", None)
                db_user = new_user
            except Exception:
                session.close()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"无法在{campus_code}校区数据库中创建用户，请联系管理员"
                )

        # 将数据库中的用户对象替换到上下文中
        session._current_db_user = db_user
        
        return session
    except Exception:
        session.close()
        raise


def create_campus_db_session_dependency(campus_code: str):
    """
    创建一个依赖函数，用于获取指定校区的数据库会话
    
    Args:
        campus_code: 校区代码
        
    Returns:
        依赖函数
    """
    def dependency(current_user: User = Depends(get_current_user)) -> Generator[Session, None, None]:
        return get_campus_db_session_by_code(campus_code, current_user)
    
    return dependency


def get_user_campus_db_session_optional(current_user: Optional[User] = Depends(get_current_user_optional)) -> Generator[Session, None, None]:
    """
    根据当前用户的校区自动选择数据库会话（可选用户）
    如果用户未登录，使用中央数据库
    """
    if current_user and current_user.profile and current_user.profile.campus:
        # 根据校区名称映射到代码
        campus_name_to_code = {
            "本部校区": "main",
            "南校区": "south", 
            "北校区": "north"
        }
        campus_code = campus_name_to_code.get(current_user.profile.campus, "hub")
        # 使用对应的数据库
        campus_to_db = {
            "hub": "mysql",
            "main": "mariadb", 
            "south": "postgres",
            "north": "mysql",
        }
        db_name = campus_to_db.get(campus_code, "mysql")
        
        from apps.core.database import db_manager
        with db_manager.session_scope(db_name) as session:
            yield session
    else:
        # 未登录或无校区信息，使用中央数据库
        yield from get_hub_db_session()
