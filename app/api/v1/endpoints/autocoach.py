import json
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status

from app.schemas.autocoach import (
    AutoCoachSessionCreate,
    AutoCoachSessionResponse,
    AutoCoachTokenRequest,
    AutoCoachReportPayload,
)
from app.schemas.report import ReportCreate
from app.schemas.room import RoomResponse
from app.schemas.token import TokenResponse
from app.services.autocoach_service import IAutoCoachService
from app.services.report_service import IReportService
from app.services.background_evaluation import run_background_evaluation
from app.api.dependencies import get_autocoach_service, get_report_service

logger = logging.getLogger("translation-agent-backend.api.v1.endpoints.autocoach")
router = APIRouter()


@router.post(
    "/start-session",
    response_model=AutoCoachSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start AutoCoach Dental Training Session with Agent Handshake",
)
async def start_session(
    payload: AutoCoachSessionCreate,
    service: IAutoCoachService = Depends(get_autocoach_service),
):
    """
    Initiates an AutoCoach dental training simulation.
    
    Workflow:
    1. Generates and creates a LiveKit room with dental training metadata.
    2. Dispatches the 'autocoach-customer-sts' agent worker to the room.
    3. Executes an asynchronous handshake, waiting until the agent worker is
       confirmed connected to the room.
    4. Only AFTER agent presence is verified, generates and returns the trainee JWT token.
    
    If the agent worker fails to join within the timeout, a 504 Gateway Timeout is returned,
    preventing the frontend trainee from entering an empty room.
    """
    try:
        return await service.create_and_dispatch_session(payload)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unhandled error starting AutoCoach session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start AutoCoach session: {str(e)}",
        )


@router.get(
    "/rooms",
    response_model=List[RoomResponse],
    summary="List Active Dental Training Rooms",
)
async def list_rooms(
    service: IAutoCoachService = Depends(get_autocoach_service),
):
    """
    Lists all active AutoCoach simulation rooms and their current participant counts.
    """
    try:
        return await service.list_sessions()
    except Exception as e:
        logger.exception(f"Error listing AutoCoach rooms: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list rooms: {str(e)}",
        )


@router.get(
    "/rooms/{room_name}",
    response_model=RoomResponse,
    summary="Get AutoCoach Room Details",
)
async def get_room(
    room_name: str,
    service: IAutoCoachService = Depends(get_autocoach_service),
):
    """
    Retrieves full details and active participant status for an AutoCoach room.
    """
    room = await service.get_session(room_name)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AutoCoach room '{room_name}' not found",
        )
    return room


@router.delete(
    "/rooms/{room_name}",
    status_code=status.HTTP_200_OK,
    summary="Close AutoCoach Room",
)
async def delete_room(
    room_name: str,
    service: IAutoCoachService = Depends(get_autocoach_service),
):
    """
    Closes and tears down an AutoCoach simulation room.
    """
    success = await service.delete_session(room_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close room '{room_name}'",
        )
    return {"status": "success", "message": f"Room '{room_name}' closed successfully"}


@router.post(
    "/rooms/{room_name}/token",
    response_model=TokenResponse,
    summary="Generate Participant Token for AutoCoach Room",
)
async def generate_token(
    room_name: str,
    token_req: AutoCoachTokenRequest,
    service: IAutoCoachService = Depends(get_autocoach_service),
):
    """
    Generates a join token for an observer, supervisor, or reconnecting trainee.
    """
    try:
        return service.generate_token(room_name, token_req)
    except Exception as e:
        logger.exception(f"Error generating token for room '{room_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate token: {str(e)}",
        )


@router.post(
    "/reports",
    status_code=status.HTTP_201_CREATED,
    summary="Receive AutoCoach Session Report and Trigger Background Evaluation",
)
async def receive_autocoach_report(
    payload: AutoCoachReportPayload,
    background_tasks: BackgroundTasks,
    report_service: IReportService = Depends(get_report_service),
):
    """
    Receives call conclusion telemetry and chat transcript from the AutoCoach agent worker.
    Stores the session record in PostgreSQL and dispatches the background Gemini evaluation
    using the Dental Front Desk SOP rubric.
    """
    try:
        # Extract simulation details
        sim_data = payload.simulation or {}
        trainee_data = payload.trainee or {}

        scenario = (
            sim_data.get("scenario")
            or payload.scenario
            or "dental_scheduling"
        )
        patient_name = (
            sim_data.get("persona_name")
            or payload.customer_name
            or "Dental Patient"
        )
        sales_rep = (
            trainee_data.get("trainee_name")
            or trainee_data.get("trainee_id")
            or "Front Desk Trainee"
        )

        room_id = payload.room_id or payload.room_name or payload.job_id
        room_name = payload.room_name or payload.room_id or "AutoCoach-Dental"

        # Adapt chat history to dict structure if sent as a list
        raw_chat = payload.chat_history
        if isinstance(raw_chat, list):
            chat_history_dict = {"items": raw_chat}
        elif isinstance(raw_chat, dict):
            chat_history_dict = raw_chat
        else:
            chat_history_dict = None

        adapted_report = ReportCreate(
            job_id=payload.job_id,
            room_id=room_id,
            room=room_name,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
            customer_name=patient_name,
            agent_type="AutoCoach STS",
            sales_rep=sales_rep,
            scenario=scenario,
            chat_history=chat_history_dict,
        )

        result = await report_service.receive_report(adapted_report)

        # Trigger background evaluation with Dental Front Desk SOP Rubric
        chat_history_str = json.dumps(chat_history_dict) if chat_history_dict else None
        background_tasks.add_task(
            run_background_evaluation,
            payload.job_id,
            chat_history_str,
            scenario,
        )

        logger.info(
            f"AutoCoach report for job {payload.job_id} (scenario={scenario}) received. "
            "Background SOP evaluation scheduled."
        )
        return result

    except Exception as e:
        logger.exception(f"Failed to receive AutoCoach report for job {payload.job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process AutoCoach report: {str(e)}",
        )
