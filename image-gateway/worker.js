export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname !== "/image") return new Response("Not found", {status:404});
    const source = url.searchParams.get("url");
    if (!source) return new Response("Missing url", {status:400});
    let target;
    try { target = new URL(source); } catch { return new Response("Invalid url", {status:400}); }
    const allowed = ["media.printables.com","makerworld.bblmw.com","makerworld.com"];
    if (target.protocol !== "https:" || !allowed.includes(target.hostname)) {
      return new Response("Source host not allowed", {status:403});
    }
    const cacheKey = new Request(url.toString(), request);
    const cache = caches.default;
    let cached = await cache.match(cacheKey);
    if (cached) return cached;
    const upstream = await fetch(target.toString(), {
      headers: { "Accept": "image/avif,image/webp,image/*,*/*;q=0.8" },
      cf: { cacheEverything: true, cacheTtl: 604800 }
    });
    if (!upstream.ok) return new Response("Upstream image unavailable", {status:502});
    const headers = new Headers(upstream.headers);
    headers.set("Cache-Control","public, max-age=604800, s-maxage=604800, stale-while-revalidate=86400");
    headers.set("X-Content-Type-Options","nosniff");
    const response = new Response(upstream.body,{status:200,headers});
    ctx.waitUntil(cache.put(cacheKey,response.clone()));
    return response;
  }
};