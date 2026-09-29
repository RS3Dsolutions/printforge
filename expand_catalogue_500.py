import json, re, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "products.json"
TARGET_NEW = 500
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
API = "https://api.printables.com/graphql/"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Content-Type": "application/json"})

# Conservative commercial-use allowlist. We intentionally exclude NC, SA,
# Standard Digital File License, club-only/private-use licenses, and unknowns.
ALLOWED_LICENSES = (
    "cc0", "public domain", "cc by", "cc by-nd"
)

BLOCKED_WORDS = re.compile(
    r"\\b("
    r"nsfw|porn|sex|nude|adult|erotic|weapon|gun|firearm|rifle|pistol|"
    r"grenade|bomb|explosive|drug|cannabis|marijuana|thc|political"
    r")\\b", re.I
)

# Broad catalogue discovery: practical objects first, then hobby/creative.
QUERY_GROUPS = {
    "Automotive": [
        "car accessory","car holder","car organizer","car mount","dashboard organizer",
        "car clip","car trim","car interior","vehicle accessory","motorcycle accessory",
        "motorcycle holder","bike accessory","scooter accessory","cup holder car",
        "phone holder car","car cable organizer","car storage","garage car tool",
        "automotive replacement","car repair clip","automotive bracket","car hook"
    ],
    "Tools & Workshop": [
        "tool holder","tool organizer","workbench organizer","workshop storage",
        "socket holder","screwdriver holder","hex key holder","wrench holder",
        "pliers holder","drill holder","power tool holder","bit organizer",
        "screw organizer","bolt organizer","nut organizer","caliper holder",
        "measuring tool holder","paint tool holder","clamp organizer","magnet holder",
        "pegboard tool","garage organizer","maker tool","3d printer tool holder"
    ],
    "Office & Desk": [
        "desk organizer","office organizer","pen holder","pencil holder","phone stand",
        "tablet stand","laptop stand","monitor accessory","desk cable management",
        "cable clip desk","headphone stand","business card holder","document holder",
        "notebook holder","desk tray","drawer organizer","desk hook","office storage",
        "charging dock","stationery organizer","remote holder","desk name plate"
    ],
    "Electronics & Tech": [
        "electronics enclosure","raspberry pi case","arduino case","sensor enclosure",
        "usb organizer","cable organizer","cable clip","power adapter holder",
        "charger holder","sd card holder","micro sd holder","battery holder",
        "electronics stand","router mount","smartphone dock","webcam mount",
        "controller stand","gamepad stand","keyboard accessory","electronics bracket",
        "led enclosure","maker electronics","tech organizer"
    ],
    "Home & Living": [
        "home organizer","kitchen organizer","bathroom organizer","drawer organizer",
        "shelf organizer","storage box","storage bin","wall hook","coat hook",
        "key holder","soap dish","toothbrush holder","toilet paper holder",
        "kitchen hook","bag holder","cable organizer home","remote control holder",
        "plant pot","plant holder","flower pot","desk decor","wall decor","door stop",
        "furniture connector","shelf bracket","cabinet organizer","closet organizer",
        "laundry organizer","household gadget","kitchen gadget","bottle holder",
        "cup holder","food bag clip","spice organizer","kitchen tool holder"
    ],
    "Business & Retail": [
        "retail display","shop display stand","product display stand","price tag holder",
        "sign holder","business card stand","counter display","brochure holder",
        "menu holder","receipt holder","queue token holder","retail organizer",
        "store shelf label","peg display","merchandise stand","jewelry display",
        "watch display","glasses display","phone display stand","sample holder"
    ],
    "Repair & Replacement": [
        "replacement clip","replacement bracket","replacement knob","replacement cap",
        "replacement cover","replacement spacer","replacement bushing","repair part",
        "repair clip","hinge repair","broken plastic replacement","appliance knob",
        "appliance clip","furniture repair","drawer repair","latch replacement",
        "switch cover","button replacement","cable strain relief","grommet",
        "washer spacer","mechanical spacer","plastic repair part","replacement foot"
    ],
    "Hobby & Gaming": [
        "board game organizer","card holder","card deck box","dice tray","dice tower",
        "gaming token holder","miniature holder","paint bottle holder","model stand",
        "tabletop organizer","chess piece box","puzzle organizer","lego organizer",
        "gaming accessory","controller stand","headset stand","craft organizer",
        "sewing organizer","yarn holder","hobby tool holder","art supply organizer",
        "paint brush holder","camera accessory","photography accessory"
    ],
    "Garden & Outdoor": [
        "garden tool holder","plant label","plant support","seed organizer","garden hook",
        "hose holder","irrigation clip","plant pot holder","trellis clip","garden organizer",
        "outdoor hook","camping organizer","tent accessory","bike storage","fishing organizer",
        "bird feeder accessory","greenhouse clip","garden connector"
    ],
    "Education & Maker": [
        "classroom organizer","school supply organizer","teacher desk organizer",
        "science model","math teaching aid","geometry model","educational tool",
        "maker project","maker organizer","lab organizer","STEM project","robotics holder",
        "3d printing accessory","filament organizer","filament clip","spool holder",
        "printer accessory","printer stand","slicer tool holder","workbench accessory"
    ]
}

