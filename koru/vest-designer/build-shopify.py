#!/usr/bin/env python3
"""Build the Shopify theme files from index.html.

The designer keeps changing, so the theme section is generated rather than
maintained by hand. Three things happen here:

  1. Tokens are rebound to Dawn's own CSS variables, so the designer takes
     whatever colour scheme the merchant drops it into instead of carrying
     its own palette. The fallbacks are korusports.ie's values today.
  2. Every selector is namespaced under .koru-vd and every id prefixed with
     kvd-, because a theme section shares a page with the rest of the theme.
  3. Saving moves from the artifact database to an endpoint the merchant
     sets in the theme editor.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "index.html")
SEC = os.path.join(HERE, "shopify", "sections", "vest-designer.liquid")
CSS = os.path.join(HERE, "shopify", "assets", "koru-vest-designer.css")
JS  = os.path.join(HERE, "shopify", "assets", "koru-vest-designer.js")

ROOT = "koru-vd"
IDP = "kvd-"

# ---------------------------------------------------------------- read
src = open(SRC, encoding="utf-8").read()
style = re.search(r"<style>(.*?)</style>", src, re.S).group(1)
script = re.search(r"<script>\n(\(function \(\).*?)\n</script>", src, re.S).group(1)
body = re.search(r"(<header class=\"masthead\">.*?)\n<script>", src, re.S).group(1)

# ------------------------------------------------------------- names
# A section shares its page with the rest of the theme, so nothing generic can
# stay generic. Ids take a kvd- prefix and classes a kv- one: Dawn styles a
# .field of its own, and namespacing a selector under .koru-vd does not stop
# Dawn's own rules matching our elements.
IDS = ["palette", "styles", "colourDock", "opacity", "opacityVal", "clubName", "nameCount",
       "fontPicker", "stageHost", "status", "fClub", "fName", "fEmail", "fPhone",
       "fNotes", "submitBtn", "saveBtn", "crestFile", "sponsorFile",
       "crestSizeRow", "crestSizeVal", "sponsorSizeRow", "sponsorSizeVal",
       "frontSizeRow", "frontSizeVal", "backSizeRow", "backSizeVal",
       "p-colours", "p-style", "p-name", "p-send"]

CLP = "kv-"
CLASSES = set(re.findall(r"\.([A-Za-z][\w-]*)", style))
for m in re.finditer(r'class="([^"]+)"', body):
    CLASSES.update(m.group(1).split())
CLASSES.discard(ROOT)
# classes this build introduces, so they are named like the rest
CLASSES.update(["intro", "intro-copy", "fineprint"])

def alt(names):
    return "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))

CSS_ID_RE = re.compile(r"#(%s)(?![\w-])" % alt(IDS))
CSS_CLASS_RE = re.compile(r"\.(%s)(?![\w-])" % alt(CLASSES))

def rename_css(text):
    text = CSS_ID_RE.sub(lambda m: "#" + IDP + m.group(1), text)
    return CSS_CLASS_RE.sub(lambda m: "." + CLP + m.group(1), text)

def rename_class_attrs(text):
    """Rewrite class="a b" wherever it appears, markup or JS string."""
    return re.sub(r'class="([^"]*)"',
                  lambda m: 'class="%s"' % " ".join(
                      (CLP + t if t in CLASSES else t) for t in m.group(1).split()),
                  text)

def rename_js_classes(js):
    js = rename_class_attrs(js)
    js = js.replace('el.className = "status" + (isError ? " err" : "");',
                    'el.className = "%sstatus" + (isError ? " %serr" : "");' % (CLP, CLP))
    js = re.sub(r'(classList\.(?:add|remove|toggle)\()"([\w-]+)"',
                lambda m: '%s"%s"' % (m.group(1),
                                      CLP + m.group(2) if m.group(2) in CLASSES else m.group(2)), js)
    js = re.sub(r'(\$\$?|querySelector|querySelectorAll|closest|matches)\((["\'])\.([\w-]+)',
                lambda m: '%s(%s.%s' % (m.group(1), m.group(2),
                                        CLP + m.group(3) if m.group(3) in CLASSES else m.group(3)), js)
    return js

style = rename_css(style)

# ---------------------------------------------------------------- css
BRAND_TOKENS = """
/* Bound to Dawn's colour scheme variables, so the designer inherits whatever
   scheme it is placed in. Fallbacks are korusports.ie as configured today:
   #0A0A0A on #FAFAF7, warm sand #F1EEE4, no accent colour, every radius 0. */
