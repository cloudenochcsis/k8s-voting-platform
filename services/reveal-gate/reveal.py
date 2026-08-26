import os
import sys
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/voting_db")

def main():
    print("Executing reveal-gate: flipping election results reveal flag...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute("UPDATE election_state SET revealed = TRUE, revealed_at = NOW() WHERE id = 1")
            conn.commit()
        conn.close()
        print("Success: election_state.revealed is now TRUE.")
    except Exception as e:
        print(f"Error in reveal-gate: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
