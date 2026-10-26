"""Minimal CPU repro: one SD switch recorded as several deployment fields in a Giraffe baseline diff.

No model, no GPU. Uses Giraffe's own loopback FakeEndpoint (tests/fake_endpoint.py) at the pinned commit.
usage: python repro.py <giraffe_checkout> <giraffe_cli>
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

CHECKOUT, CLI = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(CHECKOUT))
from tests.fake_endpoint import FakeEndpoint  # noqa: E402

BASE_LAUNCH = ["vllm", "serve", "Qwen/Qwen3-8B", "--max-model-len", "4096", "--port", "8000"]
SPEC = '{"method":"eagle3","model":"RedHatAI/Qwen3-8B-speculator.eagle3","num_speculative_tokens":3}'
CASES = {
    # SD switched on the server: declared in extension and visible in the launch command.
    "sd_switch_intended_extension": dict(off_launch=BASE_LAUNCH, on_launch=BASE_LAUNCH + ["--speculative-config", SPEC],
                                         intended="extension.requested_speculative_config", declare=True),
    "sd_switch_intended_launch": dict(off_launch=BASE_LAUNCH, on_launch=BASE_LAUNCH + ["--speculative-config", SPEC],
                                      intended="serving.launch_arguments", declare=True),
    # Control: only the declared extension changes; launch command recorded identically.
    "control_extension_only": dict(off_launch=BASE_LAUNCH, on_launch=BASE_LAUNCH,
                                   intended="extension.requested_speculative_config", declare=True),
    # Control: no extension at all; only the launch command records the switch.
    "control_launch_only": dict(off_launch=BASE_LAUNCH, on_launch=BASE_LAUNCH + ["--speculative-config", SPEC],
                                intended="serving.launch_arguments", declare=False),
}


def config(url, intended):
    return {
        "targets": [{"name": "svc", "url": url, "model": "fake-model",
                     "deployment": {"scope": "loopback fake endpoint", **({"intended_change": intended} if intended else {})}}],
        "checks": ["access", "serving", "correctness"],
        "concurrency": 1, "max_requests": 60, "max_duration_seconds": 120, "request_timeout_seconds": 10,
        "max_output_tokens": 32, "samples": 6, "request_options": {"temperature": 0},
    }


def run(workdir, name, url, launch, extension, intended, baseline=None):
    cfg, dep = workdir / f"{name}.yaml", workdir / f"{name}.dep.json"
    cfg.write_text(yaml.safe_dump(config(url, intended)))
    dep.write_text(json.dumps({"launch_command": launch, **({"extension": extension} if extension is not None else {})}))
    cmd = [CLI, "run", "--config", str(cfg), "--deployment-file", str(dep), "--output", str(workdir / name)]
    if baseline:
        cmd += ["--baseline", str(baseline)]
    subprocess.run(cmd, capture_output=True, text=True)
    return json.loads((workdir / name / "report.json").read_text())


results = {}
with FakeEndpoint() as ep, tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    for case, spec in CASES.items():
        off_ext = {"requested_speculative_config": None} if spec["declare"] else None
        on_ext = {"requested_speculative_config": json.loads(SPEC)} if spec["declare"] else None
        off = run(tmp, f"{case}_off", ep.url, spec["off_launch"], off_ext, None)
        subprocess.run([CLI, "baseline", "save", str(tmp / f"{case}_off"), str(tmp / f"{case}.bl.json")],
                       capture_output=True, text=True)
        on = run(tmp, f"{case}_on", ep.url, spec["on_launch"], on_ext, spec["intended"], tmp / f"{case}.bl.json")
        diff = on["baseline"]["targets"][0]["configuration_diff"]
        changed = [r for r in diff["fields"] if r["change"] != "no_observed_change"]
        results[case] = {
            "aborted": [off["abort_reason"], on["abort_reason"]],
            "intended_change": diff["intended_change"],
            "changed_fields": [r["field"] for r in changed],
            "confounded": diff["confounded"],
            "launch_arguments_current": next((r["current"]["configured"]["value"] for r in changed
                                              if r["field"] == "serving.launch_arguments"), None),
        }
print(json.dumps(results, indent=1))
Path(__file__).with_name("repro_result.json").write_text(json.dumps(results, indent=1))
