#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result_emit.py -- assemble /app/output/result.json honestly and completely.

Reads the original case file (/input/case.json), extracts case_id and the
output_contract, and merges the agent's answers so that:
  * every field named in output_contract is present in the result
    (missing ones are set to null AND listed in `missing_contract_fields`);
  * case_id is always echoed;
  * status / sources / uncertainty / changes / artifacts are carried over
    verbatim from the answers file.

Usage:
  python result_emit.py --case /input/case.json \
      --answers answers.json --out /app/output/result.json

answers.json is written by the agent during the run and should contain the
contract fields plus the honesty block, e.g.:
{
  "status": "success | partial | failed",
  "<contract field>": ...,
  "sources":    [{"fact": "...", "origin": "file:line or page"}],
  "changes":    [{"file": "...", "before": "...", "after": "...", "reason": "..."}],
  "uncertainty":["..."],
  "artifacts":  ["output/main.tex", "output/main.pdf"]
}

Exit codes: 0 ok (contract complete); 1 ok but contract fields missing;
2 input files unreadable.
"""

import argparse
import json
import os
import sys


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        print("error: cannot read %s: %s" % (path, exc), file=sys.stderr)
        sys.exit(2)


def contract_fields(case):
    """Return list of required field names from the case's output_contract.

    Tolerates the common shapes: dict {field: spec}, list of names, list of
    {name: ...} dicts, or a nested {"fields": ...}.
    """
    oc = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(oc, dict) and "fields" in oc:
        oc = oc["fields"]
    if isinstance(oc, dict):
        return [k for k in oc.keys()]
    if isinstance(oc, list):
        names = []
        for item in oc:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                names.append(item.get("name") or item.get("field"))
        return [n for n in names if n]
    return []


def main():
    ap = argparse.ArgumentParser(description="assemble result.json")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out", default="/app/output/result.json")
    args = ap.parse_args()

    case = load_json(args.case)
    answers = load_json(args.answers)

    case_id = (case.get("case_id") or case.get("caseId") or case.get("id")
               or answers.get("case_id") or "unknown")

    result = {}
    missing = []
    fields = contract_fields(case)
    for field in fields:
        if field in answers:
            result[field] = answers[field]
        else:
            result[field] = None
            missing.append(field)

    # carry the honesty / traceability block and any extra answer keys
    for key in ("status", "summary", "sources", "changes", "uncertainty",
                "artifacts", "build_report", "limits", "notes"):
        if key in answers:
            result[key] = answers[key]
    for key, value in answers.items():
        if key not in result and key != "case_id":
            result[key] = value

    result["case_id"] = case_id
    result.setdefault("status", "partial" if missing else "success")
    if missing:
        result["missing_contract_fields"] = missing
        result.setdefault("uncertainty", [])
        if isinstance(result["uncertainty"], list):
            result["uncertainty"].append(
                "output_contract 字段缺失: %s" % ", ".join(missing))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    print(json.dumps({
        "written": os.path.abspath(args.out),
        "case_id": case_id,
        "contract_fields": len(fields),
        "missing_contract_fields": missing,
        "status": result["status"],
    }, ensure_ascii=False, indent=2))
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
