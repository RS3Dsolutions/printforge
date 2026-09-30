# PrintForge Image Gateway

This directory is reserved for the edge image-delivery layer. The production migration should place optimized product images in object storage and serve them through a CDN/edge transformation layer. The browser should request PrintForge-owned image URLs rather than hotlinking source platforms.