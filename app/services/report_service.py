import json
import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from app.schemas.report import ReportCreate, ReportSummary, ReportDetail, ReportListResponse
from app.repositories.report_repository import IReportRepository
from app.services.evaluation_service import IEvaluationService

logger = logging.getLogger("translation-agent-backend.services.report_service")


class IReportService(ABC):
    """
    Interface for report business operations (Interface Segregation).
    """
    @abstractmethod
    async def receive_report(self, payload: ReportCreate) -> dict:
        """Receives and stores a report, returns acknowledgement."""
        pass

    @abstractmethod
    async def list_reports(self) -> ReportListResponse:
        """Lists all reports with aggregate statistics."""
        pass

    @abstractmethod
    async def get_report(self, job_id: str) -> Optional[ReportDetail]:
        """Returns full report detail by job_id."""
        pass

    @abstractmethod
    async def get_report_status(self, job_id: str) -> Optional[dict]:
        """Returns the evaluation status of a report."""
        pass

    @abstractmethod
    async def retry_evaluation(self, job_id: str) -> dict:
        """Re-runs Gemini evaluation on a stored report's chat history."""
        pass

    @abstractmethod
    async def get_ongoing_reports(self) -> list[dict]:
        """Retrieves all reports with status = 'ongoing'."""
        pass


