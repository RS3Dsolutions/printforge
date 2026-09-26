# PrintForge V1 — Deployment

The site is a static HTML/CSS/JavaScript prototype. No database, server or paid hosting is
required for this version.

## Easiest route: Cloudflare Pages Direct Upload

1. Create/sign in to a Cloudflare account.
2. Open Workers & Pages.
3. Choose Create application > Get started > Drag and drop your files.
4. Create a project name, for example `printforge-catalogue`.
5. Upload this entire folder (or a ZIP containing it).
6. Select Deploy site.
7. Cloudflare will provide a `pages.dev` address.

Cloudflare's official Direct Upload documentation:
https://developers.cloudflare.com/pages/get-started/direct-upload/

## Alternative: GitHub Pages

1. Create a GitHub account if you don't already have one.
2. Create a new public repository, for example `printforge-catalogue`.
3. Upload the contents of this package to the repository root.
4. Open Settings > Pages.
5. Under Build and deployment, choose Deploy from a branch.
6. Select `main` and `/ (root)`, then Save.
7. GitHub will publish the site at a github.io address.

GitHub's official documentation:
https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site

## What requires the owner

Only the account creation/login and the final Deploy/Save action require the user's
intervention. Do not give passwords or OTPs to anyone.

## V1 scope

The deployed site is intentionally a catalogue:
- 106 products
- search
- category/subcategory browsing
- product descriptions
- product detail view
- quantity selection
- enquiry/order list

No payments, live manufacturing prices, print-time estimates, CAD uploads or production
automation are included in V1.
