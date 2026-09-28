import json, os, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'products.json'
ASSET = ROOT / 'assets' / 'products'
ASSET.mkdir(parents=True, exist_ok=True)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'
S = requests.Session()
S.headers.update({'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'})
BAD = ('avatar', 'logo', 'icon', 'emoji', 'profile', 'favicon', 'badge', 'social', 'qr-code')
IMG_EXTS = ('.jpg', '.jpeg', '.png', '.webp')


def log(msg=''):
    print(msg, flush=True)


def absu(u, base):
    if not u:
        return None
    u = u.strip().replace('\\/', '/')
    if u.startswith('//'):
        return 'https:' + u
    return urljoin(base, u)


def add(out, u):
    if not u:
        return
    u = u.strip().rstrip('.,')
    low = u.lower()
    if low.startswith('data:') or any(x in low for x in BAD):
        return
    out.append(u)


def extract_images(text, base):
    out = []
    soup = BeautifulSoup(text, 'html.parser')
    for img in soup.find_all('img'):
        for a in ('src', 'data-src', 'data-original', 'data-lazy-src'):
            add(out, absu(img.get(a), base))
        ss = img.get('srcset') or img.get('data-srcset')
        if ss:
            for part in ss.split(','):
                add(out, absu(part.strip().split()[0], base))
    for m in soup.select('meta[property="og:image"],meta[name="twitter:image"],meta[property="og:image:url"]'):
        add(out, absu(m.get('content'), base))
    seen = set()
    good = []
    for u in out:
        if not u or u in seen:
            continue
        seen.add(u)
        low = u.lower()
        if any(x in low for x in ('/models/', '/model/', '/user/', '/search', '/collections/')) and not any(x in low for x in ('media.', 'image.', 'cdn.')):
            continue
        good.append(u)
    good.sort(key=lambda u: (0 if any(h in u.lower() for h in ('media.printables.com', 'makerworld.com', 'cdn.', 'images.')) else 1, len(u)))
    return good


def reader_urls(src):
    return [
        'https://r.jina.ai/' + src,
        ('https://r.jina.ai/http://' + src.split('://', 1)[1]) if '://' in src else None,
    ]


def fetch_source(src):
    for u in reader_urls(src) + [src]:
        if not u:
            continue
        try:
            r = S.get(u, timeout=18, allow_redirects=True)
            if r.ok and len(r.text) > 500:
                return r.text, r.url
        except Exception:
            pass
    return '', src


def download(u, path, referer):
    try:
        r = S.get(u, timeout=12, allow_redirects=True, headers={'Referer': referer})
        r.raise_for_status()
        ct = (r.headers.get('content-type') or '').lower()
        data = r.content
        if not ct.startswith('image/') or len(data) < 10000 or len(data) > 12_000_000:
            return False
        path.write_bytes(data)
        return True
    except Exception:
        return False


def browser_candidates(page, src):
    """Return real image URLs exposed by the rendered source page."""
    candidates = []
    try:
        page.evaluate('window.scrollTo(0, document.body.scrollHeight * 0.22)')
        page.wait_for_timeout(350)
        page.evaluate('window.scrollTo(0, document.body.scrollHeight * 0.58)')
        page.wait_for_timeout(450)
        page.evaluate('window.scrollTo(0, document.body.scrollHeight * 0.88)')
        page.wait_for_timeout(450)
        page.evaluate('window.scrollTo(0, 0)')
        page.wait_for_timeout(300)

        # Prefer OpenGraph image first: it is normally the actual model/product image.
        for selector in ('meta[property="og:image"]', 'meta[property="og:image:url"]', 'meta[name="twitter:image"]'):
            val = page.locator(selector).first.get_attribute('content', timeout=1500)
            if val:
                candidates.append(absu(val, page.url))

        imgs = page.locator('img')
        count = min(imgs.count(), 100)
        for i in range(count):
            try:
                el = imgs.nth(i)
                box = el.bounding_box()
                if not box or box['width'] < 180 or box['height'] < 120:
                    continue
                alt = (el.get_attribute('alt', timeout=500) or '').lower()
                vals = [
                    el.get_attribute('src', timeout=500),
                    el.get_attribute('data-src', timeout=500),
                    el.get_attribute('data-original', timeout=500),
                ]
                ss = el.get_attribute('srcset', timeout=500) or el.get_attribute('data-srcset', timeout=500)
                if ss:
                    vals.append(ss.split(',')[-1].strip().split()[0])
                for val in vals:
                    u = absu(val, page.url)
                    if not u:
                        continue
                    low = (u + ' ' + alt).lower()
                    if any(x in low for x in BAD):
                        continue
                    candidates.append(u)
            except Exception:
                continue
    except Exception:
        pass

    seen = set()
    result = []
    for u in candidates:
        if not u or u in seen:
            continue
        seen.add(u)
        low = u.lower()
        if low.startswith('data:'):
            continue
        result.append(u)
    return result[:30]


