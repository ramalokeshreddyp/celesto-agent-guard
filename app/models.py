import re
from sqlalchemy import Column, Integer, String, DateTime, func
from app.database import Base

SANDBOX_NAME_RE = re.compile(r"^sbx-[a-z0-9]{8,}$")
VALID_STATES = {"created", "ready", "running", "succeeded", "failed", "deleted"}
VALID_EXECUTION_TARGETS = {"celesto_sandbox"}


class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, unique=True, nullable=False)
    sandbox_name = Column(String, nullable=False)
    problem_id = Column(String, nullable=False)
    state = Column(String, nullable=False)
    execution_target = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
