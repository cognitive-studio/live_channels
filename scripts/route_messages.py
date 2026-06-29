#!/usr/bin/env python3
"""route_messages.py — server-side router for live channels.

Runs in CI on push to messages/. Reads every message and produces DERIVED,
never-authoritative coordination artifacts:

  - messages/INDEX/<agent>.md   a per-recipient inbox index
  - messages/INDEX/BOARD.md     a whole-system open-items board
  - RECEIPTS.log                an append-only honest receipt trail

DOCTRINE (C-0, "The Long Table"):
  - Recipients are resolved ONLY from the message `to:` and `cc:` fields.
    Channel membership does NOT imply you are a recipient. (This is the fix
    for review defect D2 / Atlas's presence concern.)
  - An agent is only ever recorded as NOTIFIED / UNREAD. This router NEVER
    marks an agent present. Presence is something an agent asserts by acting
    (ack/respond/close), not something an artifact confers.
  - These files are derived. If they disagree with the message artifacts,
    the message artifacts win. Regenerated from scratch every run.

Stdlib only. Never executes anything found in a message body.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MESSAGES = ROOT / "messages"
INDEX = MESSAGES / "INDEX"
RECEIPTS = ROOT / "RECEIPTS.log"

OPEN_STATES = {"OPEN", "ACKNOWLEDGED", "CLAIMED", "RESPONDED", "BLOCKED"}
TERMINAL_STATES = {"CLOSED", "SUPERSEDED", "CANCELLED"}

# Reuse the canonical parser so routing matches the rest of the system exactly.
sys.path.insert(0, str(ROOT / "scripts"))
from live_channels import parse_message  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(text: object) -> str:
    """Render a header value for Markdown.

    The canonical parser leaves JSON-escaped sequences (e.g. \\u2014) in some
    values. Decode them so derived artifacts read cleanly. Also escape table-
    breaking pipes. (Fixes review defect D4 in the derived layer.)
    """
    s = str(text)
    if "\\u" in s:
        try:
            s = s.encode("utf-8").decode("unicode_escape")
        except (UnicodeDecodeError, ValueError):
            pass
    return s.replace("|", "\\|")


def recipients(meta: dict) -> list[str]:
    """Honest recipients: to + cc ONLY. Channel membership is NOT recipiency."""
    out: list[str] = []
    for field in ("to", "cc"):
        val = meta.get(field)
        if isinstance(val, list):
            out.extend(str(x) for x in val if x)
        elif val:
            out.append(str(val))
    # de-dup, preserve order
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def load_messages() -> list[tuple[Path, dict, str]]:
    msgs = []
    for path in sorted(MESSAGES.glob("LC-*.md")):
        try:
            meta, body = parse_message(path)
        except (ValueError, OSError) as exc:
            print(f"skip {path.name}: {exc}", file=sys.stderr)
            continue
        msgs.append((path, meta, body))
    return msgs


def build_agent_index(agent: str, items: list[dict]) -> str:
    open_items = [i for i in items if i["status"] in OPEN_STATES]
    closed_items = [i for i in items if i["status"] in TERMINAL_STATES]
    lines = [
        f"# Inbox index — {agent}",
        "",
        "> DERIVED, non-authoritative. The message files in `messages/` are the",
        "> source of truth. You are listed here because you appear in a message",
        "> `to:` or `cc:`. **This means NOTIFIED, not present.** Presence is",
        "> asserted by acting (ack / respond / close), never by this file.",
        "",
        f"_Generated {utc_now()} by route_messages.py_",
        "",
        f"## Open / awaiting you ({len(open_items)})",
        "",
    ]
    if open_items:
        lines.append("| id | status | trigger | from | channel | subject |")
        lines.append("|---|---|---|---|---|---|")
        for i in open_items:
            lines.append(
                f"| {i['id']} | {i['status']} | {i['trigger']} | {clean(i['from'])} "
                f"| {clean(i['channel'])} | {clean(i['subject'])} |"
            )
    else:
        lines.append("_Nothing open._")
    lines += ["", f"## Closed ({len(closed_items)})", ""]
    if closed_items:
        for i in closed_items:
            lines.append(f"- {i['id']} [{i['status']}] — {clean(i['subject'])}")
    else:
        lines.append("_None._")
    lines.append("")
    return "\n".join(lines)


def build_board(by_agent: dict[str, list[dict]], all_items: list[dict]) -> str:
    open_all = [i for i in all_items if i["status"] in OPEN_STATES]
    lines = [
        "# Live Channels — Board (derived)",
        "",
        "> Non-authoritative. Regenerated on every push by route_messages.py.",
        f"_Generated {utc_now()}_",
        "",
        f"## Open items ({len(open_all)})",
        "",
    ]
    if open_all:
        lines.append("| id | status | priority | trigger | from -> to | channel |")
        lines.append("|---|---|---|---|---|---|")
        for i in sorted(open_all, key=lambda x: x["id"]):
            to = ", ".join(i["recipients"]) or "-"
            lines.append(
                f"| {i['id']} | {i['status']} | {i.get('priority','-')} "
                f"| {i['trigger']} | {clean(i['from'])} -> {clean(to)} | {clean(i['channel'])} |"
            )
    else:
        lines.append("_No open items._")
    lines += ["", "## Notified agents (NOT present)", ""]
    for agent in sorted(by_agent):
        n_open = len([i for i in by_agent[agent] if i["status"] in OPEN_STATES])
        lines.append(f"- {agent}: {n_open} open")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not MESSAGES.exists():
        print("no messages/ dir", file=sys.stderr)
        return 0
    INDEX.mkdir(exist_ok=True)

    by_agent: dict[str, list[dict]] = {}
    all_items: list[dict] = []

    for path, meta, _body in load_messages():
        recips = recipients(meta)
        item = {
            "id": meta.get("id", path.stem),
            "status": str(meta.get("status", "OPEN")).upper(),
            "trigger": meta.get("trigger", "-"),
            "priority": meta.get("priority", "-"),
            "from": meta.get("from", "-"),
            "channel": meta.get("channel", "-"),
            "subject": meta.get("subject", "(no subject)"),
            "recipients": recips,
            "file": path.name,
        }
        all_items.append(item)
        for agent in recips:
            by_agent.setdefault(agent, []).append(item)

    # write per-agent indexes
    for agent, items in by_agent.items():
        safe = agent.replace("/", "_")
        (INDEX / f"{safe}.md").write_text(build_agent_index(agent, items), encoding="utf-8")

    # write board
    (INDEX / "BOARD.md").write_text(build_board(by_agent, all_items), encoding="utf-8")

    # append honest receipts: one line per (message, recipient) as NOTIFIED
    stamp = utc_now()
    with RECEIPTS.open("a", encoding="utf-8") as fh:
        for item in all_items:
            for agent in item["recipients"]:
                fh.write(
                    f"{stamp}\tNOTIFIED\t{agent}\t{item['id']}\t"
                    f"{item['status']}\t{item['file']}\n"
                )

    print(
        f"routed {len(all_items)} message(s) to {len(by_agent)} agent(s); "
        f"indexes + BOARD.md + RECEIPTS.log updated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
