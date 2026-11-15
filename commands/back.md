---
description: Your limit reset early, so tell the Team Owner now
---
The user's limit is over sooner than the reminder expected.

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notify.py" status` (use `python` if `python3` is not found). If it says no limit is being waited out, tell the user and stop.
2. Otherwise run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notify.py" back`. It posts the "limit is over" message to Discord now, pinging the Team Owner, and cancels the scheduled reminder.
3. Tell the user it was sent.
