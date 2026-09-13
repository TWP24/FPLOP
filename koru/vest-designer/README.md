# Koru Club Vest Designer

A self-serve designer for club kit. A club's gear officer builds their vest, sends it in,
and Koru opens a pre-order window on korusports.ie — the same model already running for
Bandon AC, but without Koru hand-building the spec each time.

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
- **Spec sheet** carries the real mill codes already on the store: Zhongkang TJ010 (men's,
  kids), TJ005 (women's), Tarstone TS0738M / TS0661W (elite), and generates the store's
  existing SKU shape, `KORU-<CLUB>-<CUT>-<SIZE>`.
- **Saving** uses the artifact `db` capability: designs are written to `designs/<code>` and
  the page reopens one from `#d=<code>`, so a committee can share a link before committing.

## Numbers that need confirming before this goes live

These are placeholders chosen to be plausible, not facts pulled from the store:

| Value | Currently | Where |
|---|---|---|
| Mill minimum run | 30 units | `MOQ` |
| Proof turnaround | 3 days | `renderTimeline` |
| Window length | 21 days | `renderTimeline` |
| Production + delivery | 35 days after close | `renderTimeline` |
| Stock colour card | 16 colours | `PALETTE` |
| Elite availability | senior cuts only | `CUTS[*].price.elite` |

Prices (€30 senior club, €25 kids, €40 elite) are taken from live products and should
stay in step with them.

## Getting it onto korusports.ie

Three stages, each shippable on its own.

**1. Page on the storefront.** Drop the markup, CSS and JS into a custom section
(`sections/vest-designer.liquid`) and assign it to a page template at
`/pages/vest-designer`. The section's schema exposes MOQ, prices, lead times and the
colour card as settings so they change in the theme editor rather than in code. Keep
three.js on cdnjs — the store's CSP allows it, and it is the one heavy dependency.

**2. Submissions.** The designer already produces a clean JSON spec and can render the
canvas to a PNG (`three.renderer.domElement.toDataURL()`). Post both to a Make.com webhook
— Make is already connected to this stack — and have the scenario email Koru, drop the
design into a sheet, and create or update the club contact in Klaviyo. That avoids needing
a custom app on the Basic plan. If submissions should live in Shopify itself, define a
`club_kit_design` metaobject and write to it via the Admin API instead.

**3. Opening a window.** On approval, create the product set from the stored spec: one
product per selected cut, per-size variants, tags `club:<handle>`, `tier:`, `mill:`,
`style:`, `window:YYYY-MM`, and inventory left to go negative as pre-orders — exactly the
shape the Bandon AC products already use. This is the step worth scripting, because it is
the one Koru currently does by hand for every club.

## Open questions for Koru

- Is the minimum run per window, per cut, or per mill order?
- Can a club mix club mesh and race mesh in one window, or is that two windows?
- Do crest files need to arrive before the proof, or can a window open without one?
- Should the club see the window's running total while it is open?
