# Stage 3E: Rate History / Sparkline

**Baseline:** Stage 3D at commit 5ee642a  
**Implementation SHA:** (to be updated after commit)  
**Branch:** feat/stage-3e-rate-history

## Architecture

Stage 3E adds bounded short-term rate history and sparkline visualization without modifying the existing ETW collection kernel.

### Data Flow

`
MonitorSnapshot
    ↓
UiController._on_snapshot_ready()
    ↓
aggregate_application_network()
    ↓
RateHistoryStore.record(key, upload_bps, download_bps)
    ↓
MicroProjection.frame() fetches history
    ↓
WidgetFrame.rate_history
    ↓
Sparkline widget renders upload/download lines
`

### Components

- **RateHistoryStore** (src/net_monitor/ui/rate_history.py): Pure logic module, no Qt/ETW dependencies
- **Sparkline** (src/net_monitor/ui/sparkline.py): 60x20px QWidget, upload green (#7dd3a8), download blue (#6ba4d9)
- **Integration**: UiController creates RateHistoryStore, passes to MicroProjection
- **UI**: MicroWindow and ApplicationCard both display sparklines

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| duration_seconds | 60.0 | Target history window |
| expected_interval_seconds | 0.5 | Nominal sampling interval (500ms heartbeat) |
| max_samples | 120 | Hard limit per application (derived from duration / interval) |
| max_applications | 32 | Hard cap on tracked applications |
| eviction_policy | LRU | Least-recently-seen evicted first |

## Rate Semantics

### None vs 0.0

- **None** = unknown/unavailable rate (UNKNOWN != 0, STALE != 0, FAILED != 0)
- **0.0** = confirmed measured zero rate

None values are preserved in the history and displayed as gaps in the sparkline, not as zero values.

### Time-Based Pruning

- Samples older than duration_seconds are pruned on read
- Uses monotonic timestamps (no wall clock dependency)
- get_series(key, now=current_time) performs lazy pruning
- Application keys persist until LRU eviction, but their history becomes empty after expiry

### Timestamp Ordering

- Out-of-order timestamps are rejected to maintain monotonic time axis
- Duplicate timestamps are accepted
- Ensures deterministic, testable behavior

## History Ownership

History is keyed by **application key** (same as existing aggregation):
- xe:<normalized_path> for trusted executables
- process:<pid>:<create_time> for UNKNOWN processes

PID changes within the same trusted application key do not create a new series.

## UNKNOWN and STALE Handling

- **UNKNOWN application identity**: Processes without executable paths get distinct keys. Each is isolated, never merged.
- **UNKNOWN rate value**: Represented as None, displayed as gap in sparkline
- **STALE**: Application keys persist until LRU eviction, but their sample history is pruned by time window

## Sparkline Rendering

- **Size**: 60x20 logical pixels (fixed)
- **Colors**: Upload #7dd3a8 (green), Download #6ba4d9 (blue)
- **Scaling**: Y-axis auto-scales to peak value across both series
- **None handling**: Creates gaps in the line (not drawn as zero)
- **No axes, no labels**: Just the two lines
- **Performance**: QPainter.drawLine, antialiased, no external dependencies

## Performance Boundaries

- **No new threads**: Consumes existing SamplingWorker heartbeat
- **No new collectors**: Uses existing MonitorSnapshot
- **No new ETW sessions**: Reuses existing session
- **No new timers**: Sparkline repaints on frame update only
- **Memory**: Bounded by max_samples (120) × max_applications (32) = 3840 RateSample objects max

## Architecture Impact

**Modified files:**
- src/net_monitor/ui/controller.py: +18 lines (create store, record rates)
- src/net_monitor/ui/micro_model.py: +12 lines (add rate_history field to WidgetFrame, fetch from store)
- src/net_monitor/ui/micro_window.py: +9 lines (add Sparkline widgets to MicroWindow and ApplicationCard)

**New files:**
- src/net_monitor/ui/rate_history.py: RateSample, RateSeries, RateHistoryStore
- src/net_monitor/ui/sparkline.py: Sparkline QWidget
- tests/test_rate_history.py: 13 tests covering bounded semantics

**NOT modified (frozen architecture):**
- src/net_monitor/collectors/ — no changes
- src/net_monitor/services/monitor_service.py — no changes
- src/net_monitor/ui/sampling_worker.py — no changes
- ETW session lifecycle — no changes

## Test Results

`
$ python -m pytest tests/test_rate_history.py -v
13 passed
`

All 13 tests pass:
- None rates preserved as None (UNKNOWN != 0)
- 0.0 distinct from None
- Time-based pruning (60s window)
- max_samples=120 hard limit
- Timestamp ordering (rejects out-of-order)
- Application key isolation
- LRU eviction
- LRU refresh on access
- get_series with explicit now parameter
- Unknown key returns empty tuple
- clear() removes all history
- Mixed None and real rates

**Full test suite:** 256 passed, 2 pre-existing failures (font/environment, not Stage 3E)

**compileall:** All modified files compile successfully

## Persistence

**No SQLite, no persistence.** Rate history is in-memory only and resets on application restart.

## Known Limitations

1. **Physical desktop verification not completed**: Sparkline rendering tested via compileall and unit tests, but not visually verified on a real Windows 11 desktop with live ETW data.
2. **Font environment**: 2 pre-existing test failures related to Qt font configuration in offscreen mode (not caused by Stage 3E).
3. **Editable install**: net-monitor.exe launcher not present in test environment (pre-existing).

## CI Branch Filter

No changes required to .github/workflows/ci.yml or .github/workflows/etw-experiment.yml. The new branch feat/stage-3e-rate-history will be picked up automatically by the default branch patterns.

## Git Status

- Branch: feat/stage-3e-rate-history
- Baseline: 5ee642a (Stage 3D)
- Implementation SHA: (to be updated after commit)
- Remote: (to be updated after push)
