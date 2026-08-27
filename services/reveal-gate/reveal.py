import os
import sys
import psycopg2


def main():
    print("Executing reveal-gate: flipping election results reveal flag...")
    try:
        with psycopg2.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
            cur.execute("UPDATE election_state SET revealed = TRUE, revealed_at = NOW() WHERE id = 1")
        print("Success: election_state.revealed is now TRUE.")
    except Exception as e:
        print(f"Error in reveal-gate: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
