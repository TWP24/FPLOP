(function () {
  "use strict";
  var ROOT = document.querySelector(".koru-vd");
  if (!ROOT) return;
  var $ = function (s) { return ROOT.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(ROOT.querySelectorAll(s)); };

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c];
    });
  }
  function smooth(a) { return a * a * (3 - 2 * a); }

  var PALETTE = readPalette() || [
    ["Chalk","#F2F1EC"], ["Silver","#C7CCC9"], ["Steel","#6E7A80"], ["Jet","#15161A"],
    ["Sky","#4FA3D9"],   ["Royal","#1B4FA8"],  ["Navy","#14284B"],  ["Bottle","#0C3B2B"],
    ["Emerald","#17875A"],["Club Yellow","#F5C518"],["Amber","#E8890C"],["Scarlet","#CE2027"],
    ["Maroon","#6E1A2E"],["Plum","#5B2A6E"],   ["Magenta","#C61A72"],["Sand","#D9C9A3"]
  ];
  /* The colour card is editable in the theme editor: one "Name #HEX" per line. */
  function readPalette() {
    var raw = ROOT.getAttribute("data-palette");
    if (!raw) return null;
    var out = [];
    raw.split("\n").forEach(function (line) {
      var m = line.trim().match(/^(.+?)\s+(#[0-9a-fA-F]{6})$/);
      if (m) out.push([m[1].trim(), m[2].toUpperCase()]);
    });
    return out.length ? out : null;
  }

  function colourName(hex) {
    for (var i = 0; i < PALETTE.length; i++) {
      if (PALETTE[i][1].toLowerCase() === String(hex).toLowerCase()) return PALETTE[i][0];
    }
    return "Custom " + String(hex).toUpperCase();
  }

  var LEAN = 0.25;

  /* Chest prints, in the faces clubs actually ask for. `track` is the
     letter-spacing each face wants; `upper` is off for the script,
     which reads badly in capitals. */
  var FONTS = [
    { key:"block",     label:"Block",     family:"Archivo",        weight:"700", track:0.055, upper:true },
    { key:"condensed", label:"Condensed", family:"Oswald",         weight:"600", track:0.045, upper:true },
    { key:"slab",      label:"Slab",      family:"Bevan",          weight:"400", track:0.030, upper:true },
    { key:"varsity",   label:"Varsity",   family:"Graduate",       weight:"400", track:0.075, upper:true },
    { key:"script",    label:"Script",    family:"Kaushan Script", weight:"400", track:0.000, upper:false },
    { key:"blur",      label:"Blur",      family:"Archivo",        weight:"700", track:0.075, upper:true, dots:true }
  ];
  function fontOf(key) {
    for (var i = 0; i < FONTS.length; i++) if (FONTS[i].key === key) return FONTS[i];
    return FONTS[0];
  }
  /* A webfont used only on a canvas is never requested by the document,
     so it has to be asked for explicitly or it silently falls back. */
  function loadFonts(then) {
    if (!document.fonts || !document.fonts.load) { then(); return; }
    Promise.all(FONTS.map(function (f) {
      return document.fonts.load(f.weight + " 120px '" + f.family + "'");
    })).then(then, then);
  }

  /* A layer is a handful of numbers in texture space. Clubs never see
     these — they pick a style below and the numbers come with it. */
  var SHAPES = {
    band:    { group:"shape", make:function(){ return {v:0.35, h:0.14}; } },
    hoops:   { group:"shape", make:function(){ return {v:0.08, h:0.075, gap:0.075}; } },
    sash:    { group:"shape", make:function(){ return {u:0.075, w:0.12}; } },
    panels:  { group:"shape", make:function(){ return {w:0.064}; } },
    chevron: { group:"shape", make:function(){ return {v:0.235, h:0.10}; } },
    yoke:    { group:"shape", make:function(){ return {v:0.17}; } },
    hem:     { group:"shape", make:function(){ return {h:0.10}; } },
    stripe:  { group:"shape", make:function(){ return {w:0.07}; } },
    gradient:{ group:"print", make:function(){ return {v:0.55, soft:0.35, angle:0.5}; } },
    halftone:{ group:"print", make:function(){ return {v:0.52, soft:0.40, size:0.26, angle:0.12}; } },
    grain:   { group:"print", make:function(){ return {v:0.55, soft:0.45, density:0.28, angle:0.5}; } },
    ikat:    { group:"print", make:function(){ return {v:0.55, soft:0.70, density:0.42}; } },
    blocks:  { group:"print", make:function(){ return {size:0.16, lean:0.30}; } },
    camo:    { group:"print", make:function(){ return {size:0.14, coverage:0.50, stretch:0.55}; } },
    smear:   { group:"print", make:function(){ return {size:0.12, soft:0.28, grain:0.30}; } },
    snake:   { group:"print", make:function(){ return {size:0.12, coverage:0.55}; } },
    mosaic:  { group:"print", make:function(){ return {size:0.16, coverage:0.40, v:0.55}; } },
    warp:    { group:"print", make:function(){ return {w:0.20, lean:0.30, density:0.60}; } },
    bleach:  { group:"print", make:function(){ return {size:0.34, coverage:0.52, soft:0.34}; } },
    cubes:   { group:"print", make:function(){ return {size:0.22, face:0, hatch:false}; } },
    caustic: { group:"print", make:function(){ return {size:0.34, sharp:0.55, lean:0.45}; } },
    marble:  { group:"print", make:function(){ return {size:0.20, coverage:0.50, swirl:0.62}; } },
    flame:   { group:"print", make:function(){ return {w:0.14, h:0.07, band:0.038}; } },
    weave:   { group:"print", make:function(){ return {size:0.26, levels:5, star:true}; } },
    dotcamo: { group:"print", make:function(){ return {size:0.18, coverage:0.50, dot:0.28}; } },
    ikatband:{ group:"print", make:function(){ return {w:0.17, density:0.55, soft:0.55}; } },
    bolt:    { group:"print", make:function(){ return {w:0.30, h:0.10, thick:0.045, lean:0.55}; } },
    pour:    { group:"print", make:function(){ return {size:0.26, v:0.70, vBack:null, soft:0.075,
                                                       spread:0.36, swirl:2.6, reach:0.56}; } },
    ripple:  { group:"print", make:function(){ return {lines:34, duty:0.46, warp:2.4,
                                                       size:0.20, drift:0.22, lean:0.35}; } },

    /* The standard club-kit templates, laid out per panel. */
    vstripes:{ group:"kit", make:function(){ return {w:0.055, gap:0.055}; } },
    halves:  { group:"kit", make:function(){ return {v:0.5}; } },
    quarters:{ group:"kit", make:function(){ return {v:0.42, u:0.5}; } },
    shoulders:{group:"kit", make:function(){ return {h:0.26, w:0.085}; } },
    piping:  { group:"kit", make:function(){ return {v:0.35, gap:0.155, w:0.011}; } },
    topo:    { group:"kit", make:function(){ return {size:0.50, density:0.35, w:0.24}; } },
    monogram:{ group:"kit", make:function(){ return {size:0.28}; } },
    terrazzo:{ group:"kit", make:function(){ return {size:0.55, density:0.45}; } },
    tartan:  { group:"kit", make:function(){ return {size:0.11, w:0.34, offset:0}; } }
  };

  /* Styles name a colour ROLE rather than a hex, so changing one of the
     club's colours restyles the whole gallery at once. */
  var STYLES = [
    ["Solid",           [], "block"],
    ["Chest band",      [{ t:"band", r:"design" }], "block"],
    ["Piped band",      [{ t:"band", r:"design" },
                         { t:"piping", r:"accent" }], "block"],
    ["Hoops",           [{ t:"hoops", r:"design" }], "block"],
    ["Vertical stripes",[{ t:"vstripes", r:"design" }], "block"],
    ["Pinstripes",      [{ t:"vstripes", r:"design", w:0.009, gap:0.046 }], "block"],
    ["Halves",          [{ t:"halves", r:"design" }], "block"],
    ["Quarters",        [{ t:"quarters", r:"design" }], "block"],
    ["Sash",            [{ t:"sash", r:"design" }], "block"],
    ["Chevron",         [{ t:"chevron", r:"design" }], "block"],
    ["Side panels",     [{ t:"panels", r:"design" }], "block"],
    ["Shoulder yoke",   [{ t:"yoke", r:"design" }], "block"],
    ["Shoulder stripes",[{ t:"shoulders", r:"design" }], "block"],
    ["Hem band",        [{ t:"hem", r:"design" },
                         { t:"stripe", r:"accent", w:0.05 }], "block"],
    ["Dip dye",         [{ t:"gradient", r:"design", v:0.58, soft:0.30 }], "print"],
    ["Halftone",        [{ t:"halftone", r:"design", angle:0.07, v:0.46, soft:0.34 },
                         { t:"halftone", r:"accent", angle:0.21, v:0.62, soft:0.40 }], "print"],
    ["Contours",        [{ t:"topo", r:"design" }], "print"],
    ["Tiled crest",     [{ t:"monogram", r:"design" }], "print"],
    ["Terrazzo",        [{ t:"terrazzo", r:"design", density:0.40 },
                         { t:"terrazzo", r:"accent", density:0.22 }], "print"],
    ["Tartan",          [{ t:"tartan", r:"design" },
                         { t:"tartan", r:"accent", size:0.11, offset:0.45 }], "print"],
    ["Ikat",            [{ t:"ikat", r:"design", density:0.55, soft:0.85 }], "print"],
    ["Geo blocks",      [{ t:"blocks", r:"design" },
                         { t:"grain", r:"accent", density:0.34, soft:0.9 }], "print"],
    ["Tiger camo",      [{ t:"camo", r:"design", stretch:0.72, coverage:0.52 }], "print"],
    ["Smear",           [{ t:"smear", r:"design", size:0.14, soft:0.22 }], "print"],
    ["Snakeskin",       [{ t:"snake", r:"design", coverage:1 },
                         { t:"snake", r:"accent", coverage:0.42 }], "print"],
    ["Mosaic",          [{ t:"mosaic", r:"design", coverage:0.5 },
                         { t:"mosaic", r:"accent", coverage:0.3 },
                         { t:"mosaic", r:"trim", coverage:0.28 }], "print"],
    ["Warp chevron",    [{ t:"warp", r:"design" }], "print"],
    ["Bleach wash",     [{ t:"bleach", r:"design" }], "print"],
    ["Tumbling blocks", [{ t:"cubes", r:"design", face:1 },
                         { t:"cubes", r:"accent", face:0, hatch:true }], "print"],
    ["Water",           [{ t:"caustic", r:"design" }], "print"],
    ["Marble",          [{ t:"marble", r:"design" }], "print"],
    ["Flame stitch",    [{ t:"flame", r:"design" }], "print"],
    ["Woven diamond",   [{ t:"weave", r:"design" },
                         { t:"weave", r:"accent", size:0.26, levels:2, star:false }], "print"],
    ["Dot camo",        [{ t:"dotcamo", r:"design" }], "print"],
    ["Ikat stripe",     [{ t:"ikatband", r:"design" }], "print"],
    ["Lightning",       [{ t:"bolt", r:"design" }], "print"],
    ["Ripple",          [{ t:"ripple", r:"design" }], "print"],
    ["Pour",            [{ t:"pour", r:"design", v:0.52, vBack:0.70 },
                         { t:"pour", r:"accent", v:0.20, vBack:0.30, spread:0.22,
                           swirl:3.0, reach:0.32, soft:0.060, size:0.34 }], "print"]
  ];

  /* Somewhere to start. A club landing on a blank vest has to invent a
     design; a club landing on eight finished ones only has to pick. */
  var PRESETS = [
    ["Hoops",        "Hoops",
      { base:"#F2F1EC", design:"#14284B", accent:"#CE2027", trim:"#14284B", text:"#14284B" }],
    ["Sash",         "Sash",
      { base:"#F2F1EC", design:"#0C3B2B", accent:"#F5C518", trim:"#0C3B2B", text:"#0C3B2B" }],
    ["Chest band",   "Chest band",
      { base:"#CE2027", design:"#F2F1EC", accent:"#15161A", trim:"#15161A", text:"#F2F1EC" }],
    ["Halves",       "Halves",
      { base:"#1B4FA8", design:"#F2F1EC", accent:"#F5C518", trim:"#F2F1EC", text:"#14284B" }],
    ["Stripes",      "Vertical stripes",
      { base:"#F5C518", design:"#15161A", accent:"#15161A", trim:"#15161A", text:"#15161A" }],
    ["Yoke",         "Shoulder yoke",
      { base:"#15161A", design:"#17875A", accent:"#F2F1EC", trim:"#17875A", text:"#F2F1EC" }],
    ["Dip dye",      "Dip dye",
      { base:"#4FA3D9", design:"#14284B", accent:"#F2F1EC", trim:"#14284B", text:"#F2F1EC" }],
    ["Matcha",        "Pour",
      { base:"#F4F1E6", design:"#7FA83C", accent:"#3F6B22", trim:"#3F6B22", text:"#F4F1E6" }],
    ["Plain",         "Solid",
      { base:"#6E1A2E", design:"#6E1A2E", accent:"#D9C9A3", trim:"#D9C9A3", text:"#D9C9A3" }]
  ];

  function styleIndex(name) {
    for (var i = 0; i < STYLES.length; i++) if (STYLES[i][0] === name) return i;
    return 0;
  }

  var state = {
    tab: "colours",
    view: "front",
    preview: "mens",
    backStyle: "standard",
    base:   "#F5C518",
    design: "#14284B",
    accent: "#CE2027",
    trim:   "#14284B",
    text:   "#F2F1EC",
    style: 1,
    opacity: 1,
    clubName: "KORU AC",
    front: { on:true, u:0.250, v:0.345, scale:0.58 },
    back:  { on:true, u:0.750, v:0.330, scale:0.50 },
    font: "block",
    crest:   { on:true,  u:0.188, v:0.222, scale:0.17, src:null },
    sponsor: { on:false, u:0.250, v:0.470, scale:0.30, src:null },
    contact: { club:"", name:"", email:"", phone:"", notes:"" }
  };

  /* Texture: the two printed panels laid end to end, front centred at
     u=0.25 and back at u=0.75 so neither print lands on a side seam. */
  var TW = 2048, TH = 1024, FRONT_U = 0.25, BACK_U = 0.75;
  var texCanvas = null, texCtx = null, meshPattern = null;

  function ensureTexCanvas() {
    if (texCtx) return;
    texCanvas = document.createElement("canvas");
    texCanvas.width = TW;
    texCanvas.height = TH;
    texCtx = texCanvas.getContext("2d");
  }

  function makeMeshPattern(ctx) {
    var c = document.createElement("canvas");
    c.width = c.height = 8;
    var x = c.getContext("2d");
    x.fillStyle = "rgba(0,0,0,.075)";
    x.fillRect(0, 0, 2, 2); x.fillRect(4, 4, 2, 2);
    x.fillStyle = "rgba(255,255,255,.055)";
    x.fillRect(4, 0, 2, 2); x.fillRect(0, 4, 2, 2);
    return ctx.createPattern(c, "repeat");
  }

  function vBox(ctx, colour, v0, v1) {
    ctx.fillStyle = colour;
    ctx.fillRect(0, v0 * TH, TW, (v1 - v0) * TH);
  }

  function poly(ctx, colour, pts) {
    ctx.fillStyle = colour;
    ctx.beginPath();
    pts.forEach(function (p, i) {
      var x = p[0] * TW, y = p[1] * TH;
      if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
    });
    ctx.closePath();
    ctx.fill();
  }

  /* ---------------------------------------------------------------
     Print effects. A sublimated vest is a full-bleed image dyed into
     the cloth, so these paint the whole texture and composite in
     layer order. Each keeps one colour and fades into whatever is
     underneath, which is what lets two halftone screens in two
     colours over a dark body read like a CMYK separation.
  ----------------------------------------------------------------*/
  function hexToRgb(hex) {
    var h = String(hex).replace("#", "");
    if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
    var n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rgba(hex, a) {
    var c = hexToRgb(hex);
    return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + a + ")";
  }

  /* Deterministic per layer, so a slider drag does not reshuffle the grain. */
  function rng(seed) {
    var s = (seed || 1) >>> 0;
    return function () {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 4294967296;
    };
  }

  /* The direction a fade runs in, as a line across the texture. */
  function rampLine(angleDeg) {
    var a = angleDeg * Math.PI / 180;
    var dx = Math.sin(a), dy = -Math.cos(a);
    var half = (Math.abs(TW * dx) + Math.abs(TH * dy)) / 2;
    return [TW / 2 - dx * half, TH / 2 - dy * half, TW / 2 + dx * half, TH / 2 + dy * half];
  }

  function rampStops(ctx, L, centre, spread, from, to) {
    var g = ctx.createLinearGradient(L[0], L[1], L[2], L[3]);
    var lo = Math.max(0, Math.min(1, centre - spread));
    var hi = Math.max(0, Math.min(1, centre + spread));
    if (hi - lo < 0.004) hi = Math.min(1, lo + 0.004);
    g.addColorStop(0, from);
    if (lo > 0) g.addColorStop(lo, from);
    g.addColorStop(hi, to);
    g.addColorStop(1, to);
    return g;
  }

  var scratch = null, sctx = null;
  function ensureScratch() {
    if (!sctx) {
      scratch = document.createElement("canvas");
      sctx = scratch.getContext("2d");
    }
    if (scratch.width !== TW || scratch.height !== TH) {
      scratch.width = TW;
      scratch.height = TH;
    }
    sctx.setTransform(1, 0, 0, 1, 0, 0);
    sctx.globalCompositeOperation = "source-over";
    sctx.globalAlpha = 1;
    sctx.clearRect(0, 0, TW, TH);
    return sctx;
  }

  /* Draw something full-bleed, then fade it out along a direction. */
  function maskedDraw(ctx, drawFn, angleDeg, centre, spread) {
    var s = ensureScratch();
    drawFn(s);
    s.globalCompositeOperation = "destination-in";
    s.fillStyle = rampStops(s, rampLine(angleDeg), centre, spread,
                            "rgba(0,0,0,0)", "rgba(0,0,0,1)");
    s.fillRect(0, 0, TW, TH);
    s.globalCompositeOperation = "source-over";
    ctx.drawImage(scratch, 0, 0);
  }

  /* Generated canvases are cached: regenerating noise on every pointermove
     would both crawl and re-randomise under the cursor. */
  var fxCache = {};
  function cached(key, build) {
    if (!fxCache[key]) {
      var keys = Object.keys(fxCache);
      if (keys.length > 40) delete fxCache[keys[0]];
      fxCache[key] = build();
    }
    return fxCache[key];
  }

  function noiseTile(colour, density, seed) {
    return cached("n|" + colour + "|" + density.toFixed(3) + "|" + seed, function () {
      var n = 256, c = document.createElement("canvas");
      c.width = c.height = n;
      var x = c.getContext("2d"), img = x.createImageData(n, n);
      var rgb = hexToRgb(colour), rand = rng(seed);
      for (var i = 0; i < n * n; i++) {
        img.data[i * 4] = rgb[0];
        img.data[i * 4 + 1] = rgb[1];
        img.data[i * 4 + 2] = rgb[2];
        img.data[i * 4 + 3] = rand() < density ? 255 : 0;
      }
      x.putImageData(img, 0, 0);
      return c;
    });
  }

  /* Ikat: horizontal streaks that mirror about the centre of each panel,
     which is what gives the woven-warp look. Drawn small and scaled up
     with smoothing off so the streaks stay hard-edged. */
  function ikatHalf(colour, coverage, seed) {
    return cached("i|" + colour + "|" + coverage.toFixed(3) + "|" + seed, function () {
      var w = 150, h = 420, c = document.createElement("canvas");
      c.width = w; c.height = h;
      var x = c.getContext("2d"), rand = rng(seed);
      x.fillStyle = colour;
      for (var y = 0; y < h; y++) {
        var px = 0;
        while (px < w) {
          var run = 1 + Math.floor(rand() * 9);
          /* denser towards the mirror axis at the right-hand edge */
          var bias = Math.pow(px / w, 0.7);
          if (rand() < coverage * (0.25 + 1.5 * bias)) x.fillRect(px, y, run, 1);
          px += run;
        }
      }
      return c;
    });
  }

  function polyPx(ctx, colour, pts) {
    ctx.fillStyle = colour;
    ctx.beginPath();
    pts.forEach(function (p, i) { if (i) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]); });
    ctx.closePath();
    ctx.fill();
  }

  /* Seeded value noise with fractal octaves. Camo, smear and the
     snakeskin blotches are all this function read differently. */
  function makeNoise(seed) {
    var perm = new Uint8Array(512), rand = rng(seed), i, j, k, t;
    for (i = 0; i < 256; i++) perm[i] = i;
    for (j = 255; j > 0; j--) {
      k = Math.floor(rand() * (j + 1));
      t = perm[j]; perm[j] = perm[k]; perm[k] = t;
    }
    for (i = 0; i < 256; i++) perm[i + 256] = perm[i];
    function at(ix, iy) { return perm[(perm[ix & 255] + (iy & 255)) & 255] / 255; }
    function val(x, y) {
      var ix = Math.floor(x), iy = Math.floor(y);
      var fx = smooth(x - ix), fy = smooth(y - iy);
      var a = at(ix, iy), b = at(ix + 1, iy), c = at(ix, iy + 1), d = at(ix + 1, iy + 1);
      var top = a + (b - a) * fx, bot = c + (d - c) * fx;
      return top + (bot - top) * fy;
    }
    return function (x, y, oct) {
      var sum = 0, amp = 0.5, tot = 0;
      for (var o = 0; o < (oct || 4); o++) {
        sum += val(x, y) * amp;
        tot += amp;
        x *= 2; y *= 2; amp *= 0.5;
      }
      return sum / tot;
    };
  }

  function drawPixels(ctx, canvas) {
    ctx.save();
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(canvas, 0, 0, TW, TH);
    ctx.restore();
  }

  /* Tiger stripe: noise pushed through itself so the edges tear rather
     than curve, thresholded hard, with the threshold jittered per pixel
     so the boundary breaks into speckle the way a real print does. */
  function camoCanvas(el) {
    return cached("c|" + el.colour + "|" + el.size.toFixed(3) + "|" + el.coverage.toFixed(3) +
                  "|" + el.stretch.toFixed(3) + "|" + el.seed, function () {
      var w = 340, h = Math.max(2, Math.round(340 * TH / TW));
      var c = document.createElement("canvas");
      c.width = w; c.height = h;
      var x = c.getContext("2d"), img = x.createImageData(w, h);
      var noise = makeNoise(el.seed), rand = rng(el.seed + 91);
      var rgb = hexToRgb(el.colour);
      var freq = 2 + el.size * 26;
      var stretch = 0.3 + el.stretch * 3.2;
      var cut = 1 - el.coverage;
      for (var py = 0; py < h; py++) {
        for (var px = 0; px < w; px++) {
          var u = px / w, v = py / h;
          var warp = noise(u * freq / stretch, v * freq, 3);
          var n = noise(u * freq / stretch + warp * 1.6, v * freq + warp * 1.6, 4);
          var on = (n + (rand() - 0.5) * 0.17) > cut;
          var o = (py * w + px) * 4;
          img.data[o] = rgb[0]; img.data[o + 1] = rgb[1]; img.data[o + 2] = rgb[2];
          img.data[o + 3] = on ? 255 : 0;
        }
      }
      x.putImageData(img, 0, 0);
      return c;
    });
  }

  /* Smear: the same noise stretched hard along one axis and mapped to a
     soft alpha instead of a hard cut, so it reads as motion rather than
     as shapes. */
  function smearCanvas(el) {
    return cached("s|" + el.colour + "|" + el.size.toFixed(3) + "|" + el.soft.toFixed(3) +
                  "|" + el.grain.toFixed(3) + "|" + el.seed, function () {
      var w = 320, h = Math.max(2, Math.round(320 * TH / TW));
      var c = document.createElement("canvas");
      c.width = w; c.height = h;
      var x = c.getContext("2d"), img = x.createImageData(w, h);
      var noise = makeNoise(el.seed), rand = rng(el.seed + 17);
      var rgb = hexToRgb(el.colour);
      var freq = 2 + el.size * 30;
      var edge = Math.max(0.02, el.soft);
      for (var py = 0; py < h; py++) {
        for (var px = 0; px < w; px++) {
          var n = noise((px / w) * freq, (py / h) * freq * 0.16, 4);
          var a = (n - 0.5 + edge) / (2 * edge);
          a = a < 0 ? 0 : (a > 1 ? 1 : a);
          if (el.grain > 0) a *= 1 - el.grain * rand();
          var o = (py * w + px) * 4;
          img.data[o] = rgb[0]; img.data[o + 1] = rgb[1]; img.data[o + 2] = rgb[2];
          img.data[o + 3] = Math.round(a * 255);
        }
      }
      x.putImageData(img, 0, 0);
      return c;
    });
  }

  /* Snakeskin: a grid of rotated scales, shown only where a noise blotch
     says so. Two of these — a dark one at full coverage and a light one
     on top — give the python look. */
  function paintSnake(ctx, el) {
    var cell = Math.max(6, el.size * TW * 0.055);
    var noise = makeNoise(el.seed);
    var jitter = rng(el.seed + 5);
    var cut = 1 - el.coverage;
    ctx.save();
    ctx.fillStyle = el.colour;
    for (var row = 0; row * cell * 0.7 < TH + cell; row++) {
      var cy = row * cell * 0.7;
      var off = (row % 2) ? cell * 0.5 : 0;
      for (var col = 0; col * cell < TW + cell; col++) {
        var cx = col * cell + off;
        if (el.coverage < 0.995) {
          var n = noise((cx / TW) * 7, (cy / TH) * 5, 4);
          if (n < cut) { jitter(); continue; }
        }
        var r = cell * (0.30 + 0.12 * jitter());
        ctx.beginPath();
        ctx.ellipse(cx, cy, r, r * 0.66, Math.PI / 4, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  }

  /* Mosaic: parallelogram tiles laid in rows that step down and away from
     centre-front, so the rows read as a chevron. Each layer takes a
     seeded share of the tiles, so stacking three colours interleaves them. */
  function paintMosaic(ctx, el) {
    var cell = Math.max(10, el.size * TW * 0.16);
    var pick = rng(el.seed + 3);
    var slope = 0.55;
    ctx.fillStyle = el.colour;
    for (var row = -2; row * cell * 0.62 < TH + cell * 2; row++) {
      for (var col = -2; col * cell < TW + cell * 2; col++) {
        if (pick() > el.coverage) continue;
        var x0 = col * cell + (row % 2 ? cell * 0.5 : 0);
        var mid = Math.abs(((x0 / TW) % 0.5) - 0.25) * TW;
        var y0 = row * cell * 0.62 + mid * slope;
        polyPx(ctx, el.colour, [
          [x0, y0], [x0 + cell * 0.5, y0 - cell * 0.34],
          [x0 + cell * 0.5, y0 + cell * 0.3], [x0, y0 + cell * 0.64]
        ]);
      }
    }
  }

  /* Warp chevron: rows of short dashes whose phase shifts with distance
     from centre-front, which is what draws the V. */
  function warpCanvas(el) {
    return cached("w|" + el.colour + "|" + el.w.toFixed(3) + "|" + el.lean.toFixed(3) +
                  "|" + el.density.toFixed(3) + "|" + el.seed, function () {
      var w = 384, h = 560;
      var c = document.createElement("canvas");
      c.width = w; c.height = h;
      var x = c.getContext("2d"), rand = rng(el.seed);
      x.fillStyle = el.colour;
      var period = Math.max(6, el.w * w * 0.6);
      var slope = 0.4 + el.lean * 4;
      for (var py = 0; py < h; py++) {
        for (var px = 0; px < w;) {
          var run = 2 + Math.floor(rand() * 10);
          var mid = Math.abs(((px / w) % 0.5) - 0.25) * w;
          var phase = ((py + mid * slope) % period) / period;
          if (phase < el.density && rand() < 0.85) x.fillRect(px, py, run, 1);
          px += run + 1;
        }
      }
      return c;
    });
  }

  /* Bleach wash: sponged blots with soft edges and a dappled grain inside
     them, the way bleach actually lands on cloth. */
  function bleachCanvas(el) {
    return cached("bl|" + el.colour + "|" + [el.size, el.coverage, el.soft, el.seed].join("|"),
      function () {
        var w = 320, h = Math.max(2, Math.round(320 * TH / TW));
        var c = document.createElement("canvas");
        c.width = w; c.height = h;
        var x = c.getContext("2d"), img = x.createImageData(w, h);
        var noise = makeNoise(el.seed), rgb = hexToRgb(el.colour);
        var freq = 1.6 + el.size * 9;
        var cut = 1 - el.coverage, soft = Math.max(0.03, el.soft * 0.55);
        for (var py = 0; py < h; py++) {
          for (var px = 0; px < w; px++) {
            var u = px / w, v = py / h;
            var blot = noise(u * freq, v * freq * 0.92, 3);
            var dapple = noise(u * freq * 5.4 + 11, v * freq * 5.4 + 7, 2);
            var n = blot * 0.72 + dapple * 0.28;
            var a = (n - (cut - soft)) / (2 * soft);
            a = a < 0 ? 0 : a > 1 ? 1 : a;
            var o = (py * w + px) * 4;
            img.data[o] = rgb[0]; img.data[o + 1] = rgb[1]; img.data[o + 2] = rgb[2];
            img.data[o + 3] = Math.round(255 * smooth(a));
          }
        }
        x.putImageData(img, 0, 0);
        return c;
      });
  }

  /* Water: ridged noise, which peaks along thin lines rather than in
     blobs, so it reads as light running over a surface. */
  function causticCanvas(el) {
    return cached("wt|" + el.colour + "|" + [el.size, el.sharp, el.lean, el.seed].join("|"),
      function () {
        var w = 360, h = Math.max(2, Math.round(360 * TH / TW));
        var c = document.createElement("canvas");
        c.width = w; c.height = h;
        var x = c.getContext("2d"), img = x.createImageData(w, h);
        var noise = makeNoise(el.seed), rgb = hexToRgb(el.colour);
        var freq = 4 + el.size * 34;
        var power = 3 + el.sharp * 9;
        for (var py = 0; py < h; py++) {
          for (var px = 0; px < w; px++) {
            var u = px / w, v = py / h;
            /* sheared, so the ripples run across the vest rather than
               straight down it */
            var su = u + v * el.lean;
            var q = noise(su * freq * 0.35 + 3, v * freq * 0.35, 2);
            var n = noise(su * freq + q * 1.4, v * freq * 0.55 + q * 1.4, 4);
            var ridge = 1 - Math.abs(2 * n - 1);
            /* a second, finer ridge for the glitter between the bands */
            var fine = 1 - Math.abs(2 * noise(su * freq * 2.3 + 17, v * freq * 1.3 + 4, 2) - 1);
            ridge = ridge * 0.82 + fine * 0.18;
            var o = (py * w + px) * 4;
            img.data[o] = rgb[0]; img.data[o + 1] = rgb[1]; img.data[o + 2] = rgb[2];
            img.data[o + 3] = Math.round(255 * Math.pow(ridge, power));
          }
        }
        x.putImageData(img, 0, 0);
        return c;
      });
  }

  /* Marble: noise pushed hard through itself and then cut to two tones,
     with only a pixel of ramp at the edge so it stays a poured shape
     rather than a cloud. */
  function marbleCanvas(el) {
    return cached("mb|" + el.colour + "|" + [el.size, el.coverage, el.swirl, el.seed].join("|"),
      function () {
        var w = 560, h = Math.max(2, Math.round(560 * TH / TW));
        var c = document.createElement("canvas");
        c.width = w; c.height = h;
        var x = c.getContext("2d"), img = x.createImageData(w, h);
        var noise = makeNoise(el.seed), rgb = hexToRgb(el.colour);
        var freq = 2 + el.size * 14;
        var swirl = 0.8 + el.swirl * 2.6;
        var cut = 1 - el.coverage;
        for (var py = 0; py < h; py++) {
          for (var px = 0; px < w; px++) {
            var u = px / w, v = py / h;
            var q = noise(u * freq * 0.55 + 5, v * freq * 0.55 + 2, 3);
            var n = noise(u * freq + q * swirl, v * freq + q * swirl * 1.25, 4);
            var a = (n - cut) / 0.014;
            a = a < 0 ? 0 : a > 1 ? 1 : a;
            var o = (py * w + px) * 4;
            img.data[o] = rgb[0]; img.data[o + 1] = rgb[1]; img.data[o + 2] = rgb[2];
            img.data[o + 3] = Math.round(255 * a);
          }
        }
        x.putImageData(img, 0, 0);
        return c;
      });
  }

  /* Camo read through a dot screen: the blobs are made of dots that merge
     where the shape is solid and thin out where it is not, which is how the
     reference is printed. */
  function dotCamoCanvas(el) {
    return cached("dc|" + el.colour + "|" + [el.size, el.coverage, el.dot, el.seed].join("|"),
      function () {
        var w = 900, h = Math.max(2, Math.round(900 * TH / TW));
        var c = document.createElement("canvas");
        c.width = w; c.height = h;
        var x = c.getContext("2d");
        var noise = makeNoise(el.seed);
        var freq = 2 + el.size * 22;
        var cut = 1 - el.coverage;
        var pitch = Math.max(4, el.dot * 34);
        x.fillStyle = el.colour;
        for (var gy = pitch / 2; gy < h + pitch; gy += pitch) {
          for (var gx = pitch / 2; gx < w + pitch; gx += pitch) {
            var u = gx / w, v = gy / h;
            var warp = noise(u * freq * 0.6, v * freq * 0.6, 2);
            var n = noise(u * freq + warp * 1.2, v * freq + warp * 1.2, 3);
            /* inside the shape the dots overlap, outside they are pinpricks */
            var k = (n - cut + 0.12) / 0.24;
            k = k < 0 ? 0 : k > 1 ? 1 : k;
            var r = pitch * (0.16 + 0.55 * smooth(k));
            x.beginPath();
            x.arc(gx, gy, r, 0, Math.PI * 2);
            x.fill();
          }
        }
        return c;
      });
  }

  /* Warp ikat: vertical bands whose edges feather into ragged horizontal
     ticks, the way the dye bleeds along the warp threads. */
  function ikatBandCanvas(el) {
    return cached("ib|" + el.colour + "|" + [el.w, el.density, el.soft, el.seed].join("|"),
      function () {
        var w = 640, h = Math.max(2, Math.round(640 * TH / TW));
        var c = document.createElement("canvas");
        c.width = w; c.height = h;
        var x = c.getContext("2d"), rand = rng(el.seed + 13);
        var noise = makeNoise(el.seed);
        var pitch = Math.max(10, el.w * w * 0.26);
        var core = pitch * (0.10 + el.density * 0.22);
        var feather = pitch * 0.5 * el.soft;
        x.fillStyle = el.colour;
        for (var y = 0; y < h; y += 2) {
          for (var bx = pitch / 2; bx < w + pitch; bx += pitch) {
            var wob = (noise(bx / w * 3, y / h * 9, 2) - 0.5) * feather;
            var half = core + wob;
            if (half > 0) x.fillRect(bx - half, y, half * 2, 2);
            /* ticks that stray out from the band and make the ikat edge */
            var reach = feather * (0.4 + rand() * 1.6);
            if (rand() < 0.7) {
              var side = rand() < 0.5 ? -1 : 1;
              var len = pitch * 0.06 + rand() * pitch * 0.14;
              x.fillRect(bx + side * (half + reach), y, len, 2);
            }
          }
        }
        return c;
      });
  }

  /* A pour: one colour dropping into another and bleeding down through it.
     The boundary is a wandering line rather than a level, and tendrils run
     on below it where the noise punches through — which is what a drop of
     matcha does on its way through milk. */
  function pourCanvas(el) {
    return cached("po|" + el.colour + "|" +
                  [el.size, el.v, el.vBack, el.soft, el.spread, el.swirl, el.reach, el.seed].join("|"),
      function () {
        var w = 520, h = Math.max(2, Math.round(520 * TH / TW));
        var c = document.createElement("canvas");
        c.width = w; c.height = h;
        var x = c.getContext("2d"), img = x.createImageData(w, h);
        var noise = makeNoise(el.seed), rgb = hexToRgb(el.colour);
        var freq = 1.4 + el.size * 7;
        var soft = Math.max(0.012, el.soft);
        for (var py = 0; py < h; py++) {
          for (var px = 0; px < w; px++) {
            var u = px / w, v = py / h;
            /* Curl the space itself before asking where the boundary is: a
               drop in liquid does not fall in a straight line, it rolls. */
            var swirlN = noise(u * freq * 0.55 + 3, v * freq * 0.55, 3);
            var strength = noise(u * freq * 0.9 + 17, v * freq * 0.9 + 11, 2);
            var ang = swirlN * Math.PI * 4;
            var amp = el.swirl * 0.06 * (0.35 + strength);
            var uu = u + Math.cos(ang) * amp;
            var vv = v + Math.sin(ang) * amp;
            var body = noise(uu * freq * 1.1, vv * freq * 0.85, 4);
            /* front and back can pour to different levels; the texture is one
               image, so the level is chosen per panel rather than per layer */
            var level = (u >= 0.5 && el.vBack != null) ? el.vBack : el.v;
            var edge = level + (body - 0.5) * el.spread;
            var a = (edge - vv) / soft;
            /* tendrils, thinning with the distance they have fallen */
            var drip = noise(uu * freq * 2.2 + 9, vv * freq * 0.8 + 4, 3);
            var depth = 1 - (vv - edge) / el.reach;
            if (depth > 0) {
              var t = ((drip - 0.58) / 0.05) * depth * depth;
              if (t > a) a = t;
            }
            a = a < 0 ? 0 : a > 1 ? 1 : a;
            var o = (py * w + px) * 4;
            img.data[o] = rgb[0]; img.data[o + 1] = rgb[1]; img.data[o + 2] = rgb[2];
            img.data[o + 3] = Math.round(255 * smooth(a));
          }
        }
        x.putImageData(img, 0, 0);
        return c;
      });
  }

  /* A line field bent through a warp: every stripe follows the same smooth
     distortion, so they bend together the way a knitted rib does over a
     body rather than each wandering off on its own. */
  function rippleCanvas(el) {
    return cached("rp|" + el.colour + "|" +
                  [el.lines, el.duty, el.warp, el.size, el.drift, el.seed].join("|"),
      function () {
        var w = 1100, h = Math.max(2, Math.round(1100 * TH / TW));
        var c = document.createElement("canvas");
        c.width = w; c.height = h;
        var x = c.getContext("2d"), img = x.createImageData(w, h);
        var noise = makeNoise(el.seed), rgb = hexToRgb(el.colour);
        /* lines are counted per panel, and there are two of them */
        var pitch = el.lines * 2;
        var f = 1 + el.size * 3;
        for (var py = 0; py < h; py++) {
          for (var px = 0; px < w; px++) {
            var u = px / w, v = py / h;
            /* two scales of bend so the sweep is not the same everywhere, and
               a lean so the whole field runs off the vertical */
            var bend = (noise(u * f * 1.6 + 5, v * f * 0.7 + 1, 2) - 0.5) +
                       (noise(u * f * 3.4 + 21, v * f * 1.7 + 9, 2) - 0.5) * 0.5;
            var slide = (noise(u * f * 0.7 + 11, v * f * 0.45 + 3, 2) - 0.5) * el.drift;
            var lean = (el.lean == null ? 0 : el.lean) * v * 0.16;
            var phase = (u + slide + lean) * pitch + bend * el.warp * pitch * 0.12;
            var frac = phase - Math.floor(phase);
            /* a hair of softness so the edges do not crawl when scaled */
            var d = Math.min(frac, el.duty - frac + 0.004) / 0.004;
            var a = frac < el.duty ? (d > 1 ? 1 : d < 0 ? 0 : d) : 0;
            var o = (py * w + px) * 4;
            img.data[o] = rgb[0]; img.data[o + 1] = rgb[1]; img.data[o + 2] = rgb[2];
            img.data[o + 3] = Math.round(255 * a);
          }
        }
        x.putImageData(img, 0, 0);
        return c;
      });
  }

  /* Soft-edged effects are generated small and scaled up smoothly; the
     hard-edged ones keep their pixels (drawPixels). */
  function drawSoft(ctx, canvas) {
    ctx.drawImage(canvas, 0, 0, TW, TH);
  }

  /* Engraved shading: lines inside a shape rather than a flat fill, which
     is what separates the two lit faces of a cube from the dark one. */
  function hatchPoly(ctx, pts, colour, pitch) {
    var xs = pts.map(function (p) { return p[0]; });
    var ys = pts.map(function (p) { return p[1]; });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
    var y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
    var span = y1 - y0;
    ctx.save();
    ctx.beginPath();
    pts.forEach(function (p, i) { if (i) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]); });
    ctx.closePath();
    ctx.clip();
    ctx.strokeStyle = colour;
    ctx.lineWidth = Math.max(0.8, pitch * 0.45);
    for (var sx = x0 - span; sx < x1 + pitch; sx += pitch) {
      ctx.beginPath();
      ctx.moveTo(sx, y0);
      ctx.lineTo(sx + span, y1);
      ctx.stroke();
    }
    ctx.restore();
  }

  /* Most kit shapes are per PANEL, not per texture: a vest with four
     vertical stripes has four on the front and four on the back, not
     eight spread across the pair. These helpers work a panel at a time. */
  var PANELS = [0.25, 0.75];
  function panelEdges(centre) { return [centre - 0.25, centre + 0.25]; }

  function topoCanvas(el) {
    return cached("tp|" + el.colour + "|" + el.size.toFixed(3) + "|" + el.density.toFixed(3) +
                  "|" + el.w.toFixed(3) + "|" + el.seed, function () {
      var w = 640, h = Math.max(2, Math.round(640 * TH / TW));
      var c = document.createElement("canvas");
      c.width = w; c.height = h;
      var x = c.getContext("2d"), img = x.createImageData(w, h);
      var noise = makeNoise(el.seed), rgb = hexToRgb(el.colour);
      var freq = 1.5 + el.size * 10;
      var levels = 3 + el.density * 9;
      var line = 0.06 + el.w * 0.5;
      for (var py = 0; py < h; py++) {
        for (var px = 0; px < w; px++) {
          var n = noise((px / w) * freq, (py / h) * freq, 4);
          var band = (n * levels) % 1;
          /* soft at both edges of the band, or the line climbs the pixel grid
             in stairs once it is scaled up to a garment */
          var edge = Math.min(band, line - band) / 0.018;
          var o = (py * w + px) * 4;
          img.data[o] = rgb[0]; img.data[o + 1] = rgb[1]; img.data[o + 2] = rgb[2];
          img.data[o + 3] = Math.round(255 * (edge < 0 ? 0 : edge > 1 ? 1 : edge));
        }
      }
      x.putImageData(img, 0, 0);
      return c;
    });
  }

  /* The club's own initials, tiled — a stand-in for their crest until we
     have the file, and it reads as their vest rather than a generic one. */
  function clubInitials() {
    var src = (state.clubName || "K").toUpperCase().replace(/[^A-Z ]/g, " ").trim();
    var parts = src.split(/\s+/).filter(Boolean);
    if (!parts.length) return "K";
    if (parts.length === 1) return parts[0].slice(0, 2);
    return parts.map(function (p) { return p.charAt(0); }).join("").slice(0, 3);
  }

  function paintKitShape(ctx, el) {
    var c = el.colour, i, k;
    switch (el.type) {

      case "vstripes": {
        var period = el.w + el.gap;
        if (period < 0.004) break;
        ctx.fillStyle = c;
        PANELS.forEach(function (centre) {
          var e = panelEdges(centre);
          for (k = -8; k <= 8; k++) {
            var a = centre + k * period - el.w / 2;
            var b = a + el.w;
            if (b <= e[0] || a >= e[1]) continue;
            a = Math.max(a, e[0]); b = Math.min(b, e[1]);
            ctx.fillRect(a * TW, 0, (b - a) * TW, TH);
          }
        });
        break;
      }

      case "halves":
        ctx.fillStyle = c;
        PANELS.forEach(function (centre) {
          var e = panelEdges(centre);
          var split = Math.max(e[0], Math.min(e[1], centre + (el.v - 0.5) * 0.4));
          if (e[1] > split) ctx.fillRect(split * TW, 0, (e[1] - split) * TW, TH);
        });
        break;

      case "quarters":
        ctx.fillStyle = c;
        PANELS.forEach(function (centre) {
          var e = panelEdges(centre);
          var split = Math.max(e[0], Math.min(e[1], centre + (el.u - 0.5) * 0.4));
          var vy = el.v * TH;
          if (split > e[0]) ctx.fillRect(e[0] * TW, 0, (split - e[0]) * TW, vy);
          if (e[1] > split) ctx.fillRect(split * TW, vy, (e[1] - split) * TW, TH - vy);
        });
        break;

      case "shoulders": {
        var sh = el.h * TH, wIn = el.w * TW;
        PANELS.forEach(function (centre) {
          var e = panelEdges(centre), l = e[0] * TW, r = e[1] * TW;
          polyPx(ctx, c, [[l, 0], [l + wIn, 0], [l + wIn * 0.5, sh], [l, sh]]);
          polyPx(ctx, c, [[r, 0], [r - wIn, 0], [r - wIn * 0.5, sh], [r, sh]]);
        });
        break;
      }

      case "piping":
        vBox(ctx, c, el.v - el.gap / 2 - el.w, el.v - el.gap / 2);
        vBox(ctx, c, el.v + el.gap / 2, el.v + el.gap / 2 + el.w);
        break;

      case "topo":
        /* smoothed on the way up: a contour line is a curve, and nearest
           neighbour turns it into a staircase */
        drawSoft(ctx, topoCanvas(el));
        break;

      case "monogram": {
        var cell = Math.max(46, el.size * TW * 0.42);
        var txt = clubInitials();
        ctx.save();
        ctx.strokeStyle = c;
        ctx.fillStyle = c;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.font = "700 " + (cell * 0.24).toFixed(1) + "px Archivo, sans-serif";
        ctx.lineWidth = Math.max(1, cell * 0.022);
        for (var row = 0; row * cell * 0.88 < TH + cell; row++) {
          var cy = row * cell * 0.88;
          var off = (row % 2) ? cell * 0.5 : 0;
          for (var col = 0; col * cell < TW + cell; col++) {
            var cx = col * cell + off;
            ctx.beginPath();
            ctx.arc(cx, cy, cell * 0.30, 0, Math.PI * 2);
            ctx.stroke();
            ctx.fillText(txt, cx, cy);
          }
        }
        ctx.restore();
        break;
      }

      case "terrazzo": {
        var rnd = rng(el.seed);
        var count = Math.round(180 + el.density * 1500);
        var chip = el.size * TW * 0.022;
        ctx.fillStyle = c;
        for (i = 0; i < count; i++) {
          var px = rnd() * TW, py = rnd() * TH, rr = chip * (0.4 + rnd());
          ctx.save();
          ctx.translate(px, py);
          ctx.rotate(rnd() * Math.PI);
          ctx.beginPath();
          for (k = 0; k < 5; k++) {
            var ang = (k / 5) * Math.PI * 2, rad = rr * (0.55 + rnd() * 0.8);
            var qx = Math.cos(ang) * rad, qy = Math.sin(ang) * rad * 0.72;
            if (k) ctx.lineTo(qx, qy); else ctx.moveTo(qx, qy);
          }
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        }
        break;
      }

      case "tartan": {
        var pitch = Math.max(24, el.size * TW * 0.5);
        var bar = pitch * el.w;
        var shift = el.offset * pitch;
        ctx.save();
        /* enough overprint for the crossings to read, not so much that a
           club's navy comes out olive over yellow */
        ctx.globalAlpha = ctx.globalAlpha * 0.82;
        ctx.fillStyle = c;
        for (var gx = shift - pitch; gx < TW; gx += pitch) ctx.fillRect(gx, 0, bar, TH);
        for (var gy = shift - pitch; gy < TH; gy += pitch) ctx.fillRect(0, gy, TW, bar);
        ctx.restore();
        break;
      }
    }
  }

  function paintEffect(ctx, el) {
    var c = el.colour;
    switch (el.type) {

      case "gradient":
        ctx.fillStyle = rampStops(ctx, rampLine(el.angle * 360), el.v, el.soft,
                                  rgba(c, 0), rgba(c, 1));
        ctx.fillRect(0, 0, TW, TH);
        break;

      case "halftone": {
        var deg = el.angle * 360;
        var L = rampLine(deg);
        var vx = L[2] - L[0], vy = L[3] - L[1];
        var len2 = (vx * vx + vy * vy) || 1;
        var lo = el.v - el.soft, span = (2 * el.soft) || 1e-6;
        /* Screen sits off the fade direction so two stacked screens
           interfere the way a real separation does. */
        var sa = (deg + 34) * Math.PI / 180;
        var cos = Math.cos(sa), sin = Math.sin(sa);
        var cell = Math.max(3, el.size * TW * 0.052);
        var reach = Math.sqrt(TW * TW + TH * TH) / 2 + cell;
        ctx.fillStyle = c;
        for (var gy = -reach; gy < reach; gy += cell) {
          for (var gx = -reach; gx < reach; gx += cell) {
            var px = TW / 2 + gx * cos - gy * sin;
            var py = TH / 2 + gx * sin + gy * cos;
            if (px < -cell || px > TW + cell || py < -cell || py > TH + cell) continue;
            var t = ((px - L[0]) * vx + (py - L[1]) * vy) / len2;
            var k = (t - lo) / span;
            if (k <= 0) continue;
            var r = cell * 0.72 * (k > 1 ? 1 : k);
            if (r < 0.4) continue;
            ctx.beginPath();
            ctx.arc(px, py, r, 0, Math.PI * 2);
            ctx.fill();
          }
        }
        break;
      }

      case "bleach":
        drawSoft(ctx, bleachCanvas(el));
        break;

      case "pour":
        drawSoft(ctx, pourCanvas(el));
        break;

      case "ripple":
        drawSoft(ctx, rippleCanvas(el));
        break;

      case "dotcamo":
        drawSoft(ctx, dotCamoCanvas(el));
        break;

      case "ikatband":
        drawSoft(ctx, ikatBandCanvas(el));
        break;

      /* A woven diamond lattice: nested diamonds for the chevron hatching
         the weave makes, and a star where the lattice crosses. */
      case "weave": {
        var cell = Math.max(32, el.size * TW * 0.30);
        var rings = Math.max(2, Math.round(el.levels));
        var line = Math.max(1.2, cell * 0.035);
        ctx.save();
        ctx.strokeStyle = c;
        ctx.fillStyle = c;
        ctx.lineWidth = line;
        ctx.lineJoin = "miter";
        for (var wRow = -1; wRow * cell * 0.5 < TH + cell; wRow++) {
          var wy = wRow * cell * 0.5;
          var wOff = (wRow % 2) ? cell * 0.5 : 0;
          for (var wCol = -1; wCol * cell < TW + cell; wCol++) {
            var wx = wCol * cell + wOff;
            for (var r = 1; r <= rings; r++) {
              var rad = (cell * 0.5) * (r / rings);
              ctx.beginPath();
              ctx.moveTo(wx, wy - rad);
              ctx.lineTo(wx + rad, wy);
              ctx.lineTo(wx, wy + rad);
              ctx.lineTo(wx - rad, wy);
              ctx.closePath();
              ctx.stroke();
            }
            if (el.star) {
              var sr = cell * 0.13;
              ctx.beginPath();
              for (var sp = 0; sp < 8; sp++) {
                var sa = (sp / 8) * Math.PI * 2;
                var srad = sp % 2 ? sr * 0.36 : sr;
                var sxp = wx + Math.cos(sa) * srad, syp = wy + Math.sin(sa) * srad;
                if (sp) ctx.lineTo(sxp, syp); else ctx.moveTo(sxp, syp);
              }
              ctx.closePath();
              ctx.fill();
            }
          }
        }
        ctx.restore();
        break;
      }

      /* Lightning: thick zigzag bars leaning across the vest, with the
         gaps between them as wide as the bars themselves. */
      case "bolt": {
        var run = Math.max(30, el.w * TW * 0.22);
        var rise = el.h * TH;
        var thick = Math.max(6, el.thick * TH);
        var gap = rise + thick * 2.1;
        var slide = run * el.lean;
        ctx.save();
        ctx.strokeStyle = c;
        ctx.lineWidth = thick;
        ctx.lineJoin = "miter";
        ctx.lineCap = "butt";
        ctx.miterLimit = 8;
        for (var by = -gap * 2; by < TH + gap * 2; by += gap) {
          ctx.beginPath();
          var step = 0;
          for (var bx2 = -run * 2; bx2 <= TW + run * 2; bx2 += run) {
            var byy = by + (step % 2 ? rise : 0) + (bx2 / run) * 0 ;
            var bxx = bx2 + (by / gap) * slide * 0.15;
            if (step) ctx.lineTo(bxx, byy); else ctx.moveTo(bxx, byy);
            step++;
          }
          ctx.stroke();
        }
        ctx.restore();
        break;
      }

      case "caustic":
        drawSoft(ctx, causticCanvas(el));
        break;

      case "marble":
        drawSoft(ctx, marbleCanvas(el));
        break;

      /* Tumbling blocks. Each layer paints one face of the cube, so the
         third face is whatever the body colour is and the whole thing
         restyles with the club's colours like everything else. */
      case "cubes": {
        var R = Math.max(22, el.size * TW * 0.30);
        var stepX = R * Math.sqrt(3), stepY = R * 1.5;
        var face = el.face | 0;
        var at = function (cx, cy, deg) {
          var a = deg * Math.PI / 180;
          return [cx + R * Math.cos(a), cy + R * Math.sin(a)];
        };
        for (var cRow = -1; cRow * stepY < TH + stepY; cRow++) {
          var cy0 = cRow * stepY;
          var offX = (cRow % 2) ? stepX / 2 : 0;
          for (var cCol = -1; cCol * stepX < TW + stepX; cCol++) {
            var cx0 = cCol * stepX + offX;
            var pts = face === 0
              ? [[cx0, cy0], at(cx0, cy0, -30), at(cx0, cy0, -90), at(cx0, cy0, -150)]
              : face === 1
                ? [[cx0, cy0], at(cx0, cy0, -150), at(cx0, cy0, 150), at(cx0, cy0, 90)]
                : [[cx0, cy0], at(cx0, cy0, -30), at(cx0, cy0, 30), at(cx0, cy0, 90)];
            if (el.hatch) hatchPoly(ctx, pts, c, R * 0.15);
            else polyPx(ctx, c, pts);
          }
        }
        break;
      }

      /* Flame stitch: interlocking zigzag bands, jittered row by row so
         the peaks do not line up into a grid. */
      case "flame": {
        var period = Math.max(18, el.w * TW * 0.38);
        var amp = el.h * TH;
        var band = Math.max(3, el.band * TH);
        var pitch = amp + band * 1.5;
        var rnd = rng(el.seed + 5);
        var half = period / 2;
        var wave = function (x, shift, y0) {
          return y0 + (Math.round((x + shift) / half) % 2 ? amp : 0);
        };
        ctx.fillStyle = c;
        for (var fy = -pitch * 2; fy < TH + pitch; fy += pitch) {
          var shift = rnd() * period;
          var x;
          ctx.beginPath();
          ctx.moveTo(-period * 2, wave(-period * 2, shift, fy));
          for (x = -period * 2 + half; x <= TW + period * 2; x += half) {
            ctx.lineTo(x, wave(x, shift, fy));
          }
          for (x = TW + period * 2; x >= -period * 2; x -= half) {
            ctx.lineTo(x, wave(x, shift, fy) + band);
          }
          ctx.closePath();
          ctx.fill();
        }
        break;
      }

      case "grain":
        maskedDraw(ctx, function (s) {
          s.fillStyle = s.createPattern(noiseTile(c, el.density, el.seed), "repeat");
          s.fillRect(0, 0, TW, TH);
        }, el.angle === undefined ? 180 : el.angle * 360, el.v, el.soft);
        break;

      case "ikat":
        maskedDraw(ctx, function (s) {
          var half = ikatHalf(c, el.density, el.seed);
          s.imageSmoothingEnabled = false;
          [FRONT_U, BACK_U].forEach(function (u) {
            var x0 = (u - 0.25) * TW, w = 0.25 * TW;
            s.drawImage(half, x0 + w, 0, w, TH);
            s.save();
            s.translate(x0 + w, 0);
            s.scale(-1, 1);
            s.drawImage(half, 0, 0, w, TH);
            s.restore();
          });
          s.imageSmoothingEnabled = true;
        }, 180, el.v, el.soft);
        break;

      case "blocks": {
        var sz = Math.max(12, el.size * TW * 0.5);
        var lean = el.lean * sz;
        var bar = sz * 0.42;
        for (var row = -1; row * sz < TH + sz; row++) {
          var yy = row * sz;
          var off = (row % 2) ? sz * 0.5 : 0;
          for (var col = -2; col * sz < TW + 2 * sz; col++) {
            var xx = col * sz + off;
            polyPx(ctx, c, [[xx, yy + sz], [xx + lean, yy],
                            [xx + lean + bar, yy], [xx + bar, yy + sz]]);
          }
        }
        break;
      }

      case "camo":
        drawPixels(ctx, camoCanvas(el));
        break;

      case "smear":
        drawPixels(ctx, smearCanvas(el));
        break;

      case "snake":
        paintSnake(ctx, el);
        break;

      case "mosaic":
        maskedDraw(ctx, function (s) { paintMosaic(s, el); }, 0, el.v, 0.35);
        break;

      case "warp":
        ctx.save();
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(warpCanvas(el), 0, 0, TW, TH);
        ctx.restore();
        break;
    }
  }

  function paintLayer(ctx, el) {
    var def = SHAPES[el.type];
    if (def && def.group === "kit") { paintKitShape(ctx, el); return; }
    if (def && def.group === "print") { paintEffect(ctx, el); return; }
    var c = el.colour, o;
    switch (el.type) {
      case "band":
        vBox(ctx, c, el.v - el.h / 2, el.v + el.h / 2);
        break;
      case "hoops":
        var step = el.h + el.gap;
        if (step <= 0.005) break;
        for (var v = el.v; v < 1; v += step) vBox(ctx, c, v, Math.min(v + el.h, 1));
        break;
      case "sash":
        for (o = 0; o < 1; o += 0.5) {
          poly(ctx, c, [[o + el.u, 0.02], [o + el.u + el.w, 0.02],
                        [o + el.u + el.w + LEAN, 1], [o + el.u + LEAN, 1]]);
        }
        break;
      case "panels":
        ctx.fillStyle = c;
        ctx.fillRect((0.5 - el.w / 2) * TW, 0, el.w * TW, TH);
        ctx.fillRect((1 - el.w / 2) * TW, 0, (el.w / 2) * TW, TH);
        ctx.fillRect(0, 0, (el.w / 2) * TW, TH);
        break;
      case "chevron":
        for (o = 0; o < 1; o += 0.5) {
          poly(ctx, c, [
            [o + 0.02, el.v], [o + 0.25, el.v + 0.14], [o + 0.48, el.v],
            [o + 0.48, el.v + el.h], [o + 0.25, el.v + 0.14 + el.h], [o + 0.02, el.v + el.h]
          ]);
        }
        break;
      case "yoke":
        vBox(ctx, c, 0, el.v);
        break;
      case "hem":
        vBox(ctx, c, 1 - el.h, 1);
        break;
      case "stripe":
        ctx.fillStyle = c;
        [FRONT_U, BACK_U].forEach(function (u) {
          ctx.fillRect((u - el.w / 2) * TW, 0, el.w * TW, TH);
        });
        break;
    }
  }

  /* Lettering as a dot screen that dissolves at the edges: the word is drawn
     to a scratch canvas, then read back cell by cell, and each cell becomes a
     soft dot sized by how much of the letter fell in it. Sublimation prints
     the dots exactly as they are, so the blur is in the artwork rather than
     something the press has to do. */
  function dottedText(ctx, chars, widths, tracking, size, cxPx, cyPx, total, colour, fontSpec) {
    var pad = Math.ceil(size * 0.6);
    var bw = Math.ceil(total + pad * 2), bh = Math.ceil(size * 2 + pad * 2);
    var sc = document.createElement("canvas");
    sc.width = bw; sc.height = bh;
    var s = sc.getContext("2d", { willReadFrequently: true });
    s.font = fontSpec;
    s.textAlign = "left";
    s.textBaseline = "middle";
    s.fillStyle = "#ffffff";
    var sx = pad;
    chars.forEach(function (c, i) {
      s.fillText(c, sx, bh / 2);
      sx += widths[i] + tracking * size;
    });
    /* Blur the mask before screening it. Down to a fraction of the size and
       back up is a cheap box blur, and it is the blur that makes the edge
       dots thin out over a band rather than stopping at the letter. */
    var small = document.createElement("canvas");
    var k = Math.max(1, Math.round(size * 0.055));
    small.width = Math.max(1, Math.round(bw / k));
    small.height = Math.max(1, Math.round(bh / k));
    var sm = small.getContext("2d");
    sm.drawImage(sc, 0, 0, small.width, small.height);
    s.clearRect(0, 0, bw, bh);
    s.imageSmoothingEnabled = true;
    s.drawImage(small, 0, 0, bw, bh);
    var data;
    try { data = s.getImageData(0, 0, bw, bh).data; } catch (e) { return; }
    /* fine enough that the middle of a letter fills solid where the dots
       overlap, and only the edge reads as dots */
    var cell = Math.max(3, size * 0.085);
    var step = Math.max(1, Math.round(cell / 2));
    var x0 = cxPx - total / 2 - pad, y0 = cyPx - bh / 2;
    ctx.save();
    for (var gy = cell / 2; gy < bh; gy += cell) {
      for (var gx = cell / 2; gx < bw; gx += cell) {
        var sum = 0, n = 0;
        for (var oy = -cell / 2; oy < cell / 2; oy += step) {
          for (var ox = -cell / 2; ox < cell / 2; ox += step) {
            var px = Math.round(gx + ox), py = Math.round(gy + oy);
            if (px < 0 || py < 0 || px >= bw || py >= bh) continue;
            sum += data[(py * bw + px) * 4 + 3] / 255;
            n++;
          }
        }
        var cov = n ? sum / n : 0;
        if (cov < 0.04) continue;
        var r = cell * 0.95 * Math.sqrt(cov);
        var dx = x0 + gx, dy = y0 + gy;
        var g = ctx.createRadialGradient(dx, dy, r * 0.2, dx, dy, r);
        g.addColorStop(0, rgba(colour, 1));
        g.addColorStop(0.5, rgba(colour, 0.95));
        g.addColorStop(1, rgba(colour, 0));
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(dx, dy, r, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  }

  function trackedText(ctx, text, cxPx, cyPx, maxPx, colour, capSize, font) {
    if (!text) return null;
    var face = "'" + font.family + "', 'Arial Narrow', 'Helvetica Neue', sans-serif";
    var tracking = font.track;
    var size = capSize;
    ctx.font = font.weight + " " + size + "px " + face;
    var chars = text.split("");
    var natural = 0;
    chars.forEach(function (c) { natural += ctx.measureText(c).width; });
    natural += tracking * size * (chars.length - 1);
    if (natural > maxPx) {
      size = size * (maxPx / natural);
      ctx.font = font.weight + " " + size + "px " + face;
    }
    var widths = chars.map(function (c) { return ctx.measureText(c).width; });
    var total = tracking * size * (chars.length - 1);
    widths.forEach(function (w) { total += w; });
    if (font.dots) {
      dottedText(ctx, chars, widths, tracking, size, cxPx, cyPx, total, colour, ctx.font);
      return { w: total, h: size };
    }
    var x = cxPx - total / 2;
    ctx.fillStyle = colour;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    chars.forEach(function (c, i) {
      ctx.fillText(c, x, cyPx);
      x += widths[i] + tracking * size;
    });
    return { w: total, h: size };
  }

  /* ---------------------------------------------------------------
     Crest and sponsor artwork. Each is a badge: a position in texture
     space, a size as a fraction of one panel, and optionally an image.
     With no image it draws as a placeholder, so a club without their
     logo to hand can still say where it goes.
  ----------------------------------------------------------------*/
  var badgeImg = { crest: null, sponsor: null };
  /* Text rects come from the last paint rather than being predicted: only
     the painter knows how wide a name ended up at a given size. */
  var lastTextRect = { front: null, back: null };
  var BADGES = ["sponsor", "crest", "back", "front"];

  function badgeAspect(key) {
    var img = badgeImg[key];
    if (img && img.naturalWidth) return img.naturalHeight / img.naturalWidth;
    return key === "crest" ? 1 : 0.34;
  }

  function badgeRect(key) {
    if (key === "front" || key === "back") {
      var t = lastTextRect[key];
      if (!t) return null;
      var pad = Math.max(10, t.h * 0.25);
      return { x: t.x - pad, y: t.y - pad, w: t.w + pad * 2, h: t.h + pad * 2 };
    }
    var b = state[key];
    var w = b.scale * TW * 0.5;
    var h = w * badgeAspect(key);
    return { x: b.u * TW - w / 2, y: b.v * TH - h / 2, w: w, h: h };
  }

  function paintBadge(ctx, key, colour) {
    var b = state[key];
    if (!b.on) return;
    var r = badgeRect(key);
    var img = badgeImg[key];
    if (img && img.naturalWidth) {
      ctx.drawImage(img, r.x, r.y, r.w, r.h);
      return;
    }
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * 0.9;
    ctx.strokeStyle = colour;
    ctx.fillStyle = colour;
    ctx.lineWidth = Math.max(2, r.w * 0.02);
    ctx.setLineDash([r.w * 0.09, r.w * 0.075]);
    if (key === "crest") {
      ctx.beginPath();
      ctx.arc(b.u * TW, b.v * TH, r.w / 2, 0, Math.PI * 2);
      ctx.stroke();
    } else {
      ctx.strokeRect(r.x, r.y, r.w, r.h);
    }
    ctx.setLineDash([]);
    ctx.font = "500 " + Math.max(9, r.h * 0.26).toFixed(1) + "px 'IBM Plex Mono', monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(key === "crest" ? "CREST" : "SPONSOR", b.u * TW, b.v * TH);
    ctx.restore();
  }

  /* Uploads are scaled down before anything else touches them: a club's
     logo can be 4000px, and this only ever has to look right on a mockup.
     The print file is the vector they send with the proof. */
  function loadArtwork(file, done) {
    if (!file || !/^image\//.test(file.type)) { done(null); return; }
    var reader = new FileReader();
    reader.onerror = function () { done(null); };
    reader.onload = function () {
      var probe = new Image();
      probe.onerror = function () { done(null); };
      probe.onload = function () {
        var max = 360;
        var k = Math.min(1, max / Math.max(probe.width, probe.height));
        var c = document.createElement("canvas");
        c.width = Math.max(1, Math.round(probe.width * k));
        c.height = Math.max(1, Math.round(probe.height * k));
        c.getContext("2d").drawImage(probe, 0, 0, c.width, c.height);
        done(c.toDataURL("image/png"));
      };
      probe.src = reader.result;
    };
    reader.readAsDataURL(file);
  }

  /* Clubs know their colours by sight, not by hex. Sampling the crest they
     just uploaded turns "our green" into a swatch they can click. */
  var crestColours = [];

  function rgbToHex(r, g, b) {
    return "#" + [r, g, b].map(function (n) {
      return ("0" + Math.max(0, Math.min(255, Math.round(n))).toString(16)).slice(-2);
    }).join("").toUpperCase();
  }

  function paletteFromImage(img, want) {
    var n = 48;
    var c = document.createElement("canvas");
    c.width = n; c.height = n;
    var x = c.getContext("2d", { willReadFrequently: true });
    var data;
    try {
      x.drawImage(img, 0, 0, n, n);
      data = x.getImageData(0, 0, n, n).data;
    } catch (e) { return []; }
    /* Bucket to 4 bits a channel, then average each bucket back: close
       shades of the one colour count once, gradients do not shatter. */
    var bins = {};
    for (var i = 0; i < data.length; i += 4) {
      if (data[i + 3] < 128) continue;
      var r = data[i], g = data[i + 1], b = data[i + 2];
      var k = (r >> 4) + "," + (g >> 4) + "," + (b >> 4);
      var bin = bins[k] || (bins[k] = { n: 0, r: 0, g: 0, b: 0 });
      bin.n++; bin.r += r; bin.g += g; bin.b += b;
    }
    var list = Object.keys(bins).map(function (k) {
      var b = bins[k];
      return { n: b.n, r: b.r / b.n, g: b.g / b.n, b: b.b / b.n };
    }).sort(function (a, b) { return b.n - a.n; });
    var out = [];
    list.forEach(function (c0) {
      if (out.length >= (want || 4)) return;
      var apart = out.every(function (o) {
        return Math.abs(o.r - c0.r) + Math.abs(o.g - c0.g) + Math.abs(o.b - c0.b) > 90;
      });
      if (apart) out.push(c0);
    });
    return out.map(function (c0) { return rgbToHex(c0.r, c0.g, c0.b); });
  }

  function luma(hex) {
    var c = hexToRgb(hex);
    return c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114;
  }

  function renderCrestColours() {
    var host = $(".kv-crestcols");
    if (!host) return;
    host.hidden = !crestColours.length;
    if (!crestColours.length) { host.innerHTML = ""; return; }
    host.innerHTML =
      '<span class="kv-label">From your crest</span>' +
      '<div class="kv-palette">' + crestColours.map(function (hex) {
        return '<button type="button" class="kv-swatch" data-cresthex="' + hex +
               '" style="background:' + hex + '" title="' + hex +
               '" aria-label="Use ' + hex + '"></button>';
      }).join("") + '</div>' +
      '<button type="button" class="kv-mini" data-clubcolours="1">Use these as the vest colours</button>';
  }

  function adoptArtwork(key, src, then) {
    if (!src) {
      badgeImg[key] = null;
      state[key].src = null;
      if (key === "crest") crestColours = [];
      if (then) then();
      return;
    }
    var img = new Image();
    img.onload = function () {
      badgeImg[key] = img;
      state[key].src = src;
      if (key === "crest") crestColours = paletteFromImage(img, 4);
      if (then) then();
    };
    img.onerror = function () { badgeImg[key] = null; state[key].src = null; if (then) then(); };
    img.src = src;
  }

  /* ---------------------------------------------------------------
     Dragging a badge on the flat mockup
  ----------------------------------------------------------------*/
  var stageLayout = null, dragging = null, repaintQueued = false;
  /* What the club last tapped on the vest. Not part of the design, so it
     never reaches the spec or the save. */
  var selected = null;
  /* While a drag is within a whisker of a panel's centre line it sticks
     there, and the guide shows why. */
  var SNAP = 0.012;
  var snapGuide = null;

  function panelCentreFor(u) { return u < 0.5 ? FRONT_U : BACK_U; }

  function centreBadge(key) {
    var b = state[key];
    if (!b) return;
    b.u = panelCentreFor(b.u);
    save();
  }

  function queueRepaint() {
    if (repaintQueued) return;
    repaintQueued = true;
    requestAnimationFrame(function () {
      repaintQueued = false;
      paintTexture();
      renderStage();
    });
  }

  /* Screen point -> texture coordinates, via whichever panel it landed in. */
  function toTexture(ev) {
    if (!stageLayout) return null;
    var host = $("#kvd-stageHost");
    var box = host.getBoundingClientRect();
    var px = ev.clientX - box.left, py = ev.clientY - box.top;
    var hit = null;
    ["front", "back"].forEach(function (side) {
      var L = stageLayout[side];
      if (!L || hit) return;
      if (px >= L.x && px <= L.x + L.w && py >= L.y && py <= L.y + L.h) {
        hit = { u: (side === "back" ? 0.5 : 0) + ((px - L.x) / L.w) * 0.5,
                v: (py - L.y) / L.h };
      }
    });
    return hit;
  }

  function badgeAt(p) {
    var found = null;
    BADGES.forEach(function (key) {
      if (found || !state[key].on) return;
      var r = badgeRect(key);
      if (!r) return;
      var x = p.u * TW, y = p.v * TH;
      if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) found = key;
    });
    return found;
  }

  function bindBadgeDrag(stage) {
    /* pan-y keeps the page scrollable over the preview; a touch that lands
       on a badge is claimed here instead, so vertical drags move the badge. */
    stage.addEventListener("touchstart", function (ev) {
      if (ev.touches.length !== 1) return;
      var p = toTexture(ev.touches[0]);
      if (p && badgeAt(p)) ev.preventDefault();
    }, { passive: false });

    stage.addEventListener("pointerdown", function (ev) {
      var p = toTexture(ev);
      var key = p ? badgeAt(p) : null;
      /* Tapping the vest selects what you tapped, and tapping bare fabric
         lets it go — the controls follow the selection. */
      if (key !== selected) {
        selected = key;
        renderInspector();
      }
      if (!key) { renderStage(); return; }
      ev.preventDefault();
      try { stage.focus({ preventScroll: true }); } catch (e) { stage.focus(); }
      dragging = { key: key, du: state[key].u - p.u, dv: state[key].v - p.v };
      stage.classList.add("kv-grabbing");
      renderStage();
      try { stage.setPointerCapture(ev.pointerId); } catch (e) { /* no capture */ }
    });

    /* Arrow keys place a print to the pixel, which a trackpad drag cannot. */
    stage.addEventListener("keydown", function (ev) {
      var d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[ev.key];
      if (!d || !selected || !state[selected] || !state[selected].on) return;
      ev.preventDefault();
      var step = ev.shiftKey ? 0.02 : 0.004;
      var b = state[selected];
      b.u = Math.max(0.02, Math.min(0.98, b.u + d[0] * step * 0.5));
      b.v = Math.max(0.03, Math.min(0.97, b.v + d[1] * step));
      queueRepaint();
      save();
    });

    stage.addEventListener("pointermove", function (ev) {
      if (!dragging) {
        var hover = toTexture(ev);
        stage.classList.toggle("kv-over", !!(hover && badgeAt(hover)));
        return;
      }
      var p = toTexture(ev);
      if (!p) return;
      var b = state[dragging.key];
      var u = Math.max(0.02, Math.min(0.98, p.u + dragging.du));
      var centre = panelCentreFor(u);
      if (Math.abs(u - centre) < SNAP) { u = centre; snapGuide = centre; }
      else { snapGuide = null; }
      b.u = u;
      b.v = Math.max(0.03, Math.min(0.97, p.v + dragging.dv));
      queueRepaint();
    });

    function release(ev) {
      if (!dragging) return;
      dragging = null;
      snapGuide = null;
      stage.classList.remove("kv-grabbing");
      renderInspector();
      renderStage();
      try { stage.releasePointerCapture(ev.pointerId); } catch (e) { /* gone */ }
      save();
    }
    stage.addEventListener("pointerup", release);
    stage.addEventListener("pointercancel", release);
  }

  function paintElement(ctx, el) {
    var prev = ctx.globalAlpha;
    ctx.globalAlpha = prev * (el.opacity == null ? 1 : el.opacity);
    paintLayer(ctx, el);
    ctx.globalAlpha = prev;
  }

  /* Materialise the chosen style: roles become the club's actual colours,
     and seeds come from the style index so noise never reshuffles. */
  function activeLayers() {
    var spec = (STYLES[state.style] || STYLES[0])[1];
    return spec.map(function (s, i) {
      var el = SHAPES[s.t].make();
      el.type = s.t;
      el.colour = state[s.r] || state.design;
      el.opacity = state.opacity;
      el.seed = state.style * 977 + i * 31 + 7;
      Object.keys(s).forEach(function (k) {
        if (k !== "t" && k !== "r") el[k] = s[k];
      });
      return el;
    });
  }

  function paintTexture(layers) {
    ensureTexCanvas();
    var ctx = texCtx;
    var font = fontOf(state.font);
    var raw = (state.clubName || "").trim();
    var name = font.upper ? raw.toUpperCase() : raw;
    /* Each print spans a fraction of its panel, so a short club name and
       a long one fill the same width. */

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.fillStyle = state.base;
    ctx.fillRect(0, 0, TW, TH);

    (layers || activeLayers()).forEach(function (el) { paintElement(ctx, el); });

    if (!meshPattern) meshPattern = makeMeshPattern(ctx);
    ctx.fillStyle = meshPattern;
    ctx.fillRect(0, 0, TW, TH);

    ["front", "back"].forEach(function (key) {
      var b = state[key];
      if (!b.on) { lastTextRect[key] = null; return; }
      var m = trackedText(ctx, name, b.u * TW, b.v * TH, b.scale * TW * 0.5,
                          state.text, key === "front" ? 200 : 180, font);
      lastTextRect[key] = m
        ? { x: b.u * TW - m.w / 2, y: b.v * TH - m.h / 2, w: m.w, h: m.h }
        : null;
    });
    paintBadge(ctx, "sponsor", state.text);
    paintBadge(ctx, "crest", state.text);
  }

  /* ---------------------------------------------------------------
     Flat mockup. Front and back, drawn the way a kit supplier presents
     them, rather than a garment turned in space.
  ----------------------------------------------------------------*/
  var CUTS = {
    mens:   { label:"Men's",    ratio:1.30, neckW:0.26, neckD:0.150, shoulder:0.600,
              armIn:0.600, uaX:0.950, uaY:0.420, waist:0.930, hemX:0.945 },
    womens: { label:"Women's",  ratio:1.28, neckW:0.25, neckD:0.170, shoulder:0.545,
              armIn:0.545, uaX:0.910, uaY:0.400, waist:0.855, hemX:0.915 },
    kids:   { label:"Kids",     ratio:1.20, neckW:0.25, neckD:0.130, shoulder:0.575,
              armIn:0.575, uaX:0.930, uaY:0.400, waist:0.915, hemX:0.935 },
    crop:   { label:"Crop top", ratio:0.84, neckW:0.25, neckD:0.240, shoulder:0.545,
              armIn:0.545, uaX:0.920, uaY:0.550, waist:0.890, hemX:0.920 }
  };

  function vestPath(cut, x, y, w, h, back) {
    var cx = x + w / 2, hw = w / 2;
    if (back && state.backStyle === "racer") return racerPath(cut, x, y, w, h);
    var nd = y + (back ? cut.neckD * 0.42 : cut.neckD) * h;
    var X = function (f) { return cx + f * hw; };
    var Y = function (f) { return y + f * h; };
    var p = new Path2D();
    p.moveTo(X(-cut.shoulder), Y(0.048));
    p.lineTo(X(-cut.neckW), Y(0.012));
    p.bezierCurveTo(X(-cut.neckW * 0.80), nd * 0.55 + Y(0.012) * 0.45, X(-cut.neckW * 0.44), nd, cx, nd);
    p.bezierCurveTo(X(cut.neckW * 0.44), nd, X(cut.neckW * 0.80), nd * 0.55 + Y(0.012) * 0.45, X(cut.neckW), Y(0.012));
    p.lineTo(X(cut.shoulder), Y(0.048));
    p.bezierCurveTo(X(cut.armIn * 0.97), Y(cut.uaY * 0.36), X(cut.armIn * 1.24), Y(cut.uaY * 0.78),
                    X(cut.uaX), Y(cut.uaY));
    p.bezierCurveTo(X(cut.waist), Y(0.63), X(cut.hemX), Y(0.87), X(cut.hemX), Y(0.982));
    p.bezierCurveTo(X(cut.hemX * 0.42), Y(1.0), X(-cut.hemX * 0.42), Y(1.0), X(-cut.hemX), Y(0.982));
    p.bezierCurveTo(X(-cut.hemX), Y(0.87), X(-cut.waist), Y(0.63), X(-cut.uaX), Y(cut.uaY));
    p.bezierCurveTo(X(-cut.armIn * 1.24), Y(cut.uaY * 0.78), X(-cut.armIn * 0.97), Y(cut.uaY * 0.36),
                    X(-cut.shoulder), Y(0.048));
    p.closePath();
    return p;
  }

  /* A racer back: the armholes cut deep and inward, leaving two straps that
     run up to a wide opening between them. Same side seam and hem as the
     standard back, so the two sides of a vest still match at the seam. */
  function racerPath(cut, x, y, w, h) {
    var cx = x + w / 2, hw = w / 2;
    var X = function (f) { return cx + f * hw; };
    var Y = function (f) { return y + f * h; };
    var p = new Path2D();
    /* the armhole hugs the centre before it swings out to the underarm —
       control points outside that line give a deep V, not a racer */
    p.moveTo(X(-0.33), Y(0.02));
    p.bezierCurveTo(X(-0.33), Y(0.24), X(-0.56), Y(0.40), X(-cut.uaX), Y(cut.uaY));
    p.bezierCurveTo(X(-cut.waist), Y(0.63), X(-cut.hemX), Y(0.87), X(-cut.hemX), Y(0.982));
    p.bezierCurveTo(X(-cut.hemX * 0.42), Y(1.0), X(cut.hemX * 0.42), Y(1.0), X(cut.hemX), Y(0.982));
    p.bezierCurveTo(X(cut.hemX), Y(0.87), X(cut.waist), Y(0.63), X(cut.uaX), Y(cut.uaY));
    p.bezierCurveTo(X(0.56), Y(0.40), X(0.33), Y(0.24), X(0.33), Y(0.02));
    p.lineTo(X(0.13), Y(0.02));
    p.bezierCurveTo(X(0.12), Y(0.22), X(0.05), Y(0.34), cx, Y(0.40));
    p.bezierCurveTo(X(-0.05), Y(0.34), X(-0.12), Y(0.22), X(-0.13), Y(0.02));
    p.closePath();
    return p;
  }

  function drawVest(ctx, cut, x, y, w, h, back) {
    var p = vestPath(cut, x, y, w, h, back);

    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,.22)";
    ctx.shadowBlur = w * 0.06;
    ctx.shadowOffsetY = w * 0.022;
    ctx.fillStyle = state.base;
    ctx.fill(p);
    ctx.restore();

    ctx.save();
    ctx.clip(p);
    ctx.drawImage(texCanvas, back ? TW * 0.5 : 0, 0, TW * 0.5, TH, x, y, w, h);
    /* Binding follows the outline itself, so neck, armhole and hem all
       get it from one stroke. */
    ctx.strokeStyle = state.trim;
    ctx.lineWidth = w * 0.036;
    ctx.stroke(p);
    ctx.restore();

    ctx.save();
    ctx.strokeStyle = "rgba(0,0,0,.28)";
    ctx.lineWidth = Math.max(1, w * 0.004);
    ctx.stroke(p);
    ctx.restore();
  }

  var stageCanvas = null, stageCtx = null;

  /* Where a badge lands on screen, so the thing you picked can be outlined
     on top of the vest rather than only in the texture underneath it. */
  function badgeScreenRect(key) {
    var r = badgeRect(key);
    if (!r || !stageLayout) return null;
    var side = (r.x + r.w / 2) < TW * 0.5 ? "front" : "back";
    var L = stageLayout[side];
    if (!L) return null;
    var ox = side === "back" ? TW * 0.5 : 0;
    return { x: L.x + ((r.x - ox) / (TW * 0.5)) * L.w, y: L.y + (r.y / TH) * L.h,
             w: (r.w / (TW * 0.5)) * L.w, h: (r.h / TH) * L.h };
  }

  function drawSelection(ctx) {
    if (!selected || !state[selected] || !state[selected].on) return;
    var r = badgeScreenRect(selected);
    if (!r) return;
    var pad = 4, tick = Math.min(12, r.w * 0.28, r.h * 0.6);
    var x = r.x - pad, y = r.y - pad, w = r.w + pad * 2, h = r.h + pad * 2;
    ctx.save();
    ctx.strokeStyle = "rgba(255,255,255,.85)";
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, w, h);
    ctx.strokeStyle = getComputedStyle(document.documentElement)
      .getPropertyValue("--accent").trim() || "#2E5E5A";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x, y, w, h);
    ctx.lineWidth = 3;
    [[x, y, 1, 1], [x + w, y, -1, 1], [x, y + h, 1, -1], [x + w, y + h, -1, -1]]
      .forEach(function (c) {
        ctx.beginPath();
        ctx.moveTo(c[0] + c[2] * tick, c[1]);
        ctx.lineTo(c[0], c[1]);
        ctx.lineTo(c[0], c[1] + c[3] * tick);
        ctx.stroke();
      });
    ctx.restore();
  }

  function renderStage() {
    var host = $("#kvd-stageHost");
    if (!host) return;
    if (!stageCanvas) {
      stageCanvas = document.createElement("canvas");
      host.appendChild(stageCanvas);
      stageCtx = stageCanvas.getContext("2d");
    }
    var w = host.clientWidth || 520, h = host.clientHeight || 350;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (stageCanvas.width !== Math.round(w * dpr) || stageCanvas.height !== Math.round(h * dpr)) {
      stageCanvas.width = Math.round(w * dpr);
      stageCanvas.height = Math.round(h * dpr);
    }
    var ctx = stageCtx;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    var cut = CUTS[state.preview];
    /* One side fills the stage; both is there for the committee screenshot.
       A vest at half the width is too small to judge a design on. */
    var both = state.view === "both";
    var sides = both ? ["front", "back"] : [state.view === "back" ? "back" : "front"];
    var gap = w * 0.05, margin = w * 0.06, labelBand = both ? 26 : 8;
    var avail = h - labelBand - 16;
    var boxW, boxH;
    if (both) {
      boxW = (w - gap - margin * 2) / 2;
      boxH = boxW * cut.ratio;
      if (boxH > avail) { boxH = avail; boxW = boxH / cut.ratio; }
    } else {
      boxH = avail;
      boxW = boxH / cut.ratio;
      if (boxW > w - margin * 2) { boxW = w - margin * 2; boxH = boxW * cut.ratio; }
    }
    var totalW = boxW * sides.length + (both ? gap : 0);
    var x0 = (w - totalW) / 2;
    var y0 = (h - labelBand - boxH) / 2 + (both ? 4 : 0);

    stageLayout = {};
    sides.forEach(function (sd, i) {
      var bx = x0 + i * (boxW + gap);
      drawVest(ctx, cut, bx, y0, boxW, boxH, sd === "back");
      stageLayout[sd] = { x: bx, y: y0, w: boxW, h: boxH };
    });

    if (both) {
      ctx.fillStyle = "rgba(128,136,132,.95)";
      ctx.font = "500 11px 'IBM Plex Mono', monospace";
      ctx.textAlign = "center";
      sides.forEach(function (sd, i) {
        ctx.fillText(sd.toUpperCase(), x0 + i * (boxW + gap) + boxW / 2, y0 + boxH + 18);
      });
      ctx.textAlign = "left";
    }

    drawSelection(ctx);

    if (snapGuide !== null) {
      var side = snapGuide < 0.5 ? "front" : "back";
      var L = stageLayout[side];
      var gx = L.x + ((snapGuide - (side === "back" ? 0.5 : 0)) / 0.5) * L.w;
      ctx.save();
      ctx.strokeStyle = "rgba(46,94,90,.8)";
      ctx.setLineDash([6, 5]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(gx, L.y - 8);
      ctx.lineTo(gx, L.y + L.h + 8);
      ctx.stroke();
      ctx.restore();
    }
  }

  /* The texture a style would paint, at thumbnail size, in whatever
     colours are asked for rather than always the club's own. */
  function patternCanvas(spec, cols, w, h) {
    var c = document.createElement("canvas");
    c.width = w; c.height = h;
    var x = c.getContext("2d");
    var kw = TW, kh = TH;
    TW = w; TH = h;
    x.fillStyle = cols.base;
    x.fillRect(0, 0, w, h);
    spec.forEach(function (s, i) {
      var el = SHAPES[s.t].make();
      el.type = s.t;
      el.colour = cols[s.r] || cols.design;
      el.opacity = state.opacity;
      el.seed = i * 31 + 7;
      Object.keys(s).forEach(function (k) { if (k !== "t" && k !== "r") el[k] = s[k]; });
      paintElement(x, el);
    });
    TW = kw; TH = kh;
    return c;
  }

  /* Tiles are vest-shaped. Twenty-seven rectangles in the same two colours
     all look alike; twenty-seven vests are told apart at a glance. */
  function vestThumb(spec, cols) {
    var W = 132, H = 170, dpr = 2;
    var c = document.createElement("canvas");
    c.width = W * dpr; c.height = H * dpr;
    var x = c.getContext("2d");
    x.scale(dpr, dpr);
    var pat = patternCanvas(spec, cols, 288, 144);
    var cut = CUTS.mens;
    var bw = W * 0.94, bh = bw * cut.ratio;
    if (bh > H * 0.97) { bh = H * 0.97; bw = bh / cut.ratio; }
    var bx = (W - bw) / 2, by = (H - bh) / 2;
    var path = vestPath(cut, bx, by, bw, bh, false);
    x.save();
    x.clip(path);
    x.fillStyle = cols.base;
    x.fillRect(0, 0, W, H);
    x.drawImage(pat, 0, 0, 144, 144, bx, by, bw, bh);
    x.strokeStyle = cols.trim;
    x.lineWidth = bw * 0.036;
    x.stroke(path);
    x.restore();
    x.strokeStyle = "rgba(0,0,0,.30)";
    x.lineWidth = 1;
    x.stroke(path);
    return c.toDataURL();
  }

  /* ---------------------------------------------------------------
     Controls
  ----------------------------------------------------------------*/
  var ROLE_LABELS = { base:"Body", trim:"Trim", design:"Design",
                      accent:"Accent", text:"Lettering" };
  var boxRole = {};

  function boxOf(node) {
    return node && node.closest ? node.closest(".kv-colourbox") : null;
  }
  function roleOfBox(host) {
    var roles = host.dataset.roles.split(",");
    var id = host.dataset.box;
    if (!boxRole[id] || roles.indexOf(boxRole[id]) < 0) boxRole[id] = roles[0];
    return boxRole[id];
  }

  function renderColourBoxes() {
    $$(".kv-colourbox").forEach(function (host) {
      var roles = host.dataset.roles.split(",");
      var id = host.dataset.box;
      var active = roleOfBox(host);
      var current = state[active];
      var chips = roles.length < 2 ? "" :
        '<div class="kv-seg" role="group" aria-label="Which colour to change">' +
        roles.map(function (r) {
          return '<button type="button" data-role="' + r + '" aria-pressed="' +
                 (r === active) + '">' + esc(ROLE_LABELS[r]) + '</button>';
        }).join("") + '</div>';
      host.innerHTML = chips +
        '<div class="kv-palette">' + PALETTE.map(function (p) {
          var sel = p[1].toLowerCase() === String(current).toLowerCase();
          return '<button type="button" class="kv-swatch" data-hex="' + p[1] + '" title="' +
                 esc(p[0]) + '" aria-label="' + esc(p[0]) + '" aria-pressed="' + sel +
                 '" style="background:' + p[1] + '"></button>';
        }).join("") + '</div>' +
        '<div class="kv-custom-row"><label for="cc-' + id + '">Any other colour</label>' +
        '<input type="color" id="cc-' + id + '" data-custom="' + id + '" value="' +
        (/^#[0-9a-f]{6}$/i.test(current) ? current : "#F5C518") + '">' +
        '<span>' + esc(String(current).toUpperCase()) + '</span></div>';
    });
  }

  var SEL_LABEL = { front: "Club name, front", back: "Club name, back",
                    crest: "Club crest", sponsor: "Sponsor logo" };

  function renderInspector() {
    var host = $(".kv-inspector");
    if (!host) return;
    var key = selected && state[selected] && state[selected].on ? selected : null;
    host.hidden = !key;
    if (!key) { host.innerHTML = ""; return; }
    var pct = Math.round(state[key].scale * 100);
    host.innerHTML =
      '<span class="kv-insp-name">' + esc(SEL_LABEL[key] || key) + '</span>' +
      '<input type="range" data-badgesize="' + key + '" min="25" max="95" value="' + pct +
      '" aria-label="' + esc(SEL_LABEL[key] || key) + ' size">' +
      '<span class="kv-slider-val" data-sizeval="' + key + '">' + pct + '%</span>' +
      '<button type="button" class="kv-mini" data-centre="' + key + '">Centre</button>' +
      '<button type="button" class="kv-mini" data-badge="' + key + ':off">Remove</button>';
  }

  function renderFontPicker() {
    $("#kvd-fontPicker").innerHTML = FONTS.map(function (f) {
      return '<button type="button" data-font="' + f.key + '" aria-pressed="' +
             (state.font === f.key) + '" style="font-family:\'' + f.family +
             '\',sans-serif">' + esc(f.label) + '</button>';
    }).join("");
    var input = $("#kvd-clubName");
    var cur = fontOf(state.font);
    input.style.fontFamily = "'" + cur.family + "', sans-serif";
    input.style.textTransform = cur.upper ? "uppercase" : "none";
  }

  /* Thumbnails are the expensive part of a render — a noise style costs
     tens of thousands of samples — so they are cached against everything
     that can change them. */
  var thumbCache = {};
  function thumbFor(i, cols) {
    cols = cols || state;
    var key = i + "|" + [cols.base, cols.design, cols.accent, cols.trim, cols.text]
      .join(",") + "|" + state.opacity + "|" + clubInitials();
    if (!thumbCache[key]) {
      var keys = Object.keys(thumbCache);
      if (keys.length > 120) delete thumbCache[keys[0]];
      thumbCache[key] = vestThumb(STYLES[i][1], cols);
    }
    return thumbCache[key];
  }

  function renderPresets() {
    var host = $(".kv-presets");
    if (!host) return;
    host.innerHTML = PRESETS.map(function (pre, i) {
      return '<button type="button" class="kv-style" data-preset="' + i + '">' +
             '<span class="kv-sw" style="background-image:url(' +
             thumbFor(styleIndex(pre[1]), pre[2]) + ')"></span>' +
             '<span class="kv-nm">' + esc(pre[0]) + '</span></button>';
    }).join("");
  }

  /* Six of each to begin with. The whole wall of twenty-seven is a lot to
     read, and the ones clubs actually ask for are at the front. */
  var SHOW_PER_GROUP = 6;
  var stylesOpen = false;

  function renderStyles() {
    var html = "";
    [["block", "Blocks and stripes"], ["print", "Prints and textures"]].forEach(function (g) {
      var group = [];
      STYLES.forEach(function (st, i) { if (st[2] === g[0]) group.push(i); });
      var shown = stylesOpen ? group : group.slice(0, SHOW_PER_GROUP);
      /* whatever is picked stays on show, even when it lives in the tail */
      if (shown.indexOf(state.style) < 0 && group.indexOf(state.style) >= 0) {
        shown = shown.slice(0, SHOW_PER_GROUP - 1).concat([state.style]);
      }
      var items = shown.map(function (i) {
        return '<button type="button" class="kv-style" data-style="' + i + '" aria-pressed="' +
               (state.style === i) + '">' +
               '<span class="kv-sw" style="background-image:url(' + thumbFor(i) + ')"></span>' +
               '<span class="kv-nm">' + esc(STYLES[i][0]) + '</span></button>';
      }).join("");
      if (items) html += '<p class="kv-group-label">' + esc(g[1]) + '</p>' +
                         '<div class="kv-styles">' + items + '</div>';
    });
    html += '<button type="button" class="kv-mini kv-morestyles" data-morestyles="1">' +
            (stylesOpen ? "Show fewer" : "Show all " + STYLES.length + " styles") + '</button>';
    $("#kvd-styles").innerHTML = html;
  }

  function syncToggles() {
    [["preview","preview"],["font","font"],["view","view"],
     ["backstyle","backStyle"]].forEach(function (m) {
      $$("[data-" + m[0] + "]").forEach(function (b) {
        b.setAttribute("aria-pressed", String(b.dataset[m[0]] === state[m[1]]));
      });
    });
    BADGES.forEach(function (key) {
      var b = state[key];
      $$('[data-badge^="' + key + ':"]').forEach(function (btn) {
        btn.setAttribute("aria-pressed",
          String((btn.dataset.badge === key + ":on") === !!b.on));
      });
      var clear = ROOT.querySelector('[data-clear="' + key + '"]');
      if (clear) clear.hidden = !b.src;
      $$('[data-sizerow="' + key + '"]').forEach(function (row) { row.hidden = !b.on; });
      $$('[data-badgesize="' + key + '"]').forEach(function (sl) {
        sl.value = Math.round(b.scale * 100);
      });
      $$('[data-sizeval="' + key + '"]').forEach(function (val) {
        val.textContent = Math.round(b.scale * 100) + "%";
      });
    });
    if (selected && (!state[selected] || !state[selected].on)) selected = null;
    var stageEl2 = ROOT.querySelector(".kv-stage");
    if (stageEl2) {
      stageEl2.classList.toggle("kv-live", BADGES.some(function (k) { return state[k].on; }));
    }
    var n = (state.clubName || "").trim().length;
    $("#kvd-nameCount").textContent = n + " of 20 characters" +
      (n > 13 ? " · set smaller to fit the print area" : "");
    $("#kvd-opacityVal").textContent = Math.round(state.opacity * 100) + "%";
  }

  function repaint() {
    paintTexture();
    renderStage();
    save();
  }

  function renderAll() {
    renderColourBoxes();
    renderCrestColours();
    renderPresets();
    renderInspector();
    renderFontPicker();
    renderStyles();
    paintTexture();
    renderStage();
    syncToggles();
    save();
  }

  /* ---------------------------------------------------------------
     Spec, memory and sending
  ----------------------------------------------------------------*/
  var STORE_KEY = "koru-vest-design-v2";

  function clubCode() {
    var src = (state.contact.club || state.clubName || "KORU").toUpperCase();
    var letters = src.replace(/[^A-Z ]/g, "").trim().split(/\s+/)[0] || "KORU";
    return (letters + "XXX").slice(0, 3);
  }

  function spec() {
    return {
      version: 2,
      style: STYLES[state.style][0],
      strength: Math.round(state.opacity * 100) + "%",
      colours: {
        body: { hex: state.base, name: colourName(state.base) },
        design: { hex: state.design, name: colourName(state.design) },
        accent: { hex: state.accent, name: colourName(state.accent) },
        trim: { hex: state.trim, name: colourName(state.trim) },
        lettering: { hex: state.text, name: colourName(state.text) }
      },
      chestPrint: state.clubName.trim().toUpperCase(),
      frontPrint: state.front.on
        ? { text: "club name", at: Math.round(state.front.u * 100) + "," +
            Math.round(state.front.v * 100), size: Math.round(state.front.scale * 100) + "%" }
        : "none",
      backPrint: state.back.on
        ? { text: "club name", at: Math.round(state.back.u * 100) + "," +
            Math.round(state.back.v * 100), size: Math.round(state.back.scale * 100) + "%" }
        : "none",
      lettering: fontOf(state.font).label,
      crest: { shown: state.crest.on, artwork: !!state.crest.src,
               at: Math.round(state.crest.u * 100) + "," + Math.round(state.crest.v * 100),
               size: Math.round(state.crest.scale * 100) + "%" },
      sponsor: { shown: state.sponsor.on, artwork: !!state.sponsor.src,
                 at: Math.round(state.sponsor.u * 100) + "," + Math.round(state.sponsor.v * 100),
                 size: Math.round(state.sponsor.scale * 100) + "%" },
      contact: state.contact
    };
  }

  function save() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (e) { /* private mode */ }
    pushHistory();
  }

  /* ---------------------------------------------------------------
     Undo. A club that can take a step back tries things; one that
     cannot pokes at it. Only the design is remembered — not which
     step is open, not which way the vest is turned, not the contact
     details, none of which anyone means to undo.
  ----------------------------------------------------------------*/
  var HIST_KEYS = ["base", "design", "accent", "trim", "text", "style", "opacity",
                   "clubName", "font", "backStyle", "front", "back", "crest", "sponsor"];
  var undoStack = [], redoStack = [], lastPush = 0, applyingHistory = false;

  /* Canonical shape, not whatever shape the state happens to be in: a
     restored badge gains a src key, and a snapshot that differs only in
     key order would read as a change and throw the redo away. */
  function snapshot() {
    var o = {};
    HIST_KEYS.forEach(function (k) {
      var v = state[k];
      o[k] = (v && typeof v === "object")
        ? { on: !!v.on, u: v.u, v: v.v, scale: v.scale, src: v.src || null }
        : v;
    });
    return JSON.stringify(o);
  }

  function syncHistory() {
    var u = document.querySelector('[data-history="undo"]');
    var r = document.querySelector('[data-history="redo"]');
    if (u) u.disabled = undoStack.length < 2;
    if (r) r.disabled = !redoStack.length;
  }

  function pushHistory() {
    if (applyingHistory) return;
    var snap = snapshot();
    var top = undoStack[undoStack.length - 1];
    if (top === snap) return;
    var now = Date.now();
    /* A slider dragged for two seconds is one thing done, not forty —
       but two clicks a third of a second apart are two things. */
    if (undoStack.length > 1 && now - lastPush < 350) undoStack[undoStack.length - 1] = snap;
    else {
      undoStack.push(snap);
      if (undoStack.length > 50) undoStack.shift();
    }
    lastPush = now;
    redoStack.length = 0;
    syncHistory();
  }

  function applyHistory(snap) {
    applyingHistory = true;
    applyState(JSON.parse(snap));
    lastPush = 0;
    refreshArtwork(function () {
      applyingHistory = false;
      renderAll();
      syncHistory();
    });
  }

  function undo() {
    if (undoStack.length < 2) return;
    redoStack.push(undoStack.pop());
    applyHistory(undoStack[undoStack.length - 1]);
  }

  function redo() {
    if (!redoStack.length) return;
    var snap = redoStack.pop();
    undoStack.push(snap);
    applyHistory(snap);
  }

  /* ---------------------------------------------------------------
     A design in a link. The whole design is a few hundred bytes, so
     it can travel in the URL instead of needing somewhere to live:
     a club sends it to its committee, and whoever opens it sees
     exactly what the club saw. Artwork is the one thing too big to
     carry, so a crest is named rather than packed.
  ----------------------------------------------------------------*/
  var LINK_KEYS = HIST_KEYS.concat(["preview"]);

  function b64url(str) {
    var bytes = new TextEncoder().encode(str), bin = "";
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function unb64url(str) {
    var s = str.replace(/-/g, "+").replace(/_/g, "/");
    while (s.length % 4) s += "=";
    var bin = atob(s), bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  }

  function round(n, places) {
    var f = Math.pow(10, places);
    return Math.round(n * f) / f;
  }

  function encodeDesign() {
    var o = {};
    LINK_KEYS.forEach(function (k) {
      var v = state[k];
      o[k] = (v && typeof v === "object")
        ? { on: !!v.on, u: round(v.u, 4), v: round(v.v, 4), scale: round(v.scale, 3) }
        : v;
    });
    return b64url(JSON.stringify(o));
  }

  function designLink() {
    return location.href.split("#")[0].split("?")[0] + "?vd=" + encodeDesign();
  }

  function openLinkedDesign() {
    var packed = (location.search.match(/[?&]vd=([A-Za-z0-9\-_]+)/) || [])[1];
    if (!packed) return false;
    try { applyState(JSON.parse(unb64url(packed))); return true; }
    catch (e) { return false; }
  }

  /* ---------------------------------------------------------------
     A picture to send round before anyone fills in a form.
  ----------------------------------------------------------------*/
  function downloadPNG() {
    var cut = CUTS[state.preview];
    var W = 1800, pad = 80, gap = 90, band = 96;
    var boxW = (W - pad * 2 - gap) / 2;
    var boxH = boxW * cut.ratio;
    var H = Math.round(boxH + pad * 2 + band);
    var c = document.createElement("canvas");
    c.width = W; c.height = H;
    var x = c.getContext("2d");
    var paper = getComputedStyle(document.documentElement)
      .getPropertyValue("--paper").trim() || "#FAFAF7";
    x.fillStyle = paper;
    x.fillRect(0, 0, W, H);

    var y0 = pad + band * 0.45;
    drawVest(x, cut, pad, y0, boxW, boxH, false);
    drawVest(x, cut, pad + boxW + gap, y0, boxW, boxH, true);

    x.fillStyle = "rgba(20,20,20,.55)";
    x.font = "500 26px 'IBM Plex Mono', ui-monospace, monospace";
    x.textAlign = "center";
    x.fillText("FRONT", pad + boxW / 2, y0 + boxH + 46);
    x.fillText("BACK", pad + boxW + gap + boxW / 2, y0 + boxH + 46);

    x.textAlign = "left";
    x.fillStyle = "rgba(20,20,20,.9)";
    x.font = "700 34px 'Archivo', system-ui, sans-serif";
    x.fillText((state.clubName || "Club vest").toUpperCase(), pad, pad + 14);
    x.fillStyle = "rgba(20,20,20,.5)";
    x.font = "500 22px 'IBM Plex Mono', ui-monospace, monospace";
    x.textAlign = "right";
    x.fillText(STYLES[state.style][0] + " · " + CUTS[state.preview].label +
               " · koru", W - pad, pad + 12);

    var a = document.createElement("a");
    a.href = c.toDataURL("image/png");
    a.download = ((state.clubName || "koru").trim().toLowerCase()
      .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "koru") + "-vest.png";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function applyState(next) {
    if (!next || typeof next !== "object") return;
    Object.keys(state).forEach(function (k) {
      if (next[k] === undefined) return;
      if (k === "contact") {
        Object.keys(state.contact).forEach(function (f) {
          if (next.contact && next.contact[f] !== undefined) state.contact[f] = next.contact[f];
        });
      } else {
        state[k] = next[k];
      }
    });
    if (!STYLES[state.style]) state.style = 1;
    /* Older saves carried booleans and one shared size; fold them in. */
    if (next.frontText !== undefined && typeof next.front !== "object") {
      state.front = { on: !!next.frontText, u: 0.25, v: 0.345, scale: 0.58 };
    }
    if (next.backText !== undefined && typeof next.back !== "object") {
      state.back = { on: !!next.backText, u: 0.75, v: 0.33, scale: 0.50 };
    }
    [["front", true, 0.25, 0.345, 0.58], ["back", true, 0.75, 0.33, 0.50],
     ["crest", true, 0.188, 0.222, 0.17], ["sponsor", false, 0.25, 0.47, 0.30]]
      .forEach(function (d) {
        var b = (state[d[0]] && typeof state[d[0]] === "object") ? state[d[0]] : {};
        state[d[0]] = {
          on: b.on === undefined ? d[1] : !!b.on,
          u: typeof b.u === "number" ? b.u : d[2],
          v: typeof b.v === "number" ? b.v : d[3],
          scale: typeof b.scale === "number" ? b.scale : d[4],
          src: b.src || null
        };
      });
    if (!fontOf(state.font) || state.font === "wide") state.font = "block";
    $("#kvd-clubName").value = state.clubName;
    $("#kvd-opacity").value = Math.round(state.opacity * 100);
    ["club","name","email","phone","notes"].forEach(function (f) {
      var el = document.getElementById("kvd-f" + f.charAt(0).toUpperCase() + f.slice(1));
      if (el) el.value = state.contact[f] || "";
    });
  }

  function refreshArtwork(then) {
    var pending = 0;
    ["crest", "sponsor"].forEach(function (k) {
      if (!state[k].src) { badgeImg[k] = null; return; }
      pending++;
      adoptArtwork(k, state[k].src, function () { if (--pending === 0 && then) then(); });
    });
    if (!pending && then) then();
  }

  function restore() {
    try {
      var raw = localStorage.getItem(STORE_KEY);
      if (!raw) return false;
      applyState(JSON.parse(raw));
      return true;
    } catch (e) { return false; }
  }


  function newCode() {
    var alphabet = "ACDEFGHJKLMNPQRTUVWXY3479", out = "";
    for (var i = 0; i < 6; i++) out += alphabet.charAt(Math.floor(Math.random() * alphabet.length));
    return out;
  }

  function setStatus(msg, isError) {
    var el = $("#kvd-status");
    el.textContent = msg;
    el.className = "kv-status" + (isError ? " kv-err" : "");
  }

  /* Where a design goes. With an endpoint set (a Make webhook, an app
     proxy, anything that takes JSON) it is posted there with a PNG of the
     mockup and the artwork. With no endpoint it goes through the store's
     own contact form — a plain form POST, the way every Shopify theme
     sends one, so it needs no key, no app and no CORS, and it lands in
     whichever inbox the store already uses for customer email. */
  function persist(status) {
    var endpoint = ROOT.getAttribute("data-endpoint");
    if (!endpoint) return sendByContactForm(status);
    var code = newCode();
    var payload = {
      code: code,
      status: status,
      spec: spec(),
      production: { clubCode: clubCode() },
      link: designLink(),
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

  /* The design as words, because a contact-form email carries no files.
     The link at the end reopens the design itself. */
  function designSummary() {
    var c = state.contact;
    var colour = function (role) {
      return colourName(state[role]) + " " + String(state[role]).toUpperCase();
    };
    var print = function (key, label) {
      var b = state[key];
      if (!b.on) return label + ": none";
      return label + ": " + Math.round(b.scale * 100) + "% at " +
             b.u.toFixed(3) + "," + b.v.toFixed(3);
    };
    var lines = [
      "Club: " + (c.club || "(not given)"),
      "Contact: " + (c.name || "(not given)") + " · " + (c.email || "") +
        (c.phone ? " · " + c.phone : ""),
      "",
      "Style: " + STYLES[state.style][0] + " at " + Math.round(state.opacity * 100) + "%",
      "Cut shown: " + CUTS[state.preview].label,
      "Body: " + colour("base"),
      "Trim: " + colour("trim"),
      "Design: " + colour("design"),
      "Accent: " + colour("accent"),
      "Lettering: " + colour("text") + " in " + fontOf(state.font).label,
      "",
      "Name across the chest: " + (state.clubName || "(none)"),
      print("front", "Front print"),
      print("back", "Back print"),
      "Crest: " + (state.crest.on ? (state.crest.src ? "artwork uploaded — ask the club to email the file"
                                                     : "placed, no artwork yet") : "none"),
      "Sponsor: " + (state.sponsor.on ? (state.sponsor.src ? "artwork uploaded — ask the club to email the file"
                                                           : "placed, no artwork yet") : "none"),
      "",
      "Notes: " + (c.notes || "(none)"),
      "",
      "Open this design: " + designLink()
    ];
    return lines.join("\n");
  }

  function sendByContactForm(status) {
    var c = state.contact;
    var form = document.createElement("form");
    form.method = "post";
    form.action = "/contact#contact_form";
    form.acceptCharset = "UTF-8";
    form.hidden = true;
    [["form_type", "contact"],
     ["utf8", "\u2713"],
     ["contact[name]", (c.name || c.club || "Club vest designer")],
     ["contact[email]", c.email],
     ["contact[phone]", c.phone],
     ["contact[body]", "Vest design " + (status === "saved" ? "saved" : "submitted") +
                       " from the designer.\n\n" + designSummary()]
    ].forEach(function (kv) {
      var input = document.createElement("input");
      input.type = "hidden";
      input.name = kv[0];
      input.value = kv[1] || "";
      form.appendChild(input);
    });
    document.body.appendChild(form);
    form.submit();
    /* The page is on its way to the contact endpoint and back; nothing
       here resolves, and the message on return is picked up at boot. */
    return new Promise(function () {});
  }

  function contactEmail() {
    return ROOT.getAttribute("data-contact") || "us";
  }


  /* ---------------------------------------------------------------
     Wiring
  ----------------------------------------------------------------*/
  function onPick(attr, handler) {
    document.addEventListener("click", function (ev) {
      var btn = ev.target.closest ? ev.target.closest("[data-" + attr + "]") : null;
      if (!btn || btn.disabled) return;
      handler(btn.dataset[attr], btn);
      renderAll();
    });
  }
  onPick("preview", function (v) { state.preview = v; });
  onPick("view",    function (v) { state.view = v; });
  onPick("backstyle", function (v) { state.backStyle = v; });
  onPick("role",    function (v, btn) {
    var host = boxOf(btn);
    if (host) boxRole[host.dataset.box] = v;
  });
  onPick("font",    function (v) { state.font = v; });
  onPick("badge",   function (v) {
    var parts = v.split(":");
    state[parts[0]].on = parts[1] === "on";
  });
  onPick("centre",  function (v) { centreBadge(v); });
  onPick("upload",  function (v) { $("#kvd-" + v + "File").click(); });
  onPick("clear",   function (v) { adoptArtwork(v, null, renderAll); });

  ["crest", "sponsor"].forEach(function (key) {
    var input = $("#kvd-" + key + "File");
    if (!input) return;
    input.addEventListener("change", function (e) {
      var file = e.target.files && e.target.files[0];
      e.target.value = "";
      if (!file) return;
      setStatus("Reading artwork…");
      loadArtwork(file, function (src) {
        if (!src) { setStatus("That file could not be read as an image.", true); return; }
        state[key].on = true;
        adoptArtwork(key, src, function () {
          setStatus("Artwork added. Drag it on the vest to place it.");
          renderAll();
        });
      });
    });
  });
  onPick("style",   function (v) { state.style = parseInt(v, 10); });
  onPick("morestyles", function () { stylesOpen = !stylesOpen; });
  onPick("history", function (v) { if (v === "undo") undo(); else redo(); });
  onPick("download", function () { downloadPNG(); });
  onPick("preset",  function (v) {
    var pre = PRESETS[parseInt(v, 10)];
    if (!pre) return;
    state.style = styleIndex(pre[1]);
    Object.keys(pre[2]).forEach(function (k) { state[k] = pre[2][k]; });
    state.opacity = 1;
  });
  /* A crest swatch fills whichever colour the Body/Trim chips have armed,
     the same as the stock swatches beside it. */
  onPick("cresthex", function (v) { state[boxRole.garment || "base"] = v; });
  onPick("clubcolours", function () {
    var cs = crestColours.slice(0, 4);
    if (!cs.length) return;
    var byLight = cs.slice().sort(function (a, b) { return luma(b) - luma(a); });
    var light = byLight[0], dark = byLight[byLight.length - 1];
    state.base = light;
    state.design = dark;
    state.trim = dark;
    state.accent = byLight[1] || dark;
    state.text = luma(light) > 140 ? dark : light;
  });
  onPick("hex",     function (v, btn) {
    var host = boxOf(btn);
    if (host) state[roleOfBox(host)] = v;
  });

  $("#kvd-clubName").addEventListener("input", function (e) {
    state.clubName = e.target.value;
    syncToggles();
    repaint();
  });
  document.addEventListener("input", function (e) {
    if (!e.target || !e.target.dataset) return;
    if (e.target.dataset.badgesize) {
      var bk = e.target.dataset.badgesize;
      state[bk].scale = parseInt(e.target.value, 10) / 100;
      var pct = Math.round(state[bk].scale * 100) + "%";
      $$('[data-sizeval="' + bk + '"]').forEach(function (l) { l.textContent = pct; });
      $$('[data-badgesize="' + bk + '"]').forEach(function (sl) {
        if (sl !== e.target) sl.value = parseInt(e.target.value, 10);
      });
      queueRepaint();
      save();
      return;
    }
    if (!e.target.dataset.custom) return;
    var host = boxOf(e.target);
    if (!host) return;
    state[roleOfBox(host)] = e.target.value;
    var hex = host.querySelector(".kv-custom-row span");
    if (hex) hex.textContent = e.target.value.toUpperCase();
    renderStyles();
    repaint();
  });

  $("#kvd-opacity").addEventListener("input", function (e) {
    state.opacity = parseInt(e.target.value, 10) / 100;
    $("#kvd-opacityVal").textContent = Math.round(state.opacity * 100) + "%";
    repaint();
  });
  ["club","name","email","phone","notes"].forEach(function (f) {
    var el = document.getElementById("kvd-f" + f.charAt(0).toUpperCase() + f.slice(1));
    if (!el) return;
    el.addEventListener("input", function (e) { state.contact[f] = e.target.value; save(); });
  });

  $("#kvd-saveBtn").addEventListener("click", function () {
    var link = designLink();
    var shown = function () {
      setStatus("Link copied. Whoever opens it sees this exact design.");
    };
    var spelled = function () { setStatus("Copy this link: " + link); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(link).then(shown, spelled);
    } else spelled();
  });

  $("#kvd-submitBtn").addEventListener("click", function () {
    var c = state.contact;
    if (!c.club.trim()) { setStatus("Add your club name so we know whose vest this is.", true); $("#kvd-fClub").focus(); return; }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(c.email.trim())) { setStatus("Add an email we can send the proof to.", true); $("#kvd-fEmail").focus(); return; }
    setStatus("Sending…");
    persist("submitted").then(function (code) {
      if (code) setStatus("Sent — reference " + code + ". We'll come back to " + c.email.trim() +
                          " within two working days.");
    });
  });

  /* The tab bar parks itself directly under the preview, so the vest
     stays on screen while the steps scroll beneath it. */
  function syncSticky() {
    var sw = ROOT.querySelector(".kv-stagewrap");
    if (sw) document.documentElement.style.setProperty("--tabTop", sw.offsetHeight + "px");
  }

  /* Wide enough for two columns and the swatches move under the vest: the
     colours belong beside the thing they colour, and it keeps the steps
     column from running long. Only the step you are on docks its box, so
     each colour still sits with the step it belongs to. */
  var wideMQ = window.matchMedia("(min-width:880px)");
  var dockable = null;

  function dockColours() {
    var dock = $("#kvd-colourDock");
    if (!dock) return;
    if (!dockable) {
      dockable = $$("[data-dock]").map(function (el) {
        var panel = el.closest ? el.closest(".kv-panel") : null;
        return { el: el, panel: panel ? panel.dataset.panel : null,
                 parent: el.parentNode, next: el.nextSibling };
      });
    }
    dockable.forEach(function (f) {
      var wanted = wideMQ.matches && f.panel === state.tab;
      if (wanted && f.el.parentNode !== dock) dock.appendChild(f.el);
      else if (!wanted && f.el.parentNode === dock) f.parent.insertBefore(f.el, f.next);
    });
  }

  if (wideMQ.addEventListener) wideMQ.addEventListener("change", dockColours);
  else if (wideMQ.addListener) wideMQ.addListener(dockColours);

  function showTab(id) {
    if (!document.getElementById("kvd-p-" + id)) id = "colours";
    state.tab = id;
    $$(".kv-tabs [data-tab]").forEach(function (b) {
      b.setAttribute("aria-selected", String(b.dataset.tab === id));
    });
    $$(".kv-panel").forEach(function (panel) {
      panel.classList.toggle("kv-on", panel.dataset.panel === id);
    });
    dockColours();
    $$(".kv-sendbar, .kv-sendcta").forEach(function (el) { el.classList.toggle("kv-gone", id === "send"); });
    syncSticky();
    save();
  }

  document.addEventListener("click", function (ev) {
    var t = ev.target.closest ? ev.target.closest("[data-tab],[data-goto]") : null;
    if (!t) return;
    showTab(t.dataset.tab || t.dataset.goto);
    if (t.dataset.goto) {
      var tabs = ROOT.querySelector(".kv-tabs");
      if (tabs) tabs.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  });

  /* ---------------------------------------------------------------
     Boot
  ----------------------------------------------------------------*/
  var linked = openLinkedDesign();
  if (!linked) restore();
  if (/[?&]contact_posted=true/.test(location.search)) {
    setTimeout(function () {
      showTab("send");
      setStatus("Sent." + (state.crest.src || state.sponsor.src
        ? " Now email your artwork files to " + contactEmail() + " and we'll match them up."
        : " We'll come back to you within two working days."));
    }, 0);
  }
  renderAll();
  showTab(state.tab);
  bindBadgeDrag(ROOT.querySelector(".kv-stage"));
  refreshArtwork(renderAll);
  window.addEventListener("resize", function () { renderStage(); syncSticky(); });
  window.addEventListener("orientationchange", syncSticky);
  if (window.ResizeObserver) {
    new ResizeObserver(function () { renderStage(); syncSticky(); }).observe($("#kvd-stageHost"));
  }
  loadFonts(function () { paintTexture(); renderStage(); });
})();
