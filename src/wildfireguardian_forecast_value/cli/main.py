"""``wg-forecast-value`` command line interface.

Commands
--------
``degrade``           apply a degradation pipeline to the scenario truth and
                      report what it did to the fire state *and* to the
                      traditional skill scores.
``run-toy-study``     paired world-level comparison at one forecast setting.
``sweep``             the 2-D frontier sweep; writes a tidy parquet.
``estimate-frontier`` read a sweep, estimate the break-even frontier with
                      bootstrap bands, write JSON and the figure.
``cases``             run the four hand-designed cases and print the table.
``validate``          hand-solvable examples and structural invariants.
``demo``              everything above, into one output directory.

Every command that writes results also writes ``manifest.json``: the resolved
configuration, the scenario, the pipeline and the error model.  Results
without a manifest are not reproducible, so the CLI does not produce any.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from wildfireguardian_forecast_value._version import __version__
from wildfireguardian_forecast_value.cli.config import StudyConfig, load_config, write_manifest
from wildfireguardian_forecast_value.cli.report import (
    format_study_summary,
    summarise_study,
    write_json,
)
from wildfireguardian_forecast_value.decision_value.value import (
    default_policies,
    evaluate_world,
    results_to_frame,
    run_paired_study,
)
from wildfireguardian_forecast_value.degradation.latency import LatencySpec
from wildfireguardian_forecast_value.frontiers.bands import bootstrap_frontier_band
from wildfireguardian_forecast_value.frontiers.estimate import (
    frontier_from_grid,
    monotonicity_report,
)
from wildfireguardian_forecast_value.frontiers.grid import FrontierGrid, SweepAxis, sweep_grid
from wildfireguardian_forecast_value.skill_metrics.continuous import arrival_time_metrics
from wildfireguardian_forecast_value.skill_metrics.categorical import categorical_scores
from wildfireguardian_forecast_value.synthetic_decisions.scenarios import CASES, case_specs
from wildfireguardian_forecast_value.validation.hand_examples import run_hand_examples
from wildfireguardian_forecast_value.validation.invariants import run_all_invariants

BANNER = (
    "wildfireguardian-forecast-value "
    f"{__version__}  --  synthetic fixtures only; no real-world performance claim"
)


# ---------------------------------------------------------------- helpers --
def _progress(done: int, total: int) -> None:
    if total <= 1:
        return
    step = max(1, total // 40)
    if done % step == 0 or done == total:
        pct = 100.0 * done / total
        sys.stderr.write(f"\r  sweeping {done}/{total} cells ({pct:5.1f}%)")
        sys.stderr.flush()
        if done == total:
            sys.stderr.write("\n")


def _save_frame(df: pd.DataFrame, base: Path) -> Path:
    """Parquet when pyarrow is present, CSV otherwise.  Never silently neither."""
    base.parent.mkdir(parents=True, exist_ok=True)
    try:
        path = base.with_suffix(".parquet")
        df.to_parquet(path, index=False)
        return path
    except Exception as exc:  # pragma: no cover - depends on optional dep
        path = base.with_suffix(".csv")
        df.to_csv(path, index=False)
        sys.stderr.write(f"  note: parquet unavailable ({exc.__class__.__name__}), wrote CSV\n")
        return path


def _read_frame(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix in (".csv", ".txt"):
        return pd.read_csv(path)
    raise ValueError(f"unsupported results format: {path.suffix!r} (want .parquet or .csv)")


# --------------------------------------------------------------- commands --
def cmd_degrade(args) -> int:
    cfg = load_config(args.config)
    scenario, pipe = cfg.scenario(), cfg.pipeline()
    params = cfg.degradation_params()
    world = scenario.sample_world(0, cfg.seed)
    lat = cfg.latency()

    from wildfireguardian_forecast_value.degradation.latency import make_release

    release = make_release(world.truth, lat.information_time, lat.latency, pipe, params)
    truth, fc = world.truth, release.state

    print(BANNER)
    print(f"\nDegradation pipeline ({len(pipe)} operators, applied in this order):")
    for op in pipe:
        print(f"  {op.name:22s} consumes {list(op.param_names)}")
    print(f"\nParameters (identity values filled in where unset):")
    full = dict(pipe.identity_params())
    full.update(params)
    for k in pipe.param_names:
        mark = "  <- set" if k in params else ""
        print(f"  {k:22s} {full[k]:+.6g}{mark}")

    print(f"\nInformation time s = {lat.information_time} h, latency delta = {lat.latency} h, "
          f"available at {release.availability_time} h; decision at {scenario.decision_time} h")
    print(f"  forecast is {'AVAILABLE' if release.is_available_at(scenario.decision_time) else 'NOT AVAILABLE'} "
          "at the decision time")

    print("\nFire state, truth -> forecast:")
    for lab in sorted(set(truth.labels) | set(fc.labels)):
        t = truth.by_label(lab) if lab in truth.labels else None
        f = fc.by_label(lab) if lab in fc.labels else None
        if f is None:
            print(f"  {lab:8s} DROPPED by the forecast (t0={t.ignition_time:.3f} h)")
        elif t is None:
            print(f"  {lab:8s} present only in the forecast")
        else:
            print(f"  {lab:8s} origin {t.origin} -> {tuple(round(v, 4) for v in f.origin)}   "
                  f"rate {t.spread_rate:.4f} -> {f.spread_rate:.4f} km/h   "
                  f"heading {np.rad2deg(t.heading):+.2f} -> {np.rad2deg(f.heading):+.2f} deg   "
                  f"t0 {t.ignition_time:.3f} -> {f.ignition_time:.3f} h")

    pts = scenario.grid.flat_centres()
    hz = scenario.skill_horizon
    at = arrival_time_metrics(truth.arrival_time(pts), fc.arrival_time(pts), horizon=hz)
    cat = categorical_scores(truth.arrival_time(pts) <= hz, fc.arrival_time(pts) <= hz)
    print(f"\nTraditional skill against truth (grid {scenario.grid.nx}x{scenario.grid.ny}, "
          f"horizon {hz} h):")
    print(f"  arrival-time MAE {at.mae:.4f} h   RMSE {at.rmse:.4f} h   bias {at.bias:+.4f} h"
          f"   (computed on {at.n_both}/{at.n_points} cells; coverage {at.coverage:.1%})")
    print(f"  censoring: {at.n_miss} cells burn in truth but not in the forecast, "
          f"{at.n_false} the other way")
    print(f"  CSI {cat['csi']:.4f}   POD {cat['pod']:.4f}   FAR {cat['far']:.4f}   "
          f"frequency bias {cat['frequency_bias']:.4f}")
    print("\nNone of these scores is consulted by any decision in this package.")

    if args.out:
        out = Path(args.out)
        write_json({"truth": truth.to_dict(), "release": release.to_dict(),
                    "params": full, "skill": {**at.as_dict(), **cat}},
                   out / "degrade.json")
        write_manifest(cfg, out)
        print(f"\nwrote {out/'degrade.json'} and {out/'manifest.json'}")
    return 0


def cmd_run_toy_study(args) -> int:
    cfg = load_config(args.config)
    scenario, pipe = cfg.scenario(), cfg.pipeline()
    policies = default_policies(scenario, max_wait=cfg.max_wait())
    st = cfg.stats()

    print(BANNER)
    rep = run_all_invariants(scenario, pipe, policies, seed=cfg.seed)
    print(f"\ninvariants passed: {', '.join(rep.checks)}")

    em = cfg.error_model()
    results = run_paired_study(
        scenario, n_worlds=cfg.n_worlds(), seed=cfg.seed, pipeline=pipe,
        error_model=em, fixed_params=None if em else cfg.degradation_params(),
        latency=cfg.latency(), policies=policies, loss=cfg.loss(),
    )
    df = results_to_frame(results)
    summary = summarise_study(results, cfg.loss(), n_boot=int(st["n_boot"]),
                              confidence=float(st["confidence"]),
                              equivalence_margin=float(st["equivalence_margin"]),
                              seed=cfg.seed)
    print(f"\nPaired world-level study: {cfg.name}")
    print(f"  forecast error: {'sampled from the correlated error model' if em else cfg.degradation_params()}")
    print(f"  latency: s = {cfg.latency().information_time} h, delta = {cfg.latency().latency} h; "
          f"decision at {scenario.decision_time} h; policy will wait up to {cfg.max_wait()} h")
    print()
    print(format_study_summary(summary))

    out = Path(args.out) if args.out else cfg.output_dir
    p = _save_frame(df, out / "worlds")
    write_json(summary, out / "summary.json")
    write_manifest(cfg, out, {"command": "run-toy-study"})
    print(f"\nwrote {p}, {out/'summary.json'}, {out/'manifest.json'}")
    return 0


def cmd_sweep(args) -> int:
    cfg = load_config(args.config)
    scenario, pipe = cfg.scenario(), cfg.pipeline()
    policies = default_policies(scenario, max_wait=cfg.max_wait())
    x, y = cfg.axis("x"), cfg.axis("y")
    n = int(args.n_worlds or cfg.n_worlds())

    print(BANNER)
    print(f"\nSweeping {len(y.values)} x {len(x.values)} cells x {n} worlds "
          f"= {len(y.values)*len(x.values)*n} paired evaluations")
    print(f"  x: {x.name} ({x.kind}) from {x.values[0]:.4g} to {x.values[-1]:.4g}")
    print(f"  y: {y.name} ({y.kind}) from {y.values[0]:.4g} to {y.values[-1]:.4g}")
    print("  common random numbers: the same worlds are used in every cell")

    grid = sweep_grid(scenario, x, y, n_worlds=n, seed=cfg.seed, pipeline=pipe,
                      base_latency=cfg.latency(), policies=policies, loss=cfg.loss(),
                      skill_keys=(), progress=_progress)
    out = Path(args.out) if args.out else cfg.output_dir
    p = _save_frame(grid.to_long_frame(), out / "sweep")
    write_json({"x_axis": x.to_dict(), "y_axis": y.to_dict(), "meta": grid.meta},
               out / "sweep_axes.json")
    write_manifest(cfg, out, {"command": "sweep"})
    print(f"\nwrote {p}, {out/'sweep_axes.json'}, {out/'manifest.json'}")
    print(f"then: wg-forecast-value estimate-frontier {p}")
    return 0


def _grid_from_frame(df: pd.DataFrame, axes: dict) -> FrontierGrid:
    x = SweepAxis(**{**axes["x_axis"], "values": tuple(axes["x_axis"]["values"])})
    y = SweepAxis(**{**axes["y_axis"], "values": tuple(axes["y_axis"]["values"])})
    ny, nx = len(y.values), len(x.values)
    nw = int(df["world_id"].max()) + 1
    shape = (ny, nx, nw)
    idx = (df["y_index"].to_numpy(), df["x_index"].to_numpy(), df["world_id"].to_numpy())
    def _fill(col, dtype=float):
        a = np.zeros(shape, dtype=dtype)
        a[idx] = df[col].to_numpy()
        return a
    return FrontierGrid(
        x_axis=x, y_axis=y,
        delta=_fill("delta_j"), value_fraction=_fill("value_fraction"),
        action_changed=_fill("action_changed", bool), available=_fill("forecast_available", bool),
        meta=axes.get("meta", {}),
    )


def cmd_estimate_frontier(args) -> int:
    results = Path(args.results)
    df = _read_frame(results)
    axes_path = results.parent / "sweep_axes.json"
    if not axes_path.exists():
        raise FileNotFoundError(
            f"{axes_path} not found. The sweep axes are not recoverable from the results "
            "frame alone (a grid of parameter values is not the same object as the axis "
            "that generated it), so estimate-frontier needs the file that `sweep` wrote."
        )
    axes = json.loads(axes_path.read_text(encoding="utf-8"))
    grid = _grid_from_frame(df, axes)

    st = load_config(args.config).stats() if args.config else {"frontier_boot": 400, "confidence": 0.95}
    band = bootstrap_frontier_band(grid, n_boot=int(args.n_boot or st.get("frontier_boot", 400)),
                                   confidence=float(st.get("confidence", 0.95)), seed=0)
    cols = frontier_from_grid(grid)
    mono = monotonicity_report(grid)

    print(BANNER)
    print(f"\nBreak-even frontier from {results}  ({grid.n_worlds} worlds, "
          f"{grid.shape[0]}x{grid.shape[1]} cells)")
    print(f"\n  monotonicity (measured, not assumed):")
    print(f"    columns monotone in {grid.y_axis.name}: {mono['columns_monotone']}")
    print(f"    rows monotone in {grid.x_axis.name}:    {mono['rows_monotone']}")
    print(f"    frontier is a single-valued function of {grid.x_axis.name}: "
          f"{mono['frontier_is_a_function_of_x']}")
    print(f"    columns with >1 crossing: {mono['n_columns_multi_crossing']};"
          f" with none: {mono['n_columns_no_crossing']}")
    print(f"\n  {grid.x_axis.display_label:>28s} | frontier {grid.y_axis.name} "
          f"[{band.confidence:.0%} band] | crossings | crossing rate")
    for c, lo, hi, rate, mc in zip(cols, band.lower, band.upper, band.crossing_rate,
                                   band.multi_crossing_rate):
        xv = c.x_value * grid.x_axis.display_scale
        if c.n_crossings == 0:
            side = "trigger better everywhere" if c.max_value < 0 else "forecast better everywhere"
            print(f"  {xv:28.3f} | {'none  (' + side + ')':>34s} | {c.n_crossings:9d} | "
                  f"{rate:12.2f}")
        else:
            print(f"  {xv:28.3f} | {c.first:8.3f}  [{lo:7.3f}, {hi:7.3f}]     | "
                  f"{c.n_crossings:9d} | {rate:12.2f}"
                  + ("   <- multi-valued" if mc > 0.05 else ""))
    print("\n  A 'crossing rate' below 1.00 means the frontier disappeared in some world")
    print("  resamples: the band is not the whole uncertainty there, the existence is.")

    out = Path(args.out) if args.out else results.parent
    write_json({"frontier": [c.as_dict() for c in cols], "band": band.as_dict(),
                "monotonicity": mono}, out / "frontier.json")
    print(f"\nwrote {out/'frontier.json'}")

    if not args.no_figure:
        from wildfireguardian_forecast_value.plotting.frontier_plot import plot_frontier
        fig_path = out / "frontier.png"
        plot_frontier(grid, band, path=str(fig_path))
        print(f"wrote {fig_path}")
    return 0


def cmd_cases(args) -> int:
    cfg = load_config(args.config)
    scenario, pipe = cfg.scenario(), cfg.pipeline()
    print(BANNER)
    print("\nThe four cases (deterministic, one world each):\n")
    rows = []
    for key in CASES:
        c = case_specs()[key]
        print(f"{key}: {c.title}")
        for arm in c.arms:
            sc = c.scenario(scenario)
            r = evaluate_world(sc, c.world(arm, scenario), pipe, arm.degradation_params,
                               LatencySpec(arm.information_time, arm.latency), loss=cfg.loss())
            frac = r.value_fraction
            print(f"    {arm.label:28s} baseline={r.baseline_action}  forecast={r.forecast_action}"
                  f"  dJ={r.delta_j:+8.3f}  value={'n/a' if not np.isfinite(frac) else f'{frac:5.1%}'}"
                  f"  CSI={r.skill['csi']:.3f}  RMSE={r.skill['arrival_rmse']:.3f} h"
                  f"  available={r.forecast_available}")
            rows.append((f"{key}\n{arm.label}", r.skill["csi"], frac))
        print(f"    claim: {c.claim}\n")

    ranked = sorted((r for r in rows if "perfect" not in r[0]), key=lambda t: -t[1])
    print("Ranked by footprint CSI, best first -- and the value column is close to reversed:")
    for lab, csi, frac in ranked:
        print(f"  CSI {csi:.3f}   value {'n/a' if not np.isfinite(frac) else f'{frac:5.1%}'}"
              f"   {lab.replace(chr(10), ' / ')}")

    if args.out:
        from wildfireguardian_forecast_value.plotting.skill_vs_value import plot_case_comparison
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        pretty = [(lab.replace("_", " "), csi, frac) for lab, csi, frac in rows
                  if "perfect" not in lab]
        plot_case_comparison(pretty, path=str(out / "case_comparison.png"))
        print(f"\nwrote {out/'case_comparison.png'}")
    return 0


def cmd_validate(args) -> int:
    print(BANNER)
    print("\nHand-solvable examples (independent validation):\n")
    passed, total, records = run_hand_examples(verbose=args.verbose)
    for r in records:
        print(f"  [{'PASS' if r['passed'] else 'FAIL'}] {r['key']}: {r['title']}")
        if args.verbose:
            for line in r["derivation"].splitlines():
                print(f"          {line}")
            print(f"          -> expected {np.round(r['expected'], 6).tolist()}")
            print(f"          -> got      {np.round(r['got'], 6).tolist()}\n")
        elif not r["passed"]:
            print(f"          expected {r['expected']}\n          got      {r['got']}")
    print(f"\n  {passed}/{total} hand-solvable examples passed")

    cfg = load_config(args.config)
    scenario, pipe = cfg.scenario(), cfg.pipeline()
    rep = run_all_invariants(scenario, pipe, default_policies(scenario, max_wait=cfg.max_wait()),
                             seed=cfg.seed)
    print(f"  structural invariants passed: {', '.join(rep.checks)}")
    return 0 if passed == total else 1


def cmd_demo(args) -> int:
    cfg = load_config(args.config)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fig_dir = Path(args.figures) if args.figures else out
    fig_dir.mkdir(parents=True, exist_ok=True)

    from wildfireguardian_forecast_value.plotting.frontier_plot import (
        plot_frontier,
        plot_scenario_map,
    )
    from wildfireguardian_forecast_value.plotting.skill_vs_value import (
        plot_case_comparison,
        plot_skill_value_scatter,
    )

    scenario, pipe = cfg.scenario(), cfg.pipeline()
    policies = default_policies(scenario, max_wait=cfg.max_wait())
    print(BANNER)

    # 1. geometry
    world = scenario.sample_world(3, 5)
    plot_scenario_map(scenario, world, path=str(fig_dir / "scenario_map.png"))
    print(f"  wrote {fig_dir/'scenario_map.png'}")

    # 2. the four cases
    rows = []
    for key in CASES:
        c = case_specs()[key]
        for arm in c.arms:
            if arm.label == "perfect":
                continue
            r = evaluate_world(c.scenario(scenario), c.world(arm, scenario), pipe,
                               arm.degradation_params,
                               LatencySpec(arm.information_time, arm.latency), loss=cfg.loss())
            rows.append((f"{key.replace('_', ' ')}\n{arm.label.replace('_', ' ')}",
                         r.skill["csi"], r.value_fraction))
    plot_case_comparison(rows, path=str(fig_dir / "case_comparison.png"))
    print(f"  wrote {fig_dir/'case_comparison.png'}")

    # 3. skill-vs-value over a direction-error sweep
    thetas = np.deg2rad(np.linspace(-30, 30, 25))
    skill, dj = [], []
    for th in thetas:
        rs = run_paired_study(scenario, n_worlds=args.n_worlds // 2, seed=cfg.seed,
                              pipeline=pipe, fixed_params={"eps_theta": float(th)},
                              latency=cfg.latency(), policies=policies, loss=cfg.loss())
        skill.append(float(np.mean([r.skill["csi"] for r in rs])))
        dj.append(float(np.mean([r.delta_j for r in rs])))
    # Annotate the closest-matched pair of settings whose decision values have
    # opposite signs: the same prediction score, opposite advice.
    sk, dv = np.asarray(skill), np.asarray(dj)
    pos = np.where(dv > 0)[0]
    neg = np.where(dv < 0)[0]
    ann = []
    if pos.size and neg.size:
        gap = np.abs(sk[pos][:, None] - sk[neg][None, :])
        i, j = np.unravel_index(int(np.argmin(gap)), gap.shape)
        a, b = int(pos[i]), int(neg[j])
        ann = [
            (sk[a], dv[a], f"{np.rad2deg(thetas[a]):+.0f}\u00b0 heading error\n"
                           f"CSI {sk[a]:.2f}, $\\Delta J$ {dv[a]:+.1f} h"),
            (sk[b], dv[b], f"{np.rad2deg(thetas[b]):+.0f}\u00b0 heading error\n"
                           f"CSI {sk[b]:.2f}, $\\Delta J$ {dv[b]:+.1f} h"),
        ]
    plot_skill_value_scatter(sk, dv, annotations=ann,
                             path=str(fig_dir / "skill_vs_value.png"))
    print(f"  wrote {fig_dir/'skill_vs_value.png'}")

    # 4. the frontier
    x, y = cfg.axis("x"), cfg.axis("y")
    grid = sweep_grid(scenario, x, y, n_worlds=args.n_worlds, seed=cfg.seed, pipeline=pipe,
                      base_latency=cfg.latency(), policies=policies, loss=cfg.loss(),
                      skill_keys=(), progress=_progress)
    band = bootstrap_frontier_band(grid, n_boot=int(cfg.stats()["frontier_boot"]),
                                   confidence=float(cfg.stats()["confidence"]), seed=0)
    plot_frontier(grid, band, path=str(fig_dir / "frontier_direction_latency.png"))
    print(f"  wrote {fig_dir/'frontier_direction_latency.png'}")

    p = _save_frame(grid.to_long_frame(), out / "sweep")
    write_json({"x_axis": x.to_dict(), "y_axis": y.to_dict(), "meta": grid.meta},
               out / "sweep_axes.json")
    write_json({"frontier": [c.as_dict() for c in frontier_from_grid(grid)],
                "band": band.as_dict(), "monotonicity": monotonicity_report(grid)},
               out / "frontier.json")
    write_manifest(cfg, out, {"command": "demo", "n_worlds": args.n_worlds})
    print(f"  wrote {p}, {out/'frontier.json'}, {out/'manifest.json'}")
    return 0


# ------------------------------------------------------------------ parser --
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wg-forecast-value",
        description="How good must a wildfire forecast be before it deserves to change a "
                    "protective decision? (synthetic fixtures only)",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("degrade", help="apply a degradation pipeline and report what it did")
    d.add_argument("config", nargs="?", default=None)
    d.add_argument("--out", default=None)
    d.set_defaults(func=cmd_degrade)

    s = sub.add_parser("run-toy-study", help="paired world-level comparison at one setting")
    s.add_argument("config", nargs="?", default=None)
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_run_toy_study)

    w = sub.add_parser("sweep", help="2-D decision-value sweep; writes a tidy results frame")
    w.add_argument("config", nargs="?", default=None)
    w.add_argument("--out", default=None)
    w.add_argument("--n-worlds", type=int, default=None)
    w.set_defaults(func=cmd_sweep)

    f = sub.add_parser("estimate-frontier", help="estimate the break-even frontier from a sweep")
    f.add_argument("results")
    f.add_argument("--config", default=None)
    f.add_argument("--out", default=None)
    f.add_argument("--n-boot", type=int, default=None)
    f.add_argument("--no-figure", action="store_true")
    f.set_defaults(func=cmd_estimate_frontier)

    c = sub.add_parser("cases", help="run the four hand-designed cases")
    c.add_argument("config", nargs="?", default=None)
    c.add_argument("--out", default=None)
    c.set_defaults(func=cmd_cases)

    v = sub.add_parser("validate", help="hand-solvable examples and structural invariants")
    v.add_argument("config", nargs="?", default=None)
    v.add_argument("-v", "--verbose", action="store_true", help="print every derivation")
    v.set_defaults(func=cmd_validate)

    m = sub.add_parser("demo", help="produce every figure and result in one go")
    m.add_argument("config", nargs="?", default=None)
    m.add_argument("--out", default="experiments/runs/demo")
    m.add_argument("--figures", default="figures")
    m.add_argument("--n-worlds", type=int, default=100)
    m.set_defaults(func=cmd_demo)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
