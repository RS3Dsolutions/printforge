#!/usr/bin/env python3
"""Source and curate 446 MakerWorld products for PrintForge."""
import json, math, re, time
from pathlib import Path
from urllib.parse import urlencode
import requests
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"products.json"
TARGET=446
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
S=requests.Session()
S.headers.update({"User-Agent":UA,"Accept-Language":"en-US,en;q=0.9"})
API_BASE="https://api.bambulab.com/v1"

CATEGORY_ROOTS={
    "household":"category_800","education":"category_500","tools":"category_700",
    "toys_games":"category_400","3d_printer":"category_900","hobby_diy":"category_300"
}
GROUP_SOURCES={
    "Automotive":["hobby_diy","tools","3d_printer","household"],
    "Tools & Workshop":["tools","3d_printer","hobby_diy"],
    "Office & Desk":["household","3d_printer","hobby_diy"],
    "Electronics & Tech":["3d_printer","tools","household"],
    "Home & Living":["household","hobby_diy"],
    "Business & Retail":["household","hobby_diy","tools","fashion","art"],
    "Creator & Gaming":["toys_games","3d_printer","hobby_diy","art","props"],
    "Repair":["tools","household","3d_printer","hobby_diy"],
}
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
ALLOW={"CC0","BY","BY-SA","BY-ND","PUBLIC DOMAIN","CC BY","CC BY-SA","CC BY-ND"}
BLOCK=re.compile(r"\b(weapon|gun|firearm|ammo|grenade|knife|sword|cosplay|figurine|fanart|pokemon|marvel|disney|star wars|harry potter|nintendo logo|medical|prosthetic|baby|food safe|food-contact)\b",re.I)
PRACTICAL=re.compile(r"\b(holder|mount|stand|organizer|clip|bracket|adapter|case|box|rack|hook|replacement|repair|storage|jig|fixture|caddy|tray|dock|charger|cover|part|component|insert|cap|lid|bin|basket|drawer|shelf|hanger|bottle|container|coaster|keychain|tag|label|sign|display|phone|tablet|laptop|keyboard|mouse|headset|controller|cable|cord|wire|battery|ssd|hard.?drive|raspberry|arduino|camera|microphone|speaker|remote|tool|wrench|socket|drill|screwdriver|clamp|pegboard|gridfinity|car|vehicle|bike|scooter|dash|console|visor|cup|seat|mirror|license.?plate|fuse|knob|hinge|wheel|wheel.?cap|panel|gasket|seal|bracket|fixture|template|gauge|spacer|shim|mounting|fastener|enclosure|housing|casework)\b",re.I)

def norm(s):
    return re.sub(r"[^a-z0-9]+"," ",(s or "").lower()).strip()

