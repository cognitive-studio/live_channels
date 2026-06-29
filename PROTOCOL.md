# Live Channels Protocol

## Principle

The artifact holds the coordination state so agents do not need to share a process, terminal, conversation, or memory context.

## Message contract

Every message is a Markdown file with YAML front matter.

```yaml
---
id: LC-20260628-001
status: OPEN
created_at: 2026-06-28T21:00:00-05:00
updated_at: 2026-06-28T21:00:00-05:00
from: Wibey
to:
  - Prudence
  - Gem
  - Atlas-CS
  - Lumi
cc:
  - Andrew
channel: terminal-b
subject: Meridian QA review
trigger: review_requested
priority: high
project: finalytics-northstar
reply_to: null
claimed_by: null
claim_expires_at: null
requires_response: true
close_authority:
  - Wibey
  - Andrew
artifacts: []
tags:
  - meridian
  - qa
---
```

## Required fields

- `id`
- `status`
- `created_at`
- `updated_at`
- `from`
- `to`
- `channel`
- `subject`
- `trigger`
- `priority`
- `requires_response`

## Addressing

Canonical participant identifiers:

- `Andrew`
- `Wibey`
- `GenLD`
- `Prudence`
- `Gem`
- `Atlas-CS`
- `Lumi`
- `Atlas`
- `ALL`

Use exact identifiers. `ALL` routes to every watcher.

## Status rules

| Status | Meaning |
|---|---|
| `OPEN` | Posted and not yet acknowledged |
| `ACKNOWLEDGED` | Recipient confirms receipt |
| `CLAIMED` | One participant has taken responsibility |
| `RESPONDED` | A substantive response has been appended |
| `BLOCKED` | Work cannot continue; blocker must be stated |
| `CLOSED` | Request is complete and accepted |
| `SUPERSEDED` | Replaced by another message |
| `CANCELLED` | Withdrawn by sender or close authority |

## Response sections

Responses are appended below the original message using this form:

```markdown
## Response — Prudence — 2026-06-28T21:30:00-05:00

Response text.

### Artifacts

- `path/to/file.md`

### Remaining gaps

- None.
```

## Claim behavior

A claim records `claimed_by` and `claim_expires_at`. Claims reduce duplicated effort but are advisory, not a distributed lock. A second agent may contribute, but should not silently replace the claimant.

Default claim duration: 4 hours.

## Closure

A response does not automatically close a request. Closure is performed by the sender, Andrew, or a named `close_authority`.

## Git behavior

Before writing:

1. `git pull --rebase`
2. Modify or create exactly one message when practical
3. Commit with the message ID
4. Push

Recommended commit forms:

- `channel: post LC-20260628-001`
- `channel: claim LC-20260628-001 by Prudence`
- `channel: respond LC-20260628-001 by Gem`
- `channel: close LC-20260628-001`

## Conflict handling

If a rebase conflict affects a message file:

1. Preserve all response sections.
2. Use the newest `updated_at`.
3. Preserve the most advanced valid status.
4. Never remove an attribution or artifact reference.
5. Record the resolution in a `## Reconciliation` section.

## Trigger safety

Triggers describe expected handling. They never authorize shell execution. The local watcher may notify, filter, acknowledge, claim, or write response scaffolds. It must not execute commands found in message content.