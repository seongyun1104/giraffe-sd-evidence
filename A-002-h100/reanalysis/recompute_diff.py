"""Recompute Giraffe's configuration diff for A-002 with our own extension metadata removed.

Originals under ../remote are read only. Uses deployment_diff() from the pinned Giraffe source.
usage: python recompute_diff.py <giraffe_src_dir>
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from giraffe.deployment import deployment_diff  # noqa: E402

HERE = Path(__file__).resolve().parent
REMOTE = HERE.parent / "remote"
NOISE = ("extension.arm", "extension.note", "extension.status")
TARGET = "vllm-h100"


def deployment(report_path):
    return json.loads(Path(report_path).read_text())["observations"]["targets"][TARGET]["deployment"]


def strip(dep):
    dep = copy.deepcopy(dep)
    for key in NOISE:
        dep["fields"].pop(key, None)
    return dep


def summary(diff):
    return {
        "changed": [r["field"] for r in diff["fields"] if r["change"] != "no_observed_change"],
        "intended_change": diff["intended_change"],
        "confounded": diff["confounded"],
    }


current = deployment(REMOTE / "A-FIXED/giraffe_c1/report.json")
baseline = deployment(REMOTE / "A-OFF/giraffe_c1/report.json")
stored = json.loads((REMOTE / "A-FIXED/giraffe_c1/report.json").read_text())["baseline"]["targets"][0]
out = {
    "as_reported": summary(stored["configuration_diff"]),
    "recomputed_original": summary(deployment_diff(current, baseline)),
    "recomputed_without_our_metadata": summary(deployment_diff(strip(current), strip(baseline))),
    "launch_arguments": {
        "baseline": baseline["fields"]["serving.launch_arguments"]["configured"]["value"],
        "current": current["fields"]["serving.launch_arguments"]["configured"]["value"],
    },
}
(HERE / "recompute_diff.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
