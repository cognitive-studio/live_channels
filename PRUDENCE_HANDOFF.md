# Prudence Handoff — Live Channels

## Objective

Operationalize and verify the Git-backed coordination layer for:

- Terminal A: Wibey + GenLD
- Terminal B: Prudence + Gem + Atlas-CS + Lumi
- Separate window: Atlas
- Shared broadcast channel

## Branch

`atlas/operationalize-live-channels`

## Start

```bash
git clone git@github.com:cognitive-studio/live_channels.git
cd live_channels
git checkout atlas/operationalize-live-channels
bash scripts/bootstrap.sh Prudence terminal-b
```

Then run:

```bash
python3 scripts/live_channels_ops.py doctor --strict
python3 scripts/live_channels_ops.py validate
python3 scripts/live_channels_ops.py board
```

## What Atlas added

- `scripts/live_channels_ops.py`
  - `validate`
  - `ack`
  - `block`
  - `board`
  - `doctor`
- `scripts/bootstrap.sh`
- message protocol, channels, triggers, and templates on `main`

## Requested Prudence work

1. Run a local smoke test.
2. Inspect `scripts/live_channels.py` and `scripts/live_channels_ops.py` for defects.
3. Create at least one test message and exercise:
   - post
   - inbox
   - acknowledge
   - claim
   - block or respond
   - close
4. Verify concurrent pull/rebase behavior from two local clones if practical.
5. Add automated tests for parser and lifecycle behavior.
6. Decide whether to merge the two CLIs or retain the companion architecture.
7. Review the addressing rule in `addressed_to()`. The current implementation includes channel members even when not explicitly named; confirm this is desired.
8. Review claim expiration behavior. Expiration is recorded but not yet automatically surfaced or released.
9. Review validation strictness for critical-trigger message bodies.
10. Return:
    - findings
    - fixes
    - commit references
    - remaining limitations
    - merge recommendation

## Acceptance criteria

- Clean bootstrap on macOS with Python 3.10+
- All Python files compile
- Message validation passes
- Lifecycle commands preserve existing response sections
- Git conflicts do not silently remove content
- No Markdown content is executed
- Local watcher state remains ignored
- Errors are actionable
- README commands match actual CLI behavior

## Design constraints

- The Markdown artifact is the durable state.
- Git is the transport and audit trail.
- Local watcher processes are disposable.
- No hidden shared memory is assumed.
- No daemon is required for correctness.
- No arbitrary shell execution from message content.
- Human ratification remains explicit.

## Known limitations

- Atlas could create and inspect repository files through GitHub, but could not perform a local clone in its execution environment because external DNS resolution was unavailable.
- The first true runtime validation therefore belongs to the terminal environment.
- This is coordination infrastructure, not autonomous multi-agent orchestration.
