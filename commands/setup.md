---
description: Set your display name, email and Discord webhook for limit-bot
argument-hint: <display name> <email>
---
Set up limit-bot for this user.

1. Take the display name and email from the arguments: $ARGUMENTS. If either is missing, ask for it.
2. The webhook URL is a secret and must not be pasted into chat. If `$DISCORD_WEBHOOK` is not set, tell the user to quit, set it (Linux/macOS: `export DISCORD_WEBHOOK="<url>"`, Windows PowerShell: `$env:DISCORD_WEBHOOK="<url>"`), start `claude` again and rerun this command.
3. Run (use `python` if `python3` is not found): `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notify.py" setup --name "<name>" --email "<email>"`
4. Then run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notify.py" test` and tell the user to check the Discord channel.
