import re
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.database import get_db, engine
from app.models import Run, SANDBOX_NAME_RE, VALID_STATES, VALID_EXECUTION_TARGETS

app = FastAPI(title="Celesto Agent Guard - Run Ledger API")


class RunCreate(BaseModel):
    run_id: str
    sandbox_name: str
    problem_id: str
    state: str
    execution_target: str

    @field_validator("sandbox_name")
    @classmethod
    def validate_sandbox_name(cls, v: str) -> str:
        if not SANDBOX_NAME_RE.match(v):
            raise ValueError(
                "sandbox_name must match sbx- followed by 8+ lowercase letters or digits"
            )
        return v

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        if v not in VALID_STATES:
            raise ValueError(f"state must be one of {sorted(VALID_STATES)}")
        return v

    @field_validator("execution_target")
    @classmethod
    def validate_execution_target(cls, v: str) -> str:
        if v not in VALID_EXECUTION_TARGETS:
            raise ValueError("execution_target must be 'celesto_sandbox'")
        return v


@app.get("/health")
def health():
    """Health check endpoint - returns 200 when API and DB are reachable."""
    return {"status": "ok"}


@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db)):
    """List all sandbox runs recorded in the ledger."""
    runs = db.query(Run).all()
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "sandbox_name": r.sandbox_name,
            "problem_id": r.problem_id,
            "state": r.state,
            "execution_target": r.execution_target,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in runs
    ]


@app.post("/api/runs", status_code=201)
def create_run(run: RunCreate, db: Session = Depends(get_db)):
    """Record a new sandbox run in the ledger."""
    db_run = Run(
        run_id=run.run_id,
        sandbox_name=run.sandbox_name,
        problem_id=run.problem_id,
        state=run.state,
        execution_target=run.execution_target,
    )
    db.add(db_run)
    db.commit()
    db.refresh(db_run)
    return {
        "id": db_run.id,
        "run_id": db_run.run_id,
        "sandbox_name": db_run.sandbox_name,
        "problem_id": db_run.problem_id,
        "state": db_run.state,
        "execution_target": db_run.execution_target,
        "created_at": db_run.created_at.isoformat() if db_run.created_at else None,
    }


@app.exception_handler(422)
async def validation_exception_handler(request: Request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
