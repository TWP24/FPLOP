# Vest designer — Shopify theme section

Generated from `../index.html` by `../build-shopify.py`. Do not edit these files by
hand: change the designer, re-run the build, re-upload.

```
sections/vest-designer.liquid     markup + settings schema
assets/koru-vest-designer.css     styles, bound to the theme's colour scheme
assets/koru-vest-designer.js      the designer itself
test-harness.html                 the three files stitched together with a stand-in
                                  for Dawn, so it can be opened in a browser
dawn-base.css                     Dawn's own stylesheet, loaded by the harness
```

## Names

A section shares its page with the rest of the theme, so nothing generic stays generic:
the build prefixes every id `kvd-` and every class `kv-`, and namespaces every selector
under `.koru-vd`.

Namespacing alone is not enough, which is why the classes are prefixed too. Dawn styles a
`.field` of its own — `display:flex` plus `:before`/`:after` borders — and an ancestor
selector only wins for the properties we set; everything we leave alone still comes from
the theme. That is what made the first install render with overlapping labels.

The harness loads `dawn-base.css` (from `Shopify/dawn`, `main`) so the next
collision shows up locally instead of on the store. It is vendored rather than linked
because GitHub serves it as `text/plain` and a browser refuses to apply it.

## Designing

- **Start from a look.** Eight finished colourways on the first step. A club that lands
  on a blank vest has to invent a design; one that lands on eight only has to pick.
- **One vest, large.** Front, back or both, from the bar over the preview. A vest at half
  the width is too small to judge a design on.
- **Tap the vest.** Whatever you tap — a print, the crest, the sponsor — is outlined, and
  its size, centre and remove controls appear directly under the preview. Arrow keys nudge
  it; shift moves it further.
- **Colours from the crest.** Uploading a crest samples it and offers those colours as
  swatches, with one button to make them the vest's colours. Clubs know their colours by
  sight, not by hex.
- **Vest-shaped style tiles**, eight per group with the rest behind a toggle. Thirty-six
  rectangles in the same two colours all look alike; thirty-six vests do not.
- **Undo and redo**, coalesced so a dragged slider is one step, and covering the design
  only — not which step is open or which way the vest is turned.
- **Download** the mockup as a PNG, front and back, before filling in anything.
- **Send design to Koru** stands under the preview on desktop and in a fixed bar on a
  phone, so the ask is never more than one tap away.

## Live edits to carry forward

The section on the store was edited by hand to render the theme's Irish-owned badge under
the intro. The build now emits that `{% render 'koru-irish-owned' %}` itself, so a rebuild
no longer wipes it — the generated file matches the live one byte for byte. Any further
hand-edit of the section on the store needs the same treatment or it dies at the next build.

The page template carries the designer **only**: Dawn's `main-page` section was taken out,
because it printed the page title above the section's own heading with a screenful of space
between the two.

## Layout

One column on a phone: vest on top, steps under it. From 880px the vest takes the left
column and the steps the right — and the swatches for the step you are on move under the
vest, where the colours sit beside the thing they colour and the steps column stops
running long. Front and back print pair off on one row there too.

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

## Installed preview

On an unpublished duplicate of the live theme. Apart from the designer, it is that theme
byte for byte — the homepage placement that was there for the first look has been taken
back out, so publishing this theme changes nothing else on the store.

| | |
|---|---|
| Theme | **Koru — vest designer preview** (`204481134940`, unpublished) |
| Editor | `https://admin.shopify.com/store/zt0fr5-1z/themes/204481134940/editor` |
| Preview | `https://korusports.ie/?preview_theme_id=204481134940` |
| Page | **Design your vest** (`/pages/design-your-vest`, hidden), on the `vest-designer` template |

Four files sit on that theme: the section, the two assets, and
`templates/page.vest-designer.json`. They were uploaded by URL from this repo's raw
GitHub paths and the theme's MD5s check out against the local build.

## Going live

The live theme cannot be written to from here — the Shopify connector blocks theme file
writes against the published storefront, by design. Shipping is therefore two clicks in
admin, both reversible:

1. **Publish the theme** — *Online Store → Themes → Koru — vest designer preview →
   Publish*. The old theme stays in the library to roll back to.
2. **Publish the page** — *Online Store → Pages → Design your vest*, set it visible. It
   is already assigned the `vest-designer` template. Add it to a menu when you want it
   found.

Publishing the theme alone shows nothing to anyone: the page is hidden and the template
is reached by nothing else.

## Install (from scratch)

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

**With no endpoint set — which is how it ships — a design goes through the store's own
contact form.** A plain form POST to `/contact`, the way every Shopify theme sends one:
no app, no key, no CORS, no third party. It lands wherever the store already sends
customer email (*Settings → Store details*), today `koruathletic@gmail.com`. The page
comes back with `?contact_posted=true` and says so.

A contact form carries no files, so the email carries the design as words — club, contact,
style, every colour by name and hex, print sizes and positions, what artwork was placed —
and ends with a link that **reopens the exact design** in the designer. The whole design
is a few hundred bytes, so it travels in the URL (`?vd=…`) rather than needing a database.
That is also what the *Copy design link* button hands a club for its committee.

Uploaded crest and sponsor files cannot ride along. When a club has uploaded one, the page
tells them to email it, and the email to Koru says to expect it.

**With an endpoint set** (*Submission endpoint* in the theme editor) the design is POSTed
there as JSON instead, and that path carries everything — the mockup PNG and the artwork
files included:

```json
{
  "code": "TXKM47", "status": "submitted",
  "spec": { "style": "...", "colours": {...}, "frontPrint": {...}, "crest": {...} },
  "production": { "clubCode": "BAN" },
  "link": "https://korusports.ie/pages/design-your-vest?vd=...",
  "mockup": "data:image/png;base64,...",
  "artwork": { "crest": "data:image/png;base64,...", "sponsor": null },
  "shop": "korusports.ie"
}
```

A Make webhook is the shortest path to that: email Koru with the mockup attached, drop the
row in a sheet, create the club contact. It needs a sender address before it can email.

## Verified

Run in `test-harness.html` against Dawn's own stylesheet, headless, at 390px and 1200px:
no console errors, every panel laid out, the canvas sized (the first install rendered it
0×0), all 36 styles, the colour card read from the section setting. Class names were
diffed against `dawn-base.css` — no collisions.

## Not yet verified

The schema has not been parsed by Liquid on a real theme, and nothing here has been seen
in the theme editor since the rename.

The contact-form post has been exercised in the harness — the form, its fields and the
body are what Shopify expects — but not against the live storefront, which this session
cannot reach. Worth one test submission on the preview theme before it goes out.
