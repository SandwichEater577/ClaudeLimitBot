#!/usr/bin/env python3
"""limit-bot: tell the team on Discord when someone hits a Claude Code limit,
and again when the limit is over. Standard library only.

    notify.py hook       StopFailure hook: a rate limit was hit
    notify.py session    SessionStart hook: send reminders that came due while offline
    notify.py wait       background waiter that sends reminders on time
    notify.py setup      save settings (the installer calls this)
    notify.py test       post a preview with no pings
    notify.py status     show the limit you're waiting out, if any
    notify.py back       limit reset early: post "limit is over" now
"""
import argparse, collections, datetime, json, os, re, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = json.loads((ROOT / "server.json").read_text())
VERSION = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
HOME = Path.home() / ".config" / "limit-bot"
CFG, PENDING, LOCK = HOME / "config.json", HOME / "pending.json", HOME / "waiter.lock"
API = "https://discord.com/api/v10"
WINDOW = {"5-hour": 5 * 3600, "weekly": 7 * 86400, "usage": 5 * 3600}
SEATS = ("premium", "standard")
ORANGE, GREEN, GOLD = 0xD97757, 0x5FAF7A, 0xF4C542
COOLDOWN = 600
WEBHOOK = re.compile(r"https://(\w+\.)?discord(app)?\.com/api/webhooks/\d+/.+")
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}


# ─── storage ───────────────────────────────────────────────────────────────────

def load_cfg():
    return json.loads(CFG.read_text())


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o600)


def load_pending():
    try:
        return json.loads(PENDING.read_text())
    except (OSError, ValueError):
        return []


def save_pending(items):
    private_write(PENDING, json.dumps(items))


# ─── discord ───────────────────────────────────────────────────────────────────

def http(method, url, body=None, token=None):
    headers = {"Content-Type": "application/json",
               "User-Agent": f"DiscordBot (https://github.com/SandwichEater577/ClaudeLimitBot, {VERSION})"}
    if token:
        headers["Authorization"] = "Bot " + token
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data, headers, method=method), timeout=6) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def bot_get(token, path):
    try:
        return http("GET", API + path, token=token)
    except urllib.error.HTTPError:
        raise
    except (TimeoutError, urllib.error.URLError):
        return http("GET", API + path, token=token)  # Discord stalls now and then: one retry


def role(key):
    return SERVER["roles"][key]


def seat_of(roles):
    return next((k for k in SEATS if role(k) in roles), None)


def find_member(token, query):
    """Find someone on the server by username, display name or nickname.
    Returns (user id, label, seat) or None."""
    query = query.strip().lstrip("@").lower()
    found = bot_get(token, f"/guilds/{SERVER['guild']}/members/search?query={urllib.request.quote(query)}&limit=10")
    def names(m):
        return {(m["user"].get("username") or "").lower(), (m["user"].get("global_name") or "").lower(),
                (m.get("nick") or "").lower()}
    best = next((m for m in found if query in names(m)), found[0] if found else None)
    if not best:
        return None
    return best["user"]["id"], best["user"]["username"], seat_of(best["roles"])


