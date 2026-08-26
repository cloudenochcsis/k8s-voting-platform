import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/voting_db")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "admin-secret-reveal-key")

app = FastAPI(title="Results API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.get("/results", response_model=ResultsResponse)
def get_results():
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Check reveal status
                cur.execute("SELECT revealed, revealed_at FROM election_state WHERE id = 1")
                state = cur.fetchone()

                if not state or not state["revealed"]:
                    return ResultsResponse(
                        revealed=False,
                        message="Polls are still open. Results are not yet revealed."
                    )

                # 2. Get turnout statistics
                cur.execute("SELECT COUNT(*) as total, SUM(CASE WHEN has_voted THEN 1 ELSE 0 END) as turnout FROM voter_roll")
                turnout_row = cur.fetchone()
                total = turnout_row["total"] if turnout_row else 0
                turnout = turnout_row["turnout"] or 0 if turnout_row else 0
                pct = round((turnout / total * 100), 2) if total > 0 else 0.0

                # 3. Get candidate tallies
                cur.execute("""
                    SELECT candidate_choice, COUNT(*) as vote_count
                    FROM ballots
                    GROUP BY candidate_choice
                    ORDER BY vote_count DESC
                """)
                tallies = [
                    CandidateTally(candidate_choice=row["candidate_choice"], vote_count=row["vote_count"])
                    for row in cur.fetchall()
                ]

                return ResultsResponse(
                    revealed=True,
                    revealed_at=str(state["revealed_at"]) if state["revealed_at"] else None,
                    total_eligible_voters=total,
                    total_turnout=turnout,
                    turnout_percentage=pct,
                    tallies=tallies
                )
    except psycopg2.Error as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")

@app.post("/admin/reveal")
def reveal_results(x_admin_secret: Optional[str] = Header(None)):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin secret")

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE election_state SET revealed = TRUE, revealed_at = NOW() WHERE id = 1")
                conn.commit()
        return {"revealed": True, "message": "Election results have been successfully revealed."}
    except psycopg2.Error as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
