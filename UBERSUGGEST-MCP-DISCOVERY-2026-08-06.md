# Ubersuggest MCP — Discovery Notes

**Captured:** 2026-08-06 (Wednesday)
**Author:** Heidi (orchestrator profile)
**Status:** DISCOVERY ONLY — no build, no auth, no data fetched.
**Need:** Christelle's browser-click in the OAuth flow (only human step in the whole integration).

---

## TL;DR

The Ubersuggest MCP server is at `https://ubersuggest-mcp.neilpatelapi.com/mcp`.
It's a **fully MCP-compliant OAuth 2.0 + PKCE server** with Dynamic Client Registration.
**41 tools across 8 categories** are exposed. Discovery is complete — all endpoints, schemas,
auth flow, scopes, and tool categories are mapped below. No code has been written.

**Next session I can build:** the OAuth dance (DCR + PKCE + token exchange + refresh),
the MCP JSON-RPC client, the weekly_report cross-cut, a launchd job that refreshes
keywords every 24h, and a status endpoint for the SPA. Total: ~2-3 hours.

**Blocking step (only you):** log into your Ubersuggest account in a browser tab once
to authorize the public client. ~30 seconds of clicking.

---

## Server endpoints (live-probed, 2026-08-06)

| Endpoint | URL | Purpose |
|---|---|---|
| MCP JSON-RPC | `POST https://ubersuggest-mcp.neilpatelapi.com/mcp` | The actual tool calls (`tools/list`, `tools/call`) |
| OAuth Discovery | `GET https://ubersuggest-mcp.neilpatelapi.com/.well-known/oauth-authorization-server` | RFC 8414 metadata |
| Authorize | `GET https://ubersuggest-mcp.neilpatelapi.com/authorize` | User-facing consent screen (opens in browser) |
| Token | `POST https://ubersuggest-mcp.neilpatelapi.com/token` | Code → access_token (+ refresh_token) |
| **Dynamic Client Registration** | `POST https://ubersuggest-mcp.neilpatelapi.com/register` | RFC 7591 — first call everyone makes |
| Marketing site | `GET https://ubersuggest-mcp.neilpatelapi.com/` | HTML/JS dashboard, not API |

Live discovery response (verbatim):

```json
{
  "issuer": "https://ubersuggest-mcp.neilpatelapi.com/",
  "authorization_endpoint": "https://ubersuggest-mcp.neilpatelapi.com/authorize",
  "token_endpoint": "https://ubersuggest-mcp.neilpatelapi.com/token",
  "registration_endpoint": "https://ubersuggest-mcp.neilpatelapi.com/register",
  "scopes_supported": [
    "profile", "domain", "keywords", "serp", "backlinks",
    "site_audit", "content", "projects", "utility"
  ],
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "token_endpoint_auth_methods_supported": ["none"],
  "code_challenge_methods_supported": ["S256"]
}
```

---

## OAuth flow contract (verified against live server)

### 1. Dynamic Client Registration (one-time, per installation)

```http
POST /register
Content-Type: application/json

{} (empty body is fine)
```

**Live response (verbatim):**
```json
{
  "client_id": "ubersuggest-mcp",
  "client_secret": "",
  "redirect_uris": [],
  "token_endpoint_auth_method": "none",
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "scope": "profile domain keywords serp backlinks site_audit content projects utility"
}
```

**Two things to know:**

- There is **one** `client_id` for everyone (`ubersuggest-mcp`) — they handed
  out a public wildcarded client. No real "registration" per se; the endpoint
  just tells you what's allowed. You can hardcode this in the wrapper script.

- `token_endpoint_auth_method: "none"` means the client is **public** —
  no secret, no client_secret_basic on `/token` calls. Standard for MCP
  clients (RFC 8252). PKCE is the secret.

### 2. Authorization Code + PKCE (S256 only)

```
GET https://ubersuggest-mcp.neilpatelapi.com/authorize
    ?client_id=ubersuggest-mcp
    &response_type=code
    &redirect_uri=http://127.0.0.1:<port>/callback
    &state=<random-base64>
    &scope=profile+domain+keywords+serp+backlinks+site_audit+content+projects+utility
    &code_challenge=<base64url(sha256(code_verifier))>
    &code_challenge_method=S256
```

