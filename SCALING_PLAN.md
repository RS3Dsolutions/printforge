# PrintForge scaling architecture

## Current prototype
The catalogue remains a static GitHub Pages prototype. Product metadata lives in products.json and the photo refresh workflow downloads public gallery images locally.

## Image delivery direction
Do not make the browser fetch thousands of source-platform images directly.

The planned production path is:

Source platforms -> ingestion workflow -> optimized image storage/CDN -> PrintForge

For the first scaling step, the image refresh workflow can keep collecting multiple genuine gallery images per product. It now targets up to 8 images per product.

For larger catalogues, move image binaries out of the Git repository into object storage/CDN. Keep only image keys/URLs in products.json.

Recommended stack:
- Product metadata: JSON initially; database later when catalogue/search volume requires it.
- Image storage: Cloudflare R2 or equivalent object storage.
- Delivery: CDN with long-lived caching.
- Transformation: generate responsive WebP/AVIF variants at the edge.
- Browser: lazy-load catalogue thumbnails; load the gallery only when a product is opened.
- Ingestion: scheduled worker that verifies commercial-use licensing, downloads public gallery images, deduplicates them, and writes metadata.

## Why this matters
Git repositories are a poor long-term image store. At 10,000+ products, committing several images per product makes the repository and deployments unnecessarily large. The website should be able to grow from hundreds to thousands of products without forcing the browser to download the whole image library.

## Product descriptions
Descriptions are customer-facing copy. They should explain what the product is, what problem it solves, where it is useful, and any compatibility check the customer should know about. Source/creator/licensing details stay outside the customer-facing description.

## Mobile navigation
Product modals now create a browser history entry. Pressing the mobile browser back button closes the product modal instead of navigating away from the catalogue.

## Future image gateway
A Cloudflare Worker/image transformation layer can sit between the browser and image storage/source platforms. It can resize and convert images at the edge and cache the result. The gateway should use a strict source allowlist and must never become an open proxy.

This layer should be introduced when the image storage/CDN migration is made, rather than adding a third-party public image proxy to the prototype.
