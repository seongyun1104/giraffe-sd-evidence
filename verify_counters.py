"""Recompute the run summaries in README.md from the files in this bundle.

usage: python verify_counters.py [bundle_dir]   # writes counters.json next to this script
"""
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
FAMILIES = ("spec_decode_num_drafts_total", "spec_decode_num_draft_tokens_total",
            "spec_decode_num_accepted_tokens_total", "generation_tokens_total")


def prom(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        m = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+(\S+)", line)
        if m and not line.startswith("#"):
            out[(m.group(1), m.group(2) or "")] = float(m.group(3))
    return out


def delta(before, after, family):
    keys = [k for k in after if k[0] == "vllm:" + family]
    return sum(after[k] - before.get(k, 0) for k in keys) if keys else None


def per_position(before, after):
    out = {}
    for k in after:
        if k[0] == "vllm:spec_decode_num_accepted_tokens_per_pos_total":
            out[re.search(r'position="(\d+)"', k[1]).group(1)] = after[k] - before.get(k, 0)
    return dict(sorted(out.items())) or None


def run(d, c):
    r = json.loads((d / f"c{c}" / "report.json").read_text())
    b, a = prom(d / f"c{c}" / "metrics_before.prom"), prom(d / f"c{c}" / "metrics_after.prom")
    target = next(iter(r["observations"]["targets"].values()))
    families = sorted({s["name"] for snap in target["serving_telemetry"]["snapshots"] for s in snap["samples"]})
    rec = {
        "overall": r["overall"],
        "abort_reason": r["abort_reason"],
        "wall_seconds": round((datetime.fromisoformat(r["finished_at"])
                               - datetime.fromisoformat(r["started_at"])).total_seconds(), 1),
        "requests": dict(Counter(q["status"] for q in r["requests"])),
        "checks": {ch["id"]: ch["status"] for ch in r["checks"]},
        "raw_metrics_delta": {f: delta(b, a, f) for f in FAMILIES},
        "accepted_per_position": per_position(b, a),
        "report_telemetry_families": families,
        "report_mentions_spec_decode": "spec_decode" in json.dumps(r),
    }
    if r.get("baseline"):
        t = r["baseline"]["targets"][0]
        cd = t["configuration_diff"]
        rec["baseline"] = {
            "status": t["status"],
            "changed_fields": {f["field"]: f["change"] for f in cd["fields"] if f["change"] != "no_observed_change"},
            "intended_change": cd["intended_change"],
            "confounded": cd["confounded"],
            "comparisons": dict(Counter(x["status"] for x in t["comparisons"])),
            "failed": [{k: x[k] for k in ("check", "scenario", "metric", "baseline", "current", "worsening",
                                          "worsening_interval_95", "baseline_samples", "current_samples")}
                       for x in t["comparisons"] if x["status"] == "fail"],
        }
    return rec


result = {f"{g}/{arm}/c{c}": run(ROOT / g / arm, c)
          for g in ("A-001-a100", "A-002-h100") for arm in ("A-OFF", "A-FIXED") for c in (1, 4)}
(ROOT / "counters.json").write_text(json.dumps(result, indent=1) + "\n")
for k, v in result.items():
    print(k, v["overall"], v["requests"], v["raw_metrics_delta"], v["accepted_per_position"])
