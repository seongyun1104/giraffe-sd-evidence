# One SD switch → two changed deployment fields (CPU repro)

Giraffe `83756d3e00`, loopback `tests/fake_endpoint.py`, no model or GPU.

`deployment_diff()` sets `confounded=True` when any changed field differs from the single `intended_change`.
When a speculative-decoding switch is recorded both as a declared `extension` value and in `launch_command`,
one switch produces two changed fields, so the run is confounded whichever field is named.

| case | recorded in | intended_change | changed fields | confounded |
|---|---|---|---|---|
| sd_switch_intended_extension | extension + launch | `extension.requested_speculative_config` | extension, `serving.launch_arguments` | **true** |
| sd_switch_intended_launch | extension + launch | `serving.launch_arguments` | extension, `serving.launch_arguments` | **true** |
| control_extension_only | extension | `extension.requested_speculative_config` | extension | false |
| control_launch_only | launch | `serving.launch_arguments` | `serving.launch_arguments` | false |

No run aborted. In the launch-only case the diff shows `--speculative-config=[redacted]`: the switch is visible, its value is not.

The same pattern appeared on a real endpoint (vLLM 0.30.0, Qwen3-8B ± EAGLE3 K=3, H100 NVL).
After removing three of our own bookkeeping fields from both snapshots, the recomputed diff still has exactly these two changed fields and `confounded=True` (`../A-002-h100/reanalysis/recompute_diff.json`).

```
python repro.py <giraffe checkout at 83756d3e00> <path to giraffe CLI>   # writes repro_result.json
```
