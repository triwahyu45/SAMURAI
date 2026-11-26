"""
Samurai Engine Strict Schema Validator (JSON Schema Draft 2020-12).
Rejects invalid scene_spec.json with exact JSONPath errors; never silently fixes input.
"""
import argparse
import json
import sys
from pathlib import Path
from jsonschema import Draft202012Validator

DEFAULT_SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "scene_spec.schema.json"


def validate_file(spec_path: Path, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(spec), key=lambda e: list(e.absolute_path)):
        path = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
        errors.append(f"  - {path}: {err.message}")
    return errors


def main():
    ap = argparse.ArgumentParser(description="Validate scene_spec.json against Samurai Engine schema")
    ap.add_argument("spec", help="Path to scene_spec.json")
    ap.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Path to scene_spec.schema.json")
    args = ap.parse_args()

    spec_path = Path(args.spec)
    schema_path = Path(args.schema)
    if not spec_path.exists():
        print(f"FAIL: {spec_path} (file not found)")
        sys.exit(1)

    errors = validate_file(spec_path, schema_path)
    if errors:
        print(f"FAIL: {spec_path} ({len(errors)} schema error(s))")
        for line in errors:
            print(line)
        sys.exit(1)

    print(f"PASS: {spec_path}")


if __name__ == "__main__":
    main()
