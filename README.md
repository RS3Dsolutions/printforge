# PrintForge V5.2

Customer-facing 3D-print catalogue for GitHub Pages.

## Customer experience
- Real product photographs are fetched automatically from each approved source page.
- Product descriptions remain visible even before the photo workflow finishes.
- Customer-facing pages do not show material, creator, licence, source, STL/3MF, or technical model information.
- Orders collect customer/delivery details and open WhatsApp using the universal `wa.me` handoff.

## Automatic photos
The GitHub Action `.github/workflows/refresh-images.yml` runs the `fetch_product_images.py` script. The script uses Jina Reader as a page-fetching fallback for model platforms that block ordinary requests, extracts source-page image URLs, downloads up to three images per product into `assets/products/<product-id>/`, and commits them back to `main`.

After the Action completes, GitHub Pages republishes the updated catalogue.

## Important
The catalogue should only contain products whose underlying model rights permit the intended commercial print use. Photograph reuse is a separate rights question; this workflow is intended to obtain the source-page gallery images for internal catalogue preparation and should be reviewed for photo rights before public commercial launch.
