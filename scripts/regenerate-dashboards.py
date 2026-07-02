#!/usr/bin/env python3
"""
regenerate-dashboards.py
Reads dashboard-live.json and injects real numbers into all static HTML dashboards.
Run after dashboard-live.json is updated (by fetch scripts or manual refresh).
"""
import json, re, pathlib, datetime

REPO = pathlib.Path(__file__).parent.parent
DATA_FILE = REPO / 'data' / 'dashboard-live.json'
SOCIAL_FILE = REPO / 'social-dashboard.html'
MKTG_FILE = REPO / 'marketing-intelligence.html'
PROGRESS_FILE = REPO / 'progress-dashboard.html'
LEAD_FILE = REPO / 'lead-engine.html'
GOLF_FILE = REPO / 'golf-news.html'
CAL_FILE = REPO / 'content-calendar.html'
UNIFIED_FILE = REPO / 'unified-dashboard-v2.html'

def load_data():
    try:
        return json.load(open(DATA_FILE))
    except Exception as e:
        print(f"⚠️  Could not load {DATA_FILE}: {e}")
        return {}

def num(n):
    """Format number with comma separators."""
    if isinstance(n, (int, float)) and n > 0:
        return f"{int(n):,}"
    return str(n)

def pct(v, mult=100, decimals=1):
    """Format as percentage."""
    if isinstance(v, (int, float)):
        return f"{v * mult:.{decimals}f}%"
    return str(v)

def safeget(d, *keys, default='--'):
    """Safe dict get."""
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d if d is not None else default

def inject(html, selectors_values):
    """Replace content at CSS selectors. selectors_values: [(selector, value), ...]"""
    for selector, value in selectors_values:
        # Match self-closing tag or open tag followed by content
        pattern = rf'(<[^>]+(?:class|id)=["\'](?:[^"\']*\s)?{re.escape(selector)}["\'][^>]*>)\s*([^<]*)\s*(?=</)'
        replacement = rf'\g<1>{value}'
        html, n = re.subn(pattern, replacement, html)
    return html

def replace_by_id(html, id_attr, value):
    """Replace inner HTML of element with given id."""
    pattern = rf'(<[^>]*\sid=["\']' + re.escape(id_attr) + r'["\'][^>]*>)\s*[^<]*(?=</)'
    html = re.sub(pattern, rf'\g<1>{value}', html)
    return html

def replace_in_text(html, label_pattern, value):
    """Find text node after a label pattern and replace the following value."""
    pattern = rf'({label_pattern}[^<]*</[^>]+>)\s*[^<]+(?=\s*</)'
    html = re.sub(pattern, rf'\g<1>{value}', html)
    return html

def fix_social(html, data):
    """Update social-dashboard.html with real IG/website data."""
    ig = data.get('instagram', {})
    ws = data.get('website', {})
    sc = data.get('searchConsole', [])
    followers = safeget(ig, 'followers', default='')
    
    # IG follower count
    html = re.sub(
        r'(<span[^>]*class=["\'][^"\']*platform-name["\'][^>]*>[^<]*Instagram[^<]*</span[^>]*>.*?<span[^>]*class=["\'][^"\']*stat-val["\'][^>]*>)[2,9][\d,]+',
        rf'\g<1>{num(followers)}' if followers else r'\g<1>--',
        html, flags=re.DOTALL
    )
    
    # TikTok followers (if we had real TikTok data, would be real)
    # Leave TikTok hardcoded for now - Postiz not connected
    
    # GA4 data into the website section
    sessions = safeget(ws, 'sessions', default='')
    users = safeget(ws, 'activeUsers', default='')
    pageviews = safeget(ws, 'pageViews', default='')
    
    # Find active users / sessions in the page
    html = re.sub(
        r'(Active Users.*?</span[^>]*>\s*<)[^<]+',
        rf'\g<1>{num(users)}' if users else r'\g<1>--',
        html, flags=re.DOTALL
    )
    
    # Top GSC query for "swing shack"
    top_query = ''
    top_clicks = ''
    top_impressions = ''
    top_position = ''
    for row in (sc if isinstance(sc, list) else []):
        if isinstance(row, dict) and row.get('query') in ('swing shack', 'swingshack'):
            top_query = row.get('query', '').title()
            top_clicks = num(row.get('clicks', 0))
            top_impressions = num(row.get('impressions', 0))
            top_position = row.get('position', '--')
            break
    
    if top_clicks:
        # Update the SEO section if it exists
        html = re.sub(
            r'(swing shack.*?clicks["\'][^>]*>\s*<)[^<]+',
            rf'\g<1>{top_clicks}',
            html, flags=re.IGNORECASE | re.DOTALL
        )
    
    # Update last refresh timestamp
    updated = data.get('lastUpdated', '')
    if updated:
        try:
            dt = datetime.datetime.fromisoformat(updated.replace('Z', '+00:00'))
            sa_time = dt.astimezone(datetime.timezone(datetime.timedelta(hours=2)))
            ts = sa_time.strftime('%d %b %Y %H:%M SAST')
            html = re.sub(r'(Last updated|Refreshed)[^<]*<[^>]*>\s*\d{1,2}\s\w+\s\d{4}.*?(?:SAST|UTC)', ts, html)
        except:
            pass
    
    return html

