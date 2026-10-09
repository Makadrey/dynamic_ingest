<div align="center">

# 🔄 Dynamic Ingest

**Schema-on-the-fly JSON → Postgres**

Load JSON records whose fields you don't know in advance. The table builds and evolves itself.

![Python](https://img.shields.io/badge/python-3.x-3776AB?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-JSONB-4169E1?logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM%20Core-D71F00)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/tests-17%20passing-brightgreen)
[![CI](https://github.com/Makadrey/dynamic_ingest/actions/workflows/ci.yml/badge.svg)](https://github.com/Makadrey/dynamic_ingest/actions)

[Why](#-why-this-exists) · [How it works](#-how-it-works) · [Quick start](#-quick-start) · [Demo](#-demo-three-days-of-evolving-data) · [CLI](#-cli-reference) · [Design](#-design-decisions) · [Roadmap](#-limitations--roadmap)

</div>

---

## 💡 Why this exists

Real event and API data changes shape: new fields appear, types are messy, and some rows are just broken. Hand-written `CREATE TABLE` scripts go stale. This project shows a safe way to let the data drive the schema.

| ❌ Without it | ✅ With Dynamic Ingest |
|---|---|
| Edit migration scripts every time a field appears | New fields become columns automatically |
| One bad row crashes the whole load | Bad rows are rejected, bad values become `NULL`, the load continues |
| Re-sent events create duplicates | `--key` turns inserts into upserts |
| No record of what happened | Every run is logged in `_ingest_runs` |
| Credentials end up in code | Credentials stay in `.env`, never in the repo |

## ✨ Features

| | Feature | Detail |
|---|---|---|
| 🧬 | **Schema inference** | Detects bool, int, float, ISO datetime, text, and nested JSON |
| 🌱 | **Additive evolution** | Creates the table, then `ADD COLUMN` as new fields appear |
| 🛡️ | **Safe coercion** | Converts values to the existing column type; failures become `NULL` and are reported |
| 🔁 | **Upsert** | `INSERT … ON CONFLICT DO UPDATE` on a unique key |
| 📜 | **Audit log** | Rows loaded and rejected, columns added, warnings per run |
| 🔐 | **Secrets handling** | `.env` is gitignored, special characters in passwords are escaped |

## ⚙️ How it works

```mermaid
flowchart LR
    A["📥 JSON / JSONL / stdin"] --> B["🧹 Sanitize names<br/><i>userId → user_id</i>"]
    B --> C["🔍 Infer types<br/><i>merge across rows</i>"]
    C --> D["🏗️ Create table /<br/>ADD COLUMN<br/><i>additive only</i>"]
    D --> E["🔧 Coerce values<br/><i>bad → NULL</i>"]
    E --> F["💾 Insert or upsert<br/><i>ON CONFLICT</i>"]
    F --> G[("🐘 Postgres")]
    F -.-> H["📜 _ingest_runs<br/>audit log"]

    style A fill:#e8f1ff,stroke:#4169E1
    style G fill:#dff5e1,stroke:#2e9e44
    style H fill:#fff4d6,stroke:#d69e00
```

| Step | What happens |
|---|---|
| **Sanitize** | `userId`, `Event Type`, `1st` become safe snake_case column names |
| **Infer** | bool, int, float, ISO datetime, text, nested JSON (stored as **JSONB** on Postgres) |
| **Evolve** | Missing columns are added with `ALTER TABLE … ADD COLUMN`. Columns are never dropped or retyped |
| **Coerce** | Values are converted to the **existing column type** (`"12.5"` becomes `12.5`). Unconvertible values become `NULL` and are reported |
| **Upsert** | With `--key`, a unique index is created and rows use `INSERT … ON CONFLICT DO UPDATE` |
| **Audit** | Every run is recorded in `_ingest_runs` |

### Type inference

| Example value | Column type |
|---|---|
| `true` | `BOOLEAN` |
| `42` | `BIGINT` |
| `12.5` | `DOUBLE PRECISION` |
| `"2025-06-01T10:30:00"` | `TIMESTAMP` |
| `"hello"` | `TEXT` |
| `{"a": 1}` or `[1, 2]` | `JSONB` |

When rows disagree about a field's type:

```mermaid
flowchart LR
    X["int + float"] --> Y["✅ widens to float"]
    P["any other conflict<br/><i>e.g. int + text</i>"] --> Q["⚠️ falls back to text"]
    style Y fill:#dff5e1,stroke:#2e9e44
    style Q fill:#fff4d6,stroke:#d69e00
```

## 🚀 Quick start

**1. Install**
```bash
pip install -r requirements.txt
```

**2. Configure credentials** (the repo contains placeholders only)
```bash
cp .env.example .env        # then edit .env with your real values
```

**3. Start Postgres locally** (reads the same `.env`)
```bash
docker compose up -d
```

**4. Generate sample data and load three "days" of evolving data**
```bash
python -m ingest generate
python -m ingest load data/events_day1.jsonl --table events --key event_id
python -m ingest load data/events_day2.jsonl --table events --key event_id
python -m ingest load data/events_day3.jsonl --table events --key event_id
```

**5. Inspect**
```bash
python -m ingest describe --table events
python -m ingest runs
```

> 💡 You can also load from a pipe: `cat records.jsonl | python -m ingest load - --table events`

## 🎬 Demo: three days of evolving data

The table grows from **5 to 10 data columns** across three loads, with no manual migration.

```mermaid
flowchart LR
    D1["<b>Day 1</b><br/>200 rows<br/>+5 columns"] --> D2["<b>Day 2</b><br/>200 rows<br/>+2 columns"] --> D3["<b>Day 3</b><br/>221 rows<br/>+3 columns<br/>1 rejected"]
    style D1 fill:#e8f1ff,stroke:#4169E1
    style D2 fill:#e8f1ff,stroke:#4169E1
    style D3 fill:#fff4d6,stroke:#d69e00
```

| Day | Loaded | New columns | Notes |
|---|---|---|---|
| 1 | 200 / 200 | `event_id` `user_id` `event_type` `timestamp` `amount` | Table created |
| 2 | 200 / 200 | `device` `metadata` | `metadata` is stored as JSONB |
| 3 | 220 / 221 | `country` `is_premium` `discount` | 1 invalid JSON line rejected, 1 value (`'N/A'`) coerced to `NULL`, 20 re-sent events upserted with no duplicates |

<details>
<summary><b>📟 See the terminal output</b></summary>

```text
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

</details>

<details>
<summary><b>🗂️ See the final table schema</b></summary>

```text
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

`_id` and `_ingested_at` are added by the loader. The other ten columns came from the data.

</details>

## 🧰 CLI reference

| Command | Purpose | Example |
|---|---|---|
| `generate` | Create sample JSONL files in `data/` | `python -m ingest generate` |
| `load` | Infer, evolve, and load a file (or `-` for stdin) | `python -m ingest load data/events_day1.jsonl --table events --key event_id` |
| `describe` | Show a table's columns and types | `python -m ingest describe --table events` |
| `runs` | Show the `_ingest_runs` audit log | `python -m ingest runs` |

| Option | Meaning |
|---|---|
| `--table` | Target table name |
| `--key` | Unique key column; enables upsert instead of plain insert |

## 📁 Project structure

```text
dynamic-ingest/
├── ingest/
│   ├── config.py        # reads settings from env / .env, builds the DB URL safely
│   ├── db.py            # SQLAlchemy engine
│   ├── schema.py        # name sanitizing, type inference, value coercion
│   ├── loader.py        # create/evolve table, insert/upsert, run log
│   ├── sources.py       # read json/jsonl/stdin, generate sample data
│   └── __main__.py      # CLI: generate | load | describe | runs
├── tests/               # 17 tests (SQLite by default, Postgres via TEST_DATABASE_URL)
├── data/                # sample JSONL files
├── .env.example         # placeholder settings (copy to .env)
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## 🧠 Design decisions

| Decision | Why |
|---|---|
| **Additive-only migrations** | Adding a column is safe. Dropping or retyping columns from live data is not, so the tool never does it |
| **Existing column type wins** | If `amount` is already `FLOAT`, later strings are coerced to it instead of changing the schema |
| **Missing is not null** | On upsert, a field absent from a record keeps its stored value, while an explicit `null` overwrites it |
| **Bad data does not stop the load** | Invalid JSON lines and rows missing the key are rejected, unconvertible values become `NULL`, and everything is logged |
| **Safe SQL** | Values are always bound parameters, and identifiers are sanitized and quoted by SQLAlchemy |
| **Secrets stay out of code** | `.env` is gitignored, `.env.example` holds placeholders, and `URL.create` escapes special characters in passwords |

## 🧪 Testing

```bash
# Runs on SQLite, no setup needed
pytest -q

# Run against a real Postgres
TEST_DATABASE_URL=postgresql+psycopg2://user:pass@localhost/test pytest -q
```

CI runs the suite against a Postgres service on every push.

## 🗺️ Limitations & roadmap

**Known limitations**
- Type conflicts across rows collapse to text, and widening an existing column (for example `INT` to `FLOAT`) is not automated.
- Nested objects are stored whole as JSONB.

**Roadmap**
- [ ] Optional flattening of nested objects (`a.b` → `a_b`)
- [ ] REST API source with pagination
- [ ] `--dry-run` mode that prints the planned DDL
- [ ] Alembic-style migration history
