import json, os, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parent
DATA=ROOT/"products.json"
ASSET=ROOT/"assets"/"products"
ASSET.mkdir(parents=True,exist_ok=True)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
S=requests.Session(); S.headers.update({"User-Agent":UA,"Accept-Language":"en-US,en;q=0.9","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"})
BAD=("avatar","logo","icon","emoji","profile","favicon","badge","printer-logo")
def absu(u,base):
    if not u:return None
    u=u.strip().replace("\\/","/")
    if u.startswith("//"):return "https:"+u
    return urljoin(base,u)
def candidates(html,base,platform):
    soup=BeautifulSoup(html,"html.parser"); out=[]
    for sel in ['meta[property="og:image"]','meta[name="twitter:image"]','meta[property="og:image:url"]']:
        for m in soup.select(sel):
            u=absu(m.get("content"),base)
            if u:out.append(u)
    for img in soup.find_all("img"):
        for a in ("src","data-src","data-original","data-lazy-src"):
            u=absu(img.get(a),base)
            if u:out.append(u)
        ss=img.get("srcset") or img.get("data-srcset")
        if ss:
            for part in ss.split(","):
                u=absu(part.strip().split()[0],base)
                if u:out.append(u)
    for m in re.findall(r'https?://[^"\'<> ]+?(?:\.jpg|\.jpeg|\.png|\.webp)(?:\?[^"\'<> ]*)?',html,re.I):out.append(m)
    seen=set(); good=[]
    for u in out:
        if not u or u in seen:continue
        seen.add(u); low=u.lower()
        if any(x in low for x in BAD):continue
        if platform=="Printables" and "media.printables.com" not in low:continue
        good.append(u)
    return good
def download(u,path,referer):
    r=S.get(u,timeout=40,allow_redirects=True,headers={"Referer":referer}); r.raise_for_status()
    ct=(r.headers.get("content-type") or "").lower()
    if not ct.startswith("image/"):return False
    data=r.content
    if len(data)<10000:return False
    path.write_bytes(data);return True
d=json.loads(DATA.read_text());
for p in d["products"]:
    src=p.get("source")
    if not src:continue
    dest=ASSET/p["id"];dest.mkdir(parents=True,exist_ok=True)
    try:
        r=S.get(src,timeout=40,allow_redirects=True);r.raise_for_status()
        urls=candidates(r.text,r.url,p.get("platform",""))
        got=[]
        for i,u in enumerate(urls[:25],1):
            ext=Path(urlparse(u).path).suffix.lower()
            if ext not in (".jpg",".jpeg",".png",".webp"):ext=".jpg"
            f=dest/f"{i}{ext}"
            try:
                if download(u,f,r.url):got.append(f)
            except Exception:pass
            if len(got)>=3:break
        p["imagePaths"]=[str(x.relative_to(ROOT)).replace("\\","/") for x in got]
        print(p["id"],len(got))
    except Exception as e:
        print("FAIL",p["id"],e)
        p["imagePaths"]=[]
    time.sleep(.3)
DATA.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