.koru-vd{
  --paper: rgb(var(--color-background, 250,250,247));
  --surface: rgb(var(--color-background, 250,250,247));
  --surface-2: rgba(var(--color-foreground, 10,10,10), .045);
  --ink: rgb(var(--color-foreground, 10,10,10));
  --ink-2: rgba(var(--color-foreground, 10,10,10), .68);
  --ink-3: rgba(var(--color-foreground, 10,10,10), .5);
  --rule: rgba(var(--color-foreground, 10,10,10), .18);
  --rule-2: rgba(var(--color-foreground, 10,10,10), .1);
  /* The brand has no accent: selection is the button colour, as Dawn does it. */
  --accent: rgb(var(--color-button, 10,10,10));
  --accent-ink: rgb(var(--color-button-text, 250,250,247));
  --accent-soft: rgba(var(--color-foreground, 10,10,10), .07);
  --warn: #8C5410;
  --stage: rgba(var(--color-foreground, 10,10,10), .07);
  --stage-2: rgba(var(--color-foreground, 10,10,10), .025);
  --tabTop: 0px;
  --sans: var(--font-body-family, "Archivo", ui-sans-serif, system-ui, sans-serif);
  --display: var(--font-heading-family, "Archivo", ui-sans-serif, system-ui, sans-serif);
  /* No mono in the brand; small readouts use the body face with tracking. */
  --mono: var(--font-body-family, "Archivo", ui-sans-serif, system-ui, sans-serif);
  --radius: var(--buttons-radius, 0px);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.5;
}
"""

# drop the artifact-only token blocks and the page-level body rule
style = re.sub(r"  :root\{.*?\n  \}\n", "", style, count=1, flags=re.S)
style = re.sub(r"  @media \(prefers-color-scheme:dark\)\{.*?\n  \}\n", "", style, count=1, flags=re.S)
style = re.sub(r"  :root\[data-theme=\"dark\"\]\{.*?\n  \}\n", "", style, count=1, flags=re.S)
style = re.sub(r"  body\{.*?\n  \}\n", "", style, count=1, flags=re.S)

def namespace(css):
    """Prefix every selector with .koru-vd, leaving at-rules alone."""
    out, depth, buf = [], 0, ""
    for line in css.split("\n"):
        stripped = line.strip()
        if depth == 0 and stripped.endswith("{") and not stripped.startswith("@"):
            sel = stripped[:-1].strip()
            parts = []
            for part in sel.split(","):
                part = part.strip()
                if not part:
                    continue
                if part == "*":
                    parts.append(".%s *" % ROOT)
                elif part.startswith(".%s" % ROOT):
                    parts.append(part)
                else:
                    parts.append(".%s %s" % (ROOT, part))
            out.append("  " + ", ".join(parts) + "{")
            depth += 1
            continue
        if stripped.startswith("@") and stripped.endswith("{"):
            out.append(line)
            depth += 1
            continue
        if stripped.endswith("{"):
            sel = stripped[:-1].strip()
            parts = [".%s %s" % (ROOT, p.strip()) if not p.strip().startswith(".%s" % ROOT) else p.strip()
                     for p in sel.split(",") if p.strip()]
            out.append("    " + ", ".join(parts) + "{")
            depth += 1
            continue
        if stripped == "}":
            depth -= 1
            out.append(line)
            continue
        out.append(line)
    return "\n".join(out)

THEME_FIT = """
/* Sitting inside a theme rather than owning the page: Dawn's page-width
   already provides the gutter, and the heading has more room here. */
