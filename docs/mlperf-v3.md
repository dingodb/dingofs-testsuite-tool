# MLPerf Storage 3.0 runtime

Pinned upstream tag `v3.0`, package `3.0.46`, commit
`ce28a9888076eba5a58fdd93d1c0258bf27b7aa2`; matching DLIO `3.0.4`, commit
`edaf4bb3d6343ef2fb6b9f6dbafa6102032ae8bf`. Python 3.12 is required.

Native training uses `mlpstorage whatif training MODEL run file`.
Checkpointing uses `mlpstorage whatif checkpointing run file --model MODEL`.
KV cache uses the same revision's `kv_cache_benchmark/kv-cache.py` directly,
so a single user-selected workload runs instead of the compliance wrapper's
three-option sequence. These are internal comparisons, not official submissions.

KV storage capacity is a tier limit, not a promise about bytes written.
Checkpoint read runs prepare matching data before the measured read phase.
Training defaults remain ResNet50 / UNet3D / CosmoFlow; no model substitution.

The pinned source has one local patch: `mlperf-v3-custom-capacity.patch`.
Upstream CAP-01 uses nominal Llama sizes even for explicit `model.type=custom`.
The patch keeps the capacity gate but computes custom bytes per rank × ranks ×
write count. Official/named model behavior is unchanged. This patch is required
for small custom checkpoint tests on small filesystems.

The same patch records parsed KV `effective_config` in the native JSON. The
adapter checks it against the requested model, users, duration, tiers and path.
Checkpoint metadata and every rank must match the request. Custom checkpoint
bytes/bandwidth are normalized from DLIO's per-rank values to aggregate values;
the untouched native JSON remains attached. Training requires complete epoch
records and metric series. Runtime patch identity is recorded only after its
capacity calculation has been exercised successfully.

Examples (inside DTT, byte units for these CLI arguments):

```sh
dtt -t mlperf -s benchmark -m /mount -o /output --mlperf-scenario training --mlperf-model cosmoflow --file-count 4 --mlperf-epochs 1 --concurrency 1
dtt -t mlperf -s benchmark -m /mount -o /output --mlperf-scenario checkpointing --mlperf-model custom --checkpoint-size 16777216 --checkpoint-mode read --checkpoint-count 2 --concurrency 2
dtt -t mlperf -s benchmark -m /mount -o /output --mlperf-scenario kvcache --mlperf-model tiny-1b --runtime-seconds 5 --total-size 268435456 --concurrency 1
```

Legacy named-model entrypoints on v3 images route to this adapter, preserving
model, small/medium/explicit file counts, accelerator count and rounds. They
generate a fresh isolated dataset. Legacy auto/large sizing, dataset reuse,
multi-host and arbitrary extra parameters fail with a migration message; they
are not silently reduced to a small workload. Old v2 images keep their old
adapter. Guided larger-model runs require correspondingly large free space.
