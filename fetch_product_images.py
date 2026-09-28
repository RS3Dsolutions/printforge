import json, os, re, sys, time, hashlib
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

IMAGE_HOSTS = ('media.printables.com','makerworld.bblmw.com','makerworld.com','cdn.','images.','image.')


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
        for a in ('src','currentSrc','data-src','data-original','data-lazy-src','data-image','data-url','data-full'):
            add(out, img.get(a), base)
        ss = img.get('srcset') or img.get('data-srcset')
        if ss:
            for part in ss.split(','):
                add(out, part.strip().split()[0], base)
    for source in soup.find_all('source'):
        for a in ('src','srcset','data-src','data-srcset'):
            val=source.get(a)
            if not val: continue
            for part in val.split(','):
                add(out, part.strip().split()[0], base)
    for m in soup.select('meta[property="og:image"],meta[property="og:image:url"],meta[name="twitter:image"]'):
        add(out, m.get('content'), base)
    # React/Vue serialized state often contains the actual gallery URLs.
    url_pat = re.compile(r"https?:\\?/\\?/[^\"'\\s<>]+")
    media_pat = re.compile(r"(?:https?:)?//[^\"'\\s<>]*(?:media\\.printables\\.com|makerworld\\.bblmw\\.com)[^\"'\\s<>]*")
    for tag in soup.find_all('script'):
        raw = tag.string or tag.get_text() or ''
        if not raw or len(raw) > 3_000_000:
            continue
        for u in url_pat.findall(raw): add(out, u, base)
        for u in media_pat.findall(raw): add(out, u, base)
    for host in ('media.printables.com','makerworld.bblmw.com'):
        pat = re.compile(r"https?://[^\"'\\s<>]*" + re.escape(host) + r"[^\"'\\s<>]*")
        for u in pat.findall(text): add(out, u, base)
    seen=set(); good=[]
    for u in sorted(out, key=lambda x: (-score_url(x), len(x))):
        if u in seen: continue
        seen.add(u); low=u.lower()
        if any(x in low for x in ('/models/','/model/','/user/','/search','/collections/')) and not any(h in low for h in ('media.printables.com','makerworld.bblmw.com')):
            continue
        good.append(u)
    return good[:100]

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



def score_url(u):
    low=u.lower(); score=0
    if any(h in low for h in IMAGE_HOSTS): score+=50
    if any(x in low for x in ('/images/','/media/','/pictures/','/gallery/','/cover')): score+=20
    if any(x in low for x in ('thumb','thumbnail','small','avatar','icon')): score-=25
    return score


def valid_image_bytes(data, content_type=''):
    if not data or len(data)<10000 or len(data)>15_000_000: return False
    ct=(content_type or '').lower()
    return ct.startswith('image/') or data[:3]==b'\xff\xd8\xff' or data[:8]==b'\x89PNG\r\n\x1a\n' or data[:4]==b'RIFF'


def save_bytes(data,path,content_type=''):
    if not valid_image_bytes(data,content_type): return False
    path.write_bytes(data); return True

