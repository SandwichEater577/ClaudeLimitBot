# ClaudeLimitBot

A Claude Code plugin that posts to a Discord channel when you hit your usage limit.

> **Ouro** reached the **5-hour** limit on Claude, using: **Claude Code**, most used model: **claude-sonnet-5-5**

The name links to your email, which shows on hover. A small card shows the limit, the model and your session's token count. Only Claude Code is reported, never the contents of your chats.

## Install

You need [Claude Code](https://claude.ai/code), Python 3 and the access password (ask whoever runs your server).

```bash
git clone https://github.com/SandwichEater577/ClaudeLimitBot.git && cd ClaudeLimitBot && ./installer
```

On Windows, run `python installer` instead of `./installer`.

A menu opens. Choose **Install**, then enter your name, email and the access password. The password unlocks the channel's webhook, which is stored encrypted in `sealed.json` (scrypt key derivation, so every guess is slow). Without the password the webhook can't be read. The installer adds the plugin to Claude Code and saves your settings to `~/.config/limit-bot/config.json`, readable only by you. Restart Claude Code afterwards. The menu can also send a test message, update the plugin or remove it.

Prefer to do it by hand? Inside Claude Code:

```
/plugin install limit-bot --marketplace SandwichEater577/ClaudeLimitBot
/limit-bot:setup YourName you@example.com
```

The webhook is never stored in this repo in plain text. To seal a new one, run `python3 scripts/vault.py seal`.

## How it works

- A `StopFailure` hook with the `rate_limit` matcher runs `scripts/notify.py`.
- The script reads the session transcript for the most used model and token count.
- It posts through the webhook. A 10-minute cooldown stops repeats, and errors never interrupt your session.

## Limits

- Claude on the web can't be detected. Only Claude Code is reported.
- Hook payloads carry no reset time, so the post doesn't include one.
- The limit type (5-hour or weekly) is guessed from the error text and may show as "usage".
- Not yet tested on Windows.
