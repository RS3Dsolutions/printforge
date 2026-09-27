import json, os, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'products.json'
ASSET=ROOT/'assets'/'products'
ASSET.mkdir(parents=True,exist_ok=True)

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})

IMG_EXT=re.compile(r'\.(?:jpe?g|png|webp)(?:\?|$)',re.I)
BAD=('avatar','logo','icon','emoji','profile','printer','favicon','badge')

def absu(u,base):
    if not u: return None
    u=u.strip()
    if u.startswith('//'): return 'https:'+u
    return urljoin(base,u)

def candidates_from_html(html,base,platform):
    soup=BeautifulSoup(html,'html.parser')
    urls=[]
    # og:image first
    for m in soup.select('meta[property="og:image"], meta[name="twitter:image"]'):
        u=absu(m.get('content'),base)
        if u: urls.append(u)
    for img in soup.find_all('img'):
        for attr in ('src','data-src','data-original','data-lazy-src'):
            u=absu(img.get(attr),base)
            if u: urls.append(u)
        ss=img.get('srcset') or img.get('data-srcset')
        if ss:
            for part in ss.split(','):
                u=part.strip().split(' ')[0]
                if u: urls.append(absu(u,base))
    # HTML often contains JSON-escaped image URLs
    for m in re.findall(r'https?:(?:\\/|/){2,}[^"\'\\ ]+?\.(?:jpg|jpeg|png|webp)(?:\?[^"\'\\ ]*)?',html,re.I):
        urls.append(m.replace('\\/','/'))
    for m in re.findall(r'https?://[^"\' ]+?\.(?:jpg|jpeg|png|webp)(?:\?[^"\' ]*)?',html,re.I):
        urls.append(m)
    out=[]; seen=set()
    for u in urls:
        if not u or u in seen: continue
        seen.add(u)
        low=u.lower()
        if any(x in low for x in BAD): continue
        if platform=='Printables' and 'media.printables.com' not in low: continue
        # reject tiny/known UI assets
        if any(x in low for x in ('/avatars/','/user-avatars/')): continue
        out.append(u)
    return out

def get(url):
    r=S.get(url,timeout=35,allow_redirects=True)
    r.raise_for_status(); return r

def save_image(url,path):
    r=S.get(url,timeout=35,stream=True,allow_redirects=True,headers={'Referer':'https://www.printables.com/' if 'printables.com' in url else 'https://makerworld.com/'})
    r.raise_for_status()
    ct=(r.headers.get('content-type') or '').lower()
    if not ct.startswith('image/'): return False
    data=r.content
    if len(data)<8000: return False
    path.write_bytes(data)
    return True

d=json.loads(DATA.read_text())
products=d['products']
for p in products:
    src=p.get('source')
    if not src or 'Custom / source model' in p.get('platform',''):
        p['imagePaths']=[]; continue
    dest=ASSET/p['id']; dest.mkdir(parents=True,exist_ok=True)
    # don't refetch existing good assets
    existing=sorted([x for x in dest.iterdir() if x.suffix.lower() in ('.jpg','.jpeg','.png','.webp')])
    if len(existing)>=2:
        p['imagePaths']=[str(x.relative_to(ROOT)).replace('\\','/') for x in existing[:3]]
        continue
    try:
        r=get(src); urls=candidates_from_html(r.text,r.url,p.get('platform',''))
        got=[]
        for i,u in enumerate(urls[:20]):
            ext='.jpg'
            pu=urlparse(u).path.lower()
            for e in ('.jpeg','.jpg','.png','.webp'):
                if pu.endswith(e): ext=e; break
            out=dest/f'{i+1}{ext}'
            try:
                if save_image(u,out): got.append(out)
            except Exception:
                pass
            if len(got)>=3: break
        p['imagePaths']=[str(x.relative_to(ROOT)).replace('\\','/') for x in got]
        print(p['id'], p['name'], '->', len(got))
    except Exception as e:
        print('FAIL',p['id'],p['name'],e)
        p['imagePaths']=[]
    time.sleep(.5)
# images is kept empty; website uses imagePaths
DATA.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
