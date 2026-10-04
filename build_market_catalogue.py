#!/usr/bin/env python3
"""Build the 4,000-product PrintForge market expansion from public model metadata.

Sources:
- MakerWorld public design2 search endpoint
- Printables anonymous public GraphQL search
- Thingiverse public search/model pages

Only explicit commercial-use licenses are accepted. This script never fabricates
products and is idempotent: it replaces only catalogBatch=market-expansion-4000.
"""
import json, math, re, time
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "products.json"
TARGET_NEW = 4000
BASE_TOTAL = 1000
BATCH = "market-expansion-4000"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})

ALLOW = {
    "CC0", "PUBLIC DOMAIN", "PUBLIC DOMAIN DEDICATION",
    "BY", "CC BY", "CREATIVE COMMONS - ATTRIBUTION",
    "BY-SA", "CC BY-SA", "CREATIVE COMMONS - ATTRIBUTION - SHARE ALIKE",
    "BY-ND", "CC BY-ND", "CREATIVE COMMONS - ATTRIBUTION - NO DERIVATIVES",
    "GPL", "LGPL", "BSD",
}
BLOCK = re.compile(
    r"\b(weapon|gun|firearm|ammo|grenade|knife|sword|bomb|explosive|"
    r"cosplay|figurine|fanart|pokemon|marvel|disney|star wars|harry potter|"
    r"nintendo|medical|prosthetic|baby|pacifier|food safe|food-contact|"
    r"adult|nsfw|sex toy)\b", re.I
)
PRACTICAL = re.compile(
    r"\b(holder|mount|stand|organizer|clip|bracket|adapter|case|box|rack|hook|"
    r"replacement|repair|storage|jig|fixture|caddy|tray|dock|charger|cover|"
    r"part|component|insert|cap|lid|bin|basket|drawer|shelf|hanger|bottle|"
    r"container|coaster|keychain|tag|label|sign|display|phone|tablet|laptop|"
    r"keyboard|mouse|headset|controller|cable|cord|wire|battery|ssd|hard.?drive|"
    r"raspberry|arduino|camera|microphone|speaker|remote|tool|wrench|socket|"
    r"drill|screwdriver|clamp|pegboard|gridfinity|car|vehicle|bike|scooter|"
    r"dash|console|visor|cup|seat|mirror|license.?plate|fuse|knob|hinge|wheel|"
    r"panel|gasket|seal|template|gauge|spacer|shim|mounting|fastener|enclosure|"
    r"housing|drawer|planter|pot|garden|retail|business|qr|price|counter)\b", re.I
)

GROUPS = {
    "Automotive": [
        "car phone holder","car cup holder","car organizer","car mount","car accessory",
        "car replacement part","car dashboard","car console organizer","bike mount",
        "motorcycle mount","scooter accessory","vehicle bracket","car cable holder"
    ],
    "Tools & Workshop": [
        "tool holder","tool organizer","drill holder","wrench holder","socket holder",
        "workshop organizer","pegboard organizer","gridfinity","clamp holder",
        "jig fixture","workbench organizer","battery holder","screwdriver holder",
        "mechanic organizer","toolbox organizer","garage storage"
    ],
    "Office & Desk": [
        "phone stand","laptop stand","desk organizer","pen holder","cable organizer",
        "cable clip","headphone stand","monitor stand","keyboard stand","desk accessory",
        "charging stand","document holder","desk drawer organizer","tablet stand"
    ],
    "Electronics & Tech": [
        "electronics enclosure","raspberry pi case","arduino case","ssd mount",
        "hard drive holder","router mount","remote holder","sd card holder",
        "usb organizer","smart home mount","power bank holder","sensor enclosure",
        "switch box","electronics organizer"
    ],
    "Home & Living": [
        "kitchen organizer","drawer organizer","storage box","shelf organizer",
        "wall hook","bag clip","remote control holder","bathroom organizer",
        "plant holder","household organizer","pantry organizer","closet organizer",
        "cable management home","laundry organizer","bottle holder"
    ],
    "Business & Retail": [
        "business card holder","qr code stand","display stand","price tag holder",
        "counter display","retail organizer","name plate","sign holder",
        "menu stand","product display","brochure holder","receipt holder",
        "desk sign","table number holder"
    ],
    "Creator & Gaming": [
        "controller stand","game controller holder","headset holder","gaming desk accessory",
        "stream deck mount","microphone holder","camera mount","desk gaming organizer",
        "webcam mount","game storage","controller wall mount"
    ],
    "Repair & Replacement": [
        "replacement part","replacement clip","replacement knob","repair bracket",
        "hinge repair","appliance replacement","vacuum replacement","furniture repair",
        "mounting bracket","replacement cover","replacement cap","spacer bushing",
        "repair jig","broken part replacement"
    ],
    "Garden & Outdoor": [
        "garden tool holder","hose holder","plant clip","plant support","pot holder",
        "garden organizer","seed tray","irrigation clip","outdoor hook","bike accessory"
    ],
    "Education & Maker": [
        "maker tool","arduino holder","electronics teaching","stem organizer",
        "lab organizer","maker jig","caliper gauge","measurement tool","classroom organizer"
    ],
}

