from sqlalchemy import MetaData, Table, func, select

from ingest.loader import describe_table, load_records, recent_runs


def rows_of(engine, name):
    t = Table(name, MetaData(), autoload_with=engine)
    with engine.connect() as c:
        return c.execute(select(t)).mappings().all()


def test_creates_table_and_inserts(engine):
    rep = load_records(engine, "t", [{"Name": "a", "age": 3}, {"Name": "b", "age": 4}])
    assert rep["loaded"] == 2
    assert {n for n, _ in describe_table(engine, "t")} >= {"name", "age", "_id", "_ingested_at"}


def test_adds_new_columns_on_later_loads(engine):
    load_records(engine, "t", [{"a": 1}])
    rep = load_records(engine, "t", [{"a": 2, "b": "x", "meta": {"k": 1}}])
    assert set(rep["columns_added"]) == {"b", "meta"}
    assert len(rows_of(engine, "t")) == 2


def test_upsert_is_idempotent(engine):
    data = [{"id": i, "v": i} for i in range(5)]
    load_records(engine, "t", data, key="id")
    load_records(engine, "t", data, key="id")
    assert len(rows_of(engine, "t")) == 5


def test_upsert_missing_fields_do_not_overwrite(engine):
    load_records(engine, "t", [{"id": 1, "a": "x", "b": "y"}], key="id")
    load_records(engine, "t", [{"id": 1, "a": "z"}], key="id")
    row = rows_of(engine, "t")[0]
    assert row["a"] == "z" and row["b"] == "y"


def test_coercion_and_warnings(engine):
    load_records(engine, "t", [{"amount": 1.5}])
    rep = load_records(engine, "t", [{"amount": "12.5"}, {"amount": "N/A"}])
    vals = sorted(r["amount"] for r in rows_of(engine, "t") if r["amount"] is not None)
    assert vals == [1.5, 12.5]
    assert rep["coercion_failures"] == 1 and rep["warnings"]


def test_rows_without_key_are_rejected(engine):
    rep = load_records(engine, "t", [{"id": 1}, {"other": 2}, None], key="id")
    assert rep["loaded"] == 1 and rep["rejected"] == 2


def test_nested_json_round_trips(engine):
    load_records(engine, "t", [{"meta": {"a": [1, 2]}}])
    assert rows_of(engine, "t")[0]["meta"] == {"a": [1, 2]}


def test_run_log_written(engine):
    load_records(engine, "t", [{"a": 1}])
    runs = recent_runs(engine)
    assert runs[0].table_name == "t" and runs[0].rows_loaded == 1
