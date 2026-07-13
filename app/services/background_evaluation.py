import logging
import asyncio
from datetime import datetime, UTC
from app.core.database import _async_session_factory
from app.repositories.report_repository import SQLAlchemyReportRepository
from app.services.evaluation_service import GeminiEvaluationService
from app.services.report_service import ReportService

logger = logging.getLogger("translation-agent-backend.services.background_evaluation")


def is_stuck(created_at_str: str | None, threshold_seconds: int) -> bool:
    """
    Checks if a report created_at timestamp is older than threshold_seconds.
    If no timestamp is present, returns True as a safety measure.
    """
    if not created_at_str:
        return True
    try:
        # Convert UTC ISO string ending in 'Z' to datetime
        created_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        elapsed = (now - created_dt).total_seconds()
        return elapsed > threshold_seconds
    except Exception as e:
        logger.warning(f"Error parsing created_at timestamp '{created_at_str}': {e}")
        return True  # Fallback to True to avoid leaving it stuck


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


async def recover_stuck_reports(threshold_seconds: int = 300) -> None:
    """
    Scans the database for reports with status 'ongoing' that exceed threshold_seconds
    and restarts their evaluations in the background.
    """
    if _async_session_factory is None:
        return

    async with _async_session_factory() as session:
        try:
            repository = SQLAlchemyReportRepository(session)
            ongoing_reports = await repository.get_ongoing_reports()

            if not ongoing_reports:
                return

            stuck_count = 0
            for r in ongoing_reports:
                created_at = r.get("created_at")
                if is_stuck(created_at, threshold_seconds):
                    stuck_count += 1
                    job_id = r["job_id"]
                    chat_history = r.get("chat_history")
                    scenario = r.get("scenario", "sbi")

                    logger.info(
                        f"Recovering stuck evaluation for job {job_id} "
                        f"(created_at={created_at}, threshold={threshold_seconds}s)"
                    )
                    # Dispatch as a separate background task to run concurrently
                    asyncio.create_task(run_background_evaluation(job_id, chat_history, scenario))

            if stuck_count > 0:
                logger.info(f"Stuck reports recovery sweep completed: Recovered {stuck_count} reports.")
        except Exception as e:
            logger.exception(f"Error during database recovery sweep: {e}")


async def sweep_and_recover_reports() -> None:
    """
    Self-healing startup task.
    Sweeps ALL ongoing reports immediately upon boot (since uvicorn was just restarted).
    """
    logger.info("Initializing self-healing database sweep on startup...")
    await recover_stuck_reports(threshold_seconds=0)


async def periodic_sweep_loop(
    interval_seconds: int = 300, stuck_threshold_seconds: int = 300
) -> None:
    """
    Continuously running loop that wakes up periodically to recover stuck runtime tasks.
    """
    logger.info(
        f"Starting periodic recovery sweep loop (interval={interval_seconds}s, "
        f"stuck_threshold={stuck_threshold_seconds}s)"
    )
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            logger.info("Running periodic database recovery sweep...")
            await recover_stuck_reports(threshold_seconds=stuck_threshold_seconds)
        except asyncio.CancelledError:
            logger.info("Periodic recovery sweep loop cancelled.")
            break
        except Exception as e:
            logger.exception(f"Exception in periodic recovery sweep loop: {e}")
