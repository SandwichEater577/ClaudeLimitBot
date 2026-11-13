#!/usr/bin/env python3
"""Password vault for the webhook: scrypt key derivation + HMAC-SHA256 stream cipher
with an encrypt-then-MAC tag. Standard library only.

    python3 scripts/vault.py seal      # encrypt your webhook into sealed.json
"""
import base64, getpass, hashlib, hmac, json, os, sys
from pathlib import Path

N, R, P = 2**18, 8, 1  # about 256 MiB of memory and a second or two per guess
SEALED = Path(__file__).resolve().parent.parent / "sealed.json"
b64 = lambda b: base64.b64encode(b).decode()


def _keys(password, salt, n):
    k = hashlib.scrypt(password.encode(), salt=salt, n=n, r=R, p=P, maxmem=1 << 30, dklen=64)
    return k[:32], k[32:]


def _stream(key, nonce, length):
    out, i = b"", 0
    while len(out) < length:
        out += hmac.new(key, nonce + i.to_bytes(8, "big"), "sha256").digest()
        i += 1
    return out[:length]


def seal(password, text, n=N):
    salt, nonce, pt = os.urandom(16), os.urandom(16), text.encode()
    ek, mk = _keys(password, salt, n)
    ct = bytes(a ^ b for a, b in zip(pt, _stream(ek, nonce, len(pt))))
    tag = hmac.new(mk, salt + nonce + ct, "sha256").digest()
    return {"v": 1, "n": n, "salt": b64(salt), "nonce": b64(nonce), "ct": b64(ct), "tag": b64(tag)}


def unseal(password, d):
    salt, nonce, ct, tag = (base64.b64decode(d[k]) for k in ("salt", "nonce", "ct", "tag"))
    ek, mk = _keys(password, salt, d["n"])
    if not hmac.compare_digest(hmac.new(mk, salt + nonce + ct, "sha256").digest(), tag):
        raise ValueError("wrong password")
    return bytes(a ^ b for a, b in zip(ct, _stream(ek, nonce, len(ct)))).decode()


def main():
    if sys.argv[1:] != ["seal"]:
        sys.exit(__doc__)
    cfg = Path.home() / ".config/limit-bot/config.json"
    hook = os.environ.get("DISCORD_WEBHOOK") or (json.loads(cfg.read_text())["webhook"] if cfg.exists() else "")
    if not hook.startswith("https://discord.com/api/webhooks/"):
        sys.exit("No webhook found. Run the installer setup first, or set DISCORD_WEBHOOK.")
    pw = os.environ.get("LB_PASSWORD") or getpass.getpass("New password: ")
    if len(pw) < 12:
        sys.exit("Use at least 12 characters. A long passphrase is best, because the file is public.")
    if "LB_PASSWORD" not in os.environ and getpass.getpass("Repeat password: ") != pw:
        sys.exit("Passwords do not match.")
    SEALED.write_text(json.dumps(seal(pw, hook), indent=1) + "\n")
    assert unseal(pw, json.loads(SEALED.read_text())) == hook
    print("Sealed ->", SEALED)


if __name__ == "__main__":
    main()