def server_state(token, user_id=None):
    """(the user's seat, seats held now, seat totals from the seat-count topic).
    The two requests run side by side, and the member list already has the user's roles."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(2) as pool:
        members = pool.submit(bot_get, token, f"/guilds/{SERVER['guild']}/members?limit=1000")
        channel = pool.submit(bot_get, token, f"/channels/{SERVER['seat_channel']}")
        members, topic = members.result(), channel.result().get("topic") or ""
    held = {k: sum(role(k) in m["roles"] for m in members) for k in SEATS}
    total = {}
    for k in SEATS:
        m = re.search(k + r"\D*(\d+)", topic, re.I)
        if m:
            total[k] = int(m.group(1))
    seat = next((seat_of(m["roles"]) for m in members if m["user"]["id"] == user_id), None)
    return seat, held, total


def lookup(cfg):
    """Live seat and counters. Any failure just means less detail in the message."""
    if cfg.get("token") and cfg.get("discord_id"):
        try:
            return server_state(cfg["token"], cfg["discord_id"])
        except (OSError, KeyError, ValueError, TypeError):  # OSError covers timeouts and HTTP errors
            pass
    return None, {}, {}


def post(cfg, content, embed, roles=(), users=(), everyone=False):
    body = {"content": content, "embeds": [embed],
            "allowed_mentions": {"parse": ["everyone"] if everyone else [], "roles": list(roles), "users": list(users)}}
    http("POST", cfg["webhook"] + "?wait=true", body)


# ─── message pieces ────────────────────────────────────────────────────────────

def R(key):
    return f"<@&{role(key)}>"


def U(cfg):
    return f"<@{cfg['discord_id']}>" if cfg.get("discord_id") else f"**{cfg['name']}**"


def ts(t, style):
    return f"<t:{int(t)}:{style}>"


def who(cfg):
    # A masked link with a title: Discord shows the email when you hover the name.
    return f'[**{cfg["name"]}**](https://claude.ai "{cfg["email"]}")'


def seat_name(key):
    return {"premium": "Premium", "standard": "Standard", None: "No Seat"}[key]


def counters(held, total, change):
    """Free-seat bars after a seat change, e.g. Standard ▰▱▱▱ 1 of 4 free."""
    lines = []
    for k in SEATS:
        if not total.get(k):
            continue  # seat types the plan doesn't have stay hidden
        free = max(0, min(total[k], total[k] - held.get(k, 0) - change.get(k, 0)))
        bar = "▰" * free + "▱" * (total[k] - free)
        lines.append(f"`{seat_name(k):<8}` {bar or '—'}  **{free}** of {total[k]} free")
    return "\n".join(lines) or "Set the totals in the seat-count channel topic."


def card(color, title, description, fields):
    return {"color": color, "title": title, "description": description, "fields": fields,
            "footer": {"text": f"ClaudeLimitBot v{VERSION}"},
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}


def back_at(due, kind):
    return ts(due, "f" if kind == "weekly" else "t")


def back_line(due, kind, exact):
    if exact:
        return f"Back {ts(due, 'R')}, at {back_at(due, kind)}."
    return f"Back {ts(due, 'R')}, around {back_at(due, kind)} (estimated)."


# ─── the messages ──────────────────────────────────────────────────────────────

def send_limit(cfg, kind, model, tokens, start, due, seat, held, total, preview=False, exact=False):
    if seat:
        content = f"{R('owner')}, move {U(cfg)} from {R(seat)} to {R('none')}."
    else:
        content = f"{R('owner')}, {U(cfg)} hit a limit. They don't hold a seat role, so nothing to move."
    if preview:
        content = "**Preview, nobody was pinged.**\n" + content
    fields = [
        {"name": "Model", "value": f"`{model}`", "inline": True},
        {"name": "Seat", "value": f"{seat_name(seat)} → No Seat" if seat else "none", "inline": True},
        {"name": "This session", "value": f"{tokens:,} tokens", "inline": True},
        {"name": "Free seats after the move", "value": counters(held, total, {seat: -1} if seat else {}), "inline": False},
    ]
    description = f"{who(cfg)} hit the **{kind}** limit on **Claude Code**.\n" + back_line(due, kind, exact)
    roles = [] if preview else [role("owner")]
    post(cfg, content, card(ORANGE, "◆  LIMIT REACHED", description, fields), roles=roles)
    if seat == "premium":
        content = f"{'@everyone' if not preview else '@​everyone'} {R('premium')} is now available!"
        description = (f"{who(cfg)} is out until {back_at(due, kind)} ({ts(due, 'R')}).\n"
                       f"Want the seat meanwhile? Ask {R('owner')}.")
        fields = [{"name": "Free seats", "value": counters(held, total, {seat: -1}), "inline": False}]
        post(cfg, content, card(GOLD, "◆  PREMIUM SEAT OPEN", description, fields), everyone=not preview)


def send_over(cfg, entry, preview=False, early=False):
    seat = entry.get("seat")
    current, held, total = lookup(cfg)
    if seat:
        content = f"{R('owner')}, {U(cfg)}'s limit is over. Move them from {R('none')} back to {R(seat)}."
    else:
        content = f"{U(cfg)}'s limit is over."
    change = {seat: +1} if seat and current != seat else {}
    fields = [
        {"name": "Seat", "value": f"No Seat → {seat_name(seat)}" if seat else "none", "inline": True},
        {"name": "Limit", "value": entry["kind"], "inline": True},
        {"name": "Started", "value": ts(entry["start"], "t"), "inline": True},
        {"name": "Free seats after the move", "value": counters(held, total, change), "inline": False},
    ]
    description = f"{who(cfg)} can use **Claude Code** again" + (", earlier than expected." if early else ".")
    users = [cfg["discord_id"]] if cfg.get("discord_id") and not preview else []
    if preview:
        content = "**Preview, nobody was pinged.**\n" + content
    post(cfg, content, card(GREEN, "◆  LIMIT OVER", description, fields),
         roles=[] if preview else [role("owner")], users=users)


# ─── reminders ─────────────────────────────────────────────────────────────────

def send_due():
    """Send every reminder whose time has come. A claim file per reminder stops
    the waiter and a starting session from both sending it."""
    try:
        cfg = load_cfg()
    except (OSError, ValueError):
        return
    for entry in load_pending():
        if entry["due"] > time.time():
            continue
        claim = HOME / f"sending-{entry['id']}"
        try:
            os.close(os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        try:
            send_over(cfg, entry)
            save_pending([e for e in load_pending() if e["id"] != entry["id"]])
        except (urllib.error.URLError, OSError) as e:
            print(f"limit-bot: reminder not sent yet: {e}", file=sys.stderr)
        finally:
            claim.unlink(missing_ok=True)


def spawn_waiter():
    if not load_pending():
        return
    options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        options["creationflags"] = 0x00000008 | 0x00000200  # detached, own process group
    else:
        options["start_new_session"] = True  # survives the Claude Code session ending
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "wait"], **options)


def wait():
    """Sleep until each reminder is due and send it. Only one waiter runs at a time;
    it refreshes its lock every minute so a crashed waiter's lock goes stale."""
    try:
        if time.time() - LOCK.stat().st_mtime < 180:
            return
    except FileNotFoundError:
        pass
    private_write(LOCK, str(os.getpid()))
    try:
        while True:
            pending = load_pending()
            if not pending:
                return
            send_due()
            LOCK.touch()
            # at least 5 s between rounds, so a failed send (offline) retries calmly
            time.sleep(max(5, min(60, min(e["due"] for e in pending) - time.time())))
    finally:
        LOCK.unlink(missing_ok=True)