QUERY_TERMS = [t for terms in GROUPS.values() for t in terms]

def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()

def license_ok(v):
    x = norm(v).upper()
    if not x:
        return False
    if "NON-COMMERCIAL" in x or "NON COMMERCIAL" in x or "BY-NC" in x or "-NC" in x or " NC" in x:
        return False
    if "ALL RIGHTS RESERVED" in x or "EXCLUSIVE" in x or "STANDARD DIGITAL FILE LICENSE" in x:
        return False
    return x in {norm(a).upper() for a in ALLOW} or (
        "CREATIVE COMMONS" in x and "ATTRIBUTION" in x and "NON" not in x
        and ("SHARE ALIKE" in x or "NO DERIVATIVES" in x or x.endswith("ATTRIBUTION"))
    )

def clean_text(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(s or ""))).strip()

def get(url, **kwargs):
    for attempt in range(5):
        try:
            r = S.get(url, timeout=kwargs.pop("timeout", 30), **kwargs)
            if r.status_code == 429:
                time.sleep([3,8,20,45,90][attempt])
                continue
            if r.ok:
                return r
        except Exception:
            if attempt == 4:
                return None
            time.sleep([2,5,10,20][attempt])
    return None

def post(url, **kwargs):
    for attempt in range(5):
        try:
            r = S.post(url, timeout=kwargs.pop("timeout", 30), **kwargs)
            if r.status_code == 429:
                time.sleep([3,8,20,45,90][attempt])
                continue
            if r.ok:
                return r
        except Exception:
            if attempt == 4:
                return None
            time.sleep([2,5,10,20][attempt])
    return None

def classify(title, tags="", preferred=None):
    text = norm(f"{title} {tags}")
    if BLOCK.search(text) or not PRACTICAL.search(text):
        return None
    if preferred and preferred in GROUPS:
        if any(norm(term) in text for term in GROUPS[preferred]):
            return preferred
    best, score = None, 0
    for group, terms in GROUPS.items():
        s = sum(1 for term in terms if norm(term) in text)
        if s > score:
            best, score = group, s
    return best

def score(item, group):
    title = item.get("title") or item.get("name") or ""
    text = f"{title} {item.get('tags','')} {item.get('description','')}"
    if BLOCK.search(text):
        return -10**9
    downloads = int(item.get("downloads") or item.get("downloadCount") or item.get("download_count") or 0)
    likes = int(item.get("likes") or item.get("likeCount") or item.get("like_count") or 0)
    makes = int(item.get("makes") or item.get("printCount") or item.get("make_count") or 0)
    s = 2.2*math.log1p(downloads) + 1.2*math.log1p(likes) + 2.4*math.log1p(makes)
    if PRACTICAL.search(text): s += 10
    if any(k in norm(text) for k in ("customizable","parametric","modular")): s += 5
    if group in ("Automotive","Repair & Replacement","Business & Retail"): s += 5
    if any(k in norm(text) for k in ("compact","small","no support","print in place")): s += 2
    if any(k in norm(text) for k in ("giant","multi part","large scale")): s -= 2
    return s

