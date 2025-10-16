#!/usr/bin/env python3
"""
Fetch latest blog posts from RSS and inject into README markers.
"""
import sys
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
import requests

# Config
BASE_BLOG_URL = 'https://blog.chenxing.dev'
FEED_PATHS = ['/rss.xml', '/feed.xml', '/atom.xml', '/index.xml']
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
    """Attempt to fetch blog posts from common RSS/Atom feed locations.

    The function iterates over FEED_PATHS, attempts an HTTP GET for each
    candidate feed URL, parses the returned XML as RSS or Atom, and
    returns up to NUM_POSTS items as a list of dicts with keys: 'title',
    'link', and 'pub'. If no feed is found or parsing fails for all
    candidates, an empty list is returned. Network and parse exceptions
    are caught internally and the last error is printed to stderr.

    Returns:
        list[dict]: List of post dictionaries, possibly empty.
    """
    # Try common feed locations
    last_err = None
    for path in FEED_PATHS:
        url = BASE_BLOG_URL.rstrip('/') + path
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            items = root.findall(
                './/item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
            posts = []
            for item in items[:NUM_POSTS]:
                title = item.findtext('title') or item.find(
                    '{http://www.w3.org/2005/Atom}title')
                link = item.findtext('link')
                if not link:
                    # atom link handling
                    link_el = item.find(
                        "link[@rel='alternate']") or item.find('link')
                    if link_el is not None:
                        link = link_el.get('href') or link_el.text
                if not link:
                    link = BASE_BLOG_URL
                posts.append({'title': title if title is not None else 'Untitled',
                             'link': link, 'pub': item.findtext('pubDate')})
            return posts
        except (requests.exceptions.RequestException, ET.ParseError) as e:
            last_err = e
            continue
    # If we reach here, no feed found
    print('No RSS feed found; tried paths:', [
          BASE_BLOG_URL + p for p in FEED_PATHS], file=sys.stderr)
    if last_err:
        print('Last error:', last_err, file=sys.stderr)
    return []


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

    lines = []
    for p in posts:
        lines.append(f"- [{p['title']}]({p['link']})")
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
    md_en = render_markdown(posts, 'en')
    md_zh = render_markdown(posts, 'zh')
    ok1 = replace_section(READMES[0], md_en)
    ok2 = replace_section(READMES[1], md_zh)
    if not (ok1 and ok2):
        return 2
    print('Updated READMEs with latest posts at', datetime.utcnow().isoformat())
    return 0


if __name__ == '__main__':
    sys.exit(main())
