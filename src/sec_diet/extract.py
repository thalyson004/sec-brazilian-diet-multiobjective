"""Extract observed person-day consumption to a local JSON Lines file.

The output contains survey identifiers transformed into stable opaque hashes.
It has no nutrient or environmental coefficients and is ignored by Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

from .source_checks import consumption_lines, input_info
from .layout import MIN_RECORD_LENGTH, VALID_DAYS, code, field


def person_day_id(parts: tuple[str, ...]) -> str:
    return hashlib.sha256("|".join(parts).encode("ascii")).hexdigest()[:32]


def extract(pof: Path, output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    days: set[str] = set()
    with consumption_lines(pof) as lines, output.open("w", encoding="utf-8", newline="\n") as target:
        for raw_line in lines:
            counts["source_records"] += 1
            record = raw_line.rstrip(b"\r\n").decode("latin-1")
            if len(record) < MIN_RECORD_LENGTH:
                counts["short_records"] += 1
                continue
            quadro = field(record, "QUADRO")
            if quadro not in VALID_DAYS:
                counts["invalid_day_records"] += 1
                continue
            identity = tuple(field(record, name) for name in ("UF", "COD_UPA", "NUM_DOM", "NUM_UC", "COD_INFORMANTE", "QUADRO"))
            if any(not part for part in identity):
                counts["incomplete_identity_records"] += 1
                continue
            food = code(field(record, "V9001"))
            if food is None:
                counts["invalid_food_code_records"] += 1
                continue
            raw_quantity = field(record, "QTD")
            try:
                grams = float(raw_quantity)
            except ValueError:
                counts["invalid_quantity_records"] += 1
                continue
            if not math.isfinite(grams) or grams <= 0:
                counts["nonpositive_quantity_records"] += 1
                continue
            raw_hour = field(record, "V9015").upper().removesuffix("H").strip()
            hour = int(raw_hour) if raw_hour.isdigit() and 0 <= int(raw_hour) <= 23 else None
            identifier = person_day_id(identity)
            row = {
                "person_day_id": identifier,
                "day": int(VALID_DAYS[quadro]),
                "uf": identity[0],
                "food_code": food,
                "preparation_code": code(field(record, "COD_PREPARACAO_FINAL")),
                "tbca_identifier": field(record, "COD_TBCA") or None,
                "eating_occasion_code": field(record, "V9017") or None,
                "hour": hour,
                "quantity_g": grams,
            }
            target.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            counts["written_records"] += 1
            days.add(identifier)
    return {
        "schema_version": "1.0",
        "source": input_info(pof),
        "output": input_info(output),
        "counts": dict(sorted(counts.items())),
        "person_days": len(days),
        "method": "One output row per positive-quantity POF consumption record. Original eating-occasion and preparation codes are preserved. Blank preparation remains null. No six-meal remapping or coefficient substitution is applied.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pof", type=Path, required=True, help="Official Dados_20230713.zip or CONSUMO_ALIMENTAR.txt")
    parser.add_argument("--output", type=Path, required=True, help="Local JSONL output; keep outside version control")
    parser.add_argument("--manifest", type=Path, required=True, help="Aggregate manifest with input/output hashes and counts")
    args = parser.parse_args(argv)
    if not args.pof.is_file():
        parser.error(f"POF input not found: {args.pof}")
    if args.output.resolve() == args.manifest.resolve():
        parser.error("Output and manifest paths must differ")
    manifest = extract(args.pof, args.output)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {manifest['counts']['written_records']} records to {args.output}")
    print(f"Wrote aggregate manifest to {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