.koru-vd .wrap{max-width:var(--page-width, 1200px)}
.koru-vd .intro h1{max-width:20ch}
.koru-vd .intro-copy p{margin:0}
.koru-vd .intro-copy p + p{margin-top:.5em}
.koru-vd .fineprint p{margin:0}
.koru-vd .fineprint p + p{margin-top:8px}
"""

css = BRAND_TOKENS + "\n" + namespace(style) + "\n" + rename_css(THEME_FIT)
# square everything off, as the theme does
css = re.sub(r"border-radius:\s*[0-9.]+px", "border-radius:0", css)
css = re.sub(r"border-radius:\s*50%", "border-radius:50%", css)
# the theme runs flat; the only shadow left is the one under the garment itself
css = re.sub(r"\n\s*box-shadow:0 0 0 2px [^;]+;", "\n    outline:2px solid var(--accent);outline-offset:2px;", css)

# ---------------------------------------------------------------- ids
for i in IDS:
    body = body.replace('id="%s"' % i, 'id="%s%s"' % (IDP, i))
    body = body.replace('for="%s"' % i, 'for="%s%s"' % (IDP, i))
    body = body.replace('aria-controls="%s"' % i, 'aria-controls="%s%s"' % (IDP, i))
    script = script.replace('$("#%s")' % i, '$("#%s%s")' % (IDP, i))
    script = script.replace('getElementById("%s")' % i, 'getElementById("%s%s")' % (IDP, i))

# ids the script builds at runtime. Blanket rules rather than one line per
# call site: a lookup the build misses fails silently in the browser.
script = re.sub(r'\$\("#(?!%s)' % IDP, '$("#%s' % IDP, script)
script = re.sub(r'getElementById\("(?!%s)' % IDP, 'getElementById("%s' % IDP, script)
script = re.sub(r'getElementById\((\w+) \+ "', 'getElementById("%s" + \\1 + "' % IDP, script)
script = script.replace('"el" + el.id + f[0]', '"%sel" + el.id + f[0]' % IDP)
script = script.replace('"cc-" + id', '"%scc-" + id' % IDP)

# scope every lookup to the section, so the designer never reaches into the theme
script = script.replace(
    '''  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };''',
    '''  var ROOT = document.querySelector(".koru-vd");
  if (!ROOT) return;
  var $ = function (s) { return ROOT.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(ROOT.querySelectorAll(s)); };''')
script = script.replace('document.querySelector(".stagewrap")', 'ROOT.querySelector(".stagewrap")')
script = script.replace('document.querySelector(".stage")', 'ROOT.querySelector(".stage")')
script = script.replace('document.querySelector(".tabs")', 'ROOT.querySelector(".tabs")')
script = script.replace("document.querySelector('[data-clear=\"' + key + '\"]')",
                        "ROOT.querySelector('[data-clear=\"' + key + '\"]')")
script = script.replace("document.querySelector('[data-badgesize=\"' + key + '\"]')",
                        "ROOT.querySelector('[data-badgesize=\"' + key + '\"]')")
script = script.replace("document.querySelector('[data-layer=\"el:' + target.id + '\"]')",
                        "ROOT.querySelector('[data-layer=\"el:' + target.id + '\"]')")

# the colour card is a theme setting, not a constant
script = script.replace('''  var PALETTE = [''', '''  var PALETTE = readPalette() || [''')
script = script.replace('''  function colourName(hex) {''',
'''  /* The colour card is editable in the theme editor: one "Name #HEX" per line. */
  function readPalette() {
    var raw = ROOT.getAttribute("data-palette");
    if (!raw) return null;
    var out = [];
    raw.split("\\n").forEach(function (line) {
      var m = line.trim().match(/^(.+?)\\s+(#[0-9a-fA-F]{6})$/);
      if (m) out.push([m[1].trim(), m[2].toUpperCase()]);
    });
    return out.length ? out : null;
  }

  function colourName(hex) {''')

# --- saving: the artifact database is gone; post to the merchant's endpoint ---
old_persist = re.search(r"  function persist\(status\) \{.*?\n  \}\n", script, re.S).group(0)
new_persist = '''  /* The theme has no database. Designs are posted to whatever endpoint the
     merchant configures (a Make webhook, an app proxy, anything that takes
     JSON), together with a PNG of the mockup so the reply has a picture. */
  function persist(status) {
    var endpoint = ROOT.getAttribute("data-endpoint");
    if (!endpoint) {
      setStatus("This form isn't connected yet — email " + contactEmail() +
                " and we'll pick it up.", true);
      return Promise.resolve(null);
    }
    var code = newCode();
    var payload = {
      code: code,
      status: status,
      spec: spec(),
      production: { clubCode: clubCode() },
      mockup: stageCanvas ? stageCanvas.toDataURL("image/png") : null,
      artwork: { crest: state.crest.src || null, sponsor: state.sponsor.src || null },
      shop: ROOT.getAttribute("data-shop") || "",
      createdAt: new Date().toISOString()
    };
    return fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (res) {
      if (!res.ok) throw new Error("bad status");
      return code;
    }).catch(function () {
      setStatus("That didn't send. Email " + contactEmail() + " and we'll pick it up.", true);
      return null;
    });
  }

  function contactEmail() {
    return ROOT.getAttribute("data-contact") || "us";
  }
'''
script = script.replace(old_persist, new_persist)

# no shared-link loading without a database
script = re.sub(r"  function loadCode\(code\) \{.*?\n  \}\n", "", script, count=1, flags=re.S)
script = re.sub(r"  var hashCode = .*?\n  if \(!hashCode\) restore\(\);\n", "  restore();\n", script, count=1, flags=re.S)
script = re.sub(r"  if \(window\.claude && window\.claude\.use\) \{.*?\n  \}\n", "", script, count=1, flags=re.S)
script = script.replace('  var dbApi = null;\n', '')
script = script.replace('''      if (code) setStatus("Saved as " + code + ". Share this page's link with your committee.");''',
                        '''      if (code) setStatus("Saved as " + code + ". We have your design.");''')
script = script.replace('''  var stageCanvas = null, stageCtx = null;''',
                        '''  var stageCanvas = null, stageCtx = null;''')

script = rename_js_classes(script)

open(CSS, "w", encoding="utf-8").write(css.strip() + "\n")
open(JS, "w", encoding="utf-8").write(script.strip() + "\n")
print("css %d bytes, js %d bytes" % (len(css), len(script)))

# ---------------------------------------------------------------- section
# The theme already has a header, so the designer's own masthead goes, and the
# heading/intro/fineprint become settings the merchant edits in the theme editor.
body = re.sub(r"<header class=\"masthead\">.*?</header>\n\n", "", body, count=1, flags=re.S)
body = re.sub(r"  <section class=\"intro\">.*?</section>\n", """  <section class="intro">
    <h1>{{ section.settings.heading | escape }}</h1>
    <div class="intro-copy">{{ section.settings.intro }}</div>
  </section>
