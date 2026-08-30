"""Password hashing for the local admin account.

bcrypt, with one wrinkle worth knowing about: bcrypt only considers the first 72 bytes of input,
and the version pinned here truncates silently rather than raising. Left alone, two different
passphrases sharing a 72-byte prefix would both verify -- and a user who chose a long passphrase
would get far less security than they think they're getting.

The standard remedy, and what Django and passlib do, is to pre-hash to a fixed short digest
first. SHA-256 digested to base64 is 44 bytes, comfortably under the limit, so the whole
passphrase contributes to the result. Rejecting long passwords instead would be user-hostile
precisely for the people making the best choices.
"""

from __future__ import annotations

import base64
import hashlib

import bcrypt

#: Password hashes produced by this module carry this prefix so a future change of scheme can
#: recognise, and migrate, the old ones instead of locking everybody out.
SCHEME_PREFIX = "bcrypt-sha256$"


def _prehash(password: str) -> bytes:
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be empty")
    hashed = bcrypt.hashpw(_prehash(password), bcrypt.gensalt())
    return SCHEME_PREFIX + hashed.decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time-ish check. Returns False rather than raising for any malformed input, so a
    corrupted or hand-edited hash denies access instead of crashing the login route."""
    if not password or not password_hash:
        return False
    if not password_hash.startswith(SCHEME_PREFIX):
        return False

    stored = password_hash[len(SCHEME_PREFIX):].encode("ascii", errors="ignore")
    try:
        return bcrypt.checkpw(_prehash(password), stored)
    except (ValueError, TypeError):
        return False