def log(msg):
    print(msg, flush=True)

def gql_search(q, limit=30, ordering="popular"):
    query = """
    query SearchModels($query: String!, $limit: Int, $offset: Int, $ordering: SearchChoicesEnum) {
      result: searchPrints2(query: $query, printType: print, limit: $limit, offset: $offset, ordering: $ordering) {
        items {
          id
          name
          slug
          summary
          datePublished
          likesCount
          downloadCount
          ratingAvg
          user { publicUsername handle }
          license { id name disallowCommercialUse }
          image { filePath }
        }
        totalCount
      }
    }
    """
    payload = {
        "operationName": "SearchModels",
        "query": query,
        "variables": {"query": q, "limit": limit, "offset": 0, "ordering": ordering}
    }
    try:
        r = S.post(API, json=payload, timeout=25)
        if not r.ok:
            log(f"  API HTTP {r.status_code} for {q}")
            return []
        data = r.json()
        if data.get("errors"):
            # Some deployments omit disallowCommercialUse. Retry without that field.
            query2 = query.replace(" disallowCommercialUse", "")
            payload["query"] = query2
            r = S.post(API, json=payload, timeout=25)
            data = r.json()
        if data.get("errors"):
            log(f"  GraphQL error for {q}: {data['errors'][0].get('message','unknown')}")
            return []
        return ((data.get("data") or {}).get("result") or {}).get("items") or []
    except Exception as e:
        log(f"  Search failed for {q}: {e}")
        return []

def allowed_license(lic):
    if not isinstance(lic, dict):
        return False
    name = (lic.get("name") or "").strip().lower()
    if not name:
        return False
    if lic.get("disallowCommercialUse") is True:
        return False
    if "noncommercial" in name or "non-commercial" in name or "standard digital" in name:
        return False
    if "sharealike" in name or "share-alike" in name:
        return False
    return any(name == x or name.startswith(x + " ") or x in name for x in ALLOWED_LICENSES)

def blocked(item):
    text = " ".join(str(item.get(k) or "") for k in ("name","summary"))
    return bool(BLOCKED_WORDS.search(text))

def clean_name(name):
    return re.sub(r"\\s+", " ", (name or "").strip())

def customer_description(item, group, query):
    summary = re.sub(r"<[^>]+>", " ", item.get("summary") or "")
    summary = re.sub(r"\\s+", " ", summary).strip()
    if summary:
        summary = summary[:240].rstrip(" .")
        return f"{summary}. Made to order with fitment or compatibility checked before production."
    return f"A practical {clean_name(item.get('name'))} for {group.lower()}. Made to order with compatibility checked before production."

def license_label(name):
    n = (name or "").strip()
    low = n.lower()
    if "cc0" in low or "public domain" in low:
        return "CC0 / Public Domain — commercial use permitted"
    if "cc by-nd" in low:
        return f"{n} — commercial physical use permitted; attribution required; no derivatives"
    return f"{n} — commercial physical use permitted; attribution required"

def existing_state():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    products = d.get("products", [])
    ids = {p.get("source") for p in products if p.get("source")}
    names = {clean_name(p.get("name")).lower() for p in products}
    return d, products, ids, names

