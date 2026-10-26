"""从只读旧作物库可复现导出独立目录，不访问玩家库或远程。"""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


def export(source: Path) -> bytes:
    source = source.resolve()
    with closing(sqlite3.connect(
        source.as_uri() + "?mode=ro", uri=True,
    )) as connection:
        connection.row_factory = sqlite3.Row
        rows = [
            dict(row) for row in connection.execute(
                "SELECT * FROM plant ORDER BY id"
            )
        ]
    if not rows or len({row["name"] for row in rows}) != len(rows):
        raise ValueError("Invalid or duplicate catalogue")
    document = {
        "schema": 1,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "plants": rows,
    }
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path,
        default=None,
    )
    parser.add_argument(
        "--output", type=Path,
        default=None,
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument('--legacy-reference', action='store_true')
    args = parser.parse_args()
    if args.check and args.source is None:
        from check_catalogue_bootstrap import check
        check(root)
        return
    if not args.legacy_reference or args.output is None:
        parser.error('Daily updates use sync_catalogue_bootstrap.py; '
                     'legacy export requires --legacy-reference --output')
    if args.source is None:
        args.source = root / 'legacy/zhenxun_plugin_farm/resource/db/plant.db'
    content = export(args.source)
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != content:
            raise SystemExit("Catalogue differs; regenerate it explicitly")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content)
    print("Catalogue checked" if args.check else "Catalogue exported")


if __name__ == "__main__":
    main()