# ─── hook entry points ─────────────────────────────────────────────────────────

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
    if "week" in t or "7-day" in t or "7 day" in t:
        return "weekly"
    if "hour" in t or "5-h" in t:
        return "5-hour"
    return "usage"


def reset_time(text, now):
    """When the limit resets, read from Claude Code's error text, or None.
    Understands 'limit reached|1767225600', 'resets 3pm (Europe/Warsaw)',
    'resets Nov 20, 3:30pm' and 'resets in 2h 15m'."""
    t = text or ""
    due = None
    m = re.search(r"\|\s*(\d{10})\b", t)
    if m:
        due = int(m.group(1))
    elif m := re.search(r"resets?\s+in\s+(?:(\d+)\s*h\w*)?\s*(?:(\d+)\s*m\w*)?", t, re.I):
        if m.group(1) or m.group(2):
            due = now + int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60
    elif m := re.search(r"resets?\s+(?:at\s+|on\s+)?(?:([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(?:at\s+)?)?"
                        r"(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?(?:\s*\(([^)]+)\))?", t, re.I):
        mon, day, hour, minute, ampm, zone = m.groups()
        hour, minute = int(hour), int(minute or 0)
        if ampm:
            hour = hour % 12 + (12 if ampm[0].lower() == "p" else 0)
        if hour > 23 or minute > 59 or (mon and mon[:3].lower() not in MONTHS):
            return None
        tz = None
        if zone:
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(zone.strip())
            except Exception:  # unknown zone, or no tz database (Windows): use local time
                tz = None
        base = datetime.datetime.fromtimestamp(now, tz) if tz else datetime.datetime.fromtimestamp(now).astimezone()
        try:
            when = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if mon:
                when = when.replace(month=MONTHS[mon[:3].lower()], day=int(day))
                if when.timestamp() < now:
                    when = when.replace(year=when.year + 1)
        except ValueError:  # e.g. Feb 30
            return None
        while when.timestamp() <= now:
            when += datetime.timedelta(days=1)
        due = when.timestamp()
    # anything outside a week (plus slack) is a misread, not a reset time
    return due if due and now < due <= now + 8 * 86400 else None


