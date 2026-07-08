from sqlalchemy import Column, String, Integer, Text
from app.core.database import Base


class Report(Base):
    """
    SQLAlchemy model for STS agent call reports.
    Mirrors the schema from the report-server's SQLite database,
    upgraded to PostgreSQL with async support.
    """
    __tablename__ = "reports"

    job_id = Column(String, primary_key=True, index=True)
    room_id = Column(String, nullable=True)
    room = Column(String, nullable=True)
    started_at = Column(String, nullable=True)
    ended_at = Column(String, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    overall_score = Column(Integer, nullable=True, default=0)
    chat_history = Column(Text, nullable=True)
    status = Column(String, nullable=True, default="ongoing")
    customer_name = Column(String, nullable=True)
    agent_type = Column(String, nullable=True)
    sales_rep = Column(String, nullable=True)
    scenario = Column(String, nullable=True, default="sbi")
    created_at = Column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<Report(job_id={self.job_id}, room={self.room}, status={self.status})>"
