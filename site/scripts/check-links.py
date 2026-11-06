"""Check the built site (dist/): every link to a page of the site, or to a file of the
repository on GitHub, must exist, and so must its #anchor.
Usage: python3 scripts/check-links.py (from site/, after npm run build)"""
import html
import pathlib
import re
import sys

SITE = pathlib.Path(__file__).resolve().parents[1]
DIST = SITE / 'dist'
REPO = SITE.parent
BASE = '/q2-offload/'
GITHUB = re.compile(r'https://github\.com/cedbossneo/q2-offload/(?:blob|tree)/main/([^#]*)')


def page_for(path):
    target = DIST / path[len(BASE):]
    return target / 'index.html' if path.endswith('/') or target.is_dir() else target


def main():
    pages = list(DIST.rglob('*.html'))
    anchors = {p: set(re.findall(r'id="([^"]+)"', p.read_text())) for p in pages}
    broken = []
    for page in pages:
        for href in map(html.unescape, re.findall(r'href="([^"]+)"', page.read_text())):
            github = GITHUB.match(href)
            if github:
                if not (REPO / github.group(1)).exists():
                    broken.append((page, href))
            elif href.startswith(BASE):
                path, _, anchor = href.partition('#')
                target = page_for(path)
                if not target.exists() or (anchor and target.suffix == '.html' and anchor not in anchors[target]):
                    broken.append((page, href))
    for page, href in broken:
        print(f'{page.relative_to(DIST)}: broken link {href}')
    print(f'{len(pages)} pages, {len(broken)} broken links')
    return 1 if broken else 0


if __name__ == '__main__':
    sys.exit(main())
