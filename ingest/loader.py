"""Create/evolve tables from runtime schema, then insert or upsert rows."""
from datetime import datetime, timezone

from sqlalchemy import (JSON, BigInteger, Column, DateTime, Index, Integer,
                        MetaData, Table, Text, func, inspect, select, text)

from .schema import (coerce, infer_schema, kind_to_type, sanitize_column,
                     sanitize_record, type_to_kind)

SYSTEM_COLUMNS = {"_id", "_ingested_at"}


def _pk():
    return Column("_id", BigInteger().with_variant(Integer(), "sqlite"),
                  primary_key=True, autoincrement=True)


def _dialect_insert(engine):
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise NotImplementedError(f"Unsupported database: {engine.dialect.name}")
    return insert


def _runs_table(meta):
    return Table(
        "_ingest_runs", meta,
        Column("run_id", BigInteger().with_variant(Integer(), "sqlite"),
               primary_key=True, autoincrement=True),
        Column("table_name", Text, nullable=False),
        Column("started_at", DateTime(timezone=True)),
        Column("finished_at", DateTime(timezone=True)),
        Column("rows_received", Integer),
        Column("rows_loaded", Integer),
        Column("rows_rejected", Integer),
        Column("columns_added", JSON),
        Column("warnings", JSON),
        Column("status", Text),
    )


def ensure_table(engine, name, schema, key=None):
    """Create the table, or add any columns it is missing. Returns (Table, added_columns)."""
    added = []
    if not inspect(engine).has_table(name):
        meta = MetaData()
        table = Table(
            name, meta, _pk(),
            Column("_ingested_at", DateTime(timezone=True),
                   server_default=func.now(), nullable=False),
            *[Column(c, kind_to_type(k)) for c, k in schema.items()],
        )
        meta.create_all(engine)
        added = list(schema)
    else:
        table = Table(name, MetaData(), autoload_with=engine)
        prep = engine.dialect.identifier_preparer
        with engine.begin() as conn:
            for col, kind in schema.items():
                if col not in table.c:
                    col_type = kind_to_type(kind).compile(dialect=engine.dialect)
                    conn.execute(text(
                        f"ALTER TABLE {prep.quote(name)} "
                        f"ADD COLUMN {prep.quote(col)} {col_type}"))
                    added.append(col)
        if added:
            table = Table(name, MetaData(), autoload_with=engine)
    if key:
        Index(f"uq_{name}_{key}"[:63], table.c[key], unique=True).create(
            engine, checkfirst=True)
    return table, added


def load_records(engine, table, records, key=None, batch_size=500):
    """Load an iterable of dicts. With `key`, rows are upserted on that column.

    Missing keys never overwrite existing values on upsert; an explicit null does.
    """
    started = datetime.now(timezone.utc)
    table_name = sanitize_column(table)
    key = sanitize_column(key) if key else None
    rows, rejected, warnings = [], 0, []

    for rec in records:
        if isinstance(rec, dict) and rec:
            rows.append(sanitize_record(rec))
        else:
            rejected += 1
    received = len(rows) + rejected

    if key:
        kept = [r for r in rows if r.get(key) is not None]
        rejected += len(rows) - len(kept)
        rows = kept

    report = {"table": table_name, "received": received, "loaded": 0,
              "rejected": rejected, "columns_added": [], "warnings": warnings,
              "status": "empty"}

    if rows:
        schema = infer_schema(rows)
        tbl, added = ensure_table(engine, table_name, schema, key)
        kinds = {c.name: type_to_kind(c.type) for c in tbl.c
                 if c.name not in SYSTEM_COLUMNS}

        clean, failures = [], 0
        for r in rows:
            out = {}
            for col, val in r.items():
                try:
                    out[col] = coerce(val, kinds[col])
                except (ValueError, TypeError):
                    out[col] = None
                    failures += 1
                    if len(warnings) < 10:
                        warnings.append(f"{col}: cannot convert {val!r} to {kinds[col]} -> NULL")
            clean.append(out)

        if key:  # keep the last record per key, merging fields
            merged = {}
            for r in clean:
                if r.get(key) is None:
                    rejected += 1
                    continue
                merged[r[key]] = {**merged.get(r[key], {}), **r}
            clean = list(merged.values())

        groups = {}  # rows sharing the same set of columns are inserted together
        for r in clean:
            groups.setdefault(tuple(r), []).append(r)

        ins = _dialect_insert(engine)
        with engine.begin() as conn:
            for cols, group in groups.items():
                for i in range(0, len(group), batch_size):
                    stmt = ins(tbl)
                    if key:
                        update = {c: stmt.excluded[c] for c in cols if c != key}
                        stmt = (stmt.on_conflict_do_update(index_elements=[key], set_=update)
                                if update else
                                stmt.on_conflict_do_nothing(index_elements=[key]))
                    conn.execute(stmt, group[i:i + batch_size])

        report.update(loaded=len(clean), rejected=rejected, columns_added=added,
                      status="ok", coercion_failures=failures)

    meta = MetaData()
    runs = _runs_table(meta)
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(runs.insert().values(
            table_name=table_name, started_at=started,
            finished_at=datetime.now(timezone.utc),
            rows_received=received, rows_loaded=report["loaded"],
            rows_rejected=report["rejected"], columns_added=report["columns_added"],
            warnings=warnings, status=report["status"]))
    return report


def describe_table(engine, table):
    name = sanitize_column(table)
    if not inspect(engine).has_table(name):
        raise ValueError(f"Table '{name}' does not exist")
    return [(c["name"], str(c["type"])) for c in inspect(engine).get_columns(name)]


def recent_runs(engine, limit=10):
    meta = MetaData()
    runs = _runs_table(meta)
    meta.create_all(engine)
    with engine.connect() as conn:
        return conn.execute(select(runs).order_by(runs.c.run_id.desc()).limit(limit)).all()