class ReportService(IReportService):
    """
    Report business logic implementation (Dependency Inversion).
    Manages report storage, listing, and Gemini-based evaluation.
    """
    def __init__(
        self,
        repository: IReportRepository,
        evaluation_service: IEvaluationService,
    ):
        self.repository = repository
        self.evaluation_service = evaluation_service

    async def receive_report(self, payload: ReportCreate) -> dict:
        logger.info(f"Receiving report for job: {payload.job_id}")

        chat_history_str = None
        if payload.chat_history:
            chat_history_str = json.dumps(payload.chat_history)

        report_data = {
            "job_id": payload.job_id,
            "room_id": payload.room_id,
            "room": payload.room,
            "started_at": payload.started_at,
            "ended_at": payload.ended_at,
            "summary": None,
            "overall_score": 0,
            "chat_history": chat_history_str,
            "status": "ongoing",
            "customer_name": payload.customer_name or "N/A",
            "agent_type": payload.agent_type or "STS Agent",
            "sales_rep": payload.sales_rep or "N/A",
            "scenario": payload.scenario or "sbi",
        }

        await self.repository.save(report_data)
        return {
            "status": "success",
            "message": f"Report for job {payload.job_id} received. Evaluation will run in background.",
        }

    async def evaluate_and_update(self, job_id: str, chat_history_str: Optional[str], scenario: Optional[str] = "sbi") -> None:
        """
        Background task: evaluate the chat history and update the report record.
        This method is designed to be called from FastAPI BackgroundTasks.
        """
        try:
            report_card, overall_score = await self.evaluation_service.evaluate_chat_history(
                chat_history_str, scenario=scenario
            )
            if report_card:
                summary_json = json.dumps(report_card)
                await self.repository.update_summary(job_id, summary_json, overall_score, "completed")
                logger.info(f"Evaluation completed for job {job_id}: score={overall_score}")
            else:
                await self.repository.update_summary(job_id, None, 0, "failed")
                logger.warning(f"Evaluation failed for job {job_id}")
        except Exception as e:
            logger.exception(f"Error in background evaluation for job {job_id}: {e}")
            await self.repository.update_summary(job_id, None, 0, "failed")

    async def list_reports(self) -> ReportListResponse:
        logger.info("Listing all reports")
        rows = await self.repository.get_all()

        reports = []
        completed_reports = []

        readiness_counts = {
            "Production Ready": 0,
            "Ready With Supervision": 0,
            "Developing": 0,
            "Needs Significant Coaching": 0,
            "Not Ready": 0,
        }

        for r in rows:
            readiness = self._extract_readiness(r.get("summary")) if r.get("status") == "completed" else "Developing"
            reports.append(
                ReportSummary(
                    job_id=r["job_id"],
                    room=r.get("room"),
                    started_at=r.get("started_at"),
                    ended_at=r.get("ended_at"),
                    duration_seconds=r.get("duration_seconds"),
                    overall_score=r.get("overall_score"),
                    status=r.get("status"),
                    customer_name=r.get("customer_name"),
                    agent_type=r.get("agent_type"),
                    scenario=r.get("scenario"),
                    readiness_assessment=readiness,
                )
            )

            if r.get("status") == "completed":
                completed_reports.append(r)
                # Parse readiness from summary
                readiness = self._extract_readiness(r.get("summary"))
                if readiness in readiness_counts:
                    readiness_counts[readiness] += 1

        total_calls = len(completed_reports)
        avg_score = 0
        if total_calls > 0:
            avg_score = int(sum(r.get("overall_score", 0) for r in completed_reports) / total_calls)

        return ReportListResponse(
            reports=reports,
            stats={
                "total_calls": total_calls,
                "avg_score": avg_score,
                "readiness": readiness_counts,
            },
        )

    async def get_report(self, job_id: str) -> Optional[ReportDetail]:
        logger.info(f"Getting report detail: {job_id}")
        row = await self.repository.get_by_job_id(job_id)
        if not row:
            return None

        # Parse summary and chat_history from stored JSON strings
        summary = row.get("summary")
        if summary and isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except Exception:
                pass

        chat_history_raw = row.get("chat_history")
        chat_history = []
        if chat_history_raw and isinstance(chat_history_raw, str):
            try:
                data = json.loads(chat_history_raw)
                if isinstance(data, dict) and "items" in data:
                    items = data.get("items", [])
                    for item in items:
                        if item.get("type") != "message":
                            continue
                        role = item.get("role")
                        if role == "system":
                            continue

                        content_list = item.get("content", [])
                        text = ""
                        if isinstance(content_list, list):
                            text = " ".join([str(c) for c in content_list if isinstance(c, str)])
                        elif isinstance(content_list, str):
                            text = content_list

                        chat_history.append({
                            "role": role,
                            "text": text,
                            "interrupted": item.get("interrupted", False)
                        })
                elif isinstance(data, list):
                    chat_history = data
            except Exception:
                pass

        return ReportDetail(
            job_id=row["job_id"],
            room_id=row.get("room_id"),
            room=row.get("room"),
            started_at=row.get("started_at"),
            ended_at=row.get("ended_at"),
            duration_seconds=row.get("duration_seconds"),
            summary=summary,
            overall_score=row.get("overall_score"),
            chat_history=chat_history,
            status=row.get("status"),
            customer_name=row.get("customer_name"),
            agent_type=row.get("agent_type"),
            sales_rep=row.get("sales_rep"),
            scenario=row.get("scenario"),
            created_at=row.get("created_at"),
        )

    async def get_report_status(self, job_id: str) -> Optional[dict]:
        row = await self.repository.get_by_job_id(job_id)
        if not row:
            return None
        return {"status": row.get("status", "completed")}

    async def retry_evaluation(self, job_id: str) -> dict:
        logger.info(f"Retrying evaluation for job: {job_id}")
        row = await self.repository.get_by_job_id(job_id)
        if not row:
            return {"status": "error", "message": "Report not found"}

        await self.repository.update_summary(job_id, None, 0, "ongoing")
        return {
            "status": "success",
            "message": f"Retry evaluation started for job {job_id}.",
            "chat_history": row.get("chat_history"),
            "scenario": row.get("scenario", "sbi"),
        }

    async def get_ongoing_reports(self) -> list[dict]:
        logger.info("Getting all ongoing reports from repository")
        return await self.repository.get_ongoing_reports()

    @staticmethod
    def _extract_readiness(summary_str: Optional[str]) -> str:
        """Extracts the readiness_assessment from a JSON summary string."""
        if not summary_str:
            return "Developing"
        try:
            if isinstance(summary_str, str):
                parsed = json.loads(summary_str)
            else:
                parsed = summary_str
            return parsed.get("readiness_assessment", "Developing")
        except Exception:
            return "Developing"
