#!/usr/bin/env python3
with open('scripts/generate-production-plan.py', 'rb') as f:
    content = f.read()

# Fix 1: build_prompt function - strategy.get() call
old1 = b"**Primary Offer:** {campaign.get('strategy', {{}}).get('primaryOffer', '\xe2\x80\x94')}"
new1 = b"**Primary Offer:** {(campaign.get('strategy') or {}).get('primaryOffer', '\xe2\x80\x94')}"
content = content.replace(old1, new1)
print("Fix 1:", "OK" if old1 not in content else "FAILED")

# Fix 2: pp.get() in print statement
old2 = b'f\'{pp.get("assetRequirements",{{}}).get("total",0)} assets, \''
new2 = b'f\'{(pp.get("assetRequirements") or {{}}).get("total",0)} assets, \''
if old2 in content:
    content = content.replace(old2, new2)
    print("Fix 2 (pp.get): OK")
else:
    print("Fix 2 (pp.get): NOT FOUND")

# Fix 3-7: ar.get() patterns
replacements = {
    b'feedPosts': b"(ar.get('feedPosts') or {})",
    b'carousels': b"(ar.get('carousels') or {})",
    b'reels': b"(ar.get('reels') or {})",
    b'stories': b"(ar.get('stories') or {})",
    b'gmbPosts': b"(ar.get('gmbPosts') or {})",
}

for key, replacement in replacements.items():
    old = "ar.get('" + key.decode() + "',{{}}).get('count','?')".encode()
    new = replacement + b".get('count','?')"
    if old in content:
        content = content.replace(old, new)
        print(f"Fix ar.get('{key.decode()}'): OK")
    else:
        print(f"Fix ar.get('{key.decode()}'): NOT FOUND")

with open('scripts/generate-production-plan.py', 'wb') as f:
    f.write(content)

# Verify syntax
import py_compile
try:
    py_compile.compile('scripts/generate-production-plan.py', doraise=True)
    print("Syntax check: PASS")
except py_compile.PyCompileError as e:
    print(f"Syntax error: {e}")