"""
Dynamic-rerouting evaluation across voyages, vessels and weather scenarios.

For every (voyage, vessel, scenario) in the matrix, rerouting.compare_voyage
runs the same voyage twice - rerouting enabled and disabled - from the same
departure weather, initial route and weather-update schedule. Only the
controller differs. Each pair becomes one row of runs.csv.

Matrix: the 5 voyages of evaluate.VOYAGES x all 5 vessel profiles x all 6
weather_sim scenarios, on the "typical" base weather, default
RerouteConfig, A* with the ML speed cost model. Every combination is run and
classified (status):

  ok                - both voyages arrived and stayed in water at least
                      as deep as the vessel's draft
  draft_infeasible  - a sailed track crosses water shallower than the
                      vessel's draft (the navigable grid only enforces
                      config.MIN_DEPTH_M = 10 m); metrics kept, but the
                      run is excluded from aggregate means
  incomplete        - a voyage did not reach the destination
  failed            - the simulation raised an error

Outcome of an ok run (rerouting vs. no rerouting, simulated hours):
improved if delta <= -OUTCOME_TOL_H, worsened if >= +OUTCOME_TOL_H,
otherwise unchanged.

All figures are model estimates (synthetic weather changes, ML speed model
trained on synthetic data), not real-world performance.

Outputs (data/rerouting_eval/): runs.csv, events.csv,
summary_overall.csv, summary_by_voyage.csv, summary_by_vessel.csv,
summary_by_scenario.csv, config.json, rel_change_vessel_scenario.png.

Run:  python -m src.evaluate_rerouting
"""
import json
import math
import subprocess
import time
import warnings
from collections import Counter
from dataclasses import asdict

import numpy as np
import pandas as pd

import config as C
from src import (grid as G, weather as W, ports as P, vessel as V,
                 ml_model as ML, rerouting as RR, weather_sim as WS,
                 evaluate as E)

BASE_WEATHER = "typical"
SCENARIOS = WS.SCENARIOS
OUTCOME_TOL_H = 0.1          # |delta| below this (h) = no material change
OUT_DIR = C.ROOT / "data" / "rerouting_eval"
TIMING_COLUMNS = ("wall_s",)
DECISIONS = ("adopted", "retained", "failed", "cooldown", "unchanged",
             "no_trigger")


# ----------------------------------------------------------------------
# Matrix and per-run metrics
# ----------------------------------------------------------------------
def build_matrix(voyages=None, vessels=None, scenarios=None):
    """Every (voyage, vessel, scenario) combination, in a fixed order."""
    voyages = list(voyages or E.VOYAGES)
    vessels = list(vessels or V.VESSELS)
    scenarios = list(scenarios or SCENARIOS)
    return [{"voyage": f"{o} -> {d}", "origin": o, "dest": d,
             "vessel": v, "scenario": s}
            for o, d in voyages for v in vessels for s in scenarios]


def relative_change(new, base):
    """(new - base) / base, or None if either value is missing or not
    finite, or base <= 0 (no meaningful relative change)."""
    if new is None or base is None:
        return None
    if not (math.isfinite(new) and math.isfinite(base)) or base <= 0:
        return None
    return (new - base) / base


def classify_outcome(delta_h, tol=OUTCOME_TOL_H):
    if delta_h is None or not math.isfinite(delta_h):
        return None
    if delta_h <= -tol:
        return "improved"
    if delta_h >= tol:
        return "worsened"
    return "unchanged"


def min_depth_m(grid, cells):
    """Shallowest water depth (m, positive) along a list of cells."""
    return float(-max(grid.elevation[r, c] for r, c in cells))


def run_status(dynamic, static, draft_m, grid):
    """(status, min depth of the dynamic track, of the static track)."""
    dep_dyn = min_depth_m(grid, dynamic.track)
    dep_sta = min_depth_m(grid, static.track)
    if not (dynamic.arrived and static.arrived):
        return "incomplete", dep_dyn, dep_sta
    if min(dep_dyn, dep_sta) < draft_m:
        return "draft_infeasible", dep_dyn, dep_sta
    return "ok", dep_dyn, dep_sta


