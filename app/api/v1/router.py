from fastapi import APIRouter
from app.api.v1.endpoints import (
    rooms,
    tokens,
    webhooks,
    sts_rooms,
    reports,
    telephony,
    career_data,
    naaptol_order_confirmation,
    autocoach,
    patients,
    appointments,
    auth,
)

api_router = APIRouter()

# Include endpoint sub-routers
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(rooms.router, prefix="/rooms", tags=["Rooms"])
api_router.include_router(tokens.router, prefix="/rooms", tags=["Tokens"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(sts_rooms.router, prefix="/sts/rooms", tags=["STS Rooms"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(telephony.router, prefix="/telephony", tags=["Telephony"])
api_router.include_router(career_data.router, prefix="/career-data", tags=["Career Data"])
api_router.include_router(naaptol_order_confirmation.router, prefix="/naaptol-order-confirmation", tags=["Naaptol Order Confirmation"])
api_router.include_router(autocoach.router, prefix="/autocoach", tags=["AutoCoach"])
api_router.include_router(patients.router, prefix="/patients", tags=["Patients"])
api_router.include_router(appointments.router, prefix="/appointments", tags=["Appointments"])

# Pronunciation Assessment Module (conditionally mounted following Open/Closed Principle)
from app.core.config import get_settings
settings = get_settings()
if getattr(settings, "ENABLE_PRONUNCIATION_ENGINE", True):
    from app.modules.pronunciation.router import router as pronunciation_router
    api_router.include_router(pronunciation_router)