def browser_capture(page, src, dest, max_images=3):
    """Use one persistent Chromium page to capture real gallery images.
    Returns the number of images saved. No synthetic images are created.
    """
    browser_src = re.sub(r'/files/?$', '', src)
    try:
        page.goto(browser_src, wait_until='domcontentloaded', timeout=25000)
        page.wait_for_timeout(1800)
    except Exception as e:
        log(f'  browser: {type(e).__name__}')
        return 0

    candidates = browser_candidates(page, src)
    got = 0
    seen_urls = set()

    # First try direct downloads of the real image URLs exposed by the browser.
    for u in candidates:
        if got >= max_images:
            break
        if u in seen_urls:
            continue
        seen_urls.add(u)
        ext = Path(urlparse(u).path).suffix.lower()
        if ext not in IMG_EXTS:
            ext = '.jpg'
        target = dest / f'{got + 1}{ext}'
        if download(u, target, browser_src):
            got += 1

    # If the source blocks direct downloads, screenshot the actual rendered image element.
    if got < max_images:
        try:
            imgs = page.locator('img')
            count = min(imgs.count(), 100)
            for i in range(count):
                if got >= max_images:
                    break
                try:
                    el = imgs.nth(i)
                    box = el.bounding_box()
                    if not box or box['width'] < 180 or box['height'] < 120:
                        continue
                    srcv = el.get_attribute('src', timeout=500) or el.get_attribute('data-src', timeout=500) or ''
                    alt = (el.get_attribute('alt', timeout=500) or '').lower()
                    low = (srcv + ' ' + alt).lower()
                    if any(x in low for x in BAD) or srcv in seen_urls:
                        continue
                    el.scroll_into_view_if_needed(timeout=2000)
                    page.wait_for_timeout(150)
                    target = dest / f'{got + 1}.jpg'
                    el.screenshot(path=str(target), type='jpeg', quality=92, timeout=5000)
                    if target.exists() and target.stat().st_size > 10000:
                        got += 1
                except Exception:
                    continue
        except Exception:
            pass

    return got


def clean_old_assets(dest):
    for f in dest.iterdir():
        if f.is_file() and f.suffix.lower() in IMG_EXTS:
            f.unlink(missing_ok=True)


d = json.loads(DATA.read_text(encoding='utf-8'))
products = d.get('products', [])
log(f'Starting photo refresh for {len(products)} products')
log('Browser strategy: one Chromium instance reused across the full catalogue')

summary = []

try:
    from playwright.sync_api import sync_playwright
except Exception as e:
    raise SystemExit(f'Playwright is unavailable: {e}')

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1100}, user_agent=UA)
    page = context.new_page()
    page.set_default_timeout(4000)
    page.set_default_navigation_timeout(25000)

    for idx, p in enumerate(products, 1):
        pid = p.get('id', f'product-{idx}')
        name = p.get('name', pid)
        src = p.get('sourceUrl') or p.get('source')
        log(f'[{idx}/{len(products)}] {pid} — {name}')

        if not src or not src.startswith('http'):
            log('  SKIP: no source URL')
            p['imagePaths'] = []
            summary.append((pid, 0))
            continue

        dest = ASSET / pid
        dest.mkdir(parents=True, exist_ok=True)
        existing = sorted([x for x in dest.iterdir() if x.suffix.lower() in IMG_EXTS])
        if len(existing) >= 3:
            p['imagePaths'] = [str(x.relative_to(ROOT)).replace('\\', '/') for x in existing[:3]]
            log(f'  KEEP: {len(p["imagePaths"])} existing photos')
            summary.append((pid, len(p['imagePaths'])))
            continue

        # Remove partial/failed old files so the manifest reflects this run cleanly.
        clean_old_assets(dest)
        got = browser_capture(page, src, dest, 3)

        if got < 3:
            text, base = fetch_source(src)
            if text:
                urls = extract_images(text, base)
                for u in urls[:40]:
                    if got >= 3:
                        break
                    ext = Path(urlparse(u).path).suffix.lower()
                    if ext not in IMG_EXTS:
                        ext = '.jpg'
                    f = dest / f'{got + 1}{ext}'
                    if download(u, f, src):
                        got += 1

        files = sorted([x for x in dest.iterdir() if x.suffix.lower() in IMG_EXTS])
        p['imagePaths'] = [str(x.relative_to(ROOT)).replace('\\', '/') for x in files[:3]]
        log(f'  RESULT: {len(p["imagePaths"])} real photos')
        summary.append((pid, len(p['imagePaths'])))

        # Keep the runner responsive and avoid hammering source sites.
        time.sleep(0.2)

    context.close()
    browser.close()

DATA.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
all_photos = sum(len(p.get('imagePaths', [])) for p in products)
with_photos = sum(bool(p.get('imagePaths')) for p in products)
log('')
log(f'TOTAL LOCAL PHOTOS: {all_photos}; PRODUCTS WITH PHOTOS: {with_photos}/{len(products)}')

if all_photos == 0:
    raise SystemExit('No product photos were fetched. The workflow refuses to publish a catalogue with fake/broken image placeholders.')
