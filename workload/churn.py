"""Churn + failure injectors. One file, stdlib only (psycopg)."""
import argparse, time
import psycopg

SETUP = "CREATE TABLE IF NOT EXISTS churn(id SERIAL PRIMARY KEY, v TEXT); INSERT INTO churn(v) SELECT 'x' FROM generate_series(1,10000) ON CONFLICT DO NOTHING;"
CHURN = "UPDATE churn SET v = md5(random()::text) WHERE id % 10 = 0; DELETE FROM churn WHERE id % 97 = 0; INSERT INTO churn(v) SELECT md5(g::text) FROM generate_series(1,100) g ON CONFLICT DO NOTHING;"

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dsn", default="dbname=bloatdemo user=postgres password=postgres host=localhost port=5433")
    p.add_argument("--mode", choices=["churn", "idle-xact", "slot"], default="churn")
    p.add_argument("--secs", type=int, default=120)
    a = p.parse_args()
    if a.mode == "idle-xact":  # holds xmin open -> blocks vacuum, the 60s demo
        con = psycopg.connect(a.dsn, autocommit=False)
        con.execute("BEGIN; SELECT * FROM churn LIMIT 1; SELECT pg_sleep(%s)", (a.secs,))
    elif a.mode == "slot":
        with psycopg.connect(a.dsn, autocommit=True) as c:
            c.execute("SELECT pg_create_logical_replication_slot('abandoned_demo', 'test_decoding')")
            print("slot abandoned_demo created; WAL retained, xmin frozen. Drop with pg_drop_replication_slot.")
    else:
        end = time.time() + a.secs
        with psycopg.connect(a.dsn, autocommit=True) as c:
            c.execute(SETUP)
            while time.time() < end:
                c.execute(CHURN)

if __name__ == "__main__":
    main()
