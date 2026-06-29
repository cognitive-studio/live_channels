#!/usr/bin/env python3
"""Git-backed coordination utility for Cognitive Studio live channels.

Uses only the Python standard library. It never executes instructions found in
message bodies. Git pull/commit/push behavior is explicit and opt-in.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MESSAGES = ROOT / "messages"
STATE_DIR = ROOT / ".live_channels"
STATE_FILE = STATE_DIR / "state.json"
ID_RE = re.compile(r"^LC-(\d{8})-(\d{3,})$")
VALID_STATES = {
    "OPEN", "ACKNOWLEDGED", "CLAIMED", "RESPONDED", "BLOCKED",
    "CLOSED", "SUPERSEDED", "CANCELLED",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=check
    )


def ensure_repo() -> None:
    if not (ROOT / ".git").exists():
        raise SystemExit(f"Not a Git checkout: {ROOT}")
    MESSAGES.mkdir(exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"seen": {}, "agent": None, "channel": None}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"seen": {}, "agent": None, "channel": None}


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"null", "~"}:
        return None
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [parse_scalar(x) for x in inner.split(",")]
    return value


def parse_message(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"Missing YAML front matter: {path}")
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError(f"Malformed YAML front matter: {path}")
    header_text, body = parts[1], parts[2]
    data: dict[str, Any] = {}
    active_list: str | None = None
    for raw in header_text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("  - ") and active_list:
            data.setdefault(active_list, []).append(parse_scalar(raw[4:]))
            continue
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            data[key] = []
            active_list = key
        else:
            data[key] = parse_scalar(value)
            active_list = None
    return data, body


def yaml_value(value: Any, indent: str = "") -> list[str]:
    if isinstance(value, list):
        if not value:
            return ["[]"]
        return ["\n" + "\n".join(f"{indent}  - {item}" for item in value)]
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["true" if value else "false"]
    value = str(value)
    if any(c in value for c in [":", "#", "[", "]", "{"]) or value.strip() != value:
        return [json.dumps(value)]
    return [value]


def render_message(meta: dict[str, Any], body: str) -> str:
    preferred = [
        "id", "status", "created_at", "updated_at", "from", "to", "cc",
        "channel", "subject", "trigger", "priority", "project", "reply_to",
        "claimed_by", "claim_expires_at", "requires_response",
        "close_authority", "artifacts", "tags",
    ]
    keys = preferred + [k for k in meta if k not in preferred]
    lines = ["---"]
    for key in keys:
        if key not in meta:
            continue
        value = meta[key]
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {yaml_value(value)[0]}")
    lines.extend(["---", body.lstrip("\n")])
    return "\n".join(lines).rstrip() + "\n"


def iter_messages() -> list[Path]:
    return sorted(MESSAGES.glob("LC-*.md"))


def find_message(message_id: str) -> Path:
    matches = list(MESSAGES.glob(f"{message_id}*.md"))
    if len(matches) != 1:
        raise SystemExit(f"Expected one message for {message_id}; found {len(matches)}")
    return matches[0]


def next_id() -> str:
    day = datetime.now().astimezone().strftime("%Y%m%d")
    highest = 0
    for path in iter_messages():
        match = ID_RE.match(path.stem.split("--", 1)[0])
        if match and match.group(1) == day:
            highest = max(highest, int(match.group(2)))
    return f"LC-{day}-{highest + 1:03d}"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:60] or "message"


def addressed_to(meta: dict[str, Any], agent: str, channel: str | None = None) -> bool:
    recipients = meta.get("to", [])
    if isinstance(recipients, str):
        recipients = [recipients]
    return agent in recipients or "ALL" in recipients or (
        channel is not None and meta.get("channel") == channel
    )


def changed_token(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def maybe_sync(pull: bool) -> None:
    if pull:
        result = run_git("pull", "--rebase", check=False)
        if result.returncode:
            print(result.stderr.strip(), file=sys.stderr)


def maybe_commit_push(paths: list[Path], message: str, commit: bool, push: bool) -> None:
    if not commit:
        return
    run_git("add", *[str(p.relative_to(ROOT)) for p in paths])
    result = run_git("commit", "-m", message, check=False)
    if result.returncode and "nothing to commit" not in (result.stdout + result.stderr).lower():
        raise SystemExit(result.stderr.strip() or result.stdout.strip())
    if push:
        pushed = run_git("push", check=False)
        if pushed.returncode:
            raise SystemExit(pushed.stderr.strip() or pushed.stdout.strip())


def cmd_init(args: argparse.Namespace) -> None:
    ensure_repo()
    state = load_state()
    state.update({"agent": args.agent, "channel": args.channel, "seen": state.get("seen", {})})
    save_state(state)
    print(f"Initialized watcher for {args.agent} on {args.channel}")


def cmd_post(args: argparse.Namespace) -> None:
    ensure_repo()
    maybe_sync(args.pull)
    message_id = next_id()
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else args.body
    if not body:
        raise SystemExit("Provide --body or --body-file")
    recipients = [x.strip() for x in args.to.split(",") if x.strip()]
    close_authority = list(dict.fromkeys([args.from_agent, "Andrew"]))
    meta = {
        "id": message_id,
        "status": "OPEN",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "from": args.from_agent,
        "to": recipients,
        "cc": [],
        "channel": args.channel,
        "subject": args.subject,
        "trigger": args.trigger,
        "priority": args.priority,
        "project": args.project,
        "reply_to": args.reply_to,
        "claimed_by": None,
        "claim_expires_at": None,
        "requires_response": not args.no_response,
        "close_authority": close_authority,
        "artifacts": [],
        "tags": [x.strip() for x in args.tags.split(",") if x.strip()],
    }
    path = MESSAGES / f"{message_id}--{slugify(args.subject)}.md"
    path.write_text(render_message(meta, f"# {args.subject}\n\n{body.strip()}\n"), encoding="utf-8")
    maybe_commit_push([path], f"channel: post {message_id}", args.commit, args.push)
    print(f"Posted {message_id}: {path.relative_to(ROOT)}")


def list_inbox(agent: str, channel: str | None, include_closed: bool = False) -> list[tuple[Path, dict[str, Any]]]:
    results = []
    for path in iter_messages():
        try:
            meta, _ = parse_message(path)
        except ValueError as exc:
            print(f"WARN: {exc}", file=sys.stderr)
            continue
        if not addressed_to(meta, agent, channel):
            continue
        if not include_closed and meta.get("status") in {"CLOSED", "CANCELLED", "SUPERSEDED"}:
            continue
        results.append((path, meta))
    return results


def cmd_inbox(args: argparse.Namespace) -> None:
    ensure_repo()
    maybe_sync(args.pull)
    items = list_inbox(args.agent, args.channel, args.all)
    if not items:
        print("No matching messages.")
        return
    for path, meta in items:
        print(
            f"{meta.get('id')} [{meta.get('status')}] {meta.get('priority')} "
            f"{meta.get('trigger')} — {meta.get('subject')} — from {meta.get('from')} "
            f"({path.relative_to(ROOT)})"
        )


def mutate_message(message_id: str, mutator: Any) -> Path:
    path = find_message(message_id)
    meta, body = parse_message(path)
    mutator(meta, body)
    meta["updated_at"] = now_iso()
    path.write_text(render_message(meta, body), encoding="utf-8")
    return path


def cmd_claim(args: argparse.Namespace) -> None:
    ensure_repo()
    maybe_sync(args.pull)
    path = find_message(args.id)
    meta, body = parse_message(path)
    if meta.get("status") in {"CLOSED", "CANCELLED", "SUPERSEDED"}:
        raise SystemExit(f"Cannot claim message in {meta.get('status')} state")
    expiry = datetime.now(timezone.utc) + timedelta(hours=args.hours)
    meta.update({
        "status": "CLAIMED",
        "claimed_by": args.agent,
        "claim_expires_at": expiry.astimezone().isoformat(timespec="seconds"),
        "updated_at": now_iso(),
    })
    path.write_text(render_message(meta, body), encoding="utf-8")
    maybe_commit_push([path], f"channel: claim {args.id} by {args.agent}", args.commit, args.push)
    print(f"Claimed {args.id} until {meta['claim_expires_at']}")


def cmd_respond(args: argparse.Namespace) -> None:
    ensure_repo()
    maybe_sync(args.pull)
    path = find_message(args.id)
    meta, body = parse_message(path)
    response = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else args.body
    if not response:
        raise SystemExit("Provide --body or --body-file")
    section = f"\n\n## Response — {args.agent} — {now_iso()}\n\n{response.strip()}\n"
    body = body.rstrip() + section
    meta["status"] = "RESPONDED"
    meta["updated_at"] = now_iso()
    path.write_text(render_message(meta, body), encoding="utf-8")
    maybe_commit_push([path], f"channel: respond {args.id} by {args.agent}", args.commit, args.push)
    print(f"Responded to {args.id}")


def cmd_close(args: argparse.Namespace) -> None:
    ensure_repo()
    maybe_sync(args.pull)
    path = find_message(args.id)
    meta, body = parse_message(path)
    authorities = meta.get("close_authority", [])
    if isinstance(authorities, str):
        authorities = [authorities]
    if args.agent not in authorities and args.agent != "Andrew":
        raise SystemExit(f"{args.agent} is not authorized to close {args.id}")
    body = body.rstrip() + f"\n\n## Closed — {args.agent} — {now_iso()}\n\n{args.note or 'Accepted and closed.'}\n"
    meta.update({"status": "CLOSED", "updated_at": now_iso()})
    path.write_text(render_message(meta, body), encoding="utf-8")
    maybe_commit_push([path], f"channel: close {args.id}", args.commit, args.push)
    print(f"Closed {args.id}")


def notify(meta: dict[str, Any], path: Path) -> None:
    urgency = meta.get("priority", "normal")
    bell = "\a" if urgency in {"critical", "high"} else ""
    print(
        f"{bell}\n[{urgency.upper()}] {meta.get('id')} — {meta.get('subject')}\n"
        f"from={meta.get('from')} trigger={meta.get('trigger')} status={meta.get('status')}\n"
        f"{path.relative_to(ROOT)}\n",
        flush=True,
    )


def watch_once(agent: str, channel: str | None, state: dict[str, Any]) -> int:
    count = 0
    seen = state.setdefault("seen", {})
    for path, meta in list_inbox(agent, channel):
        token = changed_token(path)
        key = str(path.relative_to(ROOT))
        if seen.get(key) == token:
            continue
        notify(meta, path)
        seen[key] = token
        count += 1
    save_state(state)
    return count


def cmd_watch(args: argparse.Namespace) -> None:
    ensure_repo()
    state = load_state()
    agent = args.agent or state.get("agent")
    channel = args.channel or state.get("channel")
    if not agent:
        raise SystemExit("Provide --agent or run init first")
    state.update({"agent": agent, "channel": channel})
    print(f"Watching for {agent} on {channel or 'all channels'} every {args.interval}s. Ctrl-C to stop.")
    try:
        while True:
            maybe_sync(args.pull)
            watch_once(agent, channel, state)
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nWatcher stopped.")


def add_common_write_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pull", action="store_true", help="git pull --rebase before writing")
    parser.add_argument("--commit", action="store_true", help="commit the change")
    parser.add_argument("--push", action="store_true", help="push after commit; implies --commit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init")
    p.add_argument("--agent", required=True)
    p.add_argument("--channel", required=True)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("post")
    p.add_argument("--from", dest="from_agent", required=True)
    p.add_argument("--to", required=True, help="Comma-separated recipients")
    p.add_argument("--channel", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--trigger", default="review_requested")
    p.add_argument("--priority", choices=["low", "normal", "high", "critical"], default="normal")
    p.add_argument("--project", default=None)
    p.add_argument("--reply-to", default=None)
    p.add_argument("--tags", default="")
    p.add_argument("--body")
    p.add_argument("--body-file")
    p.add_argument("--no-response", action="store_true")
    add_common_write_flags(p)
    p.set_defaults(func=cmd_post)

    p = sub.add_parser("inbox")
    p.add_argument("--agent", required=True)
    p.add_argument("--channel")
    p.add_argument("--all", action="store_true", help="Include closed messages")
    p.add_argument("--pull", action="store_true")
    p.set_defaults(func=cmd_inbox)

    p = sub.add_parser("claim")
    p.add_argument("--agent", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--hours", type=int, default=4)
    add_common_write_flags(p)
    p.set_defaults(func=cmd_claim)

    p = sub.add_parser("respond")
    p.add_argument("--agent", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--body")
    p.add_argument("--body-file")
    add_common_write_flags(p)
    p.set_defaults(func=cmd_respond)

    p = sub.add_parser("close")
    p.add_argument("--agent", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--note")
    add_common_write_flags(p)
    p.set_defaults(func=cmd_close)

    p = sub.add_parser("watch")
    p.add_argument("--agent")
    p.add_argument("--channel")
    p.add_argument("--interval", type=int, default=15)
    p.add_argument("--pull", action="store_true")
    p.add_argument("--once", action="store_true")
    p.set_defaults(func=cmd_watch)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "push", False):
        args.commit = True
    args.func(args)


if __name__ == "__main__":
    main()