def pair_record(spec, cmp, vessel, cfg, grid, wall_s):
    """One runs.csv row from a VoyageComparison."""
    dyn, sta = cmp.dynamic, cmp.static
    status, dep_dyn, dep_sta = run_status(dyn, sta, vessel.draft_m, grid)
    decisions = Counter(e.decision for e in dyn.events)
    delta_h = dyn.sailed_hours - sta.sailed_hours
    rec = {
        **spec,
        "service_speed_kn": vessel.service_speed_kn,
        "draft_m": vessel.draft_m,
        "base_weather": BASE_WEATHER,
        "algorithm": cfg.algorithm,
        "cost_model": "ml_speed",
        "config": json.dumps(asdict(cfg), sort_keys=True),
        "weather_update_steps": " ".join(str(s) for s in sorted(cmp.updates)),
        "status": status,
        # paired voyage metrics
        "static_hours": sta.sailed_hours, "dynamic_hours": dyn.sailed_hours,
        "delta_hours": delta_h,
        "rel_change": relative_change(dyn.sailed_hours, sta.sailed_hours),
        "outcome": classify_outcome(delta_h),
        "static_km": sta.sailed_km, "dynamic_km": dyn.sailed_km,
        "delta_km": dyn.sailed_km - sta.sailed_km,
        "static_cost": sta.sailed_cost, "dynamic_cost": dyn.sailed_cost,
        "static_steps": sta.steps, "dynamic_steps": dyn.steps,
        "static_arrived": sta.arrived, "dynamic_arrived": dyn.arrived,
        "min_depth_static_m": dep_sta, "min_depth_dynamic_m": dep_dyn,
        # route plan vs. final active route (dynamic run)
        "initial_route_km": dyn.initial_route.distance_km,
        "initial_route_hours": dyn.initial_route.time_hours,
        "initial_route_cost": dyn.initial_route.cost,
        "final_route_km": dyn.active_route.distance_km,
        "final_route_cost": dyn.active_route.cost,
        # controller behaviour
        "evaluations": len(dyn.events),
        "triggered": sum(1 for e in dyn.events if e.triggers),
        "reroutes": decisions["adopted"],
        **{f"n_{d}": decisions[d] for d in DECISIONS if d != "adopted"},
        "reroute_steps": " ".join(str(e.step) for e in dyn.reroutes),
        "wall_s": wall_s,
    }
    rec["error"] = ""
    return rec


def failed_record(spec, vessel, cfg, error):
    return {**spec, "service_speed_kn": vessel.service_speed_kn,
            "draft_m": vessel.draft_m, "base_weather": BASE_WEATHER,
            "algorithm": cfg.algorithm, "cost_model": "ml_speed",
            "config": json.dumps(asdict(cfg), sort_keys=True),
            "status": "failed", "error": f"{type(error).__name__}: {error}"}


def event_records(run_id, cmp):
    """Rerouting evaluations that reached a trigger (dynamic run)."""
    return [{"run_id": run_id, "step": e.step, "decision": e.decision,
             "reason": e.reason, "triggers": "; ".join(e.triggers),
             "remaining_hours": e.remaining_hours,
             "alternative_hours": e.alternative_hours,
             "gain_pct": None if e.gain_rel is None else 100 * e.gain_rel}
            for e in cmp.dynamic.events if e.decision != "no_trigger"]


