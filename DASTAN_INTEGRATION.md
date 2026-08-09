# Replacing the xP model with Dastan — state of the integration

`qazybekb/smartplayfpl-dastan` is an open-source expected-points model that measurably
beats both this project's model and FPL's own `ep_next`. This records where the swap
got to, so it can be resumed rather than re-derived.

## Verified working

Inference runs against the released weights:

```python
sys.path.insert(0, "<clone>")
from dastan import data, predictor
frame = data.load()                       # 163,072 rows x 314 cols, 2020-21 .. 2025-26
out   = predictor.Dastan().predict_frame(frame[frame.gameweek == 20])
```

Needs `xgboost`, `scikit-learn`, `pyarrow`, `pandas` in the venv. `data.load()` is
required rather than reading `features.parquet` directly — four features
(`ar_ep_next`, `sig_status_risk`, `sig_chance_playing`, `sig_has_news`) live in
separate pre-deadline parquets and the loader joins them.

## Measured, on 17,622 identical player-gameweeks (2024-25 GW15-38)

| model | rho (all) | rho (starters) |
|---|---|---|
| Dastan, their published walk-forward | 0.7461 | 0.4140 |
| Dastan v13 released weights, my run | 0.7293 | 0.4675 |
| FPL `ep_next` | 0.6664 | 0.3319 |
| this project's model | 0.5568 | 0.3563 |

Two things to hold onto:

* **Take 0.414 as the honest figure, not 0.4675.** The released v13 was trained on a
  frame that includes 2024-25, so scoring it there is partly in-sample. Their
  walk-forward number is the one without that advantage.
* Against this project's model the gain on starters is **0.356 -> 0.414**, and MAE
  across all rows **1.272 -> 0.919**.

## The scale caveat

My run of v13 correlates 0.893 with their published predictions but sits at **0.53 of
the scale** (starters mean 1.01 against their 2.35, actual 2.79). Features were ruled
out as the cause — `ep_next` joins bit-identically. The remaining explanation is that
the published predictions come from per-block walk-forward models and three-seed
averaging, while `models/` holds the single final v13.

This does not affect squad selection: the optimiser ranks players and a uniform scale
factor leaves an ILP's answer unchanged. It **does** affect anything reading absolute
points — chip valuations, the field target, every displayed number. Either resolve the
scale properly or fit a correction against actuals before using the values as points.

## The actual blocker

The frame stops at 2025-26. Predicting 2026/27 GW1 needs features built forward, and
`dastan/rebuild/` is built for *reproducing* a published evaluation from pinned FPL and
Understat archives, not for live prediction. There is no documented forward path.

Tractable in principle — every rolling feature for GW1 comes from 2025-26 history,
which is already in the frame, and the rest is the fixture list plus a pre-deadline
snapshot. But it is a real piece of work against someone else's pipeline.

## Blending was tested and rejected

`w * dastan + (1 - w) * mine`, swept: pure Dastan is best on all players, and the
starters-only optimum at w = 0.8-0.9 beats pure Dastan by **+0.002 rho** — against
seed noise their own repo documents at 0.0106. This project's model contributes no
independent signal; it is a worse version of the same one, so averaging adds noise
rather than diversity. Replace, do not blend.
