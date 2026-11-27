"""Dedicated USV Doctor Detailing simulation and reporting module."""

from app.modules.usv_doctor.models import UsvDoctorReport
from app.modules.usv_doctor.router import router

__all__ = ["UsvDoctorReport", "router"]