def run_matrix(specs, grid, base, factories, config=None, progress=None):
    """Run every spec; returns (runs DataFrame, events DataFrame).

    factories: {vessel name: weather -> Router}. Errors are recorded as
    status "failed", never dropped."""
    cfg = config or RR.RerouteConfig()
    runs, events = [], []
    for i, spec in enumerate(specs):
        vessel = V.get(spec["vessel"])
        start = grid.nearest_cell(*P.coord(spec["origin"]))
        goal = grid.nearest_cell(*P.coord(spec["dest"]))
        t0 = time.perf_counter()
        try:
            cmp = RR.compare_voyage(grid, start, goal, base,
                                    factories[spec["vessel"]],
                                    spec["scenario"], cfg)
        except Exception as e:                 # recorded, not hidden
            rec = failed_record(spec, vessel, cfg, e)
        else:
            rec = pair_record(spec, cmp, vessel, cfg, grid,
                              time.perf_counter() - t0)
            events += event_records(i, cmp)
        rec["run_id"] = i
        runs.append(rec)
        if progress:
            progress(i, len(specs), rec)
    return pd.DataFrame(runs), pd.DataFrame(events)


# ----------------------------------------------------------------------
# Summaries
# ----------------------------------------------------------------------
def _summary(g):
    ok = g[g.status == "ok"]
    rel = ok.rel_change.dropna() * 100
    return pd.Series({
        "runs": len(g),
        "ok": len(ok),
        "draft_infeasible": int((g.status == "draft_infeasible").sum()),
        "incomplete": int((g.status == "incomplete").sum()),
        "failed": int((g.status == "failed").sum()),
        "improved": int((ok.outcome == "improved").sum()),
        "unchanged": int((ok.outcome == "unchanged").sum()),
        "worsened": int((ok.outcome == "worsened").sum()),
        "reroutes": int(ok.reroutes.sum()),
        "runs_with_reroute": int((ok.reroutes > 0).sum()),
        "reroute_runs_not_improved": int(((ok.reroutes > 0)
                                          & (ok.outcome != "improved")).sum()),
        "mean_static_hours": ok.static_hours.mean(),
        "mean_dynamic_hours": ok.dynamic_hours.mean(),
        "mean_delta_hours": ok.delta_hours.mean(),
        "mean_rel_change_pct": rel.mean(),
        "median_rel_change_pct": rel.median(),
        "best_rel_change_pct": rel.min(),
        "worst_rel_change_pct": rel.max(),
        "mean_delta_km": ok.delta_km.mean(),
        "retained": int(ok.n_retained.sum()),
        "failed_searches": int(ok.n_failed.sum()),
        "cooldown_blocks": int(ok.n_cooldown.sum()),
    })


def summarize(runs, by=None):
    """Aggregate statistics over status-ok runs (other statuses counted).
    by=None -> one overall row."""
    if by is None:
        return _summary(runs).to_frame().T.assign(group="all").set_index("group")
    return runs.groupby(by, sort=False).apply(_summary, include_groups=False)


# ----------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------
def _git_commit():
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=C.ROOT,
                             capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "src",
                                "config.py"], cwd=C.ROOT, capture_output=True,
                               text=True).stdout.strip()
        return (sha + ("+uncommitted" if dirty else "")) or "unknown"
    except OSError:
        return "unknown"


