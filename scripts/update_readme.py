#!/usr/bin/env python3
"""
Fetch latest blog posts from RSS and inject into README markers.
"""
import sys
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import requests

# Config
BASE_BLOG_URL = 'https://blog.chenxing.dev'
FEED_PATHS = ['/rss.xml']
RSS_URL = None
NUM_POSTS = 5

# Resolve README paths relative to the repository root (this script's parent folder).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
README_FILES = ['README.md', 'README-zh.md']
READMES = [os.path.join(REPO_ROOT, name) for name in README_FILES]

START_MARKER = '<!-- RECENT_BLOGS_START -->'
END_MARKER = '<!-- RECENT_BLOGS_END -->'


def fetch_posts():
    """Fetch recent posts from the site's RSS feed.

    This function attempts an HTTP GET for the site's RSS feeds.
    Returns a list of dicts with keys: 'title', 'link', 'pub', 'tags'.
    If no RSS feed is reachable or parsing fails, it
    returns None and prints the last error to stderr.
    """
    last_err = None
    for path in FEED_PATHS:
        url = BASE_BLOG_URL.rstrip('/') + path
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            items = root.findall('.//item')
            posts = []
            for item in items[:NUM_POSTS]:
                title = item.findtext('title')
                link = item.findtext('link') or BASE_BLOG_URL
                pub = item.findtext('pubDate')
                tags = [c.text.strip()
                        for c in item.findall('category') if c.text]
                posts.append({
                    'title': title if title is not None else 'Untitled',
                    'link': link,
                    'pub': pub,
                    'tags': tags,
                })
            return posts
        except (requests.exceptions.RequestException, ET.ParseError) as e:
            last_err = e
            continue
    # No RSS feed found
    print('No RSS feed found; tried paths:', [
          BASE_BLOG_URL + p for p in FEED_PATHS], file=sys.stderr)
    if last_err:
        print('Last error:', last_err, file=sys.stderr)
    return None


def render_markdown(posts, lang='en'):
    """Render the list of posts as a markdown fragment appropriate for a
    specific language.

    Args:
        posts (list[dict]): List of post dicts with 'title' and 'link'.
        lang (str): 'en' for English output, anything else yields Chinese.

    Returns:
        str: Markdown string representing the posts list (may be empty).
    """
    # If there are no posts, show a short placeholder per language.
    if not posts:
        return '\nTBA\n' if lang == 'en' else '\n暂无\n'

    def _format_date(dstr):
        """Best-effort normalize a date string to YYYY-MM-DD.

        Strategy:
        1. RFC-2822/RFC-822 via email.utils.parsedate_to_datetime (covers common
           RSS pubDate values).
        2. ISO-8601 via fromisoformat (handle trailing 'Z' specially).
        3. Small set of strptime fallbacks.
        4. Return the raw trimmed string if all parsing fails.
        """
        if not dstr:
            return ''

        # 1) RFC-2822 (e.g. 'Wed, 01 Oct 2025 00:00:00 GMT')
        try:
            dt = parsedate_to_datetime(dstr)
            return dt.date().isoformat()
        except (TypeError, ValueError):
            # parsedate_to_datetime may raise TypeError/ValueError on invalid input
            pass

        # 2) ISO-8601 via fromisoformat (Python handles most variants except 'Z')
        try:
            s = dstr.strip()
            if s.endswith('Z'):
                # fromisoformat doesn't accept trailing 'Z' — convert to +00:00
                s = s[:-1] + '+00:00'
            dt = datetime.fromisoformat(s)
            return dt.date().isoformat()
        except ValueError:
            # fromisoformat raises ValueError on parse failure
            pass

        # 3) A couple of strptime fallbacks for other common layouts
        for fmt in ('%a, %d %b %Y %H:%M:%S %z', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S'):
            try:
                dt = datetime.strptime(dstr, fmt)
                return dt.date().isoformat()
            except ValueError:
                # strptime raises ValueError if format doesn't match
                continue

        # 4) Give up: return trimmed original
        return dstr.strip()

    lines = []
    for p in posts:
        date_part = _format_date(p.get('pub'))
        tags = p.get('tags') or []
        tag_part = ''
        if tags:
            # Render up to 4 tags as inline code chips
            visible = tags[:4]
            tag_tokens = ' '.join(f'`{t}`' for t in visible)
            tag_part = f' {tag_tokens}'
        date_suffix = f" <small>({date_part})</small>" if date_part else ''
        # Small date suffix (YYYY-MM-DD) followed by tag chips
        lines.append(f"- [{p['title']}]({p['link']}){date_suffix}{tag_part}")
    lines.append('\n')
    return '\n'.join(lines)


def replace_section(path, new_section):
    """Replace the section between START_MARKER and END_MARKER in file.

    Args:
        path (str): Path to the README file to update. Can be absolute or
            relative; the caller should provide the resolved path.
        new_section (str): Markdown fragment to insert between the markers.

    Returns:
        bool: True if markers were found and file was updated, False
        otherwise (no changes made).
    """
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = re.compile(re.escape(START_MARKER) +
                         '.*?' + re.escape(END_MARKER), re.S)
    replacement = START_MARKER + '\n' + new_section + '\n' + END_MARKER
    if not pattern.search(content):
        print(f'Markers not found in {path}', file=sys.stderr)
        return False
    new_content = pattern.sub(replacement, content)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    return True


def main():
    """Main entrypoint: fetch posts and update README files.

    The function orchestrates fetching posts, rendering English and
    Chinese markdown fragments, and replacing the marked sections in
    each README. Exit codes:
      0 - success (both READMEs updated or markers replaced)
      1 - fetch failure
      2 - markers not found / file update failure
    """
    try:
        posts = fetch_posts()
    except (requests.exceptions.RequestException, ET.ParseError) as e:
        print('Failed fetching RSS:', e, file=sys.stderr)
        return 1

    # If fetch_posts returned None, no feed was found; exit without
    # updating READMEs or printing a success message.
    if posts is None:
        return 1

    md_en = render_markdown(posts, 'en')
    md_zh = render_markdown(posts, 'zh')
    ok1 = replace_section(READMES[0], md_en)
    ok2 = replace_section(READMES[1], md_zh)
    if not (ok1 and ok2):
        return 2
    # Use a timezone-aware UTC timestamp to avoid DeprecationWarning with
    # datetime.utcnow(). Use datetime.now(timezone.utc) instead.
    print('Updated READMEs with latest posts at',
          datetime.now(timezone.utc).isoformat())
    return 0


if __name__ == '__main__':
    sys.exit(main())
