import os
import signal
import sys
import time
import socket
import logging
import redis
import psycopg2
from redis.exceptions import ResponseError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/voting_db")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_STREAM = os.getenv("REDIS_STREAM", "vote_stream")
GROUP_NAME = os.getenv("REDIS_GROUP", "vote_workers")
CONSUMER_NAME = os.getenv("CONSUMER_NAME", f"worker-{socket.gethostname()}")

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
        if "BUSYGROUP" in str(e):
            logging.info(f"Consumer group {GROUP_NAME} already exists")
        else:
            raise

def main():
    logging.info(f"Starting vote worker consumer: {CONSUMER_NAME}")
    
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    init_redis_group(r)

    db_conn = get_db_connection()
    if not db_conn:
        return

    while running:
        try:
            # Read pending or new items from consumer group
            messages = r.xreadgroup(
                groupname=GROUP_NAME,
                consumername=CONSUMER_NAME,
                streams={REDIS_STREAM: ">"},
                count=20,
                block=2000
            )

            if not messages:
                continue

            for stream_name, msg_list in messages:
                for msg_id, data in msg_list:
                    student_id = data.get("student_id")
                    candidate_id = data.get("candidate_id")

                    if not student_id or not candidate_id:
                        r.xack(REDIS_STREAM, GROUP_NAME, msg_id)
                        continue

                    # Transactional single-vote enforcement:
                    # 1. Update voter_roll if has_voted = false
                    # 2. If rowcount == 1, insert ballot into ballots table
                    # 3. If rowcount == 0, duplicate vote attempt ignored
                    try:
                        with db_conn.cursor() as cur:
                            cur.execute(
                                "UPDATE voter_roll SET has_voted = TRUE, voted_at = NOW() WHERE student_id = %s AND has_voted = FALSE",
                                (student_id,)
                            )
                            if cur.rowcount == 1:
                                cur.execute(
                                    "INSERT INTO ballots (candidate_choice, cast_at) VALUES (%s, NOW())",
                                    (candidate_id,)
                                )
                                db_conn.commit()
                                logging.info(f"Cast ballot recorded for choice={candidate_id}")
                            else:
                                db_conn.rollback()
                                logging.warning(f"Duplicate/ineligible vote discarded for student {student_id}")

                        # Acknowledge processed message in Redis
                        r.xack(REDIS_STREAM, GROUP_NAME, msg_id)

                    except (psycopg2.OperationalError, psycopg2.InterfaceError) as dberr:
                        logging.error(f"Database error during message processing: {dberr}. Reconnecting...")
                        db_conn = get_db_connection()
                        # Do not ack message so it gets retried

        except Exception as e:
            if running:
                logging.error(f"Error in worker processing loop: {e}")
                time.sleep(1)

    if db_conn and not db_conn.closed:
        db_conn.close()
    logging.info("Worker stopped.")

if __name__ == "__main__":
    main()
