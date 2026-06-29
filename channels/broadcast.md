# Broadcast Channel

Use for information that must be visible across every runtime.

## Appropriate messages

- Stop-the-line findings
- Canonical decisions
- Protocol changes
- Cross-runtime handoffs
- Repository moves or renames
- Breaking schema changes
- Certification revocations
- Major Meridian phase transitions

## Not appropriate

- Routine implementation chatter
- Unverified speculation
- Large raw dumps without a stated request
- Messages addressed to only one agent

Broadcast requests should use `to: [ALL]` and one of:

- `stop_the_line`
- `decision_announced`
- `protocol_changed`
- `breaking_change`
- `handoff_ready`
- `status_update`
