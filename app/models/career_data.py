from sqlalchemy import Column, String, Text
from app.core.database import Base


class CareerRecord(Base):
    """
    SQLAlchemy model for career agent data collection.
    Stores structured details extracted by Gemini from student call transcripts.
    """
    __tablename__ = "career_records"

    job_id = Column(String, primary_key=True, index=True)
    room_id = Column(String, nullable=True)
    student_name = Column(String, nullable=True)
    current_status = Column(Text, nullable=True)
    next_study_program = Column(Text, nullable=True)
    future_goals = Column(Text, nullable=True)
    plans_foreign_institutes = Column(Text, nullable=True)
    active_search_status = Column(Text, nullable=True)
    conviction_tier = Column(String, nullable=True)  # Tier A / B / C / D
    conviction_rationale = Column(Text, nullable=True)
    chat_history = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<CareerRecord(job_id={self.job_id}, student_name={self.student_name}, tier={self.conviction_tier})>"
