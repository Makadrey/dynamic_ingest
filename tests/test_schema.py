import pytest

from ingest.schema import coerce, infer_kind, infer_schema, merge_kinds, sanitize_column


@pytest.mark.parametrize("raw,expected", [
    ("User ID", "user_id"), ("userId", "user_id"), ("123abc", "c_123abc"),
    ("Event-Type!", "event_type"), ("   ", "col"),
])
def test_sanitize_column(raw, expected):
    assert sanitize_column(raw) == expected


def test_infer_kind():
    assert infer_kind(True) == "bool"
    assert infer_kind(3) == "int"
    assert infer_kind(3.5) == "float"
    assert infer_kind({"a": 1}) == "json"
    assert infer_kind("2025-01-01T10:00:00Z") == "datetime"
    assert infer_kind("hello") == "text"
    assert infer_kind(None) is None


def test_merge_kinds():
    assert merge_kinds("int", "float") == "float"
    assert merge_kinds("int", "text") == "text"
    assert merge_kinds(None, "int") == "int"


def test_infer_schema_merges_across_rows():
    s = infer_schema([{"a": 1, "b": None}, {"a": 2.5, "b": None}])
    assert s == {"a": "float", "b": "text"}


def test_coerce():
    assert coerce("12.5", "float") == 12.5
    assert coerce("7", "int") == 7
    assert coerce({"a": 1}, "text") == '{"a": 1}'
    with pytest.raises(ValueError):
        coerce("N/A", "float")
    with pytest.raises(ValueError):
        coerce(True, "int")