def browser_capture(page, src, dest, max_images=3):
    """Capture the real gallery images loaded by the source page.
    Priority: network image responses -> exposed image URLs -> rendered image screenshots.
    """
    browser_src = re.sub(r'/files/?$', '', src)
    captured=[]
    def on_response(response):
        if len(captured) >= 20: return
        try:
            ct=(response.headers.get('content-type') or '').lower(); u=response.url; low=u.lower()
            if not ct.startswith('image/') or any(x in low for x in BAD): return
            if not any(h in low for h in IMAGE_HOSTS): return
            body=response.body()
            if valid_image_bytes(body,ct): captured.append((u,body,ct))
        except Exception: pass
    page.on('response', on_response)
    try:
        page.goto(browser_src, wait_until='domcontentloaded', timeout=25000)
        page.wait_for_timeout(1800)
        # Force lazy galleries to load.
        for frac in (0.12,0.30,0.50,0.70,0.90,0):
            try:
                page.evaluate(f'window.scrollTo(0, document.body.scrollHeight * {frac})')
                page.wait_for_timeout(300)
            except Exception: pass

        candidates=[]
        try:
            imgs=page.locator('img'); count=min(imgs.count(),150)
            for i in range(count):
                try:
                    el=imgs.nth(i); box=el.bounding_box()
                    if not box or box['width']<160 or box['height']<100: continue
                    vals=[el.get_attribute('src',timeout=300),el.get_attribute('data-src',timeout=300),el.get_attribute('data-original',timeout=300),el.get_attribute('data-image',timeout=300),el.get_attribute('data-full',timeout=300),el.get_attribute('srcset',timeout=300),el.get_attribute('data-srcset',timeout=300)]
                    try: vals.append(el.evaluate('(e)=>e.currentSrc || ""'))
                    except Exception: pass
                    for val in vals:
                        if not val: continue
                        for part in val.split(','):
                            add(candidates,part.strip().split()[0],page.url)
                except Exception: continue
        except Exception: pass
        try:
            perf=page.evaluate("""() => performance.getEntriesByType('resource').map(e=>e.name).filter(u=>/\\.(?:jpe?g|png|webp)(?:[?#]|$)/i.test(u))""")
            for u in perf or []: add(candidates,u,page.url)
        except Exception: pass
        for selector in ('meta[property="og:image"]','meta[property="og:image:url"]','meta[name="twitter:image"]'):
            try: add(candidates,page.locator(selector).first.get_attribute('content',timeout=500),page.url)
            except Exception: pass

        got=0; seen=set()
        # Exact bytes received by Chromium are preferable to a secondary HTTP fetch.
        for u,body,ct in captured:
            if got>=max_images: break
            key=hashlib.sha1(u.encode()).hexdigest()
            if key in seen: continue
            seen.add(key)
            if save_bytes(body,dest/f'{got+1}.jpg',ct): got+=1
        for u in sorted(candidates,key=lambda x:(-score_url(x),len(x))):
            if got>=max_images or u in seen: continue
            seen.add(u); ext=Path(urlparse(u).path).suffix.lower(); ext=ext if ext in IMG_EXTS else '.jpg'
            if download(u,dest/f'{got+1}{ext}',browser_src): got+=1
        if got<max_images:
            try:
                imgs=page.locator('img'); count=min(imgs.count(),150)
                for i in range(count):
                    if got>=max_images: break
                    try:
                        el=imgs.nth(i); box=el.bounding_box()
                        if not box or box['width']<180 or box['height']<120: continue
                        srcv=el.evaluate('(e)=>e.currentSrc || e.src || ""'); alt=(el.get_attribute('alt',timeout=300) or '').lower()
                        if any(x in (srcv+' '+alt).lower() for x in BAD): continue
                        el.scroll_into_view_if_needed(timeout=1500); page.wait_for_timeout(100)
                        target=dest/f'{got+1}.jpg'; el.screenshot(path=str(target),type='jpeg',quality=92,timeout=4000)
                        if target.exists() and target.stat().st_size>10000: got+=1
                    except Exception: continue
            except Exception: pass
        return got
    finally:
        try: page.remove_listener('response',on_response)
        except Exception: pass

def source_preview(page, src, dest):
    """Last-resort real source-page preview. This is NOT a fabricated product image.
    It captures the actual public source page as rendered by Chromium so the catalogue
    never shows a fake placeholder when a gallery image URL cannot be extracted.
    """
    try:
        browser_src = re.sub(r'/files/?$', '', src)
        page.goto(browser_src, wait_until='domcontentloaded', timeout=25000)
        page.wait_for_timeout(2200)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(400)
        target = dest / 'source-preview.jpg'
        page.screenshot(path=str(target), type='jpeg', quality=88, full_page=False)
        if target.exists() and target.stat().st_size > 15000:
            return target
    except Exception as e:
        log(f'  SOURCE PREVIEW ERROR: {e}')
    return None

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

        if got == 0:
            preview = source_preview(page, src, dest)
            if preview:
                got = 1
                log('  FALLBACK: saved real source-page preview')

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
