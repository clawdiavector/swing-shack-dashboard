/**
 * scripts/_lib/postiz-credentials.js
 *
 * Shared credential loader for the Postiz API key.
 *
 * Resolution order:
 *   1. process.env.POSTIZ_API_KEY_FILE  (path to a JSON file with {"api_key": "..."})
 *   2. process.env.POSTIZ_API_KEY      (raw key value)
 *
 * On success: returns the key string. NEVER logs the value — only its length
 * and which source it came from.
 *
 * On failure: throws an Error with a clear missing-credential message.
 *
 * This file deliberately contains NO fallback key, NO default value,
 * and does not auto-discover credentials by globbing the filesystem.
 *
 * Canonical credential file (configured by env var, NOT hardcoded here):
 *   /Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials/postiz-api-key.json
 *
 * The path is supplied by the caller (script-level constant or env var)
 * so this helper stays reusable across worktrees and alternative deployments.
 */

'use strict';

const fs = require('fs');

function loadPostizApiKey() {
  const fromFile = process.env.POSTIZ_API_KEY_FILE;
  if (fromFile && fromFile.trim().length > 0) {
    let parsed;
    try {
      parsed = JSON.parse(fs.readFileSync(fromFile, 'utf8'));
    } catch (e) {
      throw new Error(
        `[postiz-credentials] POSTIZ_API_KEY_FILE="${fromFile}" could not be read: ${e.message}`
      );
    }
    if (!parsed || typeof parsed.api_key !== 'string' || parsed.api_key.length === 0) {
      throw new Error(
        `[postiz-credentials] File at POSTIZ_API_KEY_FILE="${fromFile}" does not contain a non-empty "api_key" field.`
      );
    }
    return { apiKey: parsed.api_key, source: `file:${fromFile}`, length: parsed.api_key.length };
  }

  const fromEnv = process.env.POSTIZ_API_KEY;
  if (fromEnv && fromEnv.trim().length > 0) {
    return { apiKey: fromEnv, source: 'env:POSTIZ_API_KEY', length: fromEnv.length };
  }

  throw new Error(
    '[postiz-credentials] No Postiz credential configured. ' +
    'Set POSTIZ_API_KEY_FILE (path to JSON file with {"api_key": "..."}) ' +
    'or POSTIZ_API_KEY environment variable.'
  );
}

module.exports = { loadPostizApiKey };