def makerworld():
    out = {}
    base = "https://api.bambulab.com/v1/search-service/select/design2"
    for n, term in enumerate(QUERY_TERMS, 1):
        group = classify(term, preferred=next((g for g,ts in GROUPS.items() if term in ts), None))
        for page in range(1, 21):
            r = get(base, params={"keyword":term, "page":page, "limit":30}, timeout=30)
            if not r: break
            try: payload = r.json()
            except Exception: break
            raw = payload.get("hits") or payload.get("results") or payload.get("items") or []
            if isinstance(raw, dict): raw = raw.get("items") or raw.get("hits") or []
            if not raw: break
            for hit in raw:
                d = hit.get("design") if isinstance(hit,dict) and isinstance(hit.get("design"),dict) else hit
                if not isinstance(d,dict): continue
                mid = str(d.get("id") or d.get("designId") or "").strip()
                title = clean_text(d.get("title") or d.get("name"))
                if not mid or not title: continue
                lic = str(d.get("license") or "").strip()
                g = classify(title, d.get("tags") or "", group)
                if not g or not license_ok(lic): continue
                src = d.get("url") or d.get("source") or f"https://makerworld.com/en/models/{mid}"
                out[mid] = {"id":mid,"name":title,"group":g,"license":lic,"source":src,
                            "creator":clean_text((d.get("designCreator") or {}).get("name") if isinstance(d.get("designCreator"),dict) else d.get("creator")),
                            "image":d.get("coverUrl") or d.get("primaryImage") or "",
                            "downloads":d.get("downloadCount",0),"likes":d.get("likeCount",0),
                            "makes":d.get("printCount",0),"description":clean_text(d.get("summary") or d.get("description") or "")}
            if len(raw) < 30: break
            time.sleep(.15)
        print(f"MakerWorld {n}/{len(QUERY_TERMS)} {term}: {len(out)} candidates", flush=True)
        if len(out) >= 2200: break
    return list(out.values())

def printables():
    out = {}
    query = """
    query SearchModels($query:String!,$limit:Int,$offset:Int,$ordering:SearchChoicesEnum) {
      searchPrints2(query:$query, printType:print, limit:$limit, offset:$offset, ordering:$ordering) {
        items {
          id name slug ratingAvg likesCount downloadCount datePublished
          user { publicUsername handle }
          image { filePath }
          license { id name disallowRemixing }
        }
        totalCount
      }
    }"""
    for n, term in enumerate(QUERY_TERMS, 1):
        group = next((g for g,ts in GROUPS.items() if term in ts), None)
        for offset in range(0, 1500, 100):
            r = post("https://api.printables.com/graphql/",
                     json={"operationName":"SearchModels","query":query,
                           "variables":{"query":term,"limit":100,"offset":offset,"ordering":"popular"}})
            if not r: break
            try: obj = r.json().get("data",{}).get("searchPrints2",{})
            except Exception: break
            items = obj.get("items") or []
            if not items: break
            for d in items:
                title=clean_text(d.get("name"))
                lic=clean_text((d.get("license") or {}).get("name"))
                g=classify(title, "", group)
                if not g or not license_ok(lic): continue
                mid=str(d.get("id"))
                src=f"https://www.printables.com/model/{mid}-{d.get('slug') or norm(title).replace(' ','-')}"
                image=((d.get("image") or {}).get("filePath") or "")
                if image and not image.startswith("http"): image="https://media.printables.com/"+image.lstrip("/")
                out[mid]={"id":mid,"name":title,"group":g,"license":lic,"source":src,
                          "creator":clean_text((d.get("user") or {}).get("publicUsername") or (d.get("user") or {}).get("handle")),
                          "image":image,"downloads":d.get("downloadCount",0),"likes":d.get("likesCount",0),
                          "makes":0,"description":""}
            if len(items)<100: break
            time.sleep(.15)
        print(f"Printables {n}/{len(QUERY_TERMS)} {term}: {len(out)} candidates", flush=True)
        if len(out) >= 2200: break
    return list(out.values())

def thingiverse_search(term, page):
    url="https://www.thingiverse.com/search"
    r=get(url,params={"q":term,"type":"things","sort":"popular","page":page},timeout=30)
    if not r: return []
    soup=BeautifulSoup(r.text,"html.parser")
    found={}
    for a in soup.select('a[href*="/thing:"]'):
        href=a.get("href","")
        m=re.search(r"/thing:(\d+)",href)
        if not m: continue
        tid=m.group(1)
        name=clean_text(a.get_text(" ",strip=True))
        if not name or len(name)<3: continue
        found[tid]={"id":tid,"name":name,"source":urljoin("https://www.thingiverse.com",href)}
    return list(found.values())

