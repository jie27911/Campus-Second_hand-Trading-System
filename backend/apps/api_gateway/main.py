"""FastAPI entrypoint for the API Gateway."""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from apps.api_gateway.routers import (
    admin_settings,
    admin_users,
    admin_tables,
    admin_operations,
    admin_notifications,
    ai_chat,
    analytics,
    auth,
    dashboard,
    database,
    health,
    market,
    sync_api as sync,
    items,
    cart,
    orders,
    messages,
    favorites,
    search,
    campuses,
)
from apps.services import websocket
from apps.core.config import get_settings
from apps.services.monitoring_simulator import monitoring_data_simulator

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the API gateway instance."""

    settings = get_settings()
    
    # ✅ 添加 redirect_slashes=False 禁用尾斜杠重定向
    app = FastAPI(
        title=settings.app_name, 
        version="0.1.0",
        redirect_slashes=False  # ✅ 关键：禁用 /cart 重定向到 /cart/
    )

    # 设置UTF-8 JSON响应
    from fastapi.responses import JSONResponse
    import json
    
    class UTF8JSONResponse(JSONResponse):
        def __init__(self, content=None, status_code=200, headers=None, media_type="application/json; charset=utf-8", **kwargs):
            # 接受并转发任意额外参数，兼容 FastAPI/Starlette
            super().__init__(content=content, status_code=status_code, headers=headers, media_type=media_type, **kwargs)

        def render(self, content) -> bytes:
            return json.dumps(
                content,
                ensure_ascii=False,  # 允许非ASCII字符
                allow_nan=False,
                indent=None,
                separators=(",", ":"),
            ).encode("utf-8")
    
    app.router.default_response_class = UTF8JSONResponse

    # ✅ 更宽松的 CORS 配置（开发环境）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 允许所有来源
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # ✅ 挂载静态文件目录用于图片服务
    static_dir = Path(__file__).parent.parent.parent / "static"
    static_dir.mkdir(exist_ok=True)
    images_dir = static_dir / "images"
    images_dir.mkdir(exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(images_dir)), name="images")

    app.include_router(health.router)
    app.include_router(auth.router, prefix=settings.api_v1_prefix)
    app.include_router(sync.router, prefix=settings.api_v1_prefix)
    app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
    app.include_router(market.router, prefix=settings.api_v1_prefix)
    app.include_router(database.router, prefix=settings.api_v1_prefix)
    app.include_router(analytics.router, prefix=settings.api_v1_prefix)
    app.include_router(items.router, prefix=settings.api_v1_prefix)
    app.include_router(campuses.router, prefix=settings.api_v1_prefix)
    app.include_router(cart.router, prefix=settings.api_v1_prefix)
    app.include_router(orders.router, prefix=settings.api_v1_prefix)
    app.include_router(messages.router, prefix=settings.api_v1_prefix)
    app.include_router(favorites.router, prefix=settings.api_v1_prefix)
    app.include_router(search.router, prefix=settings.api_v1_prefix)
    app.include_router(admin_settings.router, prefix=settings.api_v1_prefix)
    app.include_router(admin_users.router, prefix=settings.api_v1_prefix)
    app.include_router(admin_tables.router, prefix=settings.api_v1_prefix)
    app.include_router(admin_operations.router, prefix=settings.api_v1_prefix)
    app.include_router(admin_notifications.router, prefix=settings.api_v1_prefix)
    app.include_router(ai_chat.router, prefix=settings.api_v1_prefix)
    app.include_router(websocket.router, prefix=settings.api_v1_prefix)

    @app.on_event("startup")
    async def startup_event():
        """应用启动时初始化数据库对象（触发器、存储过程等）"""
        logger.info("应用启动中...开始初始化数据库对象")
        try:
            monitoring_data_simulator.ensure_baseline(force=True)
        except Exception as e:
            logger.error(f"数据库初始化异常: {e}", exc_info=True)

    @app.get("/", tags=["root"])
    def read_root() -> dict[str, str]:
        return {"message": "CampuSwap API Gateway"}

    return app


app = create_app()
