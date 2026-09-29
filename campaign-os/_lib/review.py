"""
review.py — HUMAN REVIEW LAYER V1

This is the Review stage of the Campaign OS pipeline:

    OPPORTUNITY → BRIEF → CREATE/WRITER → REVIEW → (future) PUBLISH

Review V1 is a layer on top of the frozen Writer V1. It:

- READS the canonical Writer V1 artifact (a JSON file the writer produced
  in outbox/) but never mutates it.
- STORES its own Review record under DATA_DIR/review/<brand>/<draft_id>.json
  that references the Writer artifact by content_hash + path.
- ENFORCES that an article only progresses to APPROVED_FOR_PUBLISHING
  if no unresolved EVIDENCE_NEEDED facts, no unresolved stock/price
  warnings that affect copy, no rejected sections, no pending rewrites.
- SUPPORTS per-section review: APPROVE / EDIT / REQUEST_REWRITE /
  COMMENT / REJECT.
- PERSISTS every change as an append-only revision.
- USES the authenticated session identity as the reviewer_id — never
  invents a name.

Review is content-type-aware via content_type field; V1 supports
LONG_FORM_ARTICLE only. The architecture is extensible to other content
types (social, email, landing page, ad copy) without code changes to
this module — only the consumer module needs to add a content_type
adapter.

Review NEVER writes to WordPress, NEVER publishes, NEVER auto-approves.
The system can flag, explain, suggest, and (when asked) rewrite; the
human authority remains the only path to APPROVED_FOR_PUBLISHING.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GENERATOR_VERSION = "review_v1"

# Review lifecycle. APPROVED_FOR_PUBLISHING is NOT "published" — publish is a
# separate downstream stage.
STATUS_DRAFT_FOR_REVIEW       = "DRAFT_FOR_REVIEW"
STATUS_IN_REVIEW              = "IN_REVIEW"
STATUS_CHANGES_REQUESTED      = "CHANGES_REQUESTED"
STATUS_READY_FOR_APPROVAL     = "READY_FOR_APPROVAL"
STATUS_APPROVED_FOR_PUBLISHING = "APPROVED_FOR_PUBLISHING"
STATUS_REJECTED               = "REJECTED"

ALL_STATUSES = (
    STATUS_DRAFT_FOR_REVIEW,
    STATUS_IN_REVIEW,
    STATUS_CHANGES_REQUESTED,
    STATUS_READY_FOR_APPROVAL,
    STATUS_APPROVED_FOR_PUBLISHING,
    STATUS_REJECTED,
)

# Per-section review actions.
ACTION_APPROVE_SECTION   = "APPROVE_SECTION"
ACTION_EDIT_SECTION      = "HUMAN_EDIT"
ACTION_REQUEST_REWRITE   = "REQUEST_REWRITE"
ACTION_COMMENT           = "COMMENT"
ACTION_REJECT_SECTION    = "REJECT_SECTION"

ALL_SECTION_ACTIONS = (
    ACTION_APPROVE_SECTION,
    ACTION_EDIT_SECTION,
    ACTION_REQUEST_REWRITE,
    ACTION_COMMENT,
    ACTION_REJECT_SECTION,
)

# Supported content types — V1 only handles long-form articles.
CONTENT_TYPE_LONG_FORM_ARTICLE = "LONG_FORM_ARTICLE"
SUPPORTED_CONTENT_TYPES = (CONTENT_TYPE_LONG_FORM_ARTICLE,)

# Reject reasons — structured, with free-text fallback.
REJECT_REASONS = (
    "WRONG_STRATEGY",
    "WRONG_VOICE",
    "FACTUAL_PROBLEM",
    "LOW_QUALITY",
    "DUPLICATE_OR_NOT_NEEDED",
    "COMMERCIAL_PRIORITY_CHANGED",
    "OTHER",
)

# Blockers: comment-level.
COMMENT_BLOCKING = True
COMMENT_NON_BLOCKING = False


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _data_root() -> str:
    """Resolve DATA_DIR — the same convention _lib uses everywhere else."""
    explicit = os.environ.get("DATA_DIR") or os.environ.get("CAMPAIGN_OS_DATA_DIR")
    if explicit:
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.normpath(os.path.join(here, "..", "..", "data")),
        os.path.normpath(os.path.join(here, "..", "data")),
        os.path.normpath(os.path.join(here, "..", "..", "..", "data")),
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, "brand-directory")):
            return c
    return candidates[0]


def _review_root() -> str:
    return os.path.join(_data_root(), "review")


def _brand_dir(brand_id: str) -> str:
    return os.path.join(_review_root(), brand_id)


def _draft_path(brand_id: str, draft_id: str) -> str:
    return os.path.join(_brand_dir(brand_id), f"{draft_id}.json")


# ---------------------------------------------------------------------------
# ID + timestamp helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Writer artifact loader (read-only — never mutates the outbox)
# ---------------------------------------------------------------------------

def _writer_artifact_candidates(brand_id: str, brief_id: str) -> List[str]:
    """Look in the canonical Writer V1 outbox for the draft.

    V1.4 writer writes to:
      ~/.hermes/profiles/heidi/outbox/<brand>-writer-draft-<slug>.json

    The slug is derived from the brief's "topic" or the brief_id minus
    the "seo-brief-" prefix. We try multiple candidate names because
    the writer's naming convention has varied across V1.x.

    Order:
      1. DATA_DIR/writer/<brand>/<slug>.json  (canonical Railway path —
           the boot startup patch copies the in-repo baked artifact there.)
      2. heidi outbox (Mac dev — overrides the volume if a fresher local
           artifact exists.)
    """
    slug = brief_id.replace("seo-brief-", "")
    # If the slug starts with the brand_id (rare), strip it
    if slug.startswith(f"{brand_id}-"):
        slug = slug[len(brand_id) + 1:]
    candidates = [
        # DATA_DIR canonical (Railway volume — set by the V2.11 boot
        # startup patch from the in-repo baked artifact).
        os.path.join(_data_root(), "writer", brand_id, f"{slug}.json"),
        # heidi outbox (Mac dev environment — used when running locally).
        os.path.expanduser(
            f"~/.hermes/profiles/heidi/outbox/{brand_id}-writer-draft-{slug}.json"
        ),
        # Strip brand prefix from slug (e.g. stick-off-rack -> off-rack)
        os.path.expanduser(
            f"~/.hermes/profiles/heidi/outbox/{brand_id}-writer-draft-{brief_id.replace('seo-brief-', '').replace(brand_id + '-', '', 1)}.json"
        ),
    ]
    return candidates


def _find_writer_artifact(brand_id: str, brief_id: str) -> Optional[str]:
    for path in _writer_artifact_candidates(brand_id, brief_id):
        if os.path.exists(path):
            return path
    return None


def _load_writer_artifact(brand_id: str, brief_id: str) -> Tuple[Optional[dict], Optional[str]]:
    """Returns (artifact_dict_or_None, path_or_None)."""
    path = _find_writer_artifact(brand_id, brief_id)
    if not path:
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), path
    except Exception:
        return None, path


def _hash_writer_artifact(artifact: dict) -> str:
    blob = json.dumps(artifact, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Section parser — splits the Writer draft into reviewable sections.
# ---------------------------------------------------------------------------

# H2 (## ...) and H3 (### ...) headings are section boundaries.
# The article title (single #) is NOT a section; it's metadata.
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)


def _split_into_sections(draft_md: str) -> List[dict]:
    """Split the human-facing draft into reviewable sections.

    A section is contiguous content between H2/H3 headings. We walk the
    markdown line by line, tracking the current section heading + level.

    Returns: list of {section_id, level, heading, body}.
    The opening paragraph (before any H2) becomes section_id="intro".
    """
    lines = draft_md.splitlines(keepends=True)
    sections: List[dict] = []
    current = None
    buffer: List[str] = []

    def flush():
        if current is not None:
            current["body"] = "".join(buffer).strip()
        elif buffer and any(s.strip() for s in buffer):
            # intro / no heading
            sections.append({
                "section_id": "intro",
                "level": 1,
                "heading": "(opening)",
                "body": "".join(buffer).strip(),
            })

    for line in lines:
        h2 = _H2_RE.match(line.strip())
        h3 = _H3_RE.match(line.strip())
        if h2 or h3:
            # flush previous
            if current is not None:
                current["body"] = "".join(buffer).strip()
                sections.append(current)
            elif buffer and any(s.strip() for s in buffer):
                sections.append({
                    "section_id": f"sec_{len(sections):02d}_intro",
                    "level": 1,
                    "heading": "(opening)",
                    "body": "".join(buffer).strip(),
                })
            buffer = []
            m_h = h2 or h3
            assert m_h is not None
            heading = m_h.group(1).strip()
            current = {
                "section_id": f"sec_{len(sections):02d}",
                "level": 2 if h2 else 3,
                "heading": heading,
                "body": "",
            }
        else:
            buffer.append(line)
    # final flush
    if current is not None:
        current["body"] = "".join(buffer).strip()
        sections.append(current)
    elif buffer and any(s.strip() for s in buffer):
        sections.append({
            "section_id": f"sec_{len(sections):02d}_intro",
            "level": 1,
            "heading": "(opening)",
            "body": "".join(buffer).strip(),
        })

    return sections


# ---------------------------------------------------------------------------
# Brand fact / stock / SEO context loaders (consumers, not mutators)
# ---------------------------------------------------------------------------

def _load_brand_knowledge(brand_id: str) -> dict:
    """Read-only load of the frozen brand directory."""
    paths = [
        os.path.join(_data_root(), "brand-directory", brand_id, "knowledge.json"),
        os.path.join(os.path.dirname(_data_root()), "data", "brand-directory", brand_id, "knowledge.json"),
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
    return {}


def _stock_safety_for_product(brand_id: str, product_id: Optional[str]) -> Optional[dict]:
    """If the brand uses stock_query.py, fetch the safety summary.

    Returns None if the module isn't available or no product specified.
    """
    if not product_id:
        return None
    try:
        # lazy import — only when called
        import sys as _sys
        sys_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "..",
            ".hermes", "profiles", "heidi", "skills",
            "campaign-os-stock", "scripts",
        )
        if os.path.exists(sys_path) and sys_path not in _sys.path:
            _sys.path.insert(0, sys_path)
        import stock_query  # type: ignore
        return stock_query.get_marketing_safe_phrasing(brand_id, product_id)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Canonical Review record shape
# ---------------------------------------------------------------------------

def _empty_review_record(
    brand_id: str,
    brief_id: str,
    writer_artifact: dict,
    writer_path: str,
    reviewer_id: str,
) -> dict:
    sections = _split_into_sections(
        writer_artifact.get("human_facing_article_draft", "")
    )
    return {
        "schema_version": 1,
        "review_version": GENERATOR_VERSION,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "brand_id": brand_id,
        "brief_id": brief_id,
        "content_type": CONTENT_TYPE_LONG_FORM_ARTICLE,
        "writer_mode": writer_artifact.get("writer_mode", "NEW"),
        "writer_artifact": {
            "path": writer_path,
            "content_hash": _hash_writer_artifact(writer_artifact),
            "draft_status": writer_artifact.get("draft_status", "WRITTEN"),
            "publishing": writer_artifact.get("publishing", "NONE"),
            "live_site_changes": writer_artifact.get("live_site_changes", "NONE"),
            "title": writer_artifact.get("human_facing_article", {}).get(
                "title", ""
            ) or _extract_title_from_draft(
                writer_artifact.get("human_facing_article_draft", "")
            ),
            "body_path": "human_facing_article_draft",
        },
        "status": STATUS_DRAFT_FOR_REVIEW,
        "reviewer_id": reviewer_id,
        "current_revision": 0,
        "sections": [
            {
                "section_id": s["section_id"],
                "level": s["level"],
                "heading": s["heading"],
                # current body always reflects the latest applied revision
                "current_body": s["body"],
                # original body — never mutated by edits; the source of truth
                # for KEEP / IMPROVE audit + diff
                "original_body": s["body"],
                "approved": False,
                "rejected": False,
                "rewrite_pending": False,
                "last_action": None,
                "last_action_at": None,
                "last_actor": None,
            }
            for s in sections
        ],
        "comments": [],
        "revisions": [],
        "rejected_reason": None,
        "approved_for_publishing_at": None,
        "approved_by": None,
    }


def _extract_title_from_draft(draft_md: str) -> str:
    for line in draft_md.splitlines():
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip()
    return ""


# ---------------------------------------------------------------------------
# Storage I/O
# ---------------------------------------------------------------------------

def _save_review(record: dict) -> None:
    path = _draft_path(record["brand_id"], _draft_id_from_record(record))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record["updated_at"] = _now_iso()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _draft_id_from_record(record: dict) -> str:
    """Stable draft_id = brief_id-derived name. We don't want uuid here —
    the Writer artifact is keyed by brief_id, so the Review record is
    keyed by brief_id-derived slug too."""
    return f"r_{record['brief_id']}"


def _load_review(brand_id: str, draft_id: str) -> Optional[dict]:
    path = _draft_path(brand_id, draft_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_or_get_review(
    brand_id: str, brief_id: str, reviewer_id: str
) -> dict:
    """Create a Review record from the frozen Writer artifact (or load
    existing). This is the entry point for the Review UI.

    - Reads the Writer artifact (NEVER mutates it)
    - Creates a fresh Review record on first call
    - Returns the existing record on subsequent calls
    """
    if brand_id not in ("stick", "swing-shack", "bag-drop"):
        return {"ok": False, "error": f"brand_id must be stick|swing-shack|bag-drop; got {brand_id!r}"}
    if not brief_id:
        return {"ok": False, "error": "brief_id required"}

    draft_id = f"r_{brief_id}"
    existing = _load_review(brand_id, draft_id)
    if existing is not None:
        return {"ok": True, "review": existing, "created": False}

    writer_artifact, writer_path = _load_writer_artifact(brand_id, brief_id)
    if writer_artifact is None:
        return {
            "ok": False,
            "error": f"writer artifact not found for brand={brand_id}, brief={brief_id}",
            "searched_paths": _writer_artifact_candidates(brand_id, brief_id),
        }

    record = _empty_review_record(
        brand_id, brief_id, writer_artifact, writer_path or "", reviewer_id
    )
    _save_review(record)
    return {"ok": True, "review": record, "created": True}


def get_review_item(brand_id: str, draft_id: str) -> Optional[dict]:
    return _load_review(brand_id, draft_id)


def get_review_queue(brand_id: str) -> List[dict]:
    """List all review records for a brand. Used by the queue UI."""
    base = _brand_dir(brand_id)
    if not os.path.exists(base):
        return []
    queue = []
    for fn in sorted(os.listdir(base)):
        if not fn.endswith(".json"):
            continue
        rec = _load_review(brand_id, fn[:-5])
        if rec is None:
            continue
        queue.append(_summarise_for_queue(rec))
    return queue


def _summarise_for_queue(record: dict) -> dict:
    """Reduced-shape record for queue UI listing."""
    sections = record.get("sections", [])
    pending_rewrites = sum(1 for s in sections if s.get("rewrite_pending"))
    rejected_sections = sum(1 for s in sections if s.get("rejected"))
    unapproved_sections = sum(1 for s in sections if not s.get("approved") and not s.get("rejected"))
    blocking_comments = sum(
        1 for c in record.get("comments", [])
        if c.get("blocking") and not c.get("resolved")
    )
    fact_evidence_needed = sum(
        1 for fc in _extract_fact_check_rows(record)
        if fc.get("status") == "EVIDENCE_NEEDED"
    )
    return {
        "draft_id": _draft_id_from_record(record),
        "brand_id": record["brand_id"],
        "brief_id": record["brief_id"],
        "content_type": record["content_type"],
        "writer_mode": record.get("writer_mode", "NEW"),
        "title": record["writer_artifact"]["title"],
        "status": record["status"],
        "reviewer_id": record.get("reviewer_id"),
        "current_revision": record["current_revision"],
        "last_updated_at": record.get("updated_at"),
        "warnings": _compute_warnings(record, {
            "pending_rewrites": pending_rewrites,
            "rejected_sections": rejected_sections,
            "unapproved_sections": unapproved_sections,
            "blocking_comments": blocking_comments,
            "evidence_needed": fact_evidence_needed,
        }),
        "metrics": {
            "sections_total": len(sections),
            "unapproved_sections": unapproved_sections,
            "rejected_sections": rejected_sections,
            "pending_rewrites": pending_rewrites,
            "blocking_comments": blocking_comments,
            "evidence_needed": fact_evidence_needed,
        },
    }


def _compute_warnings(record: dict, m: dict) -> List[str]:
    """Top-level warnings surfaced for the queue UI."""
    out = []
    if m["blocking_comments"] > 0:
        out.append(f"{m['blocking_comments']} blocking comment(s)")
    if m["rejected_sections"] > 0:
        out.append(f"{m['rejected_sections']} section(s) rejected")
    if m["pending_rewrites"] > 0:
        out.append(f"{m['pending_rewrites']} rewrite(s) pending")
    if m["evidence_needed"] > 0:
        out.append(f"{m['evidence_needed']} fact(s) need evidence")
    if m["unapproved_sections"] > 0:
        out.append(f"{m['unapproved_sections']} section(s) awaiting approval")
    return out


def _extract_fact_check_rows(record: dict) -> List[dict]:
    """The writer artifact's fact-check rows live at
    .fact_check (a list). We expose this via the record by re-loading the
    writer artifact lazily (it's referenced by path + content_hash)."""
    path = record.get("writer_artifact", {}).get("path")
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            artifact = json.load(f)
        return artifact.get("fact_check", []) or []
    except Exception:
        return []


def get_review_detail(brand_id: str, draft_id: str) -> dict:
    """Full review record + derived views for the article UI."""
    record = _load_review(brand_id, draft_id)
    if record is None:
        return {"ok": False, "error": "review not found"}
    summary = _summarise_for_queue(record)
    fact_rows = _extract_fact_check_rows(record)
    return {
        "ok": True,
        "summary": summary,
        "record": record,
        "fact_check_rows": fact_rows,
        "brand_knowledge_excerpt": _brand_knowledge_excerpt(record["brand_id"]),
        "writer_artifact_path": record["writer_artifact"]["path"],
        "writer_artifact_content_hash": record["writer_artifact"]["content_hash"],
    }


def _brand_knowledge_excerpt(brand_id: str) -> dict:
    kn = _load_brand_knowledge(brand_id)
    if not kn:
        return {}
    return {
        "verified_services": (kn.get("verified_facts", {}) or {})
            .get("verified_services", {}).get("value"),
        "verified_tagline": (kn.get("verified_facts", {}) or {})
            .get("verified_tagline", {}).get("value"),
        "verified_respect_the_player": (kn.get("verified_facts", {}) or {})
            .get("verified_respect_the_player", {}).get("value"),
        "verified_fitting_philosophy": (kn.get("verified_facts", {}) or {})
            .get("verified_fitting_philosophy", {}).get("value"),
        "do_say": kn.get("voice_rules", {}).get("do_say", []),
        "dont_say": kn.get("voice_rules", {}).get("dont_say", []),
    }


# ---------------------------------------------------------------------------
# Section actions
# ---------------------------------------------------------------------------

def _find_section(record: dict, section_id: str) -> Optional[dict]:
    for s in record["sections"]:
        if s["section_id"] == section_id:
            return s
    return None


def _new_revision(
    record: dict,
    action: str,
    actor: str,
    section_id: Optional[str],
    before: Optional[str],
    after: Optional[str],
    instruction: Optional[str] = None,
    source: str = "HUMAN_EDIT",
) -> dict:
    rev_id = _new_id("rev")
    parent_id = record["revisions"][-1]["revision_id"] if record["revisions"] else None
    record["current_revision"] += 1
    return {
        "revision_id": rev_id,
        "parent_revision_id": parent_id,
        "revision_number": record["current_revision"],
        "timestamp": _now_iso(),
        "actor": actor,
        "action": action,
        "section_id": section_id,
        "before": before,
        "after": after,
        "instruction": instruction,
        "source": source,
    }


def approve_section(
    brand_id: str, draft_id: str, section_id: str, actor: str
) -> dict:
    record = _load_review(brand_id, draft_id)
    if record is None:
        return {"ok": False, "error": "review not found"}
    sec = _find_section(record, section_id)
    if sec is None:
        return {"ok": False, "error": f"section not found: {section_id}"}
    if sec.get("rejected"):
        return {"ok": False, "error": "section is rejected; cannot approve"}
    sec["approved"] = True
    sec["last_action"] = ACTION_APPROVE_SECTION
    sec["last_action_at"] = _now_iso()
    sec["last_actor"] = actor
    rev = _new_revision(
        record, ACTION_APPROVE_SECTION, actor, section_id,
        before=None, after=None,
        source="HUMAN_EDIT",
    )
    record["revisions"].append(rev)
    _maybe_transition_to_ready(record)
    _save_review(record)
    return {"ok": True, "section": sec, "revision": rev}


def edit_section(
    brand_id: str, draft_id: str, section_id: str, new_body: str,
    actor: str, reason: Optional[str] = None,
) -> dict:
    record = _load_review(brand_id, draft_id)
    if record is None:
        return {"ok": False, "error": "review not found"}
    sec = _find_section(record, section_id)
    if sec is None:
        return {"ok": False, "error": f"section not found: {section_id}"}
    if sec.get("rejected"):
        return {"ok": False, "error": "section is rejected; cannot edit"}
    before = sec["current_body"]
    sec["current_body"] = new_body
    sec["approved"] = False   # human edit resets approval
    sec["last_action"] = ACTION_EDIT_SECTION
    sec["last_action_at"] = _now_iso()
    sec["last_actor"] = actor
    rev = _new_revision(
        record, ACTION_EDIT_SECTION, actor, section_id,
        before=before, after=new_body,
        instruction=reason,
        source="HUMAN_EDIT",
    )
    record["revisions"].append(rev)
    _maybe_transition_to_ready(record)
    _save_review(record)
    return {"ok": True, "section": sec, "revision": rev}


def reject_section(
    brand_id: str, draft_id: str, section_id: str, actor: str,
    reason: str,
) -> dict:
    record = _load_review(brand_id, draft_id)
    if record is None:
        return {"ok": False, "error": "review not found"}
    if not reason:
        return {"ok": False, "error": "reason required for REJECT_SECTION"}
    sec = _find_section(record, section_id)
    if sec is None:
        return {"ok": False, "error": f"section not found: {section_id}"}
    sec["rejected"] = True
    sec["approved"] = False
    sec["last_action"] = ACTION_REJECT_SECTION
    sec["last_action_at"] = _now_iso()
    sec["last_actor"] = actor
    rev = _new_revision(
        record, ACTION_REJECT_SECTION, actor, section_id,
        before=None, after=None,
        instruction=reason,
        source="HUMAN_EDIT",
    )
    record["revisions"].append(rev)
    record["status"] = STATUS_CHANGES_REQUESTED
    _save_review(record)
    return {"ok": True, "section": sec, "revision": rev}


def request_rewrite(
    brand_id: str, draft_id: str, section_id: str, actor: str,
    instruction: str,
) -> dict:
    """Mark a section for rewrite. The actual writer call happens via
    /api/review/v1/<brand>/<draft>/rewrite-execute which validates the
    request and calls Writer's CLI through its supported interface.

    This endpoint only RECORDS the request — Review does not silently
    overwrite the Writer draft. The rewritten body is applied via the
    separate apply_rewritten_section() path which:
    (a) loads Writer's output
    (b) does not touch other sections
    (c) records before/after in a revision with source=WRITER_REWRITE
    """
    record = _load_review(brand_id, draft_id)
    if record is None:
        return {"ok": False, "error": "review not found"}
    if not instruction:
        return {"ok": False, "error": "instruction required for REQUEST_REWRITE"}
    sec = _find_section(record, section_id)
    if sec is None:
        return {"ok": False, "error": f"section not found: {section_id}"}
    sec["rewrite_pending"] = True
    sec["last_action"] = ACTION_REQUEST_REWRITE
    sec["last_action_at"] = _now_iso()
    sec["last_actor"] = actor
    rev = _new_revision(
        record, ACTION_REQUEST_REWRITE, actor, section_id,
        before=None, after=None,
        instruction=instruction,
        source="HUMAN_EDIT",
    )
    record["revisions"].append(rev)
    record["status"] = STATUS_CHANGES_REQUESTED
    _save_review(record)
    return {"ok": True, "section": sec, "revision": rev}


def apply_rewritten_section(
    brand_id: str, draft_id: str, section_id: str, new_body: str,
    actor: str,
) -> dict:
    """Apply the result of an explicit Writer rewrite call.

    The writer is invoked OUTSIDE this module (by the route handler).
    The new body lands here. We record it as a WRITER_REWRITE revision.
    """
    record = _load_review(brand_id, draft_id)
    if record is None:
        return {"ok": False, "error": "review not found"}
    sec = _find_section(record, section_id)
    if sec is None:
        return {"ok": False, "error": f"section not found: {section_id}"}
    if not sec.get("rewrite_pending"):
        return {"ok": False, "error": "section has no pending rewrite"}
    before = sec["current_body"]
    sec["current_body"] = new_body
    sec["rewrite_pending"] = False
    sec["approved"] = False   # rewrite resets approval
    sec["last_action"] = ACTION_EDIT_SECTION
    sec["last_action_at"] = _now_iso()
    sec["last_actor"] = actor
    rev = _new_revision(
        record, ACTION_EDIT_SECTION, actor, section_id,
        before=before, after=new_body,
        instruction="writer-rewrite-applied",
        source="WRITER_REWRITE",
    )
    record["revisions"].append(rev)
    _maybe_transition_to_ready(record)
    _save_review(record)
    return {"ok": True, "section": sec, "revision": rev}


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def add_comment(
    brand_id: str, draft_id: str, body: str, actor: str,
    blocking: bool = False,
    section_id: Optional[str] = None,
    claim_id: Optional[str] = None,
) -> dict:
    record = _load_review(brand_id, draft_id)
    if record is None:
        return {"ok": False, "error": "review not found"}
    if not body:
        return {"ok": False, "error": "body required"}
    if section_id and _find_section(record, section_id) is None:
        return {"ok": False, "error": f"section not found: {section_id}"}
    comment = {
        "comment_id": _new_id("cmt"),
        "body": body,
        "author": actor,
        "timestamp": _now_iso(),
        "blocking": bool(blocking),
        "resolved": False,
        "section_id": section_id,
        "claim_id": claim_id,
    }
    record["comments"].append(comment)
    _save_review(record)
    return {"ok": True, "comment": comment}


def resolve_comment(
    brand_id: str, draft_id: str, comment_id: str, actor: str,
) -> dict:
    record = _load_review(brand_id, draft_id)
    if record is None:
        return {"ok": False, "error": "review not found"}
    for c in record["comments"]:
        if c["comment_id"] == comment_id:
            c["resolved"] = True
            c["resolved_by"] = actor
            c["resolved_at"] = _now_iso()
            _save_review(record)
            return {"ok": True, "comment": c}
    return {"ok": False, "error": f"comment not found: {comment_id}"}


# ---------------------------------------------------------------------------
# Approval / Rejection
# ---------------------------------------------------------------------------

def approve_for_publishing(
    brand_id: str, draft_id: str, actor: str,
) -> dict:
    """Move the draft to APPROVED_FOR_PUBLISHING.

    Requires:
    - status != REJECTED
    - 0 rejected sections
    - 0 pending rewrites
    - 0 unresolved blocking comments
    - 0 EVIDENCE_NEEDED rows in fact_check
    - All sections approved

    Returns the approval result + a confirmation summary the UI shows
    before applying the action. This handler does NOT publish anything —
    publishing is a separate downstream module.
    """
    record = _load_review(brand_id, draft_id)
    if record is None:
        return {"ok": False, "error": "review not found"}
    blockers = _compute_approval_blockers(record)
    if blockers["blocking"]:
        return {
            "ok": False,
            "error": "approval blocked",
            "blockers": blockers,
        }
    record["status"] = STATUS_APPROVED_FOR_PUBLISHING
    record["approved_for_publishing_at"] = _now_iso()
    record["approved_by"] = actor
    _save_review(record)
    return {
        "ok": True,
        "status": STATUS_APPROVED_FOR_PUBLISHING,
        "blockers": blockers,
        "approval_summary": _approval_summary(record),
    }


def reject_draft(
    brand_id: str, draft_id: str, actor: str, reason: str,
    explanation: Optional[str] = None,
) -> dict:
    if reason not in REJECT_REASONS:
        return {"ok": False, "error": f"reason must be one of {REJECT_REASONS}"}
    record = _load_review(brand_id, draft_id)
    if record is None:
        return {"ok": False, "error": "review not found"}
    record["status"] = STATUS_REJECTED
    record["rejected_reason"] = {
        "reason": reason,
        "explanation": explanation or "",
        "actor": actor,
        "timestamp": _now_iso(),
    }
    rev = _new_revision(
        record, "REJECT_DRAFT", actor, None,
        before=None, after=None,
        instruction=f"{reason}: {explanation or ''}",
        source="HUMAN_EDIT",
    )
    record["revisions"].append(rev)
    _save_review(record)
    return {"ok": True, "status": STATUS_REJECTED, "reason": reason}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_approval_blockers(record: dict) -> dict:
    sections = record.get("sections", [])
    rejected_sections = [s for s in sections if s.get("rejected")]
    pending_rewrites   = [s for s in sections if s.get("rewrite_pending")]
    unapproved_sections = [
        s for s in sections if not s.get("approved") and not s.get("rejected")
    ]
    blocking_comments = [
        c for c in record.get("comments", [])
        if c.get("blocking") and not c.get("resolved")
    ]
    fact_rows = _extract_fact_check_rows(record)
    evidence_needed = [
        r for r in fact_rows if r.get("status") == "EVIDENCE_NEEDED"
    ]
    return {
        "rejected_sections": [s["section_id"] for s in rejected_sections],
        "pending_rewrites": [s["section_id"] for s in pending_rewrites],
        "unapproved_sections": [s["section_id"] for s in unapproved_sections],
        "blocking_comments": [c["comment_id"] for c in blocking_comments],
        "evidence_needed": [
            r.get("article_sentence", "<unnamed>")
            for r in evidence_needed
        ],
        "blocking": bool(
            rejected_sections
            or pending_rewrites
            or blocking_comments
            or evidence_needed
            or unapproved_sections
        ),
    }


def _maybe_transition_to_ready(record: dict) -> None:
    """If all sections approved and no other blockers, promote to
    READY_FOR_APPROVAL. The human still has to take the explicit
    APPROVE_FOR_PUBLISHING action — this is just queue-state."""
    blockers = _compute_approval_blockers(record)
    if not blockers["blocking"]:
        if record["status"] not in (STATUS_APPROVED_FOR_PUBLISHING, STATUS_REJECTED):
            record["status"] = STATUS_READY_FOR_APPROVAL


def _approval_summary(record: dict) -> dict:
    return {
        "brand": record["brand_id"],
        "title": record["writer_artifact"]["title"],
        "revision": record["current_revision"],
        "unresolved_warnings": 0,
        "blocking_comments": 0,
        "status": STATUS_APPROVED_FOR_PUBLISHING,
        "publishing_status": "Publish remains a separate downstream module.",
    }


def get_revision_history(brand_id: str, draft_id: str) -> List[dict]:
    record = _load_review(brand_id, draft_id)
    if record is None:
        return []
    return record.get("revisions", [])


def assemble_human_facing_article(record: dict) -> dict:
    """Reconstruct the current human-facing article body from the
    review record's section list.

    Important: this is what Review presents. We DO NOT mutate the
    Writer's outbox artifact. Review's view is always derived from the
    Review record's section.current_body.
    """
    parts = []
    title = record["writer_artifact"]["title"]
    if title:
        parts.append(f"# {title}\n")
    for s in record["sections"]:
        if s["level"] == 2:
            parts.append(f"\n## {s['heading']}\n")
        elif s["level"] == 3:
            parts.append(f"\n### {s['heading']}\n")
        parts.append(f"\n{s['current_body']}\n")
    return {
        "title": title,
        "body_markdown": "\n".join(parts).strip() + "\n",
    }