User logs in, sees scopes, clicks "Authorize" → redirects to:

```
http://127.0.0.1:<port>/callback?code=<auth-code>&state=<state>
```

**Important constraints:**
- `code_challenge_methods_supported: ["S256"]` — `plain` is **not** allowed. Must SHA256-hash the verifier. The MCP marketing site showed this on first probe.
- `redirect_uri` should be a loopback `http://127.0.0.1:<port>/callback` (Cloudflare quick tunnel if you're remote, otherwise just `127.0.0.1`).
- `state` should be a CSRF token; verify on callback.

### 3. Token exchange

```http
POST /token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=<auth-code>
&redirect_uri=http://127.0.0.1:<port>/callback
&client_id=ubersuggest-mcp
&code_verifier=<verifier>
```

(No `client_secret` — public client + PKCE.)

**Expected response:**
```json
{
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "...",
  "scope": "profile domain keywords serp backlinks site_audit content projects utility"
}
```

(Exact token TTL not yet confirmed without running the flow. Plan for refresh ~30 min before expiry.)

### 4. Refresh

```http
POST /token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token
&refresh_token=<refresh_token>
&client_id=ubersuggest-mcp
```

(No `code_verifier` needed — refresh tokens stand alone for public clients.)

### 5. Authorize tool calls

```http
POST /mcp
Authorization: Bearer <access_token>
Content-Type: application/json
Accept: application/json, text/event-stream

{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
```

Returns the 41 tools (see below). For each call:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call",
 "params":{"name":"keyword_overview",
           "arguments":{"keyword":"indoor golf johannesburg","locId":2076,"lang":"en"}}}
