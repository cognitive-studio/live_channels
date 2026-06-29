# Channel Registry

| Channel | Participants | Purpose |
|---|---|---|
| `terminal-a` | Wibey, GenLD | Meridian execution, implementation inspection, Living Design and Northspark work |
| `terminal-b` | Prudence, Gem, Atlas-CS, Lumi | Engineering, strategy, architecture, implementation, synthesis |
| `atlas-window` | Atlas | Independent architecture review, pressure-testing, doctrine, synthesis |
| `broadcast` | Andrew and all agents | Cross-runtime announcements, shared decisions, stop-the-line notices |

## Routing rule

Messages live in `messages/`, not directly in these channel documents. The channel documents describe standing context and can carry a concise current-state summary.

## Trigger routing

- `review_requested` → named reviewers
- `implementation_requested` → Prudence, Wibey, GenLD, or explicitly named implementer
- `architecture_review_requested` → Atlas, Atlas-CS, Gem
- `design_system_review_requested` → GenLD, Wibey
- `evidence_requested` → Wibey, Lumi, or named researcher
- `decision_required` → Andrew and named decision owner
- `stop_the_line` → `ALL`
- `handoff_ready` → named receiver
- `status_update` → subscribers only

See `triggers/TRIGGERS.md`.