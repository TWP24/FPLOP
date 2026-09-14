# Koru Club Vest Designer

A lead capture for club kit. A club's gear officer builds their vest, sends it in, and Koru
comes back with a proof — the design is the lead. Fabric, cuts, sizes and price are
deliberately not asked here; they are the conversation that follows, and asking a club to
decide them cold is what loses the lead.

Once a design is agreed, Koru opens a pre-order window on korusports.ie — the same model
already running for Bandon AC, but without Koru hand-building the spec each time.

`index.html` is the whole thing: one file, no build step, no dependencies.

Published draft: https://claude.ai/code/artifact/19a809e7-c2bf-430a-be1b-bfb5f9c5f205

## What a club does

Four steps: pick colours, pick a style, type the club name, send it. That is the entire
surface. Everything else is Koru's job.

## Mobile first

A gear officer opens this on a phone, so the phone layout is the base and the desktop one is
the media query. The preview sticks to the top of the viewport and the four steps are tabs
that scroll beneath it, so the vest is never off screen while you are changing it — the
earlier stacked layout pushed it away the moment you started. Tap targets are at least 44px,
text inputs are 16px so iOS does not zoom on focus, and the tab bar parks itself under the
preview by measuring it (`--tabTop`) rather than assuming a height.

From 880px up the same markup becomes two columns via grid areas: preview left, tabs and the
active step right.

## How it works

- **Flat mockup, front and back.** Both panels are drawn side by side the way a kit supplier
  presents them. An earlier version turned a generated 3D mesh, which was harder to make look
  right than it was worth — a flat drawing is what clubs are used to seeing, and it dropped
  the only external dependency the page had.
- **One texture, two panels.** The design paints to a 2048×1024 canvas holding both printed
  panels end to end, front centred at u=0.25 and back at u=0.75, so neither print lands on a
  side seam. Each vest outline clips its half of it.
- **Binding comes from the outline.** One stroke along the silhouette gives neck, armhole and
  hem trim together, so the trim can never drift out of register with the garment.
- **Colour sits with the thing it colours.** Body and trim are on the Vest tab, design and
  accent with the style gallery, lettering with the font controls. One `.colourbox` component
  renders wherever it is dropped, reading its roles from `data-roles` and keeping its own
  active target, so there is no global "which colour am I editing" state to lose track of.
- **Five chest faces**, each with the letter-spacing it wants: Block (Archivo), Condensed
  (Oswald), Slab (Bevan), Varsity (Graduate) and Script (Kaushan), the last set in mixed case
  because it reads badly in capitals. A webfont used only on a canvas is never requested by the
  document, so `loadFonts` asks for each face explicitly before painting — otherwise the canvas
  silently falls back and every face looks the same.
- **Front and back print independently.** Either can be dropped to nothing, so a club can put
  its name on the chest only, on the back only, or run a plain vest with just a crest.
- **Print size is a fraction of the panel, not a font size.** The slider sets how much of the
  chest the name spans, so a three-letter club and a twelve-letter one both fill the same
  width — which is how a chest print actually works. A cap stops short names ballooning.
- **Styles name a colour role, not a hex.** A style says "design" or "accent" where a colour
  goes, so changing one of the club's five colours restyles the whole gallery at once. That
  is what lets seventeen styles sit behind five colour swatches.
- **Twenty-seven layer types under the hood.** Blocks and stripes (band, hoops, vertical
  stripes, halves, quarters, sash, chevron, side panels, yoke, shoulder stripes, hem band,
  centre stripe, piping) and print effects (fade, halftone, grain, ikat, geo blocks, camo,
  smear, snakeskin, mosaic, warp chevron, contours, tiled crest, terrazzo, tartan). Clubs never
  see these: a style is a short list of layers with their numbers baked in. Adding a style is a
  line in `STYLES`.
- **Kit shapes lay out per panel, not per texture.** A vest with four vertical stripes has four
  on the front and four on the back, not eight spread across the pair, so stripes, halves,
  quarters and shoulder stripes work outward from each panel centre.
- **Twenty-seven styles in two groups** — blocks and stripes, prints and textures — because a
  flat list that long is a wall. Thumbnails are cached against the five colours, the strength
  and the club initials, since a noise style costs tens of thousands of samples and the gallery
  redraws on every colour change.
- **Sponsor logo** is a placement the club chooses, drawn as a placeholder box on the chest,
  back or hem. Per-runner name and number were built and then removed: this page settles one
  club design, and what an individual runner adds belongs to the order, not the design.
- **The tiled crest uses the club's own initials**, taken from the name they typed, so the
  mockup reads as their vest rather than a generic watermark.
- **Halftones behave like a separation.** A screen's dot radius follows a ramp across the
  panel and the screen sits 34° off the fade direction, so two screens in two colours
  interfere the way process printing does instead of sitting on top of each other.
- **One noise function, read four ways.** Seeded value noise with fractal octaves drives camo
  (pushed through itself so edges tear rather than curve, then hard-thresholded with the
  threshold jittered per pixel so the boundary breaks into speckle), smear (the same noise
  stretched along one axis and mapped to a soft alpha), and the snakeskin blotches. Seeds come
  from the style index, so nothing reshuffles between renders.
- **Saving** uses the artifact `db` capability: designs are written to `designs/<code>` and the
  page reopens one from `#d=<code>`, so a committee can share a link before committing.
- **Nothing about the supply chain reaches the club.** Mill names and style codes are not
  shown, not copied, and not in the page source. The stored record adds a `production` block
  with the club code for the `KORU-<CLUB>-<CUT>-<SIZE>` SKU shape.

## Worth confirming with the mill

- The smallest halftone dot that holds without filling in.
- Whether fine grain survives the press.
- How close a print can run to a seam before it distorts.

The texture wraps with the side seam at u=0, so a design running across the body has a
discontinuity there. That is how a sublimated vest actually prints — flat panels, then sewn —
so it is left as is rather than forced to wrap seamlessly.

## Getting it onto korusports.ie

**1. Page on the storefront.** Drop the markup, CSS and JS into a custom section
(`sections/vest-designer.liquid`) and assign it to a page template at `/pages/vest-designer`.
The section's schema exposes the colour card and the style list as settings, so they change in
the theme editor rather than in code. There is no external script to allow through the CSP.

**2. Submissions.** The designer produces a clean JSON spec — style, the five colours, chest
print and crest — and the stage canvas renders straight to a PNG. Post both to a Make.com
webhook (Make is already connected to this stack) and have the scenario email Koru, drop the
design into a sheet, and create or update the club contact in Klaviyo. That avoids needing a
custom app on the Basic plan. If submissions should live in Shopify itself, define a
`club_kit_design` metaobject and write to it via the Admin API.

**3. Opening a window.** Cuts, sizes and prices are agreed off the back of the proof, so the
window is opened from that conversation rather than straight from the submission. Create the
product set: one product per cut, per-size variants, tags `club:<handle>`, `tier:`, `mill:`,
`style:`, `window:YYYY-MM`, and inventory left to go negative as pre-orders — the shape the
Bandon AC products already use. This is the step worth scripting, because it is the one Koru
currently does by hand for every club.