def fix_mktg(html, data):
    """Update marketing-intelligence.html with real data."""
    ig = data.get('instagram', {})
    ws = data.get('website', {})
    sc = data.get('searchConsole', [])
    
    followers = safeget(ig, 'followers', default='')
    posts = safeget(ig, 'posts', default='')
    
    # Replace IG pending status with real data
    if followers:
        html = re.sub(
            r'(<td[^>]*>\s*📸\s*Instagram\s*</td>\s*<td[^>]*>)[^<]*(?=</td>)',
            rf'\g<1><span style="color:var(--success)">✅ Connected</span>',
            html
        )
        # Add follower count
        html = re.sub(
            r'(Instagram.*?</td>\s*<td[^>]*>)[^<]*(?=</td>)',
            rf'\g<1>{num(followers)} followers',
            html, flags=re.DOTALL
        )
        html = re.sub(
            r'(Instagram.*?</td>\s*<td[^>]*>)[^<]*(?=</td>)',
            rf'\g<1>{num(posts)} posts',
            html, flags=re.DOTALL
        )
    
    # GA4 sessions
    sessions = safeget(ws, 'sessions', default='')
    if sessions:
        html = re.sub(
            r'(GA4.*?Sessions[^<]*</td>\s*<td[^>]*>)[^<]*(?=</td>)',
            rf'\g<1>{num(sessions)}',
            html, flags=re.IGNORECASE | re.DOTALL
        )
    
    return html

def fix_progress(html, data):
    """Update progress-dashboard.html - currently phase/status focused."""
    # Progress dashboard shows workflow status, not live metrics
    # Add last updated timestamp to show freshness
    updated = data.get('lastUpdated', '')
    if updated:
        try:
            dt = datetime.datetime.fromisoformat(updated.replace('Z', '+00:00'))
            sa = dt.astimezone(datetime.timezone(datetime.timedelta(hours=2)))
            ts = sa.strftime('%d %b %H:%M SAST')
            # Look for a footer or timestamp element
            footer = re.search(r'(<div[^>]*class=["\'][^"\']*footer[^"\']*["\'][^>]*>)(.*?)(?=</div>)', html, re.IGNORECASE | re.DOTALL)
            if footer:
                html = html.replace(footer.group(0), footer.group(0) + f'<span style="color:var(--text-muted)">Data: {ts}</span>')
            else:
                # Append to header subtitle
                html = re.sub(r'(<p[^>]*>Data-driven.*?</p>)', rf'\g<1>\n<span style="color:var(--text-muted);font-size:0.8em">Last updated: {ts}</span>', html, flags=re.IGNORECASE)
        except:
            pass
    return html

def fix_lead_engine(html, data):
    """Update lead-engine.html - links to data/leads.json which may not exist."""
    # Replace broken data/leads.json link with graceful message
    html = re.sub(
        r'(fetch\s*\(\s*["\']data/leads\.json["\']\s*\).*?catch.*?\(.*?\)\s*\{)(.*?)(\})',
        r'\g<1>document.getElementById("leads-body").innerHTML=\'<tr><td colspan=5 style="color:var(--warning)">📋 Lead data pending — Connect Reddit API or import manually</td></tr>\';\g<3>',
        html, flags=re.DOTALL
    )
    
    # Update with real GA4 sessions as a lead quality signal
    ws = data.get('website', {})
    sessions = safeget(ws, 'sessions', default='')
    if sessions:
        # Add sessions to the stats bar
        html = re.sub(
            r'(Total Leads.*?</div>\s*</div>\s*<div[^>]*class=["\'][^"\']*stat-box[^"\']*["\'][^>]*>\s*<div[^>]*class=["\'][^"\']*stat-number["\'][^>]*>)\s*\d+\s*(?=</)',
            rf'\g<1>{num(sessions)}',
            html
        )
    
    return html

def fix_golf_news(html, data):
    """Golf News is sourced from Golf News data file, not dashboard-live.json."""
    # Try to load golf-news.json for fresh content
    golf_file = REPO / 'data' / 'golf-news.json'
    if golf_file.exists():
        try:
            golf_data = json.load(open(golf_file))
            news = golf_data.get('news', [])
            if news:
                # Replace static headlines with real ones
                items_html = ''
                for item in news[:5]:
                    title = item.get('title', '')[:80]
                    source = item.get('source', 'Golf News')
                    url = item.get('url', '#')
                    items_html += f'<li><a href="{url}" target="_blank">{title}</a> <span style="color:var(--muted)">— {source}</span></li>\n'
                if items_html:
                    html = re.sub(r'<li>.*?⛳\s*SA Tour News.*?</li>', items_html, html, flags=re.DOTALL)
        except Exception as e:
            print(f"Golf news parse error: {e}")
    return html

