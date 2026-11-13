#!/usr/bin/env python3
"""limit-bot: post a Discord webhook message when Claude Code hits a rate limit."""
import argparse, collections, datetime, json, os, re, sys, time, urllib.request
from pathlib import Path

CFG = Path.home() / ".config/limit-bot/config.json"
STATE = Path.home() / ".config/limit-bot/last-sent"
COOLDOWN = 600  # seconds; a limit can fire repeatedly


def load_cfg():
    return json.loads(CFG.read_text())


def setup(a):
    hook = a.webhook or os.environ.get("DISCORD_WEBHOOK", "")
    if not hook.startswith("https://discord.com/api/webhooks/"):
        sys.exit("Set DISCORD_WEBHOOK to a Discord webhook URL first.")
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps({"name": a.name, "email": a.email, "webhook": hook}))
    CFG.chmod(0o600)
    print("Saved to", CFG)


def transcript_stats(path):
    models, tokens = collections.Counter(), 0
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            try:
                o = json.loads(line)
            except ValueError:
                continue
            m = o.get("message") or {}
            if o.get("type") != "assistant" or not isinstance(m, dict):
                continue
            if m.get("model") and not m["model"].startswith("<"):
                models[m["model"]] += 1
            u = m.get("usage") or {}
            tokens += (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0)
    except OSError:
        pass
    return (models.most_common(1)[0][0] if models else "unknown"), tokens


def limit_kind(text):
    t = (text or "").lower()
    if "week" in t or "7" in t:
        return "weekly"
    if "hour" in t or "5" in t:
        return "5-hour"
    return "usage"


def post(cfg, kind, model, tokens):
    # Masked link with a title: Discord shows the title (the email) on hover.
    who = f'[**{cfg["name"]}**](https://claude.ai "{cfg["email"]}")'
    body = {
        "content": f"{who} reached the **{kind}** limit on Claude, using: **Claude Code**, most used model: **{model}**",
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "color": 0xBDBDBD,
            "fields": [
                {"name": "Limit", "value": kind, "inline": True},
                {"name": "Model", "value": model, "inline": True},
                {"name": "Session tokens", "value": f"{tokens:,}", "inline": True},
            ],
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }],
    }
    req = urllib.request.Request(
        cfg["webhook"], json.dumps(body).encode(),
        {"Content-Type": "application/json", "User-Agent": "limit-bot/0.1"})
    urllib.request.urlopen(req, timeout=8).read()


def hook():
    try:
        data = json.load(sys.stdin)
        cfg = load_cfg()
        if STATE.exists() and time.time() - float(STATE.read_text() or 0) < COOLDOWN:
            return
        model, tokens = transcript_stats(data.get("transcript_path", ""))
        kind = limit_kind((data.get("last_assistant_message") or "") + " " + (data.get("error_details") or ""))
        post(cfg, kind, model, tokens)
        STATE.write_text(str(time.time()))
    except Exception as e:  # never break the user's session
        print(f"limit-bot: {e}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    su = s.add_parser("setup"); su.add_argument("--name", required=True); su.add_argument("--email", required=True); su.add_argument("--webhook")
    s.add_parser("hook"); s.add_parser("test")
    a = p.parse_args()
    if a.cmd == "setup": setup(a)
    elif a.cmd == "hook": hook()
    else: post(load_cfg(), "5-hour", "claude-example-model", 12345); print("Test message sent.")


main()
