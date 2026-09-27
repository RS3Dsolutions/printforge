import json, os, re, time
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
BAD = ('avatar','logo','icon','emoji','profile','favicon','badge','social','qr-code')
IMG_RE = re.compile(r'(?i)(https?://[^\s)\]<">\']+)')
MD_IMG_RE = re.compile(r'!\[[^\]]*\]\((https?://[^)\s]+)\)')


def absu(u, base):
    if not u: return None
    u = u.strip().replace('\\/','/')
    if u.startswith('//'): return 'https:' + u
    return urljoin(base, u)


def add(out, u):
    if not u: return
    u = u.strip().rstrip('.,')
    low = u.lower()
    if any(x in low for x in BAD) or low.startswith('data:'): return
    out.append(u)


def extract_images(text, base):
    out=[]
    for u in MD_IMG_RE.findall(text): add(out, absu(u, base))
    for u in IMG_RE.findall(text): add(out, absu(u, base))
    soup = BeautifulSoup(text, 'html.parser')
    for img in soup.find_all('img'):
        for a in ('src','data-src','data-original','data-lazy-src'):
            add(out, absu(img.get(a), base))
        ss = img.get('srcset') or img.get('data-srcset')
        if ss:
            for part in ss.split(','):
                add(out, absu(part.strip().split()[0], base))
    for m in soup.select('meta[property="og:image"],meta[name="twitter:image"],meta[property="og:image:url"]'):
        add(out, absu(m.get('content'), base))
    seen=set(); good=[]
    for u in out:
        if not u or u in seen: continue
        seen.add(u)
        low=u.lower()
        if any(x in low for x in ('/models/','/model/','/user/','/search','/collections/')) and not any(x in low for x in ('media.','image.','cdn.')):
            continue
        good.append(u)
    good.sort(key=lambda u: (0 if any(h in u.lower() for h in ('media.printables.com','makerworld.com','cdn.','images.')) else 1, len(u)))
    return good


def reader_urls(src):
    return [
        'https://r.jina.ai/' + src,
        'https://r.jina.ai/http://' + src.split('://',1)[1] if '://' in src else None,
    ]


def fetch_source(src):
    for u in reader_urls(src) + [src]:
        if not u: continue
        try:
            r=S.get(u,timeout=45,allow_redirects=True)
            if r.ok and len(r.text)>500:
                return r.text, r.url
        except Exception:
            pass
    return '', src


def download(u, path, referer):
    try:
        r=S.get(u,timeout=30,allow_redirects=True,headers={'Referer':referer})
        r.raise_for_status()
        ct=(r.headers.get('content-type') or '').lower()
        data=r.content
        if not ct.startswith('image/') or len(data)<10000 or len(data)>12_000_000: return False
        path.write_bytes(data)
        return True
    except Exception:
        return False


def browser_capture(src, dest, max_images=3):
    """Render the actual model page and capture its real gallery images locally.
    This is a fallback for sites that expose gallery images only after JS runs or
    reject ordinary HTTP image downloads. No synthetic images are created.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return 0
    got=0
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1100}, user_agent=UA)
            page.goto(src, wait_until='domcontentloaded', timeout=45000)
            page.wait_for_timeout(2500)
            # Force lazy-loaded gallery images to materialize.
            page.evaluate('window.scrollTo(0, document.body.scrollHeight * 0.35)')
            page.wait_for_timeout(1200)
            imgs=page.locator('img')
            count=imgs.count()
            candidates=[]
            for i in range(min(count, 80)):
                try:
                    el=imgs.nth(i)
                    box=el.bounding_box()
                    if not box or box['width'] < 180 or box['height'] < 120: continue
                    srcv=el.get_attribute('src') or el.get_attribute('data-src') or ''
                    alt=(el.get_attribute('alt') or '').lower()
                    low=(srcv+' '+alt).lower()
                    if any(x in low for x in BAD): continue
                    candidates.append(el)
                except Exception:
                    continue
            # De-duplicate visually by image source URL where possible.
            seen_src=set()
            for el in candidates:
                if got>=max_images: break
                try:
                    srcv=el.get_attribute('src') or el.get_attribute('data-src') or ''
                    if srcv in seen_src and srcv: continue
                    if srcv: seen_src.add(srcv)
                    el.scroll_into_view_if_needed(timeout=5000)
                    page.wait_for_timeout(300)
                    target=dest/f'{got+1}.jpg'
                    el.screenshot(path=str(target), type='jpeg', quality=92)
                    if target.exists() and target.stat().st_size>10000:
                        got += 1
                    else:
                        target.unlink(missing_ok=True)
                except Exception:
                    continue
            browser.close()
    except Exception as e:
        print(f'  browser capture failed: {type(e).__name__}: {e}')
    return got


d=json.loads(DATA.read_text(encoding='utf-8'))
summary=[]
for p in d.get('products',[]):
    src=p.get('source')
    if not src or not src.startswith('http'):
        continue
    dest=ASSET/p['id']; dest.mkdir(parents=True,exist_ok=True)
    existing=sorted([x for x in dest.iterdir() if x.suffix.lower() in ('.jpg','.jpeg','.png','.webp')])
    if len(existing)>=3:
        p['imagePaths']=[str(x.relative_to(ROOT)).replace('\\','/') for x in existing[:3]]
        continue

    # First use a real browser page. This is the most reliable path for JS/lazy-loaded galleries.
    got=browser_capture(src,dest,3)
    if got<3:
        text,base=fetch_source(src)
        urls=extract_images(text,base)
        for u in urls[:60]:
            if got>=3: break
            ext=Path(urlparse(u).path).suffix.lower()
            if ext not in ('.jpg','.jpeg','.png','.webp'): ext='.jpg'
            f=dest/f'{got+1}{ext}'
            if download(u,f,src): got+=1

    files=sorted([x for x in dest.iterdir() if x.suffix.lower() in ('.jpg','.jpeg','.png','.webp')])
    p['imagePaths']=[str(x.relative_to(ROOT)).replace('\\','/') for x in files[:3]]
    print(f"{p['id']}: {len(p['imagePaths'])} real photos")
    summary.append((p['id'],len(p['imagePaths'])))
    time.sleep(0.4)

DATA.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
all_photos=sum(len(p.get('imagePaths',[])) for p in d.get('products',[]))
with_photos=sum(bool(p.get('imagePaths')) for p in d.get('products',[]))
print(f'TOTAL LOCAL PHOTOS: {all_photos}; PRODUCTS WITH PHOTOS: {with_photos}/{len(d.get("products",[]))}')
if all_photos == 0:
    raise SystemExit('No product photos were fetched. The workflow refuses to publish a catalogue with fake/broken image placeholders.')