def fix_content_calendar(html, data):
    """Content Calendar - workflow state, not live metrics. Show data freshness."""
    updated = data.get('lastUpdated', '')
    if updated:
        try:
            dt = datetime.datetime.fromisoformat(updated.replace('Z', '+00:00'))
            sa = dt.astimezone(datetime.timezone(datetime.timedelta(hours=2)))
            ts = sa.strftime('%d %b %H:%M SAST')
            # Add timestamp near the title
            html = re.sub(
                r'(Content Calendar.*?</h1>)',
                rf'\g<1> <span style="color:var(--muted);font-size:0.7em">· {ts}</span>',
                html, flags=re.IGNORECASE
            )
        except:
            pass
    return html

def fix_unified(html, data):
    """Update unified-dashboard-v2.html with real metrics."""
    ig = data.get('instagram', {})
    ws = data.get('website', {})
    sc = data.get('searchConsole', [])
    
    followers = safeget(ig, 'followers', default='')
    posts = safeget(ig, 'posts', default='')
    sessions = safeget(ws, 'sessions', default='')
    users = safeget(ws, 'activeUsers', default='')
    
    # Update follower count
    if followers:
        html = re.sub(
            r'(<[^>]+class=["\'][^"\']*followers["\'][^>]*>)\s*[0-9,NA-]+\s*(?=</)',
            rf'\g<1>{num(followers)}',
            html
        )
    
    # Update posts count
    if posts:
        html = re.sub(
            r'(<[^>]+class=["\'][^"\']*totalPosts["\'][^>]*>)\s*[0-9,NA-]+\s*(?=</)',
            rf'\g<1>{num(posts)}',
            html
        )
    
    # Update sessions
    if sessions:
        html = re.sub(
            r'(<[^>]+class=["\'][^"\']*stat-num["\'][^>]*>)\s*[0-9,NA-]+\s*(?=</)',
            rf'\g<1>{num(sessions)}',
            html
        )
    
    # Update top GSC keyword
    for row in (sc if isinstance(sc, list) else []):
        if isinstance(row, dict) and row.get('query') == 'swing shack':
            pos = row.get('position', '--')
            clicks = num(row.get('clicks', 0))
            html = re.sub(
                r'(<[^>]+class=["\'][^"\']*topKeyword["\'][^>]*>)\s*[0-9.#-]+\s*(?=</)',
                rf'\g<1>#{pos} "{row.get("query","swing shack")}" · {clicks} clicks',
                html
            )
            break
    
    return html

def main():
    data = load_data()
    updated = data.get('lastUpdated', 'unknown')
    print(f"Regenerating dashboards from data: {updated}")
    
    # Social
    if SOCIAL_FILE.exists():
        html = SOCIAL_FILE.read_text()
        html = fix_social(html, data)
        SOCIAL_FILE.write_text(html)
        print(f"  ✅ social-dashboard.html")
    
    # Marketing Intelligence
    if MKTG_FILE.exists():
        html = MKTG_FILE.read_text()
        html = fix_mktg(html, data)
        MKTG_FILE.write_text(html)
        print(f"  ✅ marketing-intelligence.html")
    
    # Progress
    if PROGRESS_FILE.exists():
        html = PROGRESS_FILE.read_text()
        html = fix_progress(html, data)
        PROGRESS_FILE.write_text(html)
        print(f"  ✅ progress-dashboard.html")
    
    # Lead Engine
    if LEAD_FILE.exists():
        html = LEAD_FILE.read_text()
        html = fix_lead_engine(html, data)
        LEAD_FILE.write_text(html)
        print(f"  ✅ lead-engine.html")
    
    # Golf News
    if GOLF_FILE.exists():
        html = GOLF_FILE.read_text()
        html = fix_golf_news(html, data)
        GOLF_FILE.write_text(html)
        print(f"  ✅ golf-news.html")
    
    # Content Calendar
    if CAL_FILE.exists():
        html = CAL_FILE.read_text()
        html = fix_content_calendar(html, data)
        CAL_FILE.write_text(html)
        print(f"  ✅ content-calendar.html")
    
    # Unified v2
    if UNIFIED_FILE.exists():
        html = UNIFIED_FILE.read_text()
        html = fix_unified(html, data)
        UNIFIED_FILE.write_text(html)
        print(f"  ✅ unified-dashboard-v2.html")
    
    print(f"\nDone. Last data: {updated}")

if __name__ == '__main__':
    main()