def make_id(group, number):
    prefix = {
        "Automotive":"AUTO","Tools & Workshop":"WRK","Office & Desk":"OFF",
        "Electronics & Tech":"ELEC","Home & Living":"HOM","Business & Retail":"BUS",
        "Repair & Replacement":"REP","Hobby & Gaming":"HOB","Garden & Outdoor":"GDN",
        "Education & Maker":"EDU"
    }[group]
    return f"PF-{prefix}-N{number:03d}"

def main():
    data, products, existing_sources, existing_names = existing_state()
    current_new = sum(1 for p in products if p.get("id","").endswith(tuple()))
    # Persist a dedicated marker so reruns never add a second batch.
    already_added = [p for p in products if p.get("catalogBatch") == "expansion-500"]
    if len(already_added) >= TARGET_NEW:
        log(f"Expansion already complete: {len(already_added)}/{TARGET_NEW} new products.")
        return

    candidates = {}
    query_count = 0
    for group, queries in QUERY_GROUPS.items():
        for q in queries:
            query_count += 1
            items = gql_search(q, 30, "popular")
            log(f"[{query_count}] {group}: {q} -> {len(items)} results")
            for item in items:
                src = f"https://www.printables.com/model/{item.get('id')}-{item.get('slug')}" if item.get("id") and item.get("slug") else ""
                if not src or src in existing_sources or src in candidates:
                    continue
                name = clean_name(item.get("name"))
                if not name or name.lower() in existing_names or blocked(item):
                    continue
                if not allowed_license(item.get("license")):
                    continue
                # Skip very weak/empty entries.
                if len(name) < 4:
                    continue
                candidates[src] = (group, q, item)

    log(f"Commercially-screened unique candidates: {len(candidates)}")
    need = TARGET_NEW - len(already_added)
    if len(candidates) < need:
        raise SystemExit(f"Only {len(candidates)} screened candidates available; need {need}. Refusing to publish a partial 500-product expansion.")

    # Prefer popular/high-signal models, while distributing categories.
    grouped = {}
    for src, rec in candidates.items():
        grouped.setdefault(rec[0], []).append((src, rec))
    for arr in grouped.values():
        arr.sort(key=lambda x: (x[1][2].get("downloadCount") or 0, x[1][2].get("likesCount") or 0), reverse=True)

    selected = []
    # Round-robin by category so the expansion does not become 500 near-identical desk items.
    while len(selected) < need:
        progressed = False
        for group in QUERY_GROUPS:
            arr = grouped.get(group, [])
            if arr:
                selected.append(arr.pop(0))
                progressed = True
                if len(selected) >= need:
                    break
        if not progressed:
            break

    if len(selected) < need:
        raise SystemExit(f"Selection produced only {len(selected)} products; refusing partial expansion.")

    start_num = {k: 0 for k in QUERY_GROUPS}
    new_products = []
    for src, (group, q, item) in selected:
        start_num[group] += 1
        lic = item.get("license") or {}
        pid = make_id(group, start_num[group] + len([p for p in products if p.get("id","").startswith("PF-"+{"Automotive":"AUTO","Tools & Workshop":"WRK","Office & Desk":"OFF","Electronics & Tech":"ELEC","Home & Living":"HOM","Business & Retail":"BUS","Repair & Replacement":"REP","Hobby & Gaming":"HOB","Garden & Outdoor":"GDN","Education & Maker":"EDU"}[group]+"-N")]))
        new_products.append({
            "id": pid,
            "name": clean_name(item.get("name")),
            "category": group,
            "subcategory": q.title(),
            "type": "Made-to-order 3D printed product",
            "description": customer_description(item, group, q),
            "images": [],
            "customerTags": ["Made to order", "Commercial-use source verified"],
            "imagePaths": [],
            "platform": "Printables",
            "creator": ((item.get("user") or {}).get("publicUsername") or (item.get("user") or {}).get("handle") or "Printables creator"),
            "license": license_label(lic.get("name")),
            "source": src,
            "licenseGate": True,
            "imageStatus": "Awaiting real gallery image refresh.",
            "catalogBatch": "expansion-500"
        })

    products.extend(new_products)
    data["products"] = products
    data["lastUpdated"] = time.strftime("%Y-%m-%d")
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"ADDED {len(new_products)} NEW PRODUCTS")
    log(f"TOTAL CATALOGUE: {len(products)}")
    log(f"COMMERCIAL SCREEN: {len(new_products)}/{len(new_products)} passed")
    
if __name__ == "__main__":
    main()
