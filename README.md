# Giraffe on vLLM with and without EAGLE3: report bundle (A-001, A-002)

Evidence from two existing single-session runs on 2026-10-20: raw Giraffe reports and the `/metrics` scrapes taken around each run. No new runs were made for this bundle. The originals are kept unchanged, and every difference from them is listed under "Changes from the originals".
`verify_counters.py` recomputes every number below from these files (`python verify_counters.py` → `counters.json`).

## Setup

| | A-001 | A-002 |
|---|---|---|
| GPU | A100 80GB PCIe (SM80) | H100 NVL (SM90) |
| Giraffe | `0dust/giraffe@83756d3e00` | same |
| Server | `vllm/vllm-openai:v0.30.0`, Qwen/Qwen3-8B@`b968826d9c`, max-model-len 4096, seed 0 | same |
| Arms | A-OFF: no speculative config · A-FIXED: EAGLE3 `RedHatAI/Qwen3-8B-speculator.eagle3@08610ffa01`, K=3 | same |
| Giraffe config | concurrency 1 and 4, 128 output tokens, `max_requests` 160, no latency limits | `max_requests` 320; A-FIXED c1 compared with `--baseline` against A-OFF c1 |

Giraffe ran in a separate venv on the same machine and reached the server over loopback. Single replica, no other traffic.

## Counters from raw `/metrics` (delta between the scrapes before and after each run)

| run | Giraffe overall | requests (completed / cancelled / timeout) | drafts | draft tokens | accepted | accepted per position 0/1/2 | generation tokens |
|---|---|---|---|---|---|---|---|
| A-001 A-OFF c1 | inconclusive | 156 / 1 / 1 | — | — | — | — | 5,235 |
| A-001 A-OFF c4 | inconclusive | 158 / 1 / 1 | — | — | — | — | 5,199 |
| A-001 A-FIXED c1 | inconclusive | 158 / 1 / 1 | 1,455 | 4,365 | 3,811 | 1,393 / 1,259 / 1,159 | 5,288 |
| A-001 A-FIXED c4 | inconclusive | 158 / 1 / 1 | 1,447 | 4,341 | 3,782 | 1,393 / 1,267 / 1,122 | 5,212 |
| A-002 A-OFF c1 | inconclusive | 255 / 1 / 1 | — | — | — | — | 7,136 |
| A-002 A-OFF c4 | inconclusive | 318 / 1 / 1 | — | — | — | — | 12,173 |
| A-002 A-FIXED c1 | fail (baseline) | 255 / 1 / 1 | 1,996 | 5,988 | 5,042 | 1,934 / 1,604 / 1,504 | 7,157 |
| A-002 A-FIXED c4 | inconclusive | 318 / 1 / 1 | 3,376 | 10,128 | 8,806 | 3,236 / 2,916 / 2,654 | 12,194 |

- "—": the `vllm:spec_decode_*` families are absent from the A-OFF scrapes.
- In every A-FIXED run, draft tokens / drafts = 3.0: the average proposal length over the run window matches the configured K=3. This does not show that every step proposed exactly 3 tokens. The engine log lines in `*/A-FIXED/engine_spec_lines.txt` show `SpeculativeConfig(method='eagle3', …, num_spec_tokens=3)`.
- The cancelled and timeout requests are Giraffe's intended `client_cancel` and `client_deadline` probes.
- Every run stopped at the request cap except A-002 c1. A-001 A-OFF c1 stopped at 158 of 160 because the next scenario did not fit in the remaining budget.

**What the reports contain.** In all eight reports, serving telemetry (profile `vllm-v1`) holds 8 families: KV-cache usage, running, waiting, preemptions, prefix-cache hits and queries, TTFT sum and count. None of the reports contains `spec_decode`. `--speculative-config` appears as `--speculative-config=[redacted]` in `serving.launch_arguments`.

## A-002 baseline comparison (A-FIXED c1 against A-OFF c1)

Configuration diff, `intended_change: extension.requested_speculative_config`, `confounded: true`:

| field | change |
|---|---|
| `extension.arm` | changed (A-OFF → A-FIXED) |
| `extension.note` | removed |
| `extension.requested_speculative_config` | changed (null → eagle3, K=3) |
| `extension.status` | added |
| `serving.launch_arguments` | changed (`--speculative-config=[redacted]` appended) |

`extension.arm`, `note` and `status` are our own bookkeeping. With them removed from both snapshots, `deployment_diff()` from the pinned source still returns two changed fields and `confounded: true` (`A-002-h100/reanalysis/`). A CPU reproduction with Giraffe's fake endpoint is in `repro_sd_intended_change/`.

Comparisons: 338 in total, 215 pass, 115 inconclusive (69 with fewer than 5 samples, 46 whose sample variation crosses the 20% threshold), and 8 fail. All 8 failures are `first_output_ms`, from three scenarios counted under several checks:

| scenario | counted under checks | baseline → current median (ms) | worsening (95% interval) | samples |
|---|---|---|---|---|
| generation | access, first_output, generation, serving | 12.92 → 15.84 | +22.7% (20.1–24.8%) | 6 / 6 |
| warm | access, first_output, serving | 12.89 → 15.68 | +21.6% (20.4–24.3%) | 6 / 6 |
| recovery | recovery | 12.79 → 15.68 | +22.6% (21.0–26.5%) | 6 / 6 |

This is one session with a fixed arm order (OFF, then FIXED), so it is not a performance result. The cause of the TTFT difference was not investigated.

## Layout

```
A-00x-*/A-{OFF,FIXED}/c{1,4}/report.{json,html}   Giraffe reports
A-00x-*/A-{OFF,FIXED}/c{1,4}/giraffe.yaml         Giraffe config for that run
A-00x-*/A-{OFF,FIXED}/c{1,4}/metrics_{before,after}.prom
A-00x-*/A-{OFF,FIXED}/deployment.json             metadata passed to Giraffe
A-00x-*/A-{OFF,FIXED}/launch_argv.json            unredacted server command
A-00x-*/A-{OFF,FIXED}/engine_spec_lines.txt       SpeculativeConfig / Eagle3 lines from the server log
A-00x-*/env/                                      vLLM/torch versions, GPU model and driver
A-002-h100/reanalysis/                            recompute_diff.py / .json
repro_sd_intended_change/                         CPU reproduction (fake endpoint)
MANIFEST.json                                     sha256 of every file and of its source
```

`recompute_diff.py` expects the original layout (`remote/A-FIXED/giraffe_c1/report.json` is `A-FIXED/c1/report.json` here). The baseline file Giraffe saved is identical to `A-002-h100/A-OFF/c1/report.json`, so it is not duplicated.

## Changes from the originals

All changes are listed in `MANIFEST.json`:
- `run_location.hostname` in each `report.json` (an ephemeral container id) is replaced with `[redacted]`. The HTML reports do not contain it.
- The first comment line of each `giraffe.yaml` was reworded. No settings were changed.
- `engine_spec_lines.txt` is an excerpt of the server log.

The bundle leaves out full server logs, session logs, pip lists and the remote driver script. They hold machine paths and nothing that the numbers above depend on.
