"""Runtime schema inference: safe column names, type detection, value coercion."""
import json
import re
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB

_ISO = re.compile(
    r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$"
)


def sanitize_column(name):
    """'userId' -> 'user_id', 'Event Type' -> 'event_type', '1st' -> 'c_1st'."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(name).strip())
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", s).strip("_").lower()
    if not s:
        s = "col"
    if s[0].isdigit():
        s = "c_" + s
    return s[:63]  # Postgres identifier limit


def sanitize_record(rec):
    return {sanitize_column(k): v for k, v in rec.items()}


def parse_datetime(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))


def infer_kind(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (dict, list)):
        return "json"
    if isinstance(value, str) and _ISO.match(value.strip()):
        try:
            parse_datetime(value)
            return "datetime"
        except ValueError:
            pass
    return "text"


def merge_kinds(a, b):
    if a is None or a == b:
        return b if a is None else a
    if b is None:
        return a
    if {a, b} == {"int", "float"}:
        return "float"
    return "text"  # any other conflict falls back to text


def infer_schema(rows):
    """Merge the types seen across all rows -> {column: kind}. Order = first appearance."""
    kinds = {}
    for row in rows:
        for col, val in row.items():
            kinds[col] = merge_kinds(kinds.get(col), infer_kind(val))
    return {c: (k or "text") for c, k in kinds.items()}


def kind_to_type(kind):
    return {
        "bool": Boolean(),
        "int": BigInteger(),
        "float": Float(),
        "datetime": DateTime(timezone=True),
        "text": Text(),
        "json": JSON().with_variant(JSONB(), "postgresql"),
    }[kind]


def type_to_kind(sa_type):
    if isinstance(sa_type, JSON):
        return "json"
    if isinstance(sa_type, Boolean):
        return "bool"
    if isinstance(sa_type, DateTime):
        return "datetime"
    if isinstance(sa_type, (Float, Numeric)):
        return "float"
    if isinstance(sa_type, Integer):
        return "int"
    return "text"


def coerce(value, kind):
    """Convert a value to the column's kind. Raises ValueError/TypeError if impossible."""
    if value is None:
        return None
    if kind == "text":
        return json.dumps(value) if isinstance(value, (dict, list)) else str(value)
    if kind == "json":
        if isinstance(value, (dict, list)):
            return value
        parsed = json.loads(value) if isinstance(value, str) else None
        if isinstance(parsed, (dict, list)):
            return parsed
        raise ValueError("not JSON")
    if kind == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise ValueError("not a bool")
    if kind == "int":
        if isinstance(value, bool):
            raise ValueError("bool is not int")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            return int(value.strip())
        raise ValueError("not an int")
    if kind == "float":
        if isinstance(value, (bool, dict, list)):
            raise ValueError("not a float")
        return float(value)
    if kind == "datetime":
        if isinstance(value, (str, datetime)):
            return parse_datetime(value)
        raise ValueError("not a datetime")
    raise ValueError(f"unknown kind {kind}")
