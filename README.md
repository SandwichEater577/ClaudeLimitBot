# ClaudeLimitBot

A Claude Code plugin that runs your team's Claude seats from Discord. When someone hits a usage limit, it tells the Team Owner which seat to free up. When the limit is over, it tells them to give the seat back.

**When a limit is hit** (posted to the feed channel):

> @Team Owner, move @someone from @Standard Seat to @No Seat.

with a card showing the model, the seat change, when they're back (in everyone's local time) and how many seats are free after the move. If it was a Premium seat, a second post goes out: `@everyone @Premium Seat is now available!`

**When the limit is over** (5 hours later, or 7 days for the weekly limit):

> @Team Owner, @someone's limit is over. Move them from @No Seat back to @Standard Seat.

If the computer was off at that moment, the reminder goes out the next time Claude Code starts. The name in each card shows the person's email on hover. Only Claude Code is reported, never the contents of anyone's chats.

## Install

You need [Claude Code](https://claude.ai/code), Python 3 and the access password (ask whoever runs your server).

**Linux / macOS**

```bash
git clone https://github.com/SandwichEater577/ClaudeLimitBot.git ~/ClaudeLimitBot 2>/dev/null || git -C ~/ClaudeLimitBot pull -q; python3 ~/ClaudeLimitBot/installer
```

**Windows (PowerShell)**

```powershell
if (Test-Path $HOME\ClaudeLimitBot) { git -C $HOME\ClaudeLimitBot pull -q } else { git clone https://github.com/SandwichEater577/ClaudeLimitBot.git $HOME\ClaudeLimitBot }; python $HOME\ClaudeLimitBot\installer
```

The same line installs and updates: run it again any time to get the newest version.

A menu opens. Choose **Install**, then enter the access password, your name, email and Discord username. The password unlocks the channel's webhook and a read-only bot token, both stored encrypted in `sealed.json` (scrypt key derivation, so every guess is slow). The bot token can only look up members and roles; it can't read or post in any channel. The installer adds the plugin to Claude Code and saves your settings to `~/.config/limit-bot/config.json`, readable only by you. Restart Claude Code afterwards. The menu can also update the plugin or remove it.

Already installed and want to check it works? Inside Claude Code run `/limit-bot:setup`, which posts a preview with no pings.

## Server setup

`server.json` holds the server's IDs: the guild, the `seat-count` channel and four roles (Team Owner, Premium Seat, Standard Seat, No Seat). The seat totals live in the topic of the private `seat-count` channel, for example `premium 1 · standard 4`, so the owner can change them without a new release.

The webhook is never stored in this repo in plain text. To seal a new one, run `python3 scripts/vault.py seal`.

## How it works

- A `StopFailure` hook with the `rate_limit` matcher runs `scripts/notify.py hook`. It reads the person's seat and the seat counts from Discord, posts through the webhook, and saves a reminder in `~/.config/limit-bot/pending.json`.
- A small background process sleeps until the reminder is due and posts it. A `SessionStart` hook sends any reminder that came due while the computer was off.
- One message per limit: further limit errors while waiting are ignored. Errors never interrupt your session.

## Limits

- Claude on the web can't be detected. Only Claude Code is reported.
- Hook payloads carry no reset time, so "back at" is counted from the moment the limit was hit (5 hours, or 7 days for weekly). The real reset can come a little earlier.
- The limit type (5-hour or weekly) is guessed from the error text and may show as "usage".
- Not yet tested on Windows.
