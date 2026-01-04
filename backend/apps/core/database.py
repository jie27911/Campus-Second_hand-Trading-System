"""Database utilities for managing multi-database connections."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Dict, Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .write_listeners import register_write_listeners
from .transaction import TransactionConfig, configure_engine_isolation


class DatabaseManager:
    """
    多校区分布式数据库管理器
    
    架构设计:
    - mysql: 中央汇总数据库 (高并发读写，存储汇总数据和用户管理)
    - mariadb: 本部校区数据库 (高并发，存储本部商品)
    - postgres: 南校区数据库 (复杂查询，存储南校商品)  
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        
        # 创建多校区数据库引擎
        self._engines: Dict[str, Engine] = {
            # 中央汇总数据库 - MySQL (高并发)
            "mysql": create_engine(
                self._settings.mysql_dsn,
                pool_pre_ping=True,
                pool_size=20,  # 高并发连接池
                max_overflow=30,
                pool_timeout=30,
                pool_recycle=3600,
                echo=self._settings.debug,
                future=True,
            ),
            # 本部校区 - MariaDB (高并发读写)
            "mariadb": create_engine(
                self._settings.mariadb_dsn,
                pool_pre_ping=True,
                pool_size=15,
                max_overflow=20,
                pool_timeout=30,
                pool_recycle=3600,
                echo=self._settings.debug,
                future=True,
            ),
            # 南校区 - PostgreSQL (复杂查询和事务)
            "postgres": create_engine(
                self._settings.postgres_dsn,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=15,
                pool_timeout=30,
                pool_recycle=3600,
                echo=self._settings.debug,
                future=True,
            ),
        }
        
        # 为每个数据库配置事务隔离级别
        for db_name, engine in self._engines.items():
            configure_engine_isolation(engine, db_name)
        
        # 创建 session factories
        self._sessions: Dict[str, sessionmaker[Session]] = {
            name: sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
            for name, engine in self._engines.items()
        }

        # 注册应用层写入监听器(多数据库)
        # - 雪花ID
        # - 向量时钟 v_clock
        # 变更捕获由边缘库触发器写入 sync_log 完成。
        for factory in self._sessions.values():
            register_write_listeners(factory)

    def get_engine(self, name: str) -> Engine:
        """Return the engine for the given database name."""

        return self._engines[name]

    def reconfigure_engine(self, name: str, dsn: str, pool_size: Optional[int] = None) -> None:
        """Hot-reload a database engine with a new DSN."""

        if name not in self._engines:
            raise KeyError(f"Unknown database engine: {name}")

        effective_pool = pool_size or TransactionConfig.POOL_SIZE
        engine = create_engine(
            dsn,
            pool_pre_ping=True,
            pool_size=effective_pool,
            max_overflow=TransactionConfig.MAX_OVERFLOW,
            pool_timeout=TransactionConfig.POOL_TIMEOUT,
            pool_recycle=TransactionConfig.POOL_RECYCLE,
            echo=self._settings.debug,
            future=True,
        )

        configure_engine_isolation(engine, name)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

        old_engine = self._engines.get(name)
        if old_engine is not None:
            old_engine.dispose()

        self._engines[name] = engine
        self._sessions[name] = session_factory

        register_write_listeners(session_factory)

    @contextmanager
    def session_scope(self, name: str) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations."""

        session_factory = self._sessions[name]
        session = session_factory()#工厂
        session.info.setdefault("db_name", name)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


db_manager = DatabaseManager()


def get_all_engines() -> Dict[str, Engine]:
    """Return all database engines."""
    return db_manager._engines


def get_engine(name: str) -> Engine:
    """Return the engine for the given database name."""
    return db_manager.get_engine(name)


def get_session_scope(name: str):
    """Get a session scope for the given database name."""
    return db_manager.session_scope(name)
