import logging
import asyncio
from app.core.database import _async_session_factory
from app.repositories.report_repository import SQLAlchemyReportRepository
from app.services.evaluation_service import GeminiEvaluationService
from app.services.report_service import ReportService

logger = logging.getLogger("translation-agent-backend.services.background_evaluation")


async def run_background_evaluation(
    job_id: str, chat_history_str: str | None, scenario: str
) -> None:
    """
    Standard background evaluation task runner.
    Creates a new scoped database session and runs Gemini evaluation.
    """
    if _async_session_factory is None:
        logger.error(f"Cannot run evaluation for job {job_id}: Database session factory is None.")
        return

    logger.info(f"Starting background evaluation task for job: {job_id} (scenario={scenario})")
    async with _async_session_factory() as session:
        try:
            repository = SQLAlchemyReportRepository(session)
            evaluation_service = GeminiEvaluationService()
            report_service = ReportService(repository, evaluation_service)
            await report_service.evaluate_and_update(job_id, chat_history_str, scenario)
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception(f"Unhandled exception during background evaluation for job {job_id}: {e}")


async def sweep_and_recover_reports() -> None:
    """
    Self-healing startup task.
    Identifies stuck 'ongoing' reports in the database and restarts their evaluation in the background.
    """
    if _async_session_factory is None:
        logger.error("Database session factory is not initialized. Cannot run self-healing sweep.")
        return

    logger.info("Initializing self-healing database sweep for stuck ongoing evaluations...")
    async with _async_session_factory() as session:
        try:
            repository = SQLAlchemyReportRepository(session)
            ongoing_reports = await repository.get_ongoing_reports()

            if not ongoing_reports:
                logger.info("Database sweep completed: No stuck ongoing evaluations found.")
                return

            logger.info(f"Database sweep completed: Found {len(ongoing_reports)} stuck ongoing evaluations to recover.")
            for r in ongoing_reports:
                job_id = r["job_id"]
                chat_history = r.get("chat_history")
                scenario = r.get("scenario", "sbi")

                logger.info(f"Kicking off background recovery evaluation for stuck job: {job_id}")
                # Dispatch as a separate background event loop task to prevent blocking startup/lifespan
                asyncio.create_task(run_background_evaluation(job_id, chat_history, scenario))
        except Exception as e:
            logger.exception(f"Error during self-healing database recovery sweep: {e}")
