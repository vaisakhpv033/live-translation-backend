import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from app.schemas.report import ReportCreate, ReportDetail, ReportListResponse
from app.services.report_service import IReportService
from app.api.dependencies import get_report_service
from app.services.background_evaluation import run_background_evaluation

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED)
async def receive_report(
    payload: ReportCreate,
    background_tasks: BackgroundTasks,
    report_service: IReportService = Depends(get_report_service),
):
    """
    Receives a report from the STS agent on session end.
    Stores the report in PostgreSQL and kicks off background Gemini evaluation.
    """
    try:
        result = await report_service.receive_report(payload)

        # Schedule background evaluation
        chat_history_str = None
        if payload.chat_history:
            chat_history_str = json.dumps(payload.chat_history)

        background_tasks.add_task(
            run_background_evaluation,
            payload.job_id,
            chat_history_str,
            payload.scenario or "sbi",
        )

        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to receive report: {str(e)}"
        )


@router.get("/", response_model=ReportListResponse)
async def list_reports(
    report_service: IReportService = Depends(get_report_service),
):
    """
    Lists all reports with aggregate statistics.
    """
    try:
        return await report_service.list_reports()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list reports: {str(e)}"
        )


@router.get("/{job_id}", response_model=ReportDetail)
async def get_report(
    job_id: str,
    report_service: IReportService = Depends(get_report_service),
):
    """
    Retrieves full report detail by job_id.
    """
    report = await report_service.get_report(job_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found"
        )
    return report


@router.get("/{job_id}/status")
async def get_report_status(
    job_id: str,
    report_service: IReportService = Depends(get_report_service),
):
    """
    Returns the evaluation status of a report.
    """
    result = await report_service.get_report_status(job_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found"
        )
    return result


@router.post("/{job_id}/retry")
async def retry_report_evaluation(
    job_id: str,
    background_tasks: BackgroundTasks,
    report_service: IReportService = Depends(get_report_service),
):
    """
    Retries Gemini evaluation for a failed or ongoing report.
    """
    result = await report_service.retry_evaluation(job_id)
    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.get("message", "Report not found")
        )

    # Schedule background re-evaluation
    background_tasks.add_task(
        run_background_evaluation,
        job_id,
        result.get("chat_history"),
        result.get("scenario", "sbi"),
    )

    return {"status": "success", "message": f"Retry evaluation started for job {job_id}."}

