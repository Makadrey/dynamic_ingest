import argparse

from .db import get_engine
from .loader import describe_table, load_records, recent_runs
from .sources import generate_sample, read_records


def main(argv=None):
    p = argparse.ArgumentParser(prog="ingest", description="Schema-on-the-fly JSON -> Postgres loader")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write sample JSONL files")
    g.add_argument("--out", default="data")

    ld = sub.add_parser("load", help="load a .json/.jsonl file (or '-' for stdin)")
    ld.add_argument("path")
    ld.add_argument("--table", required=True)
    ld.add_argument("--key", help="column to upsert on (creates a unique index)")
    ld.add_argument("--batch-size", type=int, default=500)

    d = sub.add_parser("describe", help="show a table's columns")
    d.add_argument("--table", required=True)

    r = sub.add_parser("runs", help="show recent ingest runs")
    r.add_argument("--limit", type=int, default=10)

    args = p.parse_args(argv)

    if args.cmd == "generate":
        for name in generate_sample(args.out):
            print(f"wrote {args.out}/{name}")
        return

    engine = get_engine()
    if args.cmd == "load":
        rep = load_records(engine, args.table, read_records(args.path),
                           key=args.key, batch_size=args.batch_size)
        print(f"Loaded {rep['loaded']}/{rep['received']} rows into '{rep['table']}' "
              f"(rejected: {rep['rejected']})")
        if rep["columns_added"]:
            print("Columns added:", ", ".join(rep["columns_added"]))
        for w in rep["warnings"]:
            print("  warning:", w)
    elif args.cmd == "describe":
        for name, typ in describe_table(engine, args.table):
            print(f"{name:<16}{typ}")
    elif args.cmd == "runs":
        for row in recent_runs(engine, args.limit):
            print(f"#{row.run_id} {row.table_name:<10} {row.status:<6} "
                  f"loaded={row.rows_loaded}/{row.rows_received} rejected={row.rows_rejected} "
                  f"new_cols={len(row.columns_added or [])}")


if __name__ == "__main__":
    main()
