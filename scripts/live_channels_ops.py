#!/usr/bin/env python3
"""Operational controls for Cognitive Studio Live Channels.

Companion to scripts/live_channels.py. Provides validation, acknowledgments,
blocking, status summaries, and environment diagnostics without adding external
dependencies or executing message content.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "scripts" / "live_channels.py"
REQUIRED_FIELDS = {
    "id",
    "status",
    "created_at",
    "updated_at",
    "from",
    "to",
    "channel",
    "subject",
    "trigger",
    "priority",
    "requires_response",
}
VALID_AGENTS = {
    "Andrew",
    "Wibey",
    "GenLD",
    "Prudence",
    "Gem",
    "Atlas-CS",
    "Lumi",
    "Atlas",
    "ALL",
}
VALID_CHANNELS = {"terminal-a", "terminal-b", "atlas-window", "broadcast"}
VALID_TRIGGERS = {
    "review_requested",
    "architecture_review_requested",
    "design_system_review_requested",
    "implementation_requested",
    "verification_requested",
    "evidence_requested",
    "synthesis_requested",
    "decision_required",
    "clarification_required",
    "handoff_ready",
    "status_update",
    "stop_the_line",
    "breaking_change",
    "protocol_changed",
    "decision_announced",
    "closure_requested",
}
VALID_PRIORITIES = {"low", "normal", "high", "critical"}


def load_core() -> Any:
    spec = importlib.util.spec_from_file_location("live_channels_core", CORE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load core utility: {CORE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = load_core()


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def parse_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_message(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        meta, body = core.parse_message(path)
    except Exception as exc:  # diagnostic boundary
        return [f"parse error: {exc}"]

    missing = sorted(REQUIRED_FIELDS - set(meta))
    if missing:
        problems.append(f"missing fields: {', '.join(missing)}")

    message_id = str(meta.get("id", ""))
    if not core.ID_RE.match(message_id):
        problems.append(f"invalid id: {message_id!r}")
    elif not path.name.startswith(message_id):
        problems.append("filename does not begin with message id")

    if meta.get("status") not in core.VALID_STATES:
        problems.append(f"invalid status: {meta.get('status')!r}")
    if meta.get("priority") not in VALID_PRIORITIES:
        problems.append(f"invalid priority: {meta.get('priority')!r}")
    if meta.get("channel") not in VALID_CHANNELS:
        problems.append(f"invalid channel: {meta.get('channel')!r}")
    if meta.get("trigger") not in VALID_TRIGGERS:
        problems.append(f"invalid trigger: {meta.get('trigger')!r}")

    sender = str(meta.get("from", ""))
    if sender not in VALID_AGENTS - {"ALL"}:
        problems.append(f"unknown sender: {sender!r}")

    recipients = normalize_list(meta.get("to"))
    if not recipients:
        problems.append("to must contain at least one recipient")
    unknown_recipients = sorted(set(recipients) - VALID_AGENTS)
    if unknown_recipients:
        problems.append(f"unknown recipients: {', '.join(unknown_recipients)}")

    for field in ("created_at", "updated_at"):
        if field in meta and not parse_datetime(meta[field]):
            problems.append(f"invalid ISO datetime in {field}: {meta[field]!r}")

    if not isinstance(meta.get("requires_response"), bool):
        problems.append("requires_response must be true or false")

    claimed_by = meta.get("claimed_by")
    if claimed_by is not None and str(claimed_by) not in VALID_AGENTS - {"ALL"}:
        problems.append(f"unknown claimant: {claimed_by!r}")

    if meta.get("status") == "CLAIMED" and not claimed_by:
        problems.append("CLAIMED message has no claimed_by")
    if meta.get("status") == "BLOCKED" and "## Blocked" not in body:
        problems.append("BLOCKED message has no Blocked section")
    if meta.get("status") == "RESPONDED" and "## Response" not in body:
        problems.append("RESPONDED message has no Response section")
    if not body.strip():
        problems.append("message body is empty")

    critical_trigger = meta.get("trigger") in {
        "stop_the_line",
        "breaking_change",
        "decision_required",
    }
    if critical_trigger:
        lowered = body.lower()
        for concept in ("scope", "evidence", "consequence", "authority"):
            if concept not in lowered:
                problems.append(
                    f"{meta.get('trigger')} body does not explicitly mention {concept}"
                )

    return problems


def cmd_validate(args: argparse.Namespace) -> None:
    core.ensure_repo()
    paths = [core.find_message(args.id)] if args.id else core.iter_messages()
    failures = 0
    for path in paths:
        problems = validate_message(path)
        if problems:
            failures += 1
            print(f"FAIL {path.relative_to(ROOT)}")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"PASS {path.relative_to(ROOT)}")
    if failures:
        raise SystemExit(1)


def write_transition(
    message_id: str,
    agent: str,
    status: str,
    heading: str,
    note: str,
    commit: bool,
    push: bool,
    pull: bool,
) -> None:
    core.ensure_repo()
    core.maybe_sync(pull)
    path = core.find_message(message_id)
    meta, body = core.parse_message(path)
    if meta.get("status") in {"CLOSED", "CANCELLED", "SUPERSEDED"}:
        raise SystemExit(f"Cannot transition a {meta.get('status')} message")
    body = (
        body.rstrip()
        + f"\n\n## {heading} — {agent} — {core.now_iso()}\n\n{note.strip()}\n"
    )
    meta["status"] = status
    meta["updated_at"] = core.now_iso()
    path.write_text(core.render_message(meta, body), encoding="utf-8")
    core.maybe_commit_push(
        [path], f"channel: {status.lower()} {message_id} by {agent}", commit, push
    )
    print(f"{status}: {message_id}")


def cmd_ack(args: argparse.Namespace) -> None:
    write_transition(
        args.id,
        args.agent,
        "ACKNOWLEDGED",
        "Acknowledged",
        args.note or "Received and reviewed for routing.",
        args.commit,
        args.push,
        args.pull,
    )


def cmd_block(args: argparse.Namespace) -> None:
    write_transition(
        args.id,
        args.agent,
        "BLOCKED",
        "Blocked",
        f"**Blocker:** {args.reason}\n\n**Needed to proceed:** {args.needed}",
        args.commit,
        args.push,
        args.pull,
    )


def cmd_board(args: argparse.Namespace) -> None:
    core.ensure_repo()
    if args.pull:
        core.maybe_sync(True)
    records: list[tuple[dict[str, Any], Path]] = []
    for path in core.iter_messages():
        try:
            meta, _ = core.parse_message(path)
        except Exception:
            continue
        if not args.all and meta.get("status") in {"CLOSED", "CANCELLED", "SUPERSEDED"}:
            continue
        records.append((meta, path))

    records.sort(
        key=lambda item: (
            {"critical": 0, "high": 1, "normal": 2, "low": 3}.get(
                str(item[0].get("priority")), 9
            ),
            str(item[0].get("updated_at", "")),
        )
    )

    counts = Counter(str(meta.get("status")) for meta, _ in records)
    print("Live Channels Board")
    print("===================")
    print(" | ".join(f"{key}: {value}" for key, value in sorted(counts.items())))
    print()
    if not records:
        print("No messages.")
        return
    for meta, path in records:
        recipients = ",".join(normalize_list(meta.get("to")))
        claimant = f" claimed={meta.get('claimed_by')}" if meta.get("claimed_by") else ""
        print(
            f"{meta.get('id')} [{meta.get('priority')}/{meta.get('status')}] "
            f"{meta.get('subject')} :: {meta.get('from')} → {recipients}{claimant}\n"
            f"  trigger={meta.get('trigger')} channel={meta.get('channel')} "
            f"updated={meta.get('updated_at')}\n"
            f"  {path.relative_to(ROOT)}"
        )


def cmd_doctor(args: argparse.Namespace) -> None:
    core.ensure_repo()
    checks: list[tuple[str, bool, str]] = []
    checks.append(("python", sys.version_info >= (3, 10), sys.version.split()[0]))
    checks.append(("git executable", shutil.which("git") is not None, shutil.which("git") or "missing"))
    checks.append(("repository", (ROOT / ".git").exists(), str(ROOT)))
    checks.append(("core utility", CORE_PATH.exists(), str(CORE_PATH)))
    checks.append(("messages directory", core.MESSAGES.exists(), str(core.MESSAGES)))

    branch = git("branch", "--show-current")
    checks.append(("git branch", branch.returncode == 0, branch.stdout.strip() or "unknown"))
    remote = git("remote", "get-url", "origin")
    checks.append(("origin", remote.returncode == 0, remote.stdout.strip() or remote.stderr.strip()))
    status = git("status", "--porcelain")
    checks.append(
        (
            "working tree",
            status.returncode == 0 and not status.stdout.strip(),
            "clean" if not status.stdout.strip() else "has local changes",
        )
    )

    validation_failures = sum(bool(validate_message(path)) for path in core.iter_messages())
    checks.append(
        (
            "message validation",
            validation_failures == 0,
            f"{validation_failures} invalid message(s)",
        )
    )

    failed = False
    for name, ok, detail in checks:
        failed = failed or not ok
        print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
    if failed and args.strict:
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate one or all message files")
    validate.add_argument("--id")
    validate.set_defaults(func=cmd_validate)

    ack = sub.add_parser("ack", help="Acknowledge receipt of a message")
    ack.add_argument("--agent", required=True)
    ack.add_argument("--id", required=True)
    ack.add_argument("--note")
    core.add_common_write_flags(ack)
    ack.set_defaults(func=cmd_ack)

    block = sub.add_parser("block", help="Mark a message blocked with an explicit need")
    block.add_argument("--agent", required=True)
    block.add_argument("--id", required=True)
    block.add_argument("--reason", required=True)
    block.add_argument("--needed", required=True)
    core.add_common_write_flags(block)
    block.set_defaults(func=cmd_block)

    board = sub.add_parser("board", help="Show cross-channel status board")
    board.add_argument("--all", action="store_true")
    board.add_argument("--pull", action="store_true")
    board.set_defaults(func=cmd_board)

    doctor = sub.add_parser("doctor", help="Check local environment and repository health")
    doctor.add_argument("--strict", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "push", False):
        args.commit = True
    args.func(args)


if __name__ == "__main__":
    main()
