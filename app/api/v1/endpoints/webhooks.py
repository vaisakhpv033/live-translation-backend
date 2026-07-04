import logging
from fastapi import APIRouter, Header, Request, HTTPException, status
from livekit.api import TokenVerifier, WebhookReceiver
from app.core.config import get_settings

logger = logging.getLogger("translation-agent-backend.api.v1.endpoints.webhooks")
router = APIRouter()
settings = get_settings()

# Initialize LiveKit Webhook Receiver for cryptographically verifying incoming event payloads
token_verifier = TokenVerifier(
    api_key=settings.LIVEKIT_API_KEY,
    api_secret=settings.LIVEKIT_API_SECRET
)
webhook_receiver = WebhookReceiver(token_verifier)

@router.post("/")
async def handle_webhook(
    request: Request,
    authorization: str = Header(None)
):
    """
    Receives and cryptographically validates incoming LiveKit webhook events.
    Verifies that the request comes from the trusted LiveKit server using the API credentials.
    """
    if not authorization:
        logger.warning("Webhook request missing Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required"
        )

    # Read the raw request body
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")

    try:
        # Validate the token and match it against the request body hash
        event = webhook_receiver.receive(body_str, authorization)
        
        logger.info(f"Verified webhook event received: {event.event} (Room: {event.room.name if event.room else 'None'})")
        
        # Dispatch processing of events (could be delegated to a background task or service)
        # Event examples: 'room_started', 'room_finished', 'participant_joined', 'participant_left'
        if event.event == "room_started":
            logger.info(f"Room started: {event.room.name} (SID: {event.room.sid})")
        elif event.event == "room_finished":
            logger.info(f"Room finished: {event.room.name} (SID: {event.room.sid})")
        elif event.event == "participant_joined":
            logger.info(f"Participant joined: {event.participant.identity} (Room: {event.room.name})")
        elif event.event == "participant_left":
            logger.info(f"Participant left: {event.participant.identity} (Room: {event.room.name})")
        else:
            logger.debug(f"Unhandled webhook event type: {event.event}")

        return {"status": "success", "event": event.event}

    except Exception as e:
        logger.error(f"Failed to verify webhook signature or payload: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Signature verification failed: {str(e)}"
        )
