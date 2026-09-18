#!/usr/bin/env python3
"""
V1.6 §1: agent-only test operator verifier generator.

This script is for THE AGENT (Heidi/Hermes/Foreman) to compute
a disposable verifier for automated testing. The plaintext
test secret is in code by design — it is throwaway and
isolated from production operator credentials.

USAGE
  python3 scripts/generate_test_operator_verifier.py > test_operator_verifier.json

OUTPUT (stdout, JSON only):
  {"test_operator": {"salt": "...", "hash": "...", "iter": 600000}}

The agent pastes this into Railway Variables tab as the
test_operator entry of OPERATOR_APPROVAL_TOKEN_HASHES.

DO NOT USE THIS SCRIPT FOR PRODUCTION OPERATOR CREDENTIALS.
Production operator secrets must be set up by the human
operator via scripts/setup_operator_verifier.py.
"""
import hashlib
import json
import secrets

PBKDF2_ITER = 600_000
SALT_BYTES = 32

# Disposable test-only secret. This is intentionally known to
# the agent so that automated tests can authenticate. It must
# NEVER be used for production operator credentials.
TEST_OPERATOR_ID = "test_operator"
TEST_OPERATOR_SECRET = "test_operator_disposable_secret_v1"


def _hash_secret(secret: str, salt: bytes,
                 iterations: int = PBKDF2_ITER) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        salt,
        iterations,
    )


def main():
    salt = secrets.token_bytes(SALT_BYTES)
    h = _hash_secret(TEST_OPERATOR_SECRET, salt, PBKDF2_ITER)
    out = {
        TEST_OPERATOR_ID: {
            "salt": salt.hex(),
            "hash": h.hex(),
            "iter": PBKDF2_ITER,
        }
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