```

---

## 41 tools across 8 categories

Pulled from the marketing-site JS bundle (`/assets/tools-*.js`) which embeds the
full tool registry as JS objects. Same schema JSON-RPC will return.

### 1. Keyword Research (7 tools) — **most useful for our case**

| Tool | Purpose |
|---|---|
| `keyword_overview` | Get search volume, CPC, SEO difficulty, paid difficulty for a keyword |
| `keyword_suggestions` | Related keywords + search volume |
| `keyword_metrics` | Recalculate search difficulty or search intent for a keyword (async, ~30s) |
| `serp_analysis` | Top SERP results for a keyword (URLs + ranks) |
| `match_keywords` | Match a list of keywords to your tracked project |
| `google_suggestions` | Google autocomplete suggestions for a phrase |
| `estimate_serp_clicks` | Estimate clicks from a given SERP position |

### 2. Domain Analysis (8 tools)

| Tool | Purpose |
|---|---|
| `domain_overview` | Headline domain metrics (traffic, keywords, backlinks) |
| `domain_keywords` | The organic or paid keywords a domain ranks for |
| `domain_top_pages` | Top pages on a domain by traffic |
| `domain_top_countries` | Traffic by country for a domain |
| `competitors` | Find organic competitors for a domain |
| `page_overview` | Per-page SEO + traffic metrics |
| `page_keywords` | Keywords a specific page ranks for |
| `traffic_value` | Estimated monthly traffic value |

### 3. Backlinks (5 tools)

| Tool | Purpose |
|---|---|
| `backlinks_overview` | Total backlinks, referring domains, domain authority |
| `backlinks` | List of individual backlinks (paginated, sortable) |
| `anchor_texts` | Top anchor texts used in backlinks |
| `linking_domains` | Referring domains (filter: new/lost/all) |
| `backlink_opportunity` | Find domains linking to competitors but not to you |

### 4. AI Search Visibility (3 tools) — paid accounts only

| Tool | Purpose |
|---|---|
| `brand_config` | AISV setup: tracked topics, prompts, competitors |
| `brand_visibility_overview` | AI assistant visibility %, share of voice by provider |
| `brand_prompts` | Per-prompt AISV breakdown |

### 5. Site Audit (5 tools) — paid accounts only

| Tool | Purpose |
|---|---|
| `site_audit` | Start a crawl (step 1 of 3) |
| `site_audit_status` | Poll until `result.done === true` (step 2) |
| `site_audit_results` | URLs affected by a specific issue id (step 3) |
| `site_audit_pages` | All crawled URLs list |
| `pagespeed_audit` | Core Web Vitals |

### 6. Projects (Rank Tracking) (7 tools)

| Tool | Purpose |
|---|---|
| `list_projects` | List tracked projects |
| `get_project` | Details + tracked keywords + settings |
| `create_project` | Create a new project for a domain |
| `add_project_keywords` | Add keywords to existing project |
| `add_project_competitors` | Add competitors |
| `project_position_info` | Rank tracking report per keyword per date |
| `seo_opportunities` | SEO improvement opportunities per project |

### 7. Content (2 tools)

| Tool | Purpose |
|---|---|
| `content_ideas` | Top-performing pages by social shares |
| `page_shares` | Social share counts + backlink/traffic metrics |

### 8. Utilities + Authentication + Blog (4 tools)

| Tool | Purpose |
|---|---|
| `auth_status` | Current auth state + account tier |
| `validate_site` | Is this domain/URL reachable? |
| `location_suggest` | Find `locId` (e.g. `2840` US, `2076` Brazil) |
| `location_details` | Resolve `locId` → name + parent hierarchy |
| `search_neilpatel_blog` | Search Neil Patel's blog (SEO knowledge base) |

---

## The 5 tools I expect we'll actually wire into weekly_report

Based on what `weekly_report()` currently reads + what these tools provide:

| Source file claim | New tool(s) | Daily run cost | Impact |
|---|---|---|---|
| `seo-rankings.json` → 10 keywords, all `current_rank: null` | `keyword_overview` × 10 keywords = 10 calls | ~3-5 sec total | Real rank movement data |
| Could add new SEO claims | `competitors` for `swingshack.co.za` | 1 call, async (~30s) | New "competitor gap" interpretation |
| Could add domain authority claims | `backlinks_overview` + `domain_overview` | 2 calls | Brand authority claim |
| (no source — new) | `serp_analysis` for top 3 keywords | 3 calls | New SERP structure insight |
| (no source — new) | `keyword_suggestions` for 1 seed | 1 call | "Rising keyword opportunities" claim |

That's ~17 tool calls per weekly refresh — very cheap on their quota system.
Could run nightly and cache `data/seo-rankings.json` with real numbers.

---

## What's wrong with what I told you earlier (in the checkpoint)

The CHECKPOINT-2026-08-06.md said:

> "Needs Ubersuggest MCP wired with a Bearer token..."

This was **wrong**. The screenshot Christelle sent today made it clear:
Ubersuggest is OAuth 2.0, not a static API key. The Bearer token comes
from the OAuth dance. I've patched the checkpoint doc to reflect this.

The MCP server still rejects calls without an Authorization header
(`{"error":"invalid_token","error_description":"Missing Authorization header"}`),
so the pattern looks like a Bearer token to the wrapper — but the **source**
of that token is OAuth + PKCE.

---

## Auth-required safety notes (from past Meta sessions — apply here)

These will be load-bearing when we build:

1. **Never log the `access_token` or `refresh_token` value.** Both should live
   in `~/.openclaw-instance2/workspace/clients/swing-shack/credentials/ubersuggest-api.json`
   (chmod 600, outside the repo). Log only "refreshed, expires_in=3600" — never
   the token bytes themselves.

2. **The 503-with-hint discipline applies.** When the token is missing or
   the refresh fails, return a structured 503 with `hint: "ask Heidi to run
   the Ubersuggest OAuth refresh"`. Never a bare 500.

3. **Refresh tokens can be revoked.** If the user logs out of Ubersuggest
   in their browser, the refresh token stops working. After 1-2 consecutive
   refresh failures, the script should re-prompt for the OAuth dance.

4. **`code_verifier` lifetime is short.** RFC 7636 says the verifier should
   be discarded after token exchange. Don't reuse.

5. **`redirect_uri` must match exactly.** Whatever URL we register in the
   authorize URL must match the `/token` exchange's `redirect_uri` byte-for-byte.
   `http://127.0.0.1:9999/callback` ≠ `http://localhost:9999/callback` ≠ `https://127.0.0.1:9999/callback`.

6. **`state` is mandatory and must be checked.** Don't skip it.

---

## Recommended build approach (when you say "go")

When you give me the go-ahead, the implementation path I'd take:

