from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.models import Base


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=5,
            max_overflow=10,
            pool_timeout=10,
            isolation_level="READ COMMITTED",
            connect_args={
                "charset": "utf8mb4",
                "connect_timeout": 5,
                "read_timeout": 30,
                "write_timeout": 30,
                "autocommit": False,
            },
        )

        @event.listens_for(self.engine, "connect")
        def configure_mysql(connection, _record):
            cursor = connection.cursor()
            cursor.execute("SET time_zone = '+00:00'")
            cursor.execute("SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci")
            cursor.close()

        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()
