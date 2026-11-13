---
description: Check limit-bot is set up and post a preview to the Discord channel
---
Check the limit-bot setup for this user.

1. If `~/.config/limit-bot/config.json` does not exist, tell the user to run the installer from the ClaudeLimitBot folder (`./installer`, or `python installer` on Windows) and stop.
2. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notify.py" test` (use `python` if `python3` is not found).
3. Tell the user to look at the Discord channel: a preview of the limit message was posted, and nobody was pinged.
