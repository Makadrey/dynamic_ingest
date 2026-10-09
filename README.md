# Dynamic Ingest: schema-on-the-fly JSON to Postgres

A small loader that takes JSON records whose fields are **not known in advance**, works out the schema at runtime, creates or evolves the Postgres table with **SQLAlchemy**, and inserts (or upserts) the data. Credentials live in `.env`, never in code.

## Why this exists
Real event and API data changes shape: new fields appear, types are messy, and some rows are just broken. Hand-written `CREATE TABLE` scripts go stale. This project shows a safe way to let the data drive the schema.

## How it works
```
 JSON / JSONL / stdin
        |
        v
  sanitize names  ->  infer types  ->  create table / ADD COLUMN  ->  coerce values  ->  insert or upsert
  (userId->user_id)   (merge rows)     (additive only)               (bad -> NULL)       (ON CONFLICT)
                                                                                              |
                                                                                              v
                                                                                       _ingest_runs log
```

| Step | What happens |
|---|---|
| Sanitize | `userId`, `Event Type`, `1st` become safe snake_case column names |
| Infer | bool, int, float, ISO datetime, text, and nested JSON (stored as **JSONB** on Postgres). Mixed int and float widen to float, any other conflict falls back to text |
| Evolve | Missing columns are added with `ALTER TABLE ... ADD COLUMN`. Columns are never dropped or retyped |
| Coerce | Values are converted to the **existing column type** (`"12.5"` becomes `12.5`). Unconvertible values become NULL and are reported |
| Upsert | With `--key`, a unique index is created and rows use `INSERT ... ON CONFLICT DO UPDATE` |
| Audit | Every run is recorded in `_ingest_runs` (rows loaded and rejected, columns added, warnings) |

## Quick start
```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure credentials (placeholders only in the repo)
cp .env.example .env        # then edit .env with your real values

# 3. Start Postgres locally (reads the same .env)
docker compose up -d

# 4. Generate sample data and load three "days" of evolving data
python -m ingest generate
python -m ingest load data/events_day1.jsonl --table events --key event_id
python -m ingest load data/events_day2.jsonl --table events --key event_id
python -m ingest load data/events_day3.jsonl --table events --key event_id

# 5. Inspect
python -m ingest describe --table events
python -m ingest runs
```

Load from a pipe too: `cat records.jsonl | python -m ingest load - --table events`

## Example output
```
$ python -m ingest load data/events_day1.jsonl --table events --key event_id
Loaded 200/200 rows into 'events' (rejected: 0)
Columns added: event_id, user_id, event_type, timestamp, amount

$ python -m ingest load data/events_day2.jsonl --table events --key event_id
Loaded 200/200 rows into 'events' (rejected: 0)
Columns added: device, metadata

$ python -m ingest load data/events_day3.jsonl --table events --key event_id
Loaded 220/221 rows into 'events' (rejected: 1)
Columns added: country, is_premium, discount
  warning: amount: cannot convert 'N/A' to float -> NULL
```
The table grew from 5 to 10 data columns across three loads with no manual migration. Day 3 also contains one invalid JSON line (rejected) and 20 re-sent events (upserted, so no duplicates).

```
$ python -m ingest describe --table events
_id             BIGINT
_ingested_at    TIMESTAMP
event_id        TEXT
user_id         BIGINT
event_type      TEXT
timestamp       TIMESTAMP
amount          DOUBLE PRECISION
device          TEXT
metadata        JSONB
country         TEXT
is_premium      BOOLEAN
discount        DOUBLE PRECISION
```

## Project structure
```
ingest/
  config.py    reads settings from env / .env, builds the DB URL safely
  db.py        SQLAlchemy engine
  schema.py    name sanitizing, type inference, value coercion
  loader.py    create/evolve table, insert/upsert, run log
  sources.py   read json/jsonl/stdin, generate sample data
  __main__.py  CLI: generate | load | describe | runs
tests/         17 tests (SQLite by default, Postgres via TEST_DATABASE_URL)
data/          sample JSONL files
.env.example   placeholder settings (copy to .env)
docker-compose.yml, .github/workflows/ci.yml
```

## Design decisions
- **Additive-only migrations.** Adding a column is safe. Dropping or retyping columns from live data is not, so the tool never does it.
- **Existing column type wins.** If `amount` is already `FLOAT`, later strings are coerced to it instead of changing the schema.
- **Missing is not null.** On upsert, a field absent from a record keeps its stored value, while an explicit `null` overwrites it.
- **Bad data does not stop the load.** Invalid JSON lines and rows missing the key are rejected, unconvertible values become NULL, and everything is logged.
- **Safe SQL.** Values are always bound parameters, and identifiers are sanitized and quoted by SQLAlchemy.
- **Secrets stay out of code.** `.env` is gitignored, `.env.example` holds placeholders, and `URL.create` escapes special characters in passwords.

## Testing
```bash
pytest -q                                   # runs on SQLite, no setup
TEST_DATABASE_URL=postgresql+psycopg2://user:pass@localhost/test pytest -q   # real Postgres
```
CI runs the suite against a Postgres service on every push.

## Limitations and roadmap
- Type conflicts across rows collapse to text, and widening an existing column (for example `INT` to `FLOAT`) is not automated.
- Nested objects are stored whole as JSONB. Optional flattening (`a.b` to `a_b`) is a possible next step.
- Add a REST API source with pagination, a `--dry-run` mode that prints the planned DDL, and Alembic-style migration history.
