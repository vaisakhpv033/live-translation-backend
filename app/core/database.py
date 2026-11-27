import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

logger = logging.getLogger("translation-agent-backend.core.database")


class Base(DeclarativeBase):
    """
    Declarative base class for all SQLAlchemy models.
    """
    pass


# Module-level references managed during application lifespan
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str) -> None:
    """
    Initializes the async SQLAlchemy engine and session factory.
    Creates all tables defined by Base subclasses.
    """
    global _engine, _async_session_factory

    if _engine is not None:
        logger.warning("Database engine already initialized, skipping.")
        return

    logger.info(f"Initializing database engine: {database_url.split('@')[-1]}")
    _engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    _async_session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    # Create tables (import models before this runs so they register with Base)
    from app.models import report, career_data  # noqa: F401
    from app.modules.dental_qa.models import DentalCallEvaluation  # noqa: F401
    from app.modules.usv_doctor.models import UsvDoctorReport  # noqa: F401
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await conn.execute(text("ALTER TABLE dental_evaluations ADD COLUMN IF NOT EXISTS voice_rating_audit TEXT;"))
        except Exception as e:
            logger.debug(f"Column migration check note for voice_rating_audit: {e}")

        usv_alter_statements = [
            "ALTER TABLE usv_doctor_reports ADD COLUMN IF NOT EXISTS agent_input_cached_tokens INTEGER DEFAULT 0;",
            "ALTER TABLE usv_doctor_reports ADD COLUMN IF NOT EXISTS agent_input_text_tokens INTEGER DEFAULT 0;",
            "ALTER TABLE usv_doctor_reports ADD COLUMN IF NOT EXISTS agent_output_text_tokens INTEGER DEFAULT 0;",
            "ALTER TABLE usv_doctor_reports ADD COLUMN IF NOT EXISTS agent_reasoning_tokens INTEGER DEFAULT 0;",
            "ALTER TABLE usv_doctor_reports ADD COLUMN IF NOT EXISTS agent_cost_usd DOUBLE PRECISION DEFAULT 0.0;",
            "ALTER TABLE usv_doctor_reports ADD COLUMN IF NOT EXISTS qa_cached_tokens INTEGER DEFAULT 0;",
            "ALTER TABLE usv_doctor_reports ADD COLUMN IF NOT EXISTS qa_cost_usd DOUBLE PRECISION DEFAULT 0.0;",
            "ALTER TABLE usv_doctor_reports ADD COLUMN IF NOT EXISTS total_cost_usd DOUBLE PRECISION DEFAULT 0.0;",
        ]
        for ddl in usv_alter_statements:
            try:
                await conn.execute(text(ddl))
            except Exception as e:
                logger.debug(f"Column migration check note for usv_doctor_reports: {e}")
    logger.info("Database tables created successfully.")


async def close_db() -> None:
    """
    Disposes the async engine and resets module state.
    """
    global _engine, _async_session_factory

    if _engine is not None:
        logger.info("Disposing database engine.")
        await _engine.dispose()
        _engine = None
        _async_session_factory = None


async def get_db_session() -> AsyncSession:
    """
    FastAPI dependency that yields an AsyncSession.
    The session is committed on success and rolled back on exception.
    """
    if _async_session_factory is None:
        raise RuntimeError("Database is not initialized. Initialize it in the lifespan.")

    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
