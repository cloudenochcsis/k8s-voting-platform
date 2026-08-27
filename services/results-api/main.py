import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional

DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI(title="Results API")


def get_db():
    return psycopg2.connect(DATABASE_URL)


class CandidateTally(BaseModel):
    candidate_choice: str
    vote_count: int


class ResultsResponse(BaseModel):
    revealed: bool
    message: Optional[str] = None
    revealed_at: Optional[str] = None
    total_eligible_voters: Optional[int] = None
    total_turnout: Optional[int] = None
    turnout_percentage: Optional[float] = None
    tallies: Optional[List[CandidateTally]] = None


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "results-api"}


# The reveal flag is flipped only by the reveal-gate CronJob (DB write); there is deliberately no HTTP route for it.
@app.get("/results", response_model=ResultsResponse)
def get_results():
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT revealed, revealed_at FROM election_state WHERE id = 1")
                state = cur.fetchone()
                if not state or not state["revealed"]:
                    return ResultsResponse(revealed=False, message="Polls are still open. Results are not yet revealed.")

                cur.execute("SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE has_voted) AS turnout FROM voter_roll")
                row = cur.fetchone()
                total, turnout = row["total"], row["turnout"]

                cur.execute(
                    "SELECT candidate_choice, COUNT(*) AS vote_count FROM ballots GROUP BY candidate_choice ORDER BY vote_count DESC"
                )
                tallies = [CandidateTally(**r) for r in cur.fetchall()]

        return ResultsResponse(
            revealed=True,
            revealed_at=str(state["revealed_at"]) if state["revealed_at"] else None,
            total_eligible_voters=total,
            total_turnout=turnout,
            turnout_percentage=round(turnout / total * 100, 2) if total else 0.0,
            tallies=tallies,
        )
    except psycopg2.Error as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
