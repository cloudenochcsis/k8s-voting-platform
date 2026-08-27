-- DB Schema for Student Council Election. Single source of truth: mounted by docker-compose
-- and shipped to Kubernetes via the configMapGenerator in kustomization.yaml.

-- Voter roll: eligibility + turnout only. No ballot info, and deliberately no timestamp —
-- a voted_at column would join to any timestamp on ballots and break secrecy.
CREATE TABLE IF NOT EXISTS voter_roll (
    student_id VARCHAR(64) PRIMARY KEY,
    has_voted BOOLEAN DEFAULT FALSE
);

-- Ballots: no student_id, no FK, no timestamp. Nothing here can be joined back to a voter.
CREATE TABLE IF NOT EXISTS ballots (
    id SERIAL PRIMARY KEY,
    candidate_choice VARCHAR(128) NOT NULL
);

-- Election state (reveal gate)
CREATE TABLE IF NOT EXISTS election_state (
    id INT PRIMARY KEY DEFAULT 1,
    revealed BOOLEAN DEFAULT FALSE,
    revealed_at TIMESTAMP NULL,
    CONSTRAINT single_row CHECK (id = 1)
);

INSERT INTO election_state (id, revealed) VALUES (1, FALSE) ON CONFLICT (id) DO NOTHING;

-- Seed 10,000 synthetic student IDs (STU00001 to STU10000)
INSERT INTO voter_roll (student_id, has_voted)
SELECT 'STU' || LPAD(i::text, 5, '0'), FALSE
FROM generate_series(1, 10000) AS i
ON CONFLICT (student_id) DO NOTHING;
