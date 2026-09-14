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
    { key:"script",    label:"Script",    family:"Kaushan Script", weight:"400", track:0.000, upper:false }
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

    /* The standard club-kit templates, laid out per panel. */
    vstripes:{ group:"kit", make:function(){ return {w:0.055, gap:0.055}; } },
    halves:  { group:"kit", make:function(){ return {v:0.5}; } },
    quarters:{ group:"kit", make:function(){ return {v:0.42, u:0.5}; } },
    shoulders:{group:"kit", make:function(){ return {h:0.26, w:0.085}; } },
    piping:  { group:"kit", make:function(){ return {v:0.35, gap:0.155, w:0.011}; } },
    topo:    { group:"kit", make:function(){ return {size:0.40, density:0.45, w:0.16}; } },
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
    ["Warp chevron",    [{ t:"warp", r:"design" }], "print"]
  ];

  var state = {
    tab: "colours",
    preview: "mens",
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

  /* Most kit shapes are per PANEL, not per texture: a vest with four
     vertical stripes has four on the front and four on the back, not
     eight spread across the pair. These helpers work a panel at a time. */
  var PANELS = [0.25, 0.75];
  function panelEdges(centre) { return [centre - 0.25, centre + 0.25]; }

  function topoCanvas(el) {
    return cached("tp|" + el.colour + "|" + el.size.toFixed(3) + "|" + el.density.toFixed(3) +
                  "|" + el.w.toFixed(3) + "|" + el.seed, function () {
      var w = 420, h = Math.max(2, Math.round(420 * TH / TW));
      var c = document.createElement("canvas");
      c.width = w; c.height = h;
      var x = c.getContext("2d"), img = x.createImageData(w, h);
      var noise = makeNoise(el.seed), rgb = hexToRgb(el.colour);
      var freq = 1.5 + el.size * 16;
      var levels = 4 + el.density * 30;
      var line = 0.03 + el.w * 0.45;
      for (var py = 0; py < h; py++) {
        for (var px = 0; px < w; px++) {
          var n = noise((px / w) * freq, (py / h) * freq, 4);
          var band = (n * levels) % 1;
          var o = (py * w + px) * 4;
          img.data[o] = rgb[0]; img.data[o + 1] = rgb[1]; img.data[o + 2] = rgb[2];
          img.data[o + 3] = band < line ? 255 : 0;
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
        drawPixels(ctx, topoCanvas(el));
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

  function adoptArtwork(key, src, then) {
    if (!src) { badgeImg[key] = null; state[key].src = null; if (then) then(); return; }
    var img = new Image();
    img.onload = function () {
      badgeImg[key] = img;
      state[key].src = src;
      if (then) then();
    };
    img.onerror = function () { badgeImg[key] = null; state[key].src = null; if (then) then(); };
    img.src = src;
  }

  /* ---------------------------------------------------------------
     Dragging a badge on the flat mockup
  ----------------------------------------------------------------*/
  var stageLayout = null, dragging = null, repaintQueued = false;
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
      if (!p) return;
      var key = badgeAt(p);
      if (!key) return;
      ev.preventDefault();
      dragging = { key: key, du: state[key].u - p.u, dv: state[key].v - p.v };
      stage.classList.add("kv-grabbing");
      try { stage.setPointerCapture(ev.pointerId); } catch (e) { /* no capture */ }
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
    var gap = w * 0.05, side = w * 0.06, labelBand = 26;
    var boxW = (w - gap - side * 2) / 2;
    var boxH = boxW * cut.ratio;
    var avail = h - labelBand - 22;
    if (boxH > avail) { boxH = avail; boxW = boxH / cut.ratio; }
    var totalW = boxW * 2 + gap;
    var x0 = (w - totalW) / 2;
    var y0 = (h - labelBand - boxH) / 2 + 4;

    drawVest(ctx, cut, x0, y0, boxW, boxH, false);
    drawVest(ctx, cut, x0 + boxW + gap, y0, boxW, boxH, true);
    stageLayout = {
      front: { x: x0, y: y0, w: boxW, h: boxH },
      back:  { x: x0 + boxW + gap, y: y0, w: boxW, h: boxH }
    };

    ctx.fillStyle = "rgba(128,136,132,.95)";
    ctx.font = "500 11px 'IBM Plex Mono', monospace";
    ctx.textAlign = "center";
    ctx.fillText("FRONT", x0 + boxW / 2, y0 + boxH + 18);
    ctx.fillText("BACK", x0 + boxW + gap + boxW / 2, y0 + boxH + 18);
    ctx.textAlign = "left";

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

  function styleThumb(spec) {
    var c = document.createElement("canvas");
    c.width = 288; c.height = 144;
    var x = c.getContext("2d");
    var kw = TW, kh = TH;
    TW = 288; TH = 144;
    x.fillStyle = state.base;
    x.fillRect(0, 0, TW, TH);
    spec.forEach(function (s, i) {
      var el = SHAPES[s.t].make();
      el.type = s.t;
      el.colour = state[s.r] || state.design;
      el.opacity = state.opacity;
      el.seed = i * 31 + 7;
      Object.keys(s).forEach(function (k) { if (k !== "t" && k !== "r") el[k] = s[k]; });
      paintElement(x, el);
    });
    TW = kw; TH = kh;
    var t = document.createElement("canvas");
    t.width = 176; t.height = 92;
    t.getContext("2d").drawImage(c, 0, 14, 144, 75, 0, 0, 176, 92);
    return t.toDataURL();
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
  function thumbFor(i) {
    var key = i + "|" + [state.base, state.design, state.accent, state.trim, state.text]
      .join(",") + "|" + state.opacity + "|" + clubInitials();
    if (!thumbCache[key]) {
      var keys = Object.keys(thumbCache);
      if (keys.length > 120) delete thumbCache[keys[0]];
      thumbCache[key] = styleThumb(STYLES[i][1]);
    }
    return thumbCache[key];
  }

  function renderStyles() {
    var html = "";
    [["block", "Blocks and stripes"], ["print", "Prints and textures"]].forEach(function (g) {
      var items = "";
      STYLES.forEach(function (st, i) {
        if (st[2] !== g[0]) return;
        items += '<button type="button" class="kv-style" data-style="' + i + '" aria-pressed="' +
                 (state.style === i) + '">' +
                 '<span class="kv-sw" style="background-image:url(' + thumbFor(i) + ')"></span>' +
                 '<span class="kv-nm">' + esc(st[0]) + '</span></button>';
      });
      if (items) html += '<p class="kv-group-label">' + esc(g[1]) + '</p>' +
                         '<div class="kv-styles">' + items + '</div>';
    });
    $("#kvd-styles").innerHTML = html;
  }

  function syncToggles() {
    [["preview","preview"],["font","font"]].forEach(function (m) {
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
      var row = document.getElementById("kvd-" + key + "SizeRow");
      if (row) row.hidden = !b.on;
      var slider = ROOT.querySelector('[data-badgesize="' + key + '"]');
      if (slider) slider.value = Math.round(b.scale * 100);
      var val = document.getElementById("kvd-" + key + "SizeVal");
      if (val) val.textContent = Math.round(b.scale * 100) + "%";
    });
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

  /* The theme has no database. Designs are posted to whatever endpoint the
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
      var lbl = document.getElementById("kvd-" + bk + "SizeVal");
      if (lbl) lbl.textContent = Math.round(state[bk].scale * 100) + "%";
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
    setStatus("Saving…");
    persist("saved").then(function (code) {
      if (code) setStatus("Saved as " + code + ". We have your design.");
    });
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
  restore();
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