""", body, count=1, flags=re.S)
body = re.sub(r"      <div class=\"fineprint\">.*?</div>\n", """      <div class="fineprint">{{ section.settings.fineprint }}</div>
""", body, count=1, flags=re.S)
# nothing here shares a link back: without the database there is no design to
# reopen, so the second button just saves what the club has so far.
body = body.replace("Save &amp; get a link", "Save my design")
# the designer's own .wrap becomes the theme's page width
# not .page-width: two sources of gutter fight each other, and the designer
# already has one. It takes the theme's width instead.

DEFAULT_PALETTE = "\n".join([
  "Chalk #F2F1EC", "Silver #C7CCC9", "Steel #6E7A80", "Jet #15161A",
  "Sky #4FA3D9", "Royal #1B4FA8", "Navy #14284B", "Bottle #0C3B2B",
  "Emerald #17875A", "Club Yellow #F5C518", "Amber #E8890C", "Scarlet #CE2027",
  "Maroon #6E1A2E", "Plum #5B2A6E", "Magenta #C61A72", "Sand #D9C9A3"])

SCHEMA = {
  "name": "Vest designer",
  "tag": "section",
  "class": "section",
  "settings": [
    {"type": "text", "id": "heading", "label": "Heading",
     "default": "Design the vest your club races in."},
    {"type": "richtext", "id": "intro", "label": "Intro",
     "default": "<p>Colours, a style, your club name. We come back with a proof \u2014 free, no commitment.</p>"},
    {"type": "color_scheme", "id": "color_scheme", "label": "Colour scheme", "default": "scheme-1"},
    {"type": "header", "content": "Colour card"},
    {"type": "textarea", "id": "palette", "label": "Stock colours",
     "info": "One per line, as Name #HEX. These are the swatches a club picks from.",
     "default": DEFAULT_PALETTE},
    {"type": "header", "content": "Where designs go"},
    {"type": "text", "id": "endpoint", "label": "Submission endpoint",
     "info": "A URL that accepts a JSON POST \u2014 a Make webhook, or an app proxy. Leave blank and the form tells clubs to email instead."},
    {"type": "text", "id": "contact_email", "label": "Fallback email",
     "default": "koruathletic@gmail.com"},
    {"type": "header", "content": "Small print"},
    {"type": "richtext", "id": "fineprint", "label": "Small print",
     "default": "<p>A new club vest design has to be registered with Athletics Ireland before it can be worn in competition. We send you the artwork sheet with your proof.</p><p>Your runners buy their own size during the window, so the club holds no stock and pays nothing up front.</p>"},
    {"type": "header", "content": "Padding"},
    {"type": "range", "id": "padding_top", "min": 0, "max": 100, "step": 4, "unit": "px",
     "label": "Padding top", "default": 36},
    {"type": "range", "id": "padding_bottom", "min": 0, "max": 100, "step": 4, "unit": "px",
     "label": "Padding bottom", "default": 52}
  ],
  "presets": [{"name": "Vest designer"}]
}

body = rename_class_attrs(body)

liquid = """{{ 'koru-vest-designer.css' | asset_url | stylesheet_tag }}

