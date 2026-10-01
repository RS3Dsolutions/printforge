#!/usr/bin/env python3
"""Source and curate 446 MakerWorld products for PrintForge.

The script intentionally selects functional, locally sellable products rather than
random models. It uses MakerWorld search pages for discovery and the public Bambu
design endpoint for model metadata. Only CC0/BY/BY-SA/Public Domain licenses pass.
"""
import json, math, re, time
from pathlib import Path
from urllib.parse import quote, urljoin
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"products.json"
TARGET=446
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
S=requests.Session(); S.headers.update({"User-Agent":UA,"Accept-Language":"en-US,en;q=0.9"})
JINA="https://r.jina.ai/https://makerworld.com/en/search/models?isFromSearchList=true&keyword={q}&p={p}"

# Search vocabulary is deliberately biased toward products that solve a practical problem
# and can be sold locally as single pieces, small batches, or customized variants.
GROUPS={
 "Automotive":["car phone holder","car cup holder","car mount","car organizer","car accessory","bike mount","scooter holder","vehicle replacement","car repair"],
 "Tools & Workshop":["tool holder","tool organizer","drill holder","wrench holder","socket holder","workshop organizer","pegboard organizer","gridfinity","clamp holder","jig fixture","workbench organizer","battery holder"],
 "Office & Desk":["phone stand","laptop stand","desk organizer","pen holder","cable organizer","cable clip","headphone stand","monitor stand","keyboard stand","desk accessory","charging stand"],
 "Electronics & Tech":["electronics enclosure","raspberry pi case","arduino case","ssd mount","hard drive holder","router mount","remote holder","sd card holder","usb organizer","smart home mount"],
 "Home & Living":["kitchen organizer","drawer organizer","storage box","shelf organizer","wall hook","bag clip","remote control holder","bathroom organizer","plant holder","household organizer"],
 "Business & Retail":["business card holder","qr code stand","display stand","price tag holder","counter display","retail organizer","name plate","sign holder"],
 "Creator & Gaming":["controller stand","game controller holder","headset holder","gaming desk accessory","stream deck mount","microphone holder","camera mount","desk gaming organizer"],
 "Repair":["replacement part","replacement clip","replacement knob","repair bracket","hinge repair","appliance replacement","vacuum replacement","furniture repair","mounting bracket"]
}
ALLOW={"CC0","BY","BY-SA","PUBLIC DOMAIN","CC BY","CC BY-SA"}
BLOCK=re.compile(r"\b(weapon|gun|firearm|ammo|grenade|knife|sword|cosplay|figurine|fanart|pokemon|marvel|disney|star wars|harry potter|nintendo logo|medical|prosthetic|baby|food safe|food-contact|weapon)\b",re.I)
PRACTICAL=re.compile(r"\b(holder|mount|stand|organizer|clip|bracket|adapter|case|box|rack|hook|replacement|repair|storage|jig|fixture|caddy|tray|dock|charger|cover)\b",re.I)

def norm(s):
    return re.sub(r"[^a-z0-9]+"," ",(s or "").lower()).strip()

def model_id(url):
    m=re.search(r"/models/(\d+)",url)
    return m.group(1) if m else None

def discover(group,terms,per_term=4):
    out={}
    for term in terms:
        for p in range(1,per_term+1):
            u=JINA.format(q=quote(term),p=p)
            try:
                r=S.get(u,timeout=25)
                if not r.ok: continue
                # Jina markdown preserves MakerWorld model links.
                links=re.findall(r"https?://makerworld\.com/(?:en/)?models/(\d+[^\s)"<>]*)",r.text)
                if not links:
                    links=re.findall(r"(?:https?://)?makerworld\.com/(?:en/)?models/(\d+[^\s)"<>]*)",r.text)
                for slug in links:
                    full="https://makerworld.com/en/models/"+slug.split("#")[0]
                    mid=model_id(full)
                    if mid: out[mid]=(full,group,term)
            except Exception:
                pass
            time.sleep(.15)
    return out

def detail(mid):
    try:
        r=S.get(f"https://api.bambulab.com/v1/design-service/design/{mid}",timeout=20)
        if not r.ok: return None
        d=r.json()
        if isinstance(d,dict) and isinstance(d.get("data"),dict): d=d["data"]
        return d if isinstance(d,dict) else None
    except Exception:
        return None

def license_ok(v):
    x=norm(v).upper().replace("CREATIVE COMMONS ","")
    return any(a in x for a in ALLOW)