1. **OAuth flow script** `scripts/ubersuggest_oauth.py`
   - Stand up a temporary `127.0.0.1:<port>` HTTP server.
   - Generate `code_verifier` + `code_challenge`.
   - Open browser to `/authorize?…`.
   - Catch the redirect at `/callback?code=…&state=…`.
   - POST `/token` for `access_token` + `refresh_token`.
   - Save to `~/.openclaw-instance2/workspace/clients/swing-shack/credentials/ubersuggest-api.json` (chmod 600).
   - Verify by calling `auth_status` with the new token.
   - Exit cleanly.

2. **MCP client wrapper** `campaign-os/_lib/ubersuggest_mcp.py`
   - `urllib.request`-based JSON-RPC caller.
   - `with token refresh on 401`.
   - Typed exception hierarchy (`UbersuggestAuthError` / `UbersuggestUpstreamError`).
   - Higher-level wrappers per tool: `keyword_overview(keyword, country, lang)` etc.

3. **Refresh script** `scripts/ubersuggest_refresh_token.py`
   - Weekly launchd run (Tuesday 04:30 SAST).
   - Refreshes access_token before expiry, atomic write to credentials file.

4. **Rank-fetching script** `scripts/fetch_ubersuggest.py`
   - Runs daily at 04:30 SAST.
   - Calls `keyword_overview` for the 10 keywords in `data/seo-rankings.json`.
   - Writes real `current_rank`, `search_volume`, `keyword_difficulty`, `cpc`, `lastUpdated`.
   - Adds `rising_keywords` + `falling_keywords` (computed from rank deltas).
   - Maybe also fetches `domain_overview` + `backlinks_overview` for `swingshack.co.za`.

5. **weekly_report() integration** — extend the existing function
   - Read the populated `seo-rankings.json` (already does, but now real data).
   - Add a new claim generator for "X keywords moved up this week" (when rank delta is available).
   - Add a domain-authority claim (from `backlinks_overview`).
   - The "needs_fetcher" flag becomes false automatically.

6. **SPA surface** — `/api/intel/ubersuggest/status` companion endpoint
   - `configured` boolean (token file exists + refresh < 7d ago)
   - `connected_tier` (from `auth_status` — free / paid / etc)
   - `next_refresh_at`
   - `rate_limit_remaining` if the API exposes it

**Effort estimate:**
- OAuth flow script: 1 hour
- MCP client wrapper: 1 hour
- Refresh + rank-fetch + integration: 1-2 hours
- **Total: 3-4 hours end-to-end including tests.** Spread over 1-2 sessions.

---

## Verification checklist for next session (before any commit)

When the OAuth flow is built and I've fetched a token:

```bash
# 1. Token file exists, chmod 600, outside repo
test -r ~/.openclaw-instance2/workspace/clients/swing-shack/credentials/ubersuggest-api.json && \
  stat -f '%Sp' ~/.openclaw-instance2/workspace/clients/swing-shack/credentials/ubersuggest-api.json  # should be 0600

# 2. Token works for /mcp
TOKEN=$(python3 -c "import json; print(json.load(open('/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials/ubersuggest-api.json'))['access_token'])")
curl -sS -X POST 'https://ubersuggest-mcp.neilpatelapi.com/mcp' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"auth_status","arguments":{}}}' \
  | python3 -m json.tool

# 3. Rank pull works
curl -sS -X POST 'https://ubersuggest-mcp.neilpatelapi.com/mcp' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"keyword_overview","arguments":{"keyword":"indoor golf johannesburg","locId":2076,"lang":"en"}}}' \
  | python3 -m json.tool
```

Until all three succeed, the integration stays offline. Every step of the
build is verifiable.

---

## Pending for next session

1. **Christelle's browser click** — log into Ubersuggest once in a browser to authorize the public client. Without this, no token, no MCP, no SEO data.
2. **Confirm scope set** — `profile domain keywords serp backlinks site_audit content projects utility` are the supported scopes. For weekly_report we want at least `keywords` + `profile` (account tier check). Probably also `backlinks` for the authority claim.
3. **Confirm account tier** — tools like `site_audit` and `brand_visibility_overview` are gated behind paid accounts. Need to know if Swing Shack has free or paid before wiring those.

---

_Captured 2026-08-06 by Heidi, no code written. Backstop: this file plus CHECKPOINT-2026-08-06.md are the source of truth for "where we left off with Ubersuggest MCP."_
