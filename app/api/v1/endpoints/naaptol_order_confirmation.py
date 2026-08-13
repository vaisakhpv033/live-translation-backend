from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.order_confirmation import (
    OrderConfirmationDialRequest,
    OrderConfirmationDialResponse,
)
from app.services.order_confirmation_service import IOrderConfirmationService
from app.api.dependencies import get_order_confirmation_service

router = APIRouter()


@router.post("/dial", response_model=OrderConfirmationDialResponse, status_code=status.HTTP_201_CREATED)
async def dial_order_confirmation(
    request: OrderConfirmationDialRequest,
    service: IOrderConfirmationService = Depends(get_order_confirmation_service),
):
    """
    Initiates an automated outbound order confirmation call for Naaptol.

    1. Dispatches the `naaptol-order-confirmation` agent worker to a dedicated room with full order metadata.
    2. Executes Pattern B readiness gate — waits for agent to connect before dialing customer.
    3. Placed outbound SIP phone call via Twilio trunk to customer's phone number.
    """
    try:
        return await service.make_outbound_confirmation_call(request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate order confirmation call: {str(e)}",
        )