def thingiverse_detail(c):
    r=get(c["source"],timeout=25)
    if not r: return None
    soup=BeautifulSoup(r.text,"html.parser")
    text=soup.get_text(" ",strip=True)
    # License is normally exposed in the model details / structured data.
    vals=[]
    for pat in [
        r"Creative Commons\s*[-–]\s*(?:Attribution(?:\s*[-–]\s*(?:Share Alike|No Derivatives))?)",
        r"Creative Commons\s*[-–]\s*Public Domain",
        r"Public Domain",
        r"GNU\s+(?:General Public License|Lesser General Public License)",
        r"BSD License",
    ]:
        vals += re.findall(pat,text,re.I)
    lic=vals[0].strip() if vals else ""
    # Prefer JSON-LD image/name when present.
    image=""
    for tag in soup.select('meta[property="og:image"],meta[property="og:image:url"],meta[name="twitter:image"]'):
        if tag.get("content"): image=tag["content"]; break
    if not lic:
        html=r.text
        m=re.search(r'(?i)(?:license(?:Name)?)[^A-Za-z]{0,40}([A-Za-z][A-Za-z -]{3,80})',html)
        if m: lic=clean_text(m.group(1))
    c["license"]=lic
    c["image"]=image
    c["creator"]=""
    m=re.search(r'(?i)(?:creator|author)[^A-Za-z]{0,30}["\']([^"\']+)["\']',r.text)
    if m: c["creator"]=clean_text(m.group(1))
    return c

def thingiverse():
    out={}
    for n,term in enumerate(QUERY_TERMS,1):
        group=next((g for g,ts in GROUPS.items() if term in ts),None)
        for page in range(1,31):
            for c in thingiverse_search(term,page):
                tid=c["id"]
                if tid in out: continue
                g=classify(c["name"],"",group)
                if not g: continue
                d=thingiverse_detail(c)
                if not d or not license_ok(d.get("license")): continue
                d["group"]=g; d["downloads"]=0; d["likes"]=0; d["makes"]=0; d["description"]=""
                out[tid]=d
                if len(out)>=1500: break
            if len(out)>=1500: break
            time.sleep(.2)
        print(f"Thingiverse {n}/{len(QUERY_TERMS)} {term}: {len(out)} licensed candidates",flush=True)
        if len(out)>=1500: break
    return list(out.values())

def make_product(d, source_key, rank):
    group=d["group"]
    sub_map={
        "Automotive":"Accessories & Replacement Parts",
        "Tools & Workshop":"Workshop Storage & Tools",
        "Office & Desk":"Desk Organization",
        "Electronics & Tech":"Device Holders & Enclosures",
        "Home & Living":"Home Organization",
        "Business & Retail":"Displays & Signage",
        "Creator & Gaming":"Gaming & Creator Accessories",
        "Repair & Replacement":"Replacement Parts",
        "Garden & Outdoor":"Garden & Outdoor",
        "Education & Maker":"Maker Tools & Education",
    }
    desc=d.get("description") or f"{d['name']} — a practical made-to-order 3D printed product selected for PrintForge based on market demand."
    img=d.get("image") or ""
    images=[img] if img.startswith("http") else []
    return {
        "id":f"PF-{source_key}-{rank:04d}",
        "name":d["name"][:180],
        "category":group,
        "subcategory":sub_map[group],
        "type":"Made-to-order 3D printed product",
        "description":clean_text(desc)[:900],
        "images":[],
        "customerTags":["Made to order","Commercial-use source verified"],
        "imagePaths":images,
        "platform":{"MW":"MakerWorld","PT":"Printables","TV":"Thingiverse"}[source_key],
        "creator":d.get("creator") or "Original creator",
        "license":d.get("license",""),
        "source":d["source"],
        "licenseGate":True,
        "catalogBatch":BATCH
    }

def dedupe_select(candidates, quota, existing_names, existing_sources):
    pool=[]
    seen=set()
    for d in candidates:
        namekey=norm(d.get("name"))
        src=d.get("source")
        if not namekey or namekey in existing_names or src in existing_sources or namekey in seen:
            continue
        seen.add(namekey)
        sc=score(d,d["group"])
        if sc>=8: pool.append((sc,d))
    pool.sort(key=lambda x:x[0],reverse=True)
    selected=[]
    counts={g:0 for g in GROUPS}
    # First satisfy category distribution, then fill by score.
    for sc,d in pool:
        g=d["group"]
        if counts[g] < quota.get(g,0):
            selected.append(d); counts[g]+=1
        if sum(counts.values())>=sum(quota.values()): break
    return selected, counts, len(pool)

