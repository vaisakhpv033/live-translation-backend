from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.telephony import (
    InboundSetupRequest, InboundSetupResponse,
    OutboundTrunkSetupRequest, OutboundTrunkSetupResponse,
    OutboundCallRequest, OutboundCallResponse,
    CallStatusResponse,
    TrunkListResponse,
)
from app.services.telephony_service import ITelephonyService
from app.api.dependencies import get_telephony_service

router = APIRouter()


@router.post("/setup-inbound", response_model=InboundSetupResponse, status_code=status.HTTP_201_CREATED)
async def setup_inbound(
    request: InboundSetupRequest,
    telephony: ITelephonyService = Depends(get_telephony_service),
):
    """
    One-time setup: registers the Twilio phone number as an inbound SIP trunk
    and creates a dispatch rule that routes calls to the Customer-sts career agent.
    Idempotent — calling this multiple times will not create duplicate trunks.
    """
    try:
        return await telephony.setup_inbound(request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to setup inbound trunk: {str(e)}",
        )


@router.post("/setup-outbound", response_model=OutboundTrunkSetupResponse, status_code=status.HTTP_201_CREATED)
async def setup_outbound_trunk(
    request: OutboundTrunkSetupRequest,
    telephony: ITelephonyService = Depends(get_telephony_service),
):
    """
    One-time setup: creates a stored outbound SIP trunk for placing calls via Twilio.
    Idempotent — calling this multiple times will not create duplicate trunks.
    Optional: outbound calls can also use inline trunk config from env vars.
    """
    try:
        return await telephony.setup_outbound_trunk(request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to setup outbound trunk: {str(e)}",
        )


@router.post("/dial", response_model=OutboundCallResponse, status_code=status.HTTP_201_CREATED)
async def dial_outbound(
    request: OutboundCallRequest,
    telephony: ITelephonyService = Depends(get_telephony_service),
):
    """
    Initiates an outbound call to the specified phone number.
    The career-agent persona (Sarah from Global Study Advisors) is used automatically.
    The agent is dispatched first, then the phone number is dialed into the same room.
    """
    try:
        return await telephony.make_outbound_call(request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate outbound call: {str(e)}",
        )


@router.get("/status/{room_name}", response_model=CallStatusResponse)
async def get_call_status(
    room_name: str,
    telephony: ITelephonyService = Depends(get_telephony_service),
):
    """
    Gets the current status of a telephony call room, including SIP participant status.
    """
    try:
        return await telephony.get_call_status(room_name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get call status: {str(e)}",
        )


@router.get("/trunks", response_model=TrunkListResponse)
async def list_trunks(
    telephony: ITelephonyService = Depends(get_telephony_service),
):
    """
    Lists all configured SIP trunks (inbound + outbound) and dispatch rules.
    """
    try:
        return await telephony.list_trunks()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list trunks: {str(e)}",
        )


@router.delete("/calls/{room_name}", status_code=status.HTTP_204_NO_CONTENT)
async def hangup_call(
    room_name: str,
    telephony: ITelephonyService = Depends(get_telephony_service),
):
    """
    Terminates an active telephony call by closing the LiveKit room.
    """
    try:
        success = await telephony.hangup_call(room_name)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to hang up call in room '{room_name}'",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error hanging up call: {str(e)}",
        )
