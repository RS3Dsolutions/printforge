# PrintForge V5 — customer catalogue + automatic product-photo pipeline

This version is designed for the public customer storefront.

## Customer-facing
- Real product photographs are downloaded from the approved source model pages by the GitHub Actions workflow.
- Product images are stored in the repository under `assets/products/<product-id>/` and served locally by GitHub Pages.
- No material, creator, source URL, licence text, STL/3MF, or model-file information is shown in the storefront.
- WhatsApp ordering uses the official WhatsApp send endpoint and provides a visible fallback link if the browser does not open WhatsApp automatically.
- Products without a successfully fetched real photo are not shown to customers until the photo is available.

## Photo pipeline
`fetch_product_images.py` reads the approved product source URLs from `products.json`, fetches the source pages, extracts gallery/cover image URLs, downloads up to three image files per product, and writes `imagePaths` back to `products.json`.

The workflow in `.github/workflows/refresh-images.yml` runs when `products.json` or the scraper changes. It commits the downloaded images back to `main`, after which GitHub Pages publishes them. GitHub Pages publishes static files from the repository; no paid hosting is required.

## Licensing note
Model/physical-print rights and image/photo rights are separate questions. The storefront should only display photographs when the applicable source terms permit the intended reuse. Where a licence requires attribution, the business must retain the required attribution in the internal/legal record or appropriate site notice; customer-facing product cards intentionally omit technical licence metadata.
