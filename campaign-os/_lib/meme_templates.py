"""Meme template catalog with public thumbnail URLs.

Every entry has:
  - id: stable slug used by Meme Lord
  - name: display name (e.g. "Drake Hotline Bling")
  - tier: "iconic" | "trending" | "classic" — surfaces in picker order
  - text_zones: typical caption slots (top/bottom, left/right, etc.)
  - thumbnail_url: public image URL (Wikipedia, imgflip CDN, or stable)
  - source: where the thumbnail came from (attribution)
  - brand_fit: dict with { tone: ['golf','sports','lifestyle'], energy: 'low'|'medium'|'high' }

Why public URLs: we don't host these ourselves (no licensing risk, no disk),
and we don't generate previews on every page load (slow). The UI fetches
and caches the thumbnail in localStorage after first load. Meme Lord itself
composes the actual text — these templates are only for visual reference.

Attribution: thumbnails are sourced from imgflip (imgflip.com) which makes
them available for meme generation. We display them as small reference
thumbnails under fair use (no modification, no large-scale scraping).
"""
from __future__ import annotations
from typing import Any

# Stable public thumbnail URLs. Imgflip CDN paths are deterministic
# (`/s/memes/<slug>.jpg`) and don't require auth. We cap usage at 30
# templates so the picker stays scannable.
_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "drake-hotline-bling",
        "name": "Drake Hotline Bling",
        "tier": "iconic",
        "text_zones": ["top:reject", "bottom:prefer"],
        "thumbnail_url": "https://i.imgflip.com/30b1gx.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["lifestyle", "opinion"], "energy": "low"},
    },
    {
        "id": "distracted-boyfriend",
        "name": "Distracted Boyfriend",
        "tier": "iconic",
        "text_zones": ["left:partner", "middle:boyfriend", "right:other"],
        "thumbnail_url": "https://i.imgflip.com/1ur9b0.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["lifestyle", "humor"], "energy": "medium"},
    },
    {
        "id": "woman-yelling-at-cat",
        "name": "Woman Yelling at Cat",
        "tier": "iconic",
        "text_zones": ["left:woman", "right:cat"],
        "thumbnail_url": "https://i.imgflip.com/345v97.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["opinion", "argument"], "energy": "high"},
    },
    {
        "id": "this-is-fine",
        "name": "This Is Fine",
        "tier": "iconic",
        "text_zones": ["caption:dismissive"],
        "thumbnail_url": "https://i.imgflip.com/w7n1z.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["self-deprecating", "situational"], "energy": "low"},
    },
    {
        "id": "two-buttons",
        "name": "Two Buttons",
        "tier": "iconic",
        "text_zones": ["button1", "button2"],
        "thumbnail_url": "https://i.imgflip.com/1g8my4.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["decision", "dilemma"], "energy": "low"},
    },
    {
        "id": "expanding-brain",
        "name": "Expanding Brain",
        "tier": "iconic",
        "text_zones": ["panel1:basic", "panel2:smart", "panel3:galaxy", "panel4:cosmic"],
        "thumbnail_url": "https://i.imgflip.com/1jwhww.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["escalation", "satire"], "energy": "low"},
    },
    {
        "id": "success-kid",
        "name": "Success Kid",
        "tier": "classic",
        "text_zones": ["top:setup", "bottom:win"],
        "thumbnail_url": "https://i.imgflip.com/1bhk.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["win", "achievement"], "energy": "high"},
    },
    {
        "id": "awkward-look-monkey",
        "name": "Awkward Look Monkey Puppet",
        "tier": "classic",
        "text_zones": ["top:situation", "bottom:reaction"],
        "thumbnail_url": "https://i.imgflip.com/26am.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["awkward", "social"], "energy": "low"},
    },
    {
        "id": "uno-draw-25",
        "name": "UNO Draw 25 Cards",
        "tier": "trending",
        "text_zones": ["caption:consequence"],
        "thumbnail_url": "https://i.imgflip.com/3pnmg.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["punchline", "reversal"], "energy": "medium"},
    },
    {
        "id": "change-my-mind",
        "name": "Change My Mind",
        "tier": "trending",
        "text_zones": ["signer:claim"],
        "thumbnail_url": "https://i.imgflip.com/24y43o.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["opinion", "bold-claim"], "energy": "medium"},
    },
    {
        "id": "left-exit-12",
        "name": "Left Exit 12 Off Ramp",
        "tier": "trending",
        "text_zones": ["left:leaving", "right:staying"],
        "thumbnail_url": "https://i.imgflip.com/2dt0py.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["choice", "exit"], "energy": "low"},
    },
    {
        "id": "buff-doge-vs-cheems",
        "name": "Buff Doge vs Cheems",
        "tier": "trending",
        "text_zones": ["left:past", "right:now"],
        "thumbnail_url": "https://i.imgflip.com/43a45p.png",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["before-after", "growth"], "energy": "low"},
    },
    {
        "id": "trade-offer",
        "name": "Trade Offer (Side Eye Chloe)",
        "tier": "trending",
        "text_zones": ["caption:skeptical"],
        "thumbnail_url": "https://i.imgflip.com/5lu4xu.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["skeptical", "evaluation"], "energy": "low"},
    },
    {
        "id": "always-has-been",
        "name": "Always Has Been (Astronaut)",
        "tier": "trending",
        "text_zones": ["astronaut:wait", "other:always"],
        "thumbnail_url": "https://i.imgflip.com/3l60ph.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["revelation", "punchline"], "energy": "medium"},
    },
    {
        "id": "bernie-asking",
        "name": "Bernie Asking For Support",
        "tier": "trending",
        "text_zones": ["caption:solicit"],
        "thumbnail_url": "https://i.imgflip.com/4sx6gp.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["solicit", "request"], "energy": "low"},
    },
    {
        "id": "pigeon-butterfly",
        "name": "Is This a Pigeon",
        "tier": "iconic",
        "text_zones": ["man:question", "labeler:false-id"],
        "thumbnail_url": "https://i.imgflip.com/2dt0py.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["misidentification", "satire"], "energy": "low"},
    },
    {
        "id": "ancient-aliens",
        "name": "Ancient Aliens Guy",
        "tier": "classic",
        "text_zones": ["caption:conspiracy"],
        "thumbnail_url": "https://i.imgflip.com/26gn.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["conspiracy", "mystery"], "energy": "low"},
    },
    {
        "id": "roll-safe",
        "name": "Roll Safe (Think About It)",
        "tier": "classic",
        "text_zones": ["top:setup", "bottom:flawed-logic"],
        "thumbnail_url": "https://i.imgflip.com/1h7n3i.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["smart-but-dumb"], "energy": "low"},
    },
    {
        "id": "disaster-girl",
        "name": "Disaster Girl",
        "tier": "classic",
        "text_zones": ["caption:menace"],
        "thumbnail_url": "https://i.imgflip.com/1ihxfe.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["menace", "scheming"], "energy": "medium"},
    },
    {
        "id": "doge",
        "name": "Doge",
        "tier": "iconic",
        "text_zones": ["top:wow", "bottom:much-X", "etc:very-Y"],
        "thumbnail_url": "https://i.imgflip.com/4t0m5.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["hype", "praise"], "energy": "low"},
    },
    {
        "id": "hide-the-pain-harold",
        "name": "Hide the Pain Harold",
        "tier": "classic",
        "text_zones": ["caption:stoic-pain"],
        "thumbnail_url": "https://i.imgflip.com/2kbn1e.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["stoic", "suffering"], "energy": "low"},
    },
    {
        "id": "futurama-fry",
        "name": "Futurama Fry (Squinting)",
        "tier": "classic",
        "text_zones": ["caption:suspicious"],
        "thumbnail_url": "https://i.imgflip.com/268k3j.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["suspicious", "doubt"], "energy": "low"},
    },
    {
        "id": "salt-bae",
        "name": "Salt Bae",
        "tier": "trending",
        "text_zones": ["caption:snatched"],
        "thumbnail_url": "https://i.imgflip.com/3i5gei.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["flex", "premium"], "energy": "medium"},
    },
    {
        "id": "galaxy-brain",
        "name": "Galaxy Brain",
        "tier": "trending",
        "text_zones": ["caption:enlightened"],
        "thumbnail_url": "https://i.imgflip.com/4kf4l3.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["enlightened", "epiphany"], "energy": "low"},
    },
    {
        "id": "we-did-it-joe",
        "name": "We Did It Joe",
        "tier": "trending",
        "text_zones": ["caption:celebration"],
        "thumbnail_url": "https://i.imgflip.com/3lmrqf.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["win", "celebration"], "energy": "high"},
    },
    {
        "id": "surprised-pikachu",
        "name": "Surprised Pikachu",
        "tier": "iconic",
        "text_zones": ["caption:obvious-consequence"],
        "thumbnail_url": "https://i.imgflip.com/2kbn1e.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["obvious", "predictable"], "energy": "low"},
    },
    {
        "id": "side-eye-chloe",
        "name": "Side Eye Chloe",
        "tier": "trending",
        "text_zones": ["caption:doubtful"],
        "thumbnail_url": "https://i.imgflip.com/5lu4xu.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["judgment", "doubt"], "energy": "low"},
    },
    {
        "id": "monkey-looking-suspicious",
        "name": "Suspicious Monkey",
        "tier": "classic",
        "text_zones": ["caption:side-eye"],
        "thumbnail_url": "https://i.imgflip.com/26am.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["suspicious"], "energy": "low"},
    },
    {
        "id": "this-is-where-id-put-my-trophy",
        "name": "If I Fits I Sits",
        "tier": "trending",
        "text_zones": ["caption:achievement"],
        "thumbnail_url": "https://i.imgflip.com/4sx6gp.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["win", "pride"], "energy": "medium"},
    },
    {
        "id": "crying-cat",
        "name": "Crying Cat",
        "tier": "trending",
        "text_zones": ["caption:sad-but-true"],
        "thumbnail_url": "https://i.imgflip.com/345v97.jpg",
        "source": "imgflip.com",
        "brand_fit": {"tone": ["sad", "vulnerable"], "energy": "low"},
    },
]


def list_templates() -> list[dict[str, Any]]:
    """Return the full catalog (sorted: iconic → trending → classic)."""
    tier_order = {"iconic": 0, "trending": 1, "classic": 2}
    return sorted(_TEMPLATES, key=lambda t: (tier_order.get(t["tier"], 9), t["name"]))


def get_template(template_id: str) -> dict[str, Any] | None:
    for t in _TEMPLATES:
        if t["id"] == template_id:
            return t
    return None