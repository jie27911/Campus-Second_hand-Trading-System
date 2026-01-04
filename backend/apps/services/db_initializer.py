"""
Database initializer for multiple database engines using SQLAlchemy ORM.
"""
import logging
from typing import Dict, Any, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from apps.core.models import Base
from apps.core.database import get_all_engines

logger = logging.getLogger(__name__)

# 全局初始化器实例（懒加载）
_initializer_instance: Optional["DatabaseInitializer"] = None


class DatabaseInitializer:
    """多数据库初始化器 - 使用SQLAlchemy ORM自动创建表"""

    def __init__(self, engines: Dict[str, Engine]):
        self.engines = engines

    def initialize_all_databases(self) -> Dict[str, Any]:
        """初始化所有数据库 - 使用ORM自动创建缺失的表"""
        results = {}

        for db_name, engine in self.engines.items():
            try:
                result = self.initialize_database(db_name, engine)
                results[db_name] = result

                # 打印简要结果
                if result.get("success"):
                    logger.info(f"✅ {db_name} 初始化成功: 创建了表结构")
                else:
                    logger.warning(f"⚠️ {db_name} 初始化失败: {result.get('error', '未知错误')}")

            except Exception as e:
                logger.error(f"❌ {db_name} 初始化失败: {e}")
                results[db_name] = {"success": False, "error": str(e)}

        return results

    def initialize_database(self, db_name: str, engine: Engine) -> Dict[str, Any]:
        """初始化单个数据库 - 使用ORM自动创建表"""
        try:
            logger.info(f"{db_name}: 开始使用ORM创建表结构...")

            # 使用SQLAlchemy的create_all()方法自动创建所有表
            Base.metadata.create_all(bind=engine)

            logger.info(f"{db_name}: 表结构创建完成")

            return {
                "success": True,
                "message": "表结构创建成功",
                "tables_created": len(Base.metadata.tables)
            }

        except Exception as e:
            error_msg = f"创建表结构失败: {str(e)}"
            logger.error(f"{db_name}: {error_msg}")
            return {"success": False, "error": error_msg}


def get_database_initializer(engines: Dict[str, Engine]) -> DatabaseInitializer:
    """获取数据库初始化器实例（单例模式）"""
    global _initializer_instance
    if _initializer_instance is None:
        _initializer_instance = DatabaseInitializer(engines)
    return _initializer_instance


def get_initializer():
    """获取数据库初始化器实例（兼容旧API）"""
    return get_database_initializer(get_all_engines())


def initialize_databases() -> Dict[str, Any]:
    """初始化所有数据库 - 便捷函数"""
    initializer = get_database_initializer(get_all_engines())
    return initializer.initialize_all_databases()