def main():
    data=json.loads(DATA.read_text(encoding="utf-8"))
    products=data.get("products",[])
    prior=[p for p in products if p.get("catalogBatch")==BATCH]
    if prior:
        products=[p for p in products if p.get("catalogBatch")!=BATCH]
        print(f"Removed {len(prior)} prior expansion products for an idempotent rebuild.",flush=True)
    if len(products)!=BASE_TOTAL:
        raise SystemExit(f"Expected exactly {BASE_TOTAL} base products, found {len(products)}.")
    existing_names={norm(p.get("name")) for p in products}
    existing_sources={p.get("source") for p in products}

    # Pull more than needed so one weak source can be compensated without
    # compromising the three-source requirement.
    mw=makerworld()
    pt=printables()
    tv=thingiverse()
    print(f"RAW CANDIDATES: MakerWorld={len(mw)} Printables={len(pt)} Thingiverse={len(tv)}",flush=True)

    # Balanced target: all three sources must contribute materially.
    source_targets={"MW":1400,"PT":1400,"TV":1200}
    selected_all=[]
    source_counts={}
    category_weights={
        "Automotive":0.15,"Tools & Workshop":0.15,"Office & Desk":0.12,
        "Electronics & Tech":0.12,"Home & Living":0.12,"Business & Retail":0.10,
        "Creator & Gaming":0.07,"Repair & Replacement":0.10,"Garden & Outdoor":0.04,
        "Education & Maker":0.03
    }
    quotas={g:round(TARGET_NEW*w) for g,w in category_weights.items()}
    # Correct rounding drift.
    while sum(quotas.values())<TARGET_NEW: quotas["Tools & Workshop"]+=1
    while sum(quotas.values())>TARGET_NEW: quotas["Home & Living"]-=1

    pools={"MW":mw,"PT":pt,"TV":tv}
    for sk in ("MW","PT","TV"):
        cand=pools[sk]
        # source-level target; category quota is soft and total target is hard.
        pool=[]
        seen=set()
        for d in cand:
            k=norm(d.get("name"))
            if not k or k in existing_names or d.get("source") in existing_sources or k in seen: continue
            seen.add(k)
            s=score(d,d["group"])
            if s>=8: pool.append((s,d))
        pool.sort(key=lambda x:x[0],reverse=True)
        source_selected=[]
        local_counts={g:0 for g in GROUPS}
        for s,d in pool:
            # Prefer categories that are still below global quotas.
            g=d["group"]
            if local_counts[g] >= quotas.get(g,0): continue
            source_selected.append(d); local_counts[g]+=1
            if len(source_selected)>=source_targets[sk]: break
        # If category caps prevent target, fill from remaining pool.
        if len(source_selected)<source_targets[sk]:
            used={norm(d["name"]) for d in source_selected}
            for s,d in pool:
                if norm(d["name"]) in used: continue
                source_selected.append(d); used.add(norm(d["name"]))
                if len(source_selected)>=source_targets[sk]: break
        if len(source_selected)<source_targets[sk]:
            raise SystemExit(f"{sk} only has {len(source_selected)} qualifying market products; need {source_targets[sk]}.")
        selected_all.extend((sk,d) for d in source_selected)
        source_counts[sk]=len(source_selected)

    if len(selected_all)!=TARGET_NEW:
        raise SystemExit(f"Selected {len(selected_all)} new products; expected exactly {TARGET_NEW}.")

    new=[]
    ranks={"MW":0,"PT":0,"TV":0}
    for sk,d in selected_all:
        ranks[sk]+=1
        new.append(make_product(d,sk,ranks[sk]))

    final=products+new
    if len(final)!=5000:
        raise SystemExit(f"Final catalogue would contain {len(final)} products, not 5000.")
    data["products"]=final
    DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

    print("SUCCESS: generated exactly 4,000 new products.",flush=True)
    print("SOURCE COUNTS:",source_counts,flush=True)
    print("FINAL TOTAL:",len(final),flush=True)

if __name__=="__main__":
    main()