<div
  class="koru-vd color-{{ section.settings.color_scheme }} gradient section-{{ section.id }}-padding"
  data-palette="{{ section.settings.palette | escape }}"
  data-endpoint="{{ section.settings.endpoint | escape }}"
  data-contact="{{ section.settings.contact_email | escape }}"
  data-shop="{{ shop.permanent_domain }}"
>
%s
</div>

<style>
  #shopify-section-{{ section.id }} .section-{{ section.id }}-padding{
    padding-top: {{ section.settings.padding_top }}px;
    padding-bottom: {{ section.settings.padding_bottom }}px;
  }
</style>

<script src="{{ 'koru-vest-designer.js' | asset_url }}" defer></script>

{%% schema %%}
%s
{%% endschema %%}
""" % (body.rstrip(), json.dumps(SCHEMA, indent=2))

open(SEC, "w", encoding="utf-8").write(liquid)
print("section %d bytes" % len(liquid))

# ---------------------------------------------------------------- harness
# A stand-in page so the section can be opened without a store. Dawn's own
# base.css is loaded alongside it: a class of ours colliding with one of the
# theme's is invisible in isolation, and namespacing does not prevent it.
# Dawn's stylesheet is vendored rather than linked: GitHub serves it as
# text/plain with nosniff, so a browser would refuse to apply it.
DAWN_BASE = "dawn-base.css"

def fake_liquid(text, dawn_css):
    defaults = {}
    for s in SCHEMA["settings"]:
        if "id" in s:
            defaults[s["id"]] = s.get("default", "")
    def setting(m):
        val = str(defaults.get(m.group(1), ""))
        return val.replace('"', "&quot;") if "escape" in m.group(0) else val
    text = re.sub(r"\{\{\s*section\.settings\.(\w+)[^}]*\}\}", setting, text)
    text = text.replace("{{ shop.permanent_domain }}", "example.myshopify.com")
    text = re.sub(r"\{\{\s*section\.id\s*\}\}", "vd", text)
    text = re.sub(r"\{\{\s*'([\w.-]+)'\s*\|\s*asset_url\s*\|\s*stylesheet_tag\s*\}\}",
                  r'<link rel="stylesheet" href="assets/\1">', text)
    text = re.sub(r"\{\{\s*'([\w.-]+)'\s*\|\s*asset_url\s*\}\}", r"assets/\1", text)
    text = re.sub(r"\{%\s*schema\s*%\}.*?\{%\s*endschema\s*%\}", "", text, flags=re.S)
    head = """<!doctype html><meta charset=utf-8>
<title>Vest designer — theme harness</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&display=swap">
<!-- Dawn's own stylesheet (dawn-base.css, from Shopify/dawn main),
     so a collision with the theme shows up here before it ships. -->
<link rel="stylesheet" href="%s">
<style>
  /* the handful of Dawn variables the section reads */
  :root{--font-body-family:Archivo,sans-serif;--font-heading-family:Archivo,sans-serif;
        --buttons-radius:0px;--page-width:1200px;--duration-short:100ms}
  .color-scheme-1{--color-background:250,250,247;--color-foreground:10,10,10;
                  --color-button:10,10,10;--color-button-text:250,250,247}
  body{margin:0;background:rgb(250,250,247)}
  .gradient{background:rgb(var(--color-background))}
</style>
""" % dawn_css
    return head + text

open(os.path.join(HERE, "shopify", "test-harness.html"), "w", encoding="utf-8").write(
    fake_liquid(liquid, DAWN_BASE))
print("harness written")
