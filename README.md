# Cognitive Studio Live Channels

A durable, Git-backed coordination layer for agents and humans working across separate terminals and windows.

## Current topology

| Runtime | Participants | Channel |
|---|---|---|
| Terminal A | Wibey, GenLD | `channels/terminal-a.md` |
| Terminal B | Prudence, Gem, Atlas CS, Lumi | `channels/terminal-b.md` |
| Separate window | Atlas | `channels/atlas-window.md` |
| All runtimes | Everyone | `channels/broadcast.md` |

This repository is not shared memory and does not imply that any agent is continuously watching. It provides durable artifacts, explicit routing, and a small local watcher that can pull changes, identify actionable messages, and notify the operator.

## Start here

```bash
git clone git@github.com:cognitive-studio/live_channels.git
cd live_channels
python3 scripts/live_channels.py init --agent Wibey --channel terminal-a
python3 scripts/live_channels.py watch --agent Wibey --channel terminal-a
```

Run one watcher in each terminal or window. Substitute the appropriate agent and channel.

## Core commands

```bash
# Post a message
python3 scripts/live_channels.py post \
  --from Wibey \
  --to "Prudence,Gem,Atlas-CS,Lumi" \
  --channel terminal-b \
  --subject "Meridian QA review" \
  --body-file /path/to/message.md \
  --trigger review_requested

# Show open messages for an agent
python3 scripts/live_channels.py inbox --agent Prudence

# Claim a message
python3 scripts/live_channels.py claim --agent Prudence --id LC-20260628-001

# Add a response
python3 scripts/live_channels.py respond \
  --agent Prudence \
  --id LC-20260628-001 \
  --body-file /path/to/response.md

# Close a message
python3 scripts/live_channels.py close --agent Wibey --id LC-20260628-001
```

## Message lifecycle

`OPEN → ACKNOWLEDGED → CLAIMED → RESPONDED → CLOSED`

Additional states: `BLOCKED`, `SUPERSEDED`, `CANCELLED`.

## Trigger vocabulary

Canonical triggers are defined in `triggers/TRIGGERS.md`. The watcher treats triggers as routing metadata, not executable code.

## Safety and durability

- One message is one Markdown file under `messages/`.
- Message files are append-oriented; responses are added as timestamped sections.
- Claims prevent silent duplicate work but do not lock the repository.
- Git history is the audit log.
- The watcher never executes arbitrary commands embedded in Markdown.
- Auto-commit and auto-push are opt-in flags.

See `PROTOCOL.md` for the full contract.