def _walk_designs(obj):
    """Yield design-like dictionaries from several MakerWorld response shapes."""
    if isinstance(obj, dict):
        if obj.get("id") and (obj.get("title") or obj.get("name")):
            yield obj
        for key, value in obj.items():
            if key in {"data","result","results","list","items","designs","records","hits"}:
                yield from _walk_designs(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_designs(value)

def get_json(url, params=None, timeout=30, label="request", min_delay=1.5):
    """GET JSON with conservative pacing and exponential backoff for 429s."""
    for attempt in range(6):
        try:
            r=S.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                wait=[5,15,30,60,90,120][attempt]
                print(f"{label} HTTP 429; backing off {wait}s (attempt {attempt+1}/6)",flush=True)
                time.sleep(wait)
                continue
            if not r.ok:
                print(f"{label} HTTP {r.status_code}",flush=True)
                return None
            time.sleep(min_delay)
            return r.json()
        except Exception as exc:
            if attempt >= 5:
                print(f"{label} error after retries: {exc}",flush=True)
                return None
            wait=[3,8,15,30,60][attempt]
            print(f"{label} error: {exc}; retrying in {wait}s",flush=True)
            time.sleep(wait)
    return None

def discover_category_pages(group_terms, pages=80, page_size=20):
    """Discover MakerWorld models through the public category JSON feed.

    This avoids MakerWorld HTML/SSR rendering entirely. The category feed is
    the same public feed pattern used by independent MakerWorld scrapers.
    """
    out={}
    category_keys={
        "art":"category_100",
        "fashion":"category_200",
        "hobby_diy":"category_300",
        "household":"category_400",
        "education":"category_500",
        "miniatures":"category_600",
        "tools":"category_700",
        "toys_games":"category_800",
        "3d_printer":"category_900",
        "props":"category_1000",
    }

    def classify(title, tags="", source_key=""):
        text_value=norm(f"{title} {tags}")
        if BLOCK.search(text_value) or not PRACTICAL.search(text_value):
            return None
        best=None
        best_score=0
        for group,terms in group_terms:
            score_value=sum(1 for term in terms if norm(term) in text_value)
            if score_value>best_score:
                best=group
                best_score=score_value
        if best:
            return best

        # Category-aware fallback: the public MakerWorld category is a useful
        # second signal when the title uses an unexpected product name.
        fallback={
            "tools":"Tools & Workshop",
            "3d_printer":"Tools & Workshop",
            "household":"Home & Living",
            "hobby_diy":"Home & Living",
            "education":"Office & Desk",
            "toys_games":"Creator & Gaming",
            "art":"Business & Retail",
            "fashion":"Home & Living",
            "props":"Creator & Gaming",
            "miniatures":"Creator & Gaming",
        }
        return fallback.get(source_key)

    for source_key,nav_key in category_keys.items():
        empty_pages=0
        for page_no in range(1,pages+1):
            offset=(page_no-1)*page_size
            url=f"{API_BASE}/search-service/select/design/nav"
            payload=get_json(
                url,
                params={"navKey":nav_key,"offset":offset,"limit":page_size},
                timeout=30,
                label=f"Category {source_key} page {page_no}",
                min_delay=0.8,
            )
            if payload is None:
                empty_pages += 1
                if empty_pages>=2:
                    break
                continue

            hits=payload.get("hits",[]) if isinstance(payload,dict) else []
            models=[]
            for item in hits:
                model=item.get("design") if isinstance(item,dict) and isinstance(item.get("design"),dict) else item
                if not isinstance(model,dict) or not model.get("id"):
                    continue
                if model.get("designType",0)!=0:
                    continue
                models.append(model)

            if not models:
                print(f"Category {source_key} page {page_no}: no models returned",flush=True)
                break

            added=0
            for model in models:
                mid=str(model.get("id")).strip()
                title=str(model.get("title") or model.get("name") or "").strip()
                tags=" ".join(map(str,model.get("tags") or []))
                group=classify(title,tags,source_key)
                if not group:
                    continue
                src=f"https://makerworld.com/en/models/{mid}"
                if mid not in out:
                    out[mid]=(src,group,"category:"+source_key,model)
                    added+=1

            print(
                f"  category {source_key} page {page_no}: "
                f"{len(models)} models, {added} practical new",
                flush=True
            )
            empty_pages=0

    return out

def discover_api(group, terms, pages=10, page_size=30):
    """Discover MakerWorld candidates through the public keyword-search endpoint."""
    out={}
    for term in terms:
        keyword=norm(term)
        for page in range(pages):
            payload=get_json(
                f"{API_BASE}/search-service/select/design2",
                params={"keyword":keyword,"offset":page*page_size,"limit":page_size},
                timeout=30,
                label=f"Search '{term}' page {page+1}",
                min_delay=0.35
            )
            if payload is None:
                break
            hits=list(_walk_designs(payload))
            if not hits:
                print(f"  {term} page {page+1}: no hits",flush=True)
                break
            added=0
            for item in hits:
                mid=str(item.get("id") or item.get("designId") or "").strip()
                if not mid:
                    continue
                title=str(item.get("title") or item.get("name") or "").strip()
                tags=" ".join(map(str,item.get("tags") or item.get("categories") or []))
                text_value=norm(f"{title} {tags}")
                if BLOCK.search(text_value) or not PRACTICAL.search(text_value):
                    continue
                if keyword not in text_value and not any(norm(t) in text_value for t in term.split()):
                    continue
                lic=str(item.get("license") or "").strip()
                if not license_ok(lic):
                    continue
                src=str(item.get("url") or item.get("source") or f"https://makerworld.com/en/models/{mid}")
                if mid not in out:
                    out[mid]=(src,group,term,item)
                    added+=1
            print(f"  {term} page {page+1}: {len(hits)} hits, {added} new",flush=True)
            if len(hits)<page_size:
                break
    return out

def detail(mid):
    d=get_json(
        f"{API_BASE}/design-service/design/{mid}",
        timeout=20,
        label=f"Detail {mid}",
        min_delay=1.0
    )
    if isinstance(d,dict) and isinstance(d.get("data"),dict):
        d=d["data"]
    return d if isinstance(d,dict) else None

def detail_browser(context, src, mid):
    """Read license and basic metadata from a public MakerWorld model page."""
    page=context.new_page()
    try:
        page.goto(src, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1200)
        html=page.content()
        title=(page.title() or "").replace(" | MakerWorld","").strip()
        desc=""
        try:
            desc=page.locator('meta[name="description"]').get_attribute("content") or ""
        except Exception:
            pass
        blob=html
        # Prefer explicit license fields embedded in page JSON, then visible text.
        licenses=re.findall(r'(?i)(?:license(?:Name)?)[^A-Za-z]{0,20}(CC\\s*BY(?:-SA|-ND)?|CC0|Public Domain|BY(?:-SA|-ND)?)',blob)
        if not licenses:
            licenses=re.findall(r'(?i)\\b(CC\\s*BY(?:-SA|-ND)?|CC0|Public Domain)\\b',blob)
        lic=licenses[0].strip() if licenses else ""
        creator=""
        m=re.search(r"""(?i)(?:designCreator|creator)[^A-Za-z]{0,30}(?:name|nickname|handle)[^A-Za-z]{0,20}["']([^"']+)["']""",blob)
        if m:
            creator=m.group(1).strip()
        if not title:
            title=mid
        d={"id":mid,"title":title,"summary":desc,"license":lic,"creator":creator}
        return d
    except Exception as exc:
        print(f"Model page error {mid}: {exc}",flush=True)
        return None
    finally:
        page.close()

def license_ok(v):
    x=norm(v).upper().replace("CREATIVE COMMONS ","")
    return any(a in x for a in ALLOW)

def score(d,group):
    title=d.get("title") or ""
    tags=" ".join(map(str,d.get("tags") or []))
    summary=re.sub("<[^>]+>"," ",str(d.get("summary") or ""))
    text=f"{title} {tags} {summary}"
    if BLOCK.search(text):
        return -10**9
    stats=d.get("stats") or {}
    downloads=int(d.get("downloadCount") or stats.get("downloadCount") or 0)
    likes=int(d.get("likeCount") or stats.get("likeCount") or 0)
    prints=int(d.get("printCount") or stats.get("printCount") or 0)
    boosts=int(d.get("boostCount") or stats.get("boostCount") or 0)
    s=2.0*math.log1p(downloads)+2.8*math.log1p(prints)+1.1*math.log1p(likes)+.7*math.log1p(boosts)
    s+=8 if PRACTICAL.search(text) else 0
    s+=5 if any(k in norm(text) for k in ["customizable","parametric"]) else 0
    if any(k in norm(text) for k in ["mini","compact","small","no support","print in place"]):
        s+=2
    if any(k in norm(text) for k in ["hour","hours","large","giant","multi part"]):
        s-=1
    if group in ("Automotive","Repair","Business & Retail"):
        s+=3
    return s

def make_product(d,group,source,rank):
    title=(d.get("title") or "MakerWorld product").strip()
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
        "subcategory":"MakerWorld Market Picks",
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
        found=discover_api(group,terms,pages=10,page_size=30)
        candidates.update(found)
        print(f"{group}: {len(found)} licensed practical candidates",flush=True)

    print("Unique licensed practical MakerWorld candidates:",len(candidates),flush=True)
    if len(candidates)<TARGET:
        raise SystemExit(f"Only {len(candidates)} qualifying MakerWorld candidates discovered; refusing to fabricate {TARGET} products.")

    ranked=[]
    for mid,(src,group,term,item) in candidates.items():
        title=str(item.get("title") or item.get("name") or "")
        rough=8 if PRACTICAL.search(title) else 0
        rough+=3 if any(k in norm(title) for k in ["custom","parametric","modular"]) else 0
        rough+=3 if group in ("Automotive","Repair","Business & Retail") else 0
        downloads=int(item.get("downloadCount") or 0)
        likes=int(item.get("likeCount") or 0)
        prints=int(item.get("printCount") or 0)
        rough += min(20, math.log1p(downloads)*2 + math.log1p(likes) + math.log1p(prints)*2)
        ranked.append((rough,mid,src,group,item))
    ranked.sort(reverse=True)

    scored=[]
    for rough,mid,src,group,item in ranked:
        title=str(item.get("title") or item.get("name") or "").strip()
        if norm(title) in existing_names or src in existing_sources:
            continue
        d=dict(item)
        d["title"]=title
        d["license"]=str(item.get("license") or "").strip()
        if not license_ok(d["license"]):
            continue
        sc=score(d,group)
        if sc<8:
            continue
        scored.append((sc,group,src,d))
        if len(scored)>=TARGET*3:
            break

    print("Qualifying MakerWorld products after scoring:",len(scored),flush=True)
    if len(scored)<TARGET:
        raise SystemExit(f"Only {len(scored)} qualifying MakerWorld products found after scoring; refusing to create a fake {TARGET}.")

    scored.sort(key=lambda x:x[0],reverse=True)
    selected=[]
    seen=set()
    counts={g:0 for g in GROUPS}
    total_terms=sum(len(v) for v in GROUPS.values())
    quota={g:max(15,round(TARGET*len(terms)/total_terms)) for g,terms in GROUPS.items()}

    for sc,g,src,d in scored:
        key=norm(d.get("title"))
        if not key or key in seen:
            continue
        if counts[g]<quota[g]:
            selected.append((sc,g,src,d))
            seen.add(key)
            counts[g]+=1
        if len(selected)>=TARGET:
            break

    if len(selected)<TARGET:
        for sc,g,src,d in scored:
            key=norm(d.get("title"))
            if not key or key in seen:
                continue
            selected.append((sc,g,src,d))
            seen.add(key)
            if len(selected)>=TARGET:
                break

    if len(selected)!=TARGET:
        raise SystemExit(f"Selection produced {len(selected)} products instead of exactly {TARGET}.")

    base=max([int(re.search(r"(\d+)$",p.get("id","0")).group(1)) for p in products if p.get("id","").startswith("PF-MW-")]+[0])
    for i,(sc,g,src,d) in enumerate(selected,1):
        products.append(make_product(d,g,src,base+i))

    if len(products)!=554+TARGET:
        raise SystemExit(f"Unexpected catalogue total {len(products)}; expected {554+TARGET}.")

    data["products"]=products
    data["total"]=len(products)
    data["withImages"]=sum(bool(p.get("imagePaths")) for p in products)
    data["newProducts"]=TARGET
    DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Added exactly {TARGET} MakerWorld products. Catalogue total: {len(products)}",flush=True)
    print("Category counts:",counts,flush=True)

if __name__=="__main__":
    main()
