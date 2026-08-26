import os
import time
import jwt
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/voting_db")
JWT_SECRET = os.getenv("JWT_SECRET", "voting-super-secret-jwt-key")
JWT_ALGORITHM = "HS256"
JWT_EXP_SECONDS = int(os.getenv("JWT_EXP_SECONDS", "900"))  # 15 minutes

app = FastAPI(title="Eligibility API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VerifyRequest(BaseModel):
    student_id: str = Field(..., min_length=3, max_length=64)

class VerifyResponse(BaseModel):
    token: str
    student_id: str

def get_db():
    # ponytail: direct psycopg2 connection per request; use connection pooling if high steady concurrency demands it
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
                cur.execute("SELECT student_id, has_voted FROM voter_roll WHERE student_id = %s", (student_id,))
                voter = cur.fetchone()

        if not voter:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student ID not found in voter roll")

        if voter["has_voted"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student has already voted")

        payload = {
            "sub": student_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + JWT_EXP_SECONDS,
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return VerifyResponse(token=token, student_id=student_id)
    except psycopg2.Error as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
