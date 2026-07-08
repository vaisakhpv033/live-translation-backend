from fastapi import APIRouter
from app.api.v1.endpoints import rooms, tokens, webhooks, sts_rooms, reports

api_router = APIRouter()

# Include endpoint sub-routers
api_router.include_router(rooms.router, prefix="/rooms", tags=["Rooms"])
api_router.include_router(tokens.router, prefix="/rooms", tags=["Tokens"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(sts_rooms.router, prefix="/sts/rooms", tags=["STS Rooms"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
