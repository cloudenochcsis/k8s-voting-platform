import os
import time
import jwt
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]  # no fallback: a missing secret must fail at boot, not sign tokens
JWT_ALGORITHM = "HS256"
JWT_EXP_SECONDS = int(os.getenv("JWT_EXP_SECONDS", "900"))  # 15 minutes

app = FastAPI(title="Eligibility API")


class VerifyRequest(BaseModel):
    student_id: str = Field(..., min_length=3, max_length=64)


class VerifyResponse(BaseModel):
    token: str
    student_id: str


def get_db():
    # ponytail: connection per request; this is the intended load-test bottleneck (CLAUDE.md §11) — add pgbouncer when it bites
    return psycopg2.connect(DATABASE_URL)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "eligibility-api"}


@app.post("/eligibility/verify", response_model=VerifyResponse)
def verify_eligibility(req: VerifyRequest):
    student_id = req.student_id.strip().upper()
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT has_voted FROM voter_roll WHERE student_id = %s", (student_id,))
                voter = cur.fetchone()
    except psycopg2.Error as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")

    if not voter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student ID not found in voter roll")
    if voter["has_voted"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student has already voted")

    now = int(time.time())
    token = jwt.encode({"sub": student_id, "iat": now, "exp": now + JWT_EXP_SECONDS}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return VerifyResponse(token=token, student_id=student_id)
