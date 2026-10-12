#!/usr/bin/env python3
"""UserPromptSubmit: if the prompt matches wiki pages, tell Claude which to read. No LLM, no network."""
import json, os, re, sys, pathlib
if os.environ.get("CAMPAIGNOS_KB_HOOKS", "on") == "off": sys.exit(0)
root = pathlib.Path(os.environ.get("CAMPAIGNOS_KB_ROOT") or pathlib.Path.home() / "CampaignOSKnowledgeBase")
if not (root / "CampaignOS").is_dir(): sys.exit(0)
try: prompt = json.load(sys.stdin).get("prompt", "")
except Exception: sys.exit(0)
STOP = set("this that with from have what when where which about into your they them then than will would could should there their been were does just like want need make some more also only over okay please check look find using used campaign".split())
words = {w.rstrip("s") for w in re.findall(r"[a-z0-9]{4,}", prompt.lower()) if w not in STOP}
if len(words) < 2: sys.exit(0)
hits = []
for p in (root / "CampaignOS").rglob("*.md"):
    if p.name in ("index.md", "log.md") or p.name.startswith("_") or "selftest" in p.name: continue
    head = p.read_text(errors="ignore")[:1200].lower()
    m = re.search(r"^title:\s*(.+)$", head, re.M); title = m.group(1).strip() if m else p.stem
    t = re.search(r"^tags:\s*(.+)$", head, re.M)
    hay = " ".join([p.stem.replace("-", " "), title.lower(), t.group(1) if t else ""])
    hay = re.sub(r"(\w)s\b", r"\1", hay)
    score = sum(1 for w in words if w in hay)
    if score >= 2: hits.append((score, str(p.relative_to(root)), title))
if not hits: sys.exit(0)
hits.sort(reverse=True)
print("Campaign OS wiki pages that look relevant to this prompt (read before answering if useful):")
for _, path, title in hits[:5]: print(f"  - {root / path}  ({title})")