def write_outputs(runs, events, out_dir=OUT_DIR, cfg=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    runs.to_csv(out_dir / "runs.csv", index=False)
    events.to_csv(out_dir / "events.csv", index=False)
    summarize(runs).to_csv(out_dir / "summary_overall.csv")
    for by in ("voyage", "vessel", "scenario"):
        summarize(runs, by).to_csv(out_dir / f"summary_by_{by}.csv")
    meta = {"code_version": _git_commit(),
            "base_weather": BASE_WEATHER,
            "scenarios": list(SCENARIOS),
            "voyages": [f"{o} -> {d}" for o, d in E.VOYAGES],
            "vessels": list(V.VESSELS),
            "reroute_config": asdict(cfg or RR.RerouteConfig()),
            "cost_model": "A* with ML speed multiplier; travel time from the "
                          "same ML speed model (Source of Truth 10.1)",
            "outcome_tolerance_hours": OUTCOME_TOL_H,
            "draft_check": "min water depth on both sailed tracks >= draft",
            "non_deterministic_columns": list(TIMING_COLUMNS)}
    (out_dir / "config.json").write_text(json.dumps(meta, indent=2) + "\n")
    _plot(runs, out_dir / "rel_change_vessel_scenario.png")


def _plot(runs, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ok = runs[runs.status == "ok"]
    order = [s for s in SCENARIOS if s in set(ok.scenario)]
    table = (ok.pivot_table(index="vessel", columns="scenario",
                            values="rel_change", aggfunc="mean") * 100)[order]
    worse = (ok.assign(w=ok.outcome == "worsened")
             .pivot_table(index="vessel", columns="scenario", values="w",
                          aggfunc="sum")[order].reindex(table.index))
    runs_n = (ok.pivot_table(index="vessel", columns="scenario", values="run_id",
                             aggfunc="count")[order].reindex(table.index))
    lim = max(1.0, float(np.nanmax(np.abs(table.values))))
    fig, ax = plt.subplots(figsize=(10, 4.6))
    im = ax.imshow(table.values, cmap="RdBu_r", vmin=-lim, vmax=lim)
    ax.set_xticks(range(len(order)), order, rotation=20, ha="right")
    ax.set_yticks(range(len(table.index)), table.index)
    for (r, c), v in np.ndenumerate(table.values):
        if np.isfinite(v):
            label = f"{v:+.1f}%\nn={int(runs_n.values[r, c])}"
            if worse.values[r, c]:
                label += f", {int(worse.values[r, c])} worse"
            ax.text(c, r, label, ha="center", va="center", fontsize=7.5)
    ax.set_title("Mean simulated travel-time change, rerouting vs. no rerouting "
                 "(negative = faster)\nstatus-ok runs only; n = voyages per cell "
                 "(draft-infeasible runs excluded); model estimates", fontsize=9)
    fig.colorbar(im, ax=ax, label="%")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def cached_base_factories(grid, base, model):
    """{vessel: weather -> Router}; the base-weather router of each vessel
    is built once and shared by all its voyages and scenarios."""
    out = {}
    for name, ves in V.VESSELS.items():
        make = RR.router_factory(grid, ves, model)
        base_router = make(base)
        out[name] = (lambda w, m=make, br=base_router:
                     br if w is base else m(w))
    return out


def main():
    grid = G.load_grid()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # sklearn pickle version skew
        model = ML.load()
    base = W.load_weather(grid, BASE_WEATHER)
    specs = build_matrix()
    factories = cached_base_factories(grid, base, model)
    cfg = RR.RerouteConfig()

    def progress(i, n, rec):
        tail = (f"{rec['outcome'] or '-':9} reroutes={rec['reroutes']} "
                f"delta={rec['delta_hours']:+.1f} h") if rec["status"] != "failed" \
            else rec["error"]
        print(f"[{i + 1:>3}/{n}] {rec['voyage'][:34]:34} {rec['vessel'][:14]:14} "
              f"{rec['scenario']:13} {rec['status']:16} {tail}", flush=True)

    t0 = time.perf_counter()
    runs, events = run_matrix(specs, grid, base, factories, cfg, progress)
    write_outputs(runs, events, cfg=cfg)
    print(f"\nRan {len(runs)} paired runs in {time.perf_counter() - t0:.0f} s; "
          f"status counts: {dict(Counter(runs.status))}")
    with pd.option_context("display.width", 200, "display.max_columns", 30,
                           "display.float_format", "{:.2f}".format):
        print("\nOverall (status ok):\n", summarize(runs).T)
        for by in ("scenario", "vessel", "voyage"):
            print(f"\nBy {by}:\n", summarize(runs, by)[[
                "ok", "improved", "unchanged", "worsened", "reroutes",
                "mean_delta_hours", "mean_rel_change_pct",
                "worst_rel_change_pct", "cooldown_blocks"]])
    print(f"\nWrote {OUT_DIR.relative_to(C.ROOT)}/ - simulated, model-based "
          "results, not real-world performance.")


if __name__ == "__main__":
    main()
