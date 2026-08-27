import os
import signal
import time
import socket
import logging
import redis
import psycopg2
from redis.exceptions import ResponseError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_STREAM = os.getenv("REDIS_STREAM", "vote_stream")
GROUP_NAME = os.getenv("REDIS_GROUP", "vote_workers")
CONSUMER_NAME = os.getenv("CONSUMER_NAME", f"worker-{socket.gethostname()}")
BATCH = 20
RECLAIM_IDLE_MS = int(os.getenv("RECLAIM_IDLE_MS", "60000"))  # unacked this long = dead consumer; tests shrink it

running = True


def handle_signal(sig, frame):
    global running
    logging.info(f"Received signal {sig}, terminating gracefully...")
    running = False


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def get_db_connection():
    while running:
        try:
            return psycopg2.connect(DATABASE_URL)
        except Exception as e:
            logging.warning(f"Database connection failed ({e}), retrying in 2s...")
            time.sleep(2)
    return None


def init_redis_group(r: redis.Redis):
    try:
        r.xgroup_create(REDIS_STREAM, GROUP_NAME, id="0", mkstream=True)
        logging.info(f"Created consumer group {GROUP_NAME} on stream {REDIS_STREAM}")
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def process(db_conn, data) -> None:
    """One-vote-per-student is enforced here, by the DB, regardless of what the queue contains."""
    student_id, candidate_id = data.get("student_id"), data.get("candidate_id")
    if not student_id or not candidate_id:
        return
    try:
        with db_conn.cursor() as cur:
            cur.execute(
                "UPDATE voter_roll SET has_voted = TRUE WHERE student_id = %s AND has_voted = FALSE",
                (student_id,),
            )
            recorded = cur.rowcount == 1
            if recorded:
                cur.execute("INSERT INTO ballots (candidate_choice) VALUES (%s)", (candidate_id,))
        db_conn.commit()
    except Exception:
        db_conn.rollback()  # never leave the connection in an aborted transaction
        raise
    # Ballot secrecy: never log student_id and candidate_id together (or with a timestamp).
    logging.info("ballot recorded" if recorded else "duplicate vote discarded")


def main():
    logging.info(f"Starting vote worker consumer: {CONSUMER_NAME}")
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    init_redis_group(r)
    db_conn = get_db_connection()

    # Start from "0" to replay anything this consumer left unacked (crash mid-batch), then switch to new messages.
    read_from = "0"
    while running:
        try:
            # Steal messages abandoned by dead consumers (scale-down, OOM); otherwise they sit in the PEL forever
            # while the voter's Redis lock says "already voted" -> silent vote loss.
            claimed = r.xautoclaim(REDIS_STREAM, GROUP_NAME, CONSUMER_NAME, RECLAIM_IDLE_MS, count=BATCH)[1]
            resp = r.xreadgroup(GROUP_NAME, CONSUMER_NAME, {REDIS_STREAM: read_from}, count=BATCH, block=2000)
            fresh = resp[0][1] if resp else []
            if read_from == "0" and not fresh:
                read_from = ">"

            for msg_id, data in claimed + fresh:
                process(db_conn, data)
                # Ack only after commit (a crash before this is retried), then delete: the entry itself is the
                # student_id -> choice pair, and Redis now persists to disk.
                r.pipeline().xack(REDIS_STREAM, GROUP_NAME, msg_id).xdel(REDIS_STREAM, msg_id).execute()
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            logging.error(f"Database error: {e}. Reconnecting...")
            db_conn = get_db_connection()
        except ResponseError as e:
            if "NOGROUP" not in str(e):
                raise
            logging.warning("Stream/group vanished (Redis restart or flush); recreating")
            init_redis_group(r)
            read_from = "0"
        except Exception as e:
            if running:
                logging.error(f"Error in worker loop: {e}")
                time.sleep(1)

    if db_conn and not db_conn.closed:
        db_conn.close()
    logging.info("Worker stopped.")


if __name__ == "__main__":
    main()
