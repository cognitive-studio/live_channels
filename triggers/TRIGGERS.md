# Canonical Triggers

Triggers are declarative routing signals. They must never contain or authorize executable code.

| Trigger | Expected handling | Default urgency |
|---|---|---|
| `review_requested` | Inspect supplied artifact or claim and return findings | normal |
| `architecture_review_requested` | Pressure-test architecture, boundaries, authority, and failure modes | high |
| `design_system_review_requested` | Review component, design-system, adapter, and certification implications | normal |
| `implementation_requested` | Claim, implement, test, and return commit plus limitations | high |
| `verification_requested` | Independently test an implementation or assertion | high |
| `evidence_requested` | Locate and return evidence with provenance | normal |
| `synthesis_requested` | Reconcile multiple findings into a coherent artifact | normal |
| `decision_required` | Present decision, options, recommendation, and consequences to the named authority | high |
| `clarification_required` | Resolve an ambiguity that materially blocks work | high |
| `handoff_ready` | Receiver should acknowledge, verify context, and claim or decline | high |
| `status_update` | Informational; acknowledgment optional | low |
| `stop_the_line` | Pause affected work and notify all relevant participants | critical |
| `breaking_change` | Review downstream impact before integration | critical |
| `protocol_changed` | Reload channel protocol or operating instructions | high |
| `decision_announced` | Update affected work to reflect a ratified decision | high |
| `closure_requested` | Sender or close authority should inspect response and close or reopen | normal |

## Trigger requirements

A message using `stop_the_line`, `breaking_change`, or `decision_required` must include:

- the affected scope
- the evidence or uncertainty
- the consequence of proceeding
- the authority needed to resolve it

A message using `implementation_requested` must include:

- target repository or artifact
- requested outcome
- acceptance criteria
- test expectations
- whether direct commits are authorized

A message using `verification_requested` should be assigned to a participant other than the original implementer whenever practical.