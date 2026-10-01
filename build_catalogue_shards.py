#!/usr/bin/env python3
"""Generate cache-friendly catalogue shards from the canonical products.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "products.json"
OUT = ROOT / "catalogue"
SHARD_SIZE = 75

data = json.loads(DATA.read_text(encoding="utf-8"))
products = data.get("products", [])
OUT.mkdir(parents=True, exist_ok=True)

for old in OUT.glob("products-*.json"):
    old.unlink()

shards = []
for start in range(0, len(products), SHARD_SIZE):
    chunk = products[start:start + SHARD_SIZE]
    number = start // SHARD_SIZE + 1
    filename = f"products-{number:02d}.json"
    (OUT / filename).write_text(
        json.dumps(
            {"schemaVersion": 1, "shard": number, "products": chunk},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    shards.append({
        "file": f"catalogue/{filename}",
        "start": start + 1,
        "end": start + len(chunk),
        "count": len(chunk),
    })

manifest = {
    "schemaVersion": 1,
    "generatedFrom": "products.json",
    "totalProducts": len(products),
    "shardSize": SHARD_SIZE,
    "shards": shards,
}
(OUT / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"Generated {len(shards)} catalogue shards for {len(products)} products.")
