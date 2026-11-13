# ClaudeLimitBot

A Claude Code plugin that posts to a Discord channel when you hit your usage limit.

> **Ouro** reached the **5-hour** limit on Claude, using: **Claude Code**, most used model: **claude-sonnet-5-5**

The name links to your email, which shows on hover. A small card shows the limit, the model and your session's token count. Only Claude Code is reported, never the contents of your chats.

## Install

You need [Claude Code](https://claude.ai/code), Python 3 and a Discord webhook URL for the channel.

```bash
git clone https://github.com/SandwichEater577/ClaudeLimitBot.git
export DISCORD_WEBHOOK="<webhook url>"          # Windows PowerShell: $env:DISCORD_WEBHOOK="<webhook url>"
claude --plugin-dir ./ClaudeLimitBot
```

Then, inside Claude Code:

```
/limit-bot:setup YourName you@example.com
```

Your name, email and webhook are saved to `~/.config/limit-bot/config.json`, readable only by you. The webhook is never stored in this repo.

## How it works

- A `StopFailure` hook with the `rate_limit` matcher runs `scripts/notify.py`.
- The script reads the session transcript for the most used model and token count.
- It posts through the webhook. A 10-minute cooldown stops repeats, and errors never interrupt your session.

## Limits

- Claude on the web can't be detected. Only Claude Code is reported.
- Hook payloads carry no reset time, so the post doesn't include one.
- The limit type (5-hour or weekly) is guessed from the error text and may show as "usage".
- Not yet tested on Windows.
