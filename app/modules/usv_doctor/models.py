"""SQLAlchemy model for USV Doctor Detailing call reports and dual usage metrics."""

from sqlalchemy import Column, Float, Integer, String, Text

from app.core.database import Base


class UsvDoctorReport(Base):
    """Stores USV Doctor Detailing sessions, QA evaluations, and AutoCoach + QA token metrics."""

    __tablename__ = "usv_doctor_reports"

    # Session & Lifecycle
    job_id = Column(String, primary_key=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    room_name = Column(String, nullable=True, index=True)
    agent_name = Column(String, nullable=True)
    agent_role = Column(String, nullable=True)
    started_at = Column(String, nullable=True)
    ended_at = Column(String, nullable=True, index=True)
    duration_seconds = Column(Integer, nullable=True, default=0)
    termination_reason = Column(String, nullable=True)
    error_info = Column(Text, nullable=True)
    status = Column(String, nullable=True, default="ongoing", index=True)
    created_at = Column(String, nullable=True)

    # Physician & Rep Context (from payload.metadata)
    scenario = Column(String, nullable=True, default="doctor-detailing")
    scenario_id = Column(String, nullable=True)
    title = Column(String, nullable=True)
    doctor_name = Column(String, nullable=True)
    doctor_specialty = Column(String, nullable=True)
    clinic_setting = Column(Text, nullable=True)
    demeanor = Column(String, nullable=True)
    trainee_name = Column(String, nullable=True)
    trainee_id = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    language = Column(String, nullable=True)
    voice_id = Column(String, nullable=True)
    session_metadata = Column(Text, nullable=True)

    # Transcript, Timeline Events & Audio Recording
    chat_history = Column(Text, nullable=True)
    events = Column(Text, nullable=True)
    audio_recording_path = Column(String, nullable=True)

    # QA Evaluation Output
    summary = Column(Text, nullable=True)
    overall_score = Column(Integer, nullable=True, default=0)
    readiness_assessment = Column(String, nullable=True)

    # AutoCoach Agent Usage Metrics (from LiveKit / Gemini Live session)
    agent_model_usage = Column(Text, nullable=True)
    agent_input_tokens = Column(Integer, nullable=True, default=0)
    agent_input_cached_tokens = Column(Integer, nullable=True, default=0)
    agent_input_text_tokens = Column(Integer, nullable=True, default=0)
    agent_input_audio_tokens = Column(Integer, nullable=True, default=0)
    agent_output_tokens = Column(Integer, nullable=True, default=0)
    agent_output_text_tokens = Column(Integer, nullable=True, default=0)
    agent_output_audio_tokens = Column(Integer, nullable=True, default=0)
    agent_reasoning_tokens = Column(Integer, nullable=True, default=0)
    agent_total_tokens = Column(Integer, nullable=True, default=0)
    agent_cost_usd = Column(Float, nullable=True, default=0.0)

    # QA Analysis Usage Metrics (from Gemini evaluation API usageMetadata)
    qa_usage_metadata = Column(Text, nullable=True)
    qa_model_name = Column(String, nullable=True)
    qa_prompt_tokens = Column(Integer, nullable=True, default=0)
    qa_cached_tokens = Column(Integer, nullable=True, default=0)
    qa_candidates_tokens = Column(Integer, nullable=True, default=0)
    qa_thoughts_tokens = Column(Integer, nullable=True, default=0)
    qa_total_tokens = Column(Integer, nullable=True, default=0)
    qa_cost_usd = Column(Float, nullable=True, default=0.0)

    # Combined Total Session Cost (AutoCoach Agent + QA Analysis)
    total_cost_usd = Column(Float, nullable=True, default=0.0)

    def __repr__(self) -> str:
        return (
            f"<UsvDoctorReport(job_id={self.job_id}, room={self.room_name}, "
            f"doctor={self.doctor_name}, status={self.status}, score={self.overall_score})>"
        )
