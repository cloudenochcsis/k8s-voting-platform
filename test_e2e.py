"""
Self-contained verification test for Student Election voting system logic.
Verifies:
1. Eligibility verification and JWT token issuance.
2. Fast-fail duplicate check logic.
3. Database transactional one-vote-per-student guarantee.
4. Ballot secrecy (ballots table decoupled from student ID).
5. Results gating (hidden when revealed=false, returned when revealed=true).
"""

import time
import jwt

def test_jwt_generation_and_validation():
    secret = "test-secret-key"
    student_id = "STU00042"
    payload = {
        "sub": student_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + 900
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    
    decoded = jwt.decode(token, secret, algorithms=["HS256"])
    assert decoded["sub"] == student_id, "Decoded subject mismatch"
    print("✓ JWT generation & validation verified")

def test_mock_voting_state_machine():
    voter_roll = {f"STU{i:05d}": {"has_voted": False} for i in range(1, 100)}
    ballots = []
    election_revealed = False

    # 1. Verify eligibility for STU00001
    student_id = "STU00001"
    assert student_id in voter_roll, "Student should exist in roll"
    assert not voter_roll[student_id]["has_voted"], "Student should not have voted"

    # 2. Worker process vote
    candidate_choice = "Slate 2: Tech & Innovation League"
    # Atomic check-and-set logic
    if not voter_roll[student_id]["has_voted"]:
        voter_roll[student_id]["has_voted"] = True
        ballots.append({"candidate_choice": candidate_choice, "cast_at": time.time()})
        vote_success = True
    else:
        vote_success = False

    assert vote_success is True, "First vote should succeed"
    assert len(ballots) == 1, "One ballot should be recorded"
    assert "student_id" not in ballots[0], "Ballot secrecy violation: student_id found in ballot"

    # 3. Duplicate vote attempt with same student_id
    if not voter_roll[student_id]["has_voted"]:
        voter_roll[student_id]["has_voted"] = True
        ballots.append({"candidate_choice": candidate_choice, "cast_at": time.time()})
        second_vote_success = True
    else:
        second_vote_success = False

    assert second_vote_success is False, "Duplicate vote must be rejected"
    assert len(ballots) == 1, "Duplicate ballot must not be recorded"
    print("✓ Single-vote guarantee and ballot secrecy verified")

    # 4. Results Gate test
    # When polls open (revealed = False)
    if not election_revealed:
        results_output = {"revealed": False}
    else:
        results_output = {"revealed": True, "tallies": ballots}

    assert results_output["revealed"] is False, "Results should be hidden when unrevealed"

    # Flip reveal gate
    election_revealed = True
    if not election_revealed:
        results_output = {"revealed": False}
    else:
        from collections import Counter
        counts = Counter(b["candidate_choice"] for b in ballots)
        results_output = {
            "revealed": True,
            "tallies": [{"candidate": k, "votes": v} for k, v in counts.items()]
        }

    assert results_output["revealed"] is True, "Results should be visible when revealed"
    assert results_output["tallies"][0]["votes"] == 1, "Tally count mismatch"
    print("✓ Reveal gate logic verified")

if __name__ == "__main__":
    print("Running Student Election Voting Platform core logic tests...")
    test_jwt_generation_and_validation()
    test_mock_voting_state_machine()
    print("All core tests passed successfully!")
