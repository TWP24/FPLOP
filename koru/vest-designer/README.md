# Koru Club Vest Designer

A lead capture for club kit. A club's gear officer builds their vest, sends it in, and
Koru comes back with a proof — the design is the lead. Fabric, cuts, sizes and price are
deliberately not asked here; they are the conversation that follows, and asking a club to
decide them cold is what loses the lead.

Once a design is agreed, Koru opens a pre-order window on korusports.ie — the same model
already running for Bandon AC, but without Koru hand-building the spec each time.

`index.html` is the whole thing: no build step, no dependencies except three.js from a CDN.

Published draft: https://claude.ai/code/artifact/19a809e7-c2bf-430a-be1b-bfb5f9c5f205

## What it does

- **3D preview.** The vest is a tube of elliptical cross-sections whose top edge is a
  function of the angle around the body — high over the shoulders, scooped at the neck,
  cut away at the sides for the armholes. One profile (`EDGE` in `index.html`) gives
  neckline, straps and armholes at once, and painting the binding against that same
  profile makes the trim follow the real edge all the way round. Drag or arrow-key to turn.
- **Fabric texture** is painted to a 2048×1024 canvas and wrapped with centre-front at
  u=0.25 and centre-back at u=0.75, so neither print lands on the side seam.
- **Falls back** to a flat projected view built from the same profile when WebGL or the
  CDN is unavailable.
- **Layered design.** Everything Koru makes is sublimated, so the design surface is a printed
  image rather than pieces of cloth. Two kinds of layer stack in one list: hard-edged blocks
  and stripes (band, hoops, sash, side panels, chevron, shoulder yoke, hem band, centre
  stripe), and full-panel effects (fade, halftone, grain, ikat, geo blocks) that blend into
  whatever is under them. Each layer is a few numbers in texture space, so all of it moves,
  resizes, recolours and restacks. Print and crest placement are free too — height on the
  chest, print size, crest in six positions with its own size.
- **Halftones behave like a separation.** A screen's dot radius follows a ramp across the
  panel and the screen sits 34° off the fade direction, so two screens in two colours
  interfere the way process printing does instead of sitting on top of each other.
- **Generated layers are seeded and cached.** Grain and ikat would otherwise re-randomise on
  every pointermove, crawling under the cursor. Each layer carries a seed, and generated
  canvases are cached by colour, parameters and seed.
- **Nothing about the supply chain reaches the club.** Mill names and style codes are not
  shown, not copied, and not in the page source — the (fabric, cut) → mill + style mapping
  is fixed and belongs on Koru's side, resolved when a submission is processed. The club's
  own copy of the spec describes their design and nothing else; the stored record adds a
  `production` block with the club code and the `KORU-<CLUB>-<CUT>-<SIZE>` SKU shape.
- **Saving** uses the artifact `db` capability: designs are written to `designs/<code>` and
  the page reopens one from `#d=<code>`, so a committee can share a link before committing.

## Numbers that need confirming before this goes live

These are placeholders chosen to be plausible, not facts pulled from the store:

| Value | Currently | Where |
|---|---|---|
| Starting colour card | 16 colours | `PALETTE` |
| Layer types | 13 | `SHAPES` |

The page asks for no headcount, quotes no total, and offers no fabric or cut choice. The
cut buttons over the preview only change which body the design is shown on. The race-mesh
edge profile (`EDGE.elite`) is still in the code but unreachable, because the club no
longer picks a fabric — it is there for when that choice comes back.

Sublimation removes most of the limits a cut-and-sew vest would have — colour count costs
nothing — but not all of them. Worth confirming: the smallest halftone dot the mill can hold
without it filling in, whether fine grain survives the press, and how close a print can run
to a seam before it distorts. Those belong in `SHAPES` as bounds once known.

The texture wraps with the side seam at u=0, so a fade running across the body has a
discontinuity there. That is how a sublimated vest actually prints — flat panels, then sewn —
so it is left as is rather than forced to wrap seamlessly.

## Getting it onto korusports.ie

Three stages, each shippable on its own.

**1. Page on the storefront.** Drop the markup, CSS and JS into a custom section
(`sections/vest-designer.liquid`) and assign it to a page template at
`/pages/vest-designer`. The section's schema exposes the colour card and the
layer defaults as settings, so they change in the theme editor rather than in code. Keep
three.js on cdnjs — the store's CSP allows it, and it is the one heavy dependency.

**2. Submissions.** The designer already produces a clean JSON spec — the full layer stack with each shape's
position and size as percentages, plus the print and crest placement — and can render the
canvas to a PNG (`three.renderer.domElement.toDataURL()`). Post both to a Make.com webhook
— Make is already connected to this stack — and have the scenario email Koru, drop the
design into a sheet, and create or update the club contact in Klaviyo. That avoids needing
a custom app on the Basic plan. If submissions should live in Shopify itself, define a
`club_kit_design` metaobject and write to it via the Admin API instead.

**3. Opening a window.** Cuts, sizes and prices are agreed off the back of the proof, not
captured here, so the window is opened from that conversation rather than straight from the
submission. Create the product set: one
product per selected cut, per-size variants, tags `club:<handle>`, `tier:`, `mill:`,
`style:`, `window:YYYY-MM`, and inventory left to go negative as pre-orders — exactly the
shape the Bandon AC products already use. This is the step worth scripting, because it is
the one Koru currently does by hand for every club.

## Open questions for Koru

- What is the smallest halftone dot the mill holds cleanly?
- Does fine grain survive the press, or fill in?
- How close to a seam can a print run before it distorts?
- Do crest files need to arrive before the proof, or can a window open without one?
