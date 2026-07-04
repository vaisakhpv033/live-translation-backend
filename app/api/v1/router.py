from fastapi import APIRouter
from app.api.v1.endpoints import rooms, tokens, webhooks

api_router = APIRouter()

# Include endpoint sub-routers
api_router.include_router(rooms.router, prefix="/rooms", tags=["Rooms"])
api_router.include_router(tokens.router, prefix="/rooms", tags=["Tokens"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