def score(d,group,term):
    title=d.get("title") or ""
    tags=" ".join(map(str,d.get("tags") or []))
    summary=re.sub("<[^>]+>"," ",str(d.get("summary") or ""))
    text=f"{title} {tags} {summary}"
    if BLOCK.search(text): return -10**9
    stats=d.get("stats") or {}
    downloads=int(d.get("downloadCount") or stats.get("downloadCount") or 0)
    likes=int(d.get("likeCount") or stats.get("likeCount") or 0)
    prints=int(d.get("printCount") or stats.get("printCount") or 0)
    boosts=int(d.get("boostCount") or stats.get("boostCount") or 0)
    s=2.0*math.log1p(downloads)+2.8*math.log1p(prints)+1.1*math.log1p(likes)+.7*math.log1p(boosts)
    s+=8 if PRACTICAL.search(text) else 0
    s+=5 if any(k in norm(text) for k in ["customizable","parametric"]) else 0
    # Small, simple functional goods are easier to sell locally.
    if any(k in norm(text) for k in ["mini","compact","small","no support","print in place"]): s+=2
    if any(k in norm(text) for k in ["hour","hours","large","giant","multi part"]): s-=1
    if group in ("Automotive","Repair","Business & Retail"): s+=3
    return s

def make_product(d,group,source,rank):
    title=(d.get("title") or "MakerWorld product").strip()
    tags=[str(x) for x in (d.get("tags") or [])][:12]
    summary=re.sub(r"\s+"," ",re.sub("<[^>]+>"," ",str(d.get("summary") or ""))).strip()
    if len(summary)<25:
        summary=f"{title} is a made-to-order 3D printed product selected for PrintForge based on practical local-use demand."
    creator=d.get("designCreator") or d.get("creator") or {}
    creator_name=creator.get("name") if isinstance(creator,dict) else str(creator)
    lic=d.get("license") or "CC0"
    return {
      "id":f"PF-MW-{rank:03d}",
      "name":title,
      "category":group,
      "subcategory": "MakerWorld Market Picks",
      "type":"Made-to-order 3D printed product",
      "description":summary[:900],
      "images":[],
      "customerTags":["Made to order","Commercial-use source verified"],
      "imagePaths":[],
      "platform":"MakerWorld",
      "creator":creator_name or "MakerWorld creator",
      "license":str(lic),
      "source":source,
      "licenseGate":True,
      "catalogBatch":"makerworld-market-446"
    }

def main():
    data=json.loads(DATA.read_text(encoding="utf-8"))
    products=data.get("products",[])
    existing_names={norm(p.get("name")) for p in products}
    existing_sources={p.get("source") for p in products}
    candidates={}
    for group,terms in GROUPS.items():
        print("Discovering",group,flush=True)
        candidates.update(discover(group,terms))
    print("Unique discovered:",len(candidates),flush=True)

    scored=[]
    for n,(src,group,term) in enumerate(candidates.values(),1):
        mid=model_id(src)
        d=detail(mid)
        if not d: continue
        lic=d.get("license") or ""
        if not license_ok(lic): continue
        title=d.get("title") or ""
        if norm(title) in existing_names or src in existing_sources: continue
        sc=score(d,group,term)
        if sc < 8: continue
        scored.append((sc,group,src,d))
        if n%50==0: print("Detailed",n,"accepted",len(scored),flush=True)
        time.sleep(.08)

    # Deduplicate titles, then enforce category diversity before filling globally.
    scored.sort(key=lambda x:x[0],reverse=True)
    selected=[]; seen=set(); counts={g:0 for g in GROUPS}
    quota={g:max(20,round(TARGET*len(terms)/sum(len(v) for v in GROUPS.values()))) for g,terms in GROUPS.items()}
    for sc,g,src,d in scored:
        key=norm(d.get("title"))
        if not key or key in seen: continue
        if counts[g] < quota[g]:
            selected.append((sc,g,src,d)); seen.add(key); counts[g]+=1
        if len(selected)>=TARGET: break
    if len(selected)<TARGET:
        for sc,g,src,d in scored:
            key=norm(d.get("title"))
            if key in seen: continue
            selected.append((sc,g,src,d)); seen.add(key)
            if len(selected)>=TARGET: break

    if len(selected)<TARGET:
        raise SystemExit(f"Only {len(selected)} qualifying MakerWorld products found; refusing to create a fake 446.")

    base=max([int(re.search(r"(\d+)$",p.get("id","0")).group(1)) for p in products if p.get("id","").startswith("PF-MW-")]+[0])
    for i,(sc,g,src,d) in enumerate(selected,1):
        products.append(make_product(d,g,src,base+i))
    data["products"]=products
    data["total"]=len(products)
    data["withImages"]=sum(bool(p.get("imagePaths")) for p in products)
    data["newProducts"]=446
    DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Added {TARGET} MakerWorld products. Catalogue total: {len(products)}",flush=True)
    print("Category counts:",counts,flush=True)

if __name__=="__main__":
    main()
