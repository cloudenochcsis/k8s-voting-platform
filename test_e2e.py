"""
Integration test against the docker-compose stack (`docker compose up -d --build`).

Verifies the load-bearing guarantees end to end, with real services:
1. Eligibility -> JWT -> vote -> worker -> Postgres, no mocks.
2. Vote-once under *concurrent* duplicate submissions (vote-api fast-fail).
3. Vote-once at the worker even when the Redis lock is bypassed (DB is the truth).
4. Ballot secrecy: `ballots` has no identity or timestamp columns to join on.
5. Candidate allowlist: arbitrary strings (incl. HTML) are rejected.
6. Results hidden until the reveal flag flips.

Env: BASE_URL (default http://localhost:8080), DATABASE_URL, REDIS_HOST.
"""
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import psycopg2
import redis

BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgrespassword@localhost:5432/voting_db")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
CANDIDATE = "Slate 2: Tech & Innovation League"


def post(path, body):
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def get(path):
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=10) as res:
        return json.loads(res.read())


def query(sql, params=()):
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else None


def wait_for(pred, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.25)
    return False


def main():
    # Fresh state so the test is re-runnable against a long-lived stack.
    query("DELETE FROM ballots; UPDATE voter_roll SET has_voted = FALSE; UPDATE election_state SET revealed = FALSE, revealed_at = NULL")
    redis.Redis(host=REDIS_HOST).flushall()

    # 4. Secrecy: the ballots table must expose nothing joinable to a voter.
    cols = {r[0] for r in query("SELECT column_name FROM information_schema.columns WHERE table_name = 'ballots'")}
    assert cols == {"id", "candidate_choice"}, f"ballots leaks joinable columns: {cols}"
    voter_cols = {r[0] for r in query("SELECT column_name FROM information_schema.columns WHERE table_name = 'voter_roll'")}
    assert "voted_at" not in voter_cols, "voter_roll.voted_at joins identity to ballots.cast_at"
    print("ok  ballot schema has no identity/timestamp columns")

    # 1. Eligibility issues a token.
    status, body = post("/eligibility/verify", {"student_id": "stu00042"})
    assert status == 200, body
    token = body["token"]
    print("ok  eligibility token issued")

    # 5. Candidate allowlist.
    status, body = post("/vote", {"token": token, "candidate_id": "<img src=x onerror=alert(1)>"})
    assert status == 422, f"expected 422 for unknown candidate, got {status} {body}"
    print("ok  unknown candidate rejected")

    # 2. Concurrent duplicate submissions with the same token.
    with ThreadPoolExecutor(max_workers=50) as ex:
        results = list(ex.map(lambda _: post("/vote", {"token": token, "candidate_id": CANDIDATE})[0], range(50)))
    assert results.count(200) == 1 and results.count(409) == 49, f"statuses: {sorted(results)}"
    print("ok  50 concurrent submits -> exactly one queued")

    assert wait_for(lambda: query("SELECT has_voted FROM voter_roll WHERE student_id = 'STU00042'")[0][0]), "worker never recorded vote"
    assert query("SELECT COUNT(*) FROM ballots")[0][0] == 1
    status, _ = post("/eligibility/verify", {"student_id": "STU00042"})
    assert status == 409, "already-voted student re-issued a token"
    print("ok  worker recorded exactly one ballot; re-verify is 409")

    # 3. Bypass the Redis lock entirely: 20 raw stream entries for one student -> still one ballot.
    r = redis.Redis(host=REDIS_HOST)
    for _ in range(20):
        r.xadd("vote_stream", {"student_id": "STU00043", "candidate_id": CANDIDATE})
    assert wait_for(lambda: query("SELECT has_voted FROM voter_roll WHERE student_id = 'STU00043'")[0][0])
    time.sleep(1)  # let any stragglers drain
    assert query("SELECT COUNT(*) FROM ballots")[0][0] == 2, "worker double-counted a student"
    assert r.xpending("vote_stream", "vote_workers")["pending"] == 0, "worker left messages unacked"
    print("ok  20 duplicate stream entries -> one ballot, all acked")

    # 6. Reveal gate.
    assert get("/results")["revealed"] is False
    query("UPDATE election_state SET revealed = TRUE, revealed_at = NOW() WHERE id = 1")
    res = get("/results")
    assert res["revealed"] is True and res["total_turnout"] == 2
    assert {t["candidate_choice"]: t["vote_count"] for t in res["tallies"]} == {CANDIDATE: 2}
    print("ok  results hidden before reveal, tallied after")
    print("ALL PASSED")


if __name__ == "__main__":
    main()
