import os
import jwt
import redis
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_STREAM = os.getenv("REDIS_STREAM", "vote_stream")
JWT_SECRET = os.getenv("JWT_SECRET", "voting-super-secret-jwt-key")
JWT_ALGORITHM = "HS256"

app = FastAPI(title="Vote API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to Redis
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
    # Verify JWT
    try:
        payload = jwt.decode(req.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        student_id = payload.get("sub")
        if not student_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Voting token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid voting token")

    # Fast-fail duplicate check via Redis SETNX
    # ponytail: redis key TTL ensures memory is freed after election window
    lock_key = f"voted_lock:{student_id}"
    acquired = r.set(lock_key, "1", nx=True, ex=86400)
    if not acquired:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Vote already submitted for this student")

    # Publish to Redis Stream
    try:
        r.xadd(REDIS_STREAM, {"student_id": student_id, "candidate_id": req.candidate_id.strip()})
    except Exception as e:
        # Revert lock on publish failure so user can retry
        r.delete(lock_key)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to queue vote: {str(e)}")

    return VoteResponse(status="queued", message="Vote successfully queued for processing")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
