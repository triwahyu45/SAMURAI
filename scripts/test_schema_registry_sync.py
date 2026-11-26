"""
Verify that layer type enums in schema/scene_spec.schema.json exactly match
LAYER_REGISTRY_TYPES declared in engine/samurai-core.js.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "scene_spec.schema.json"
CORE_JS = ROOT / "engine" / "samurai-core.js"


def main():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    schema_enums = {}
    for rule in schema.get("allOf", []):
        backend = rule["if"]["properties"]["meta"]["properties"]["renderer"]["const"]
        schema_enums[backend] = sorted(rule["then"]["properties"]["layers"]["items"]["properties"]["type"]["enum"])

    js_text = CORE_JS.read_text(encoding="utf-8")
    m = re.search(r"const\s+LAYER_REGISTRY_TYPES\s*=\s*(\{[\s\S]*?\});", js_text)
    if not m:
        print("FAIL: LAYER_REGISTRY_TYPES not found in samurai-core.js")
        sys.exit(1)

    raw = re.sub(r"//.*", "", m.group(1))
    raw = re.sub(r"([a-zA-Z0-9_]+)\s*:", r'"\1":', raw)
    raw = raw.replace("'", '"')
    raw = re.sub(r",\s*([\]}])", r"\1", raw)
    js_enums = {k: sorted(v) for k, v in json.loads(raw).items()}

    if schema_enums != js_enums:
        print("FAIL: Schema enums != samurai-core.js LAYER_REGISTRY_TYPES")
        print("  schema:", schema_enums)
        print("  js:    ", js_enums)
        sys.exit(1)

    print(f"PASS: schema enums == registry ({ {k: len(v) for k, v in schema_enums.items()} })")


if __name__ == "__main__":
    main()