def hook():
    try:
        data = json.load(sys.stdin)
        cfg = load_cfg()
        now = time.time()
        pending = load_pending()
        if any(e["due"] > now for e in pending):
            return  # already waiting out a limit: one message per limit
        last = HOME / "last-sent"
        if last.exists() and now - float(last.read_text() or 0) < COOLDOWN:
            return
        text = (data.get("last_assistant_message") or "") + " " + (data.get("error_details") or "")
        kind = limit_kind(text)
        reset = reset_time(text, now)
        if reset and kind == "usage":
            kind = "weekly" if reset - now > 86400 else "5-hour"
        due = reset or now + WINDOW[kind]
        model, tokens = transcript_stats(data.get("transcript_path", ""))
        seat, held, total = lookup(cfg)
        send_limit(cfg, kind, model, tokens, now, due, seat, held, total, exact=bool(reset))
        private_write(last, str(now))
        save_pending(pending + [{"id": f"{int(now)}", "start": now, "due": due, "seat": seat, "kind": kind,
                                 "exact": bool(reset)}])
        spawn_waiter()
    except Exception as e:  # never break the user's session
        print(f"limit-bot: {e}", file=sys.stderr)


def session():
    try:
        send_due()
        spawn_waiter()
    except Exception as e:
        print(f"limit-bot: {e}", file=sys.stderr)


def setup(a):
    cfg = {"name": a.name, "email": a.email,
           "webhook": a.webhook or os.environ.get("DISCORD_WEBHOOK", "")}
    if not WEBHOOK.match(cfg["webhook"]):
        sys.exit("A Discord webhook URL is needed.")
    if a.token:
        cfg["token"] = a.token
    if a.discord_id:
        cfg["discord_id"] = a.discord_id
    private_write(CFG, json.dumps(cfg))
    print("Saved to", CFG)


def test():
    cfg = load_cfg()
    now = time.time()
    seat, held, total = lookup(cfg)
    send_limit(cfg, "5-hour", "claude-example-model", 12345, now, now + WINDOW["5-hour"],
               seat, held, total, preview=True)
    send_over(cfg, {"seat": seat, "kind": "5-hour", "start": now}, preview=True)
    print("Preview sent.")


def local(t):
    return datetime.datetime.fromtimestamp(t).strftime("%a %d %b, %H:%M")


def status():
    if not CFG.exists():
        print("Not set up. Run the installer from the ClaudeLimitBot folder.")
        return
    cfg = load_cfg()
    print(f"limit-bot v{VERSION}, posting as {cfg.get('name')} ({'linked to Discord' if cfg.get('discord_id') else 'no Discord link'})")
    pending = sorted(load_pending(), key=lambda e: e["due"])
    if not pending:
        print("No limit right now. Nothing waiting to be sent.")
        return
    for e in pending:
        left = e["due"] - time.time()
        when = f"in {int(left // 3600)}h {int(left % 3600 // 60)}m" if left > 0 else "now (overdue, sends on next check)"
        print(f"{e['kind']} limit hit {local(e['start'])}. Back {local(e['due'])}, {when}"
              f"{'' if e.get('exact') else ' (estimated)'}. Seat to return: {seat_name(e.get('seat'))}.")
    try:
        fresh = time.time() - LOCK.stat().st_mtime < 180
    except FileNotFoundError:
        fresh = False
    print("Reminder process: " + ("running." if fresh else "not running, it starts with the next Claude Code session."))


def back():
    """The limit reset sooner than expected: post "limit is over" now and drop the reminder."""
    cfg = load_cfg()
    pending = load_pending()
    if not pending:
        print("No limit is being waited out, so there's nothing to send.")
        return
    for entry in pending:
        claim = HOME / f"sending-{entry['id']}"
        try:
            os.close(os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue  # the waiter is sending this one right now
        try:
            send_over(cfg, entry, early=entry["due"] > time.time())
            save_pending([e for e in load_pending() if e["id"] != entry["id"]])
        finally:
            claim.unlink(missing_ok=True)
    print("Sent. The Team Owner was told your limit is over.")


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    su = s.add_parser("setup")
    su.add_argument("--name", required=True)
    su.add_argument("--email", required=True)
    su.add_argument("--webhook")
    su.add_argument("--token")
    su.add_argument("--discord-id")
    for name in ("hook", "session", "wait", "test", "status", "back"):
        s.add_parser(name)
    a = p.parse_args()
    {"setup": lambda: setup(a), "hook": hook, "session": session, "wait": wait, "test": test,
     "status": status, "back": back}[a.cmd]()


if __name__ == "__main__":
    main()
