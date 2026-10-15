"""Validate the preserved legacy source without starting a bot."""

import argparse
import ast
from contextlib import closing
import hashlib
import json
from pathlib import Path, PurePosixPath
import sqlite3
import sys


def check(root):
    manifest = json.loads(
        (root / "docs/legacy-manifest.json").read_text(encoding="utf-8")
    )
    if manifest.get("schema") != "farm.legacy-baseline.v1":
        raise ValueError("Unsupported baseline manifest schema")
    baseline = (root / manifest["destination"]).resolve()
    if not baseline.is_relative_to(root.resolve()):
        raise ValueError("Baseline destination escapes repository")
    errors = []
    expected = set()
    python_count = 0
    json_count = 0
    for entry in manifest["files"]:
        name = entry["path"]
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid manifest path")
        if name in expected:
            raise ValueError("Duplicate manifest path")
        expected.add(name)
        path = (baseline / name).resolve()
        if not path.is_relative_to(baseline):
            raise ValueError("Manifest path escapes baseline")
        if not path.is_file():
            errors.append({"path": name, "error": "missing file"})
            continue
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != entry["copied_sha256"]:
            errors.append({"path": name, "error": "SHA-256 mismatch"})
        if len(content) != entry["bytes"]:
            errors.append({"path": name, "error": "size mismatch"})
        if path.suffix == ".py":
            python_count += 1
            try:
                ast.parse(content, filename=name, feature_version=(3, 10))
            except SyntaxError as exc:
                errors.append(
                    {"path": name, "error": "syntax", "line": exc.lineno}
                )
        if path.suffix == ".json":
            json_count += 1
            try:
                json.loads(content)
            except (ValueError, UnicodeError):
                errors.append({"path": name, "error": "invalid JSON"})
    actual = {
        path.relative_to(baseline).as_posix()
        for path in baseline.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }
    for name in sorted(actual - expected):
        errors.append({"path": name, "error": "unmanifested file"})
    catalogues = []
    for name in ("plant.db", "plant-test.db"):
        path = baseline / "resource/db" / name
        with closing(
            sqlite3.connect(
                path.resolve().as_uri() + "?mode=ro", uri=True
            )
        ) as connection:
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
            tables = sorted(
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            )
        if integrity != "ok" or tables != ["plant", "sqlite_sequence"]:
            errors.append({"path": name, "error": "unexpected catalogue"})
        catalogues.append(
            {"name": name, "quick_check": integrity, "tables": tables}
        )
    return {
        "status": "passed" if not errors else "failed",
        "files": len(expected),
        "python_syntax_files": python_count,
        "json_files": json_count,
        "catalogues": catalogues,
        "errors": errors,
        "scope": "integrity and syntax only; no host or gameplay verified",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    try:
        result = check(args.root.resolve())
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        result = {"status": "failed", "error_type": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
