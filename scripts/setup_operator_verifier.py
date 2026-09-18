#!/usr/bin/env python3
"""
V1.6 §1: offline operator-verifier setup script.

USAGE (run by the human operator OUT OF BAND, never by an agent):
  python3 scripts/setup_operator_verifier.py <operator_id>

The script PROMPTS for the operator's plaintext approval secret
interactively (never via Hermes / Heidi / CLI args / files).

The script computes the PBKDF2 verifier and prints the
OPERATOR_APPROVAL_TOKEN_HASHES JSON value to stdout.

The operator pastes that JSON into Railway Variables tab.
The plaintext secret NEVER enters Hermes context, agent
logs, source code, or any persistent file.

ENVIRONMENT VARIABLES (output, not input):
  The script only outputs to stdout. It does not read env vars.

EXAMPLES
  $ python3 scripts/setup_operator_verifier.py christelle
  Enter approval secret for operator 'christelle':
  Confirm approval secret for operator 'christelle':
  OPERATOR_APPROVAL_TOKEN_HASHES={"christelle":{"salt":"...","hash":"...","iter":600000}}

SECURITY NOTES
  - Plaintext secret read via getpass (no echo)
  - PBKDF2-HMAC-SHA256, 32-byte random salt, 600k iterations
  - Plaintext discarded immediately after hash
  - Script does NOT touch any file system
  - Script does NOT call any network
"""
import getpass
import hashlib
import json
import os
import secrets
import sys


PBKDF2_ITER = 600_000
SALT_BYTES = 32


def _hash_secret(secret: str, salt: bytes,
                 iterations: int = PBKDF2_ITER) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        salt,
        iterations,
    )


def _build_verifier(operator_id: str, plaintext: str) -> dict:
    salt = secrets.token_bytes(SALT_BYTES)
    h = _hash_secret(plaintext, salt, PBKDF2_ITER)
    return {
        operator_id: {
            "salt": salt.hex(),
            "hash": h.hex(),
            "iter": PBKDF2_ITER,
        }
    }


def _read_existing_store() -> dict:
    """Read current Railway OPERATOR_APPROVAL_TOKEN_HASHES value from
    the local .railway-operator-tokens.json file (if present)."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".railway-operator-tokens.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.loads(f.read())
    except Exception:
        return {}


def _write_local_store(store: dict) -> None:
    """Persist the operator-tokens config to
    .railway-operator-tokens.json so the operator can copy-paste."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".railway-operator-tokens.json")
    with open(path, "w") as f:
        json.dump(store, f, indent=2, sort_keys=True)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    operator_id = argv[1].strip()
    if not operator_id:
        print("operator_id must be non-empty", file=sys.stderr)
        sys.exit(2)
    # Read existing store
    existing = _read_existing_store()
    # Prompt for secret TWICE (confirmation)
    secret1 = getpass.getpass(
        f"Enter approval secret for operator '{operator_id}': ")
    secret2 = getpass.getpass(
        f"Confirm approval secret for operator '{operator_id}': ")
    if secret1 != secret2:
        print("Secrets do not match. Aborting.", file=sys.stderr)
        sys.exit(1)
    if len(secret1) < 12:
        print("Secret must be at least 12 characters.", file=sys.stderr)
        sys.exit(1)
    # Compute verifier
    new_entry = _build_verifier(operator_id, secret1)
    # Merge into existing store
    merged = {**existing, **new_entry}
    # Write to local file
    _write_local_store(merged)
    # Output env var line for Railway paste
    env_value = "OPERATOR_APPROVAL_TOKEN_HASHES=" + json.dumps(merged)
    print("\n=== Paste this into Railway Variables tab ===")
    print(env_value)
    print("==============================================\n")
    print(f"Wrote {len(merged)} verifier(s) to "
          f".railway-operator-tokens.json")
    print(f"  - {operator_id}: NEW (just generated)")
    for k in sorted(existing.keys()):
        if k != operator_id:
            print(f"  - {k}: preserved")
    # Discard secret from memory
    secret1 = None
    secret2 = None


if __name__ == "__main__":
    main(sys.argv)
