# Vest designer — Shopify theme section

Generated from `../index.html` by `../build-shopify.py`. Do not edit these files by
hand: change the designer, re-run the build, re-upload.

```
sections/vest-designer.liquid     markup + settings schema
assets/koru-vest-designer.css     styles, bound to the theme's colour scheme
assets/koru-vest-designer.js      the designer itself
test-harness.html                 the three files stitched together with a stand-in
                                  for Dawn, so it can be opened in a browser
```

## Brand

Nothing here carries its own palette. Tokens are bound to Dawn's colour-scheme
variables, so the section takes whatever scheme it is placed in and follows the theme
if those change:

| Token | Bound to | Today |
|---|---|---|
| `--paper`, `--surface` | `--color-background` | `#FAFAF7` |
| `--ink` | `--color-foreground` | `#0A0A0A` |
| `--accent` | `--color-button` | `#0A0A0A` |
| `--accent-ink` | `--color-button-text` | `#FAFAF7` |
| `--sans`, `--display` | `--font-body-family`, `--font-heading-family` | Archivo |

Three things changed from the standalone draft to match the store: the teal accent is
gone (the brand has no accent — selection is the button colour, as Dawn does it), every
radius is 0, and the two extra typefaces are gone. Dark mode needs no media query: drop
the section into `scheme-3` and the variables invert it.

## Install

1. **Assets.** Upload `koru-vest-designer.css` and `koru-vest-designer.js` in
   *Online Store → Themes → ⋯ → Edit code → Assets → Add a new asset*.
2. **Section.** Add `vest-designer.liquid` under *Sections*.
3. **Page.** Create a page (*Design your vest*), then a template
   `templates/page.vest-designer.json` with the section in it, and assign that template
   to the page. Or add the section to any existing page in the theme editor.
4. **Settings.** In the theme editor: heading, intro, colour card, small print, and the
   submission endpoint.

Do all of this on a **duplicate of the live theme** and preview it before publishing.

## Where designs go

The artifact draft wrote to its own database. A theme has none, so the section posts
JSON to whatever endpoint is set in *Submission endpoint*:

```json
{
  "code": "TXKM47", "status": "submitted",
  "spec": { "style": "...", "colours": {...}, "frontPrint": {...}, "crest": {...} },
  "production": { "clubCode": "BAN" },
  "mockup": "data:image/png;base64,...",
  "artwork": { "crest": "data:image/png;base64,...", "sponsor": null },
  "shop": "korusports.ie"
}
```

Make is already connected to this stack, so a Make webhook is the shortest path: email
Koru, drop the row in a sheet, create the club contact in Klaviyo. With no endpoint set,
the form tells clubs to email instead — so the page is safe to publish before the
plumbing exists.

`mockup` is the preview canvas as a PNG, so the reply to a club can show their own vest.

## Not yet verified

The generated files have been run in `test-harness.html` — no console errors, all 27
styles, the colour card read from the section setting, controls and canvas rendering.
They have **not** been rendered by Liquid on a real theme. Worth checking on a duplicate
theme first: that the schema parses, that `.koru-vd` doesn't collide with anything in
Dawn, and that the section behaves in the theme editor.

The share-by-link feature is not in this build. It depended on the artifact database;
reinstating it needs the endpoint to hand a code back.
