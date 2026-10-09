"""Read JSON records from .json, .jsonl, or stdin ('-'); generate sample data."""
import json
import logging
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("ingest")


def _read_lines(lines):
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            log.warning("line %d is not valid JSON, skipped", n)
            yield None  # counted as rejected by the loader


def read_records(path):
    if path == "-":
        return _read_lines(sys.stdin)
    p = Path(path)
    if p.suffix in (".jsonl", ".ndjson"):
        with p.open() as f:
            return list(_read_lines(f))
    data = json.loads(p.read_text())
    return data if isinstance(data, list) else [data]


def generate_sample(out_dir="data", seed=7):
    """3 daily files where the schema evolves, plus messy rows to show the guard rails."""
    rng = random.Random(seed)
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    types = ["page_view", "click", "purchase", "signup"]
    out = Path(out_dir)
    out.mkdir(exist_ok=True)

    def make(day, n, device=False, geo=False):
        rows = []
        for i in range(n):
            ts = base + timedelta(days=day, seconds=rng.randint(0, 86399))
            r = {"event_id": f"evt_{day}_{i:04d}", "userId": rng.randint(1, 50),
                 "Event Type": rng.choice(types), "timestamp": ts.isoformat(),
                 "amount": round(rng.uniform(1, 200), 2)}
            if device:
                r["device"] = rng.choice(["ios", "android", "web"])
                r["metadata"] = {"browser": rng.choice(["chrome", "safari"]),
                                 "version": rng.randint(90, 120)}
            if geo:
                r["country"] = rng.choice(["NG", "GH", "KE", "ZA"])
                r["is_premium"] = rng.random() < 0.3
                r["discount"] = round(rng.uniform(0, 0.3), 2)
            rows.append(r)
        return rows

    day1 = make(0, 200)
    day2 = make(1, 200, device=True)
    day3 = make(2, 200, device=True, geo=True)
    day3[0]["amount"] = "19.99"   # string -> coerced to float
    day3[1]["amount"] = "N/A"     # not convertible -> NULL + warning
    resent = [{"event_id": f"evt_1_{i:04d}", "amount": 999.0} for i in range(20)]  # upsert demo

    for name, rows, bad in [("events_day1", day1, False), ("events_day2", day2, False),
                            ("events_day3", day3 + resent, True)]:
        lines = [json.dumps(r) for r in rows]
        if bad:
            lines.insert(5, '{"event_id": "evt_broken", "amount": ')  # invalid JSON line
        (out / f"{name}.jsonl").write_text("\n".join(lines) + "\n")
    return sorted(p.name for p in out.glob("events_day*.jsonl"))
