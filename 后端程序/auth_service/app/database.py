from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def build_database(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
    if url.startswith("sqlite"):
        # SQLite 默认不校验外键，PostgreSQL 一直校验。测试跑在 SQLite 上，
        # 不打开这个开关，任何违反外键的写入都要等到生产 PG 上才炸。
        @event.listens_for(engine, "connect")
        def _enforce_sqlite_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine, sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
