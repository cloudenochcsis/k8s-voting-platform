import os
import jwt
import redis
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_STREAM = os.getenv("REDIS_STREAM", "vote_stream")
JWT_SECRET = os.environ["JWT_SECRET"]  # no fallback: a missing secret must fail at boot, not sign tokens
JWT_ALGORITHM = "HS256"
# Pipe-separated allowlist; anything else is rejected before it reaches the queue, the DB, or the results page.
CANDIDATES = frozenset(c.strip() for c in os.environ["CANDIDATES"].split("|") if c.strip())

app = FastAPI(title="Vote API")

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


class VoteRequest(BaseModel):
    token: str
    candidate_id: str = Field(..., min_length=1, max_length=128)


class VoteResponse(BaseModel):
    status: str
    message: str


@app.get("/healthz")
def healthz():
    try:
        r.ping()
        return {"status": "ok", "service": "vote-api"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Redis error: {str(e)}")


@app.post("/vote", response_model=VoteResponse)
def submit_vote(req: VoteRequest):
    try:
        payload = jwt.decode(req.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        student_id = payload.get("sub")
        if not student_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Voting token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid voting token")

    candidate_id = req.candidate_id.strip()
    if candidate_id not in CANDIDATES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown candidate")

    # Fast-fail duplicate check via SETNX. The DB is the real guarantee; this just saves queue work.
    lock_key = f"voted_lock:{student_id}"
    if not r.set(lock_key, "1", nx=True, ex=86400):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Vote already submitted for this student")

    try:
        r.xadd(REDIS_STREAM, {"student_id": student_id, "candidate_id": candidate_id})
    except Exception as e:
        r.delete(lock_key)  # let the voter retry
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to queue vote: {str(e)}")

    return VoteResponse(status="queued", message="Vote successfully queued for processing")
