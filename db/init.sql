-- DB Schema for Student Council Election
-- Voter roll: Tracks eligibility and turnout. NO ballot info.
CREATE TABLE IF NOT EXISTS voter_roll (
    student_id VARCHAR(64) PRIMARY KEY,
    has_voted BOOLEAN DEFAULT FALSE,
    voted_at TIMESTAMP NULL
);

-- Ballots: Ballot secrecy guaranteed by having NO student_id column
CREATE TABLE IF NOT EXISTS ballots (
    id SERIAL PRIMARY KEY,
    candidate_choice VARCHAR(128) NOT NULL,
    cast_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
-- ponytail: simple synthetic range generation via generate_series
INSERT INTO voter_roll (student_id, has_voted)
SELECT 'STU' || LPAD(i::text, 5, '0'), FALSE
FROM generate_series(1, 10000) AS i
ON CONFLICT (student_id) DO NOTHING;
