"""
Simulated weather updates for dynamic-rerouting experiments.

Weather changes are applied to an existing Weather field (see weather.py)
as smooth local changes in significant wave height - a storm (delta > 0)
or a calm patch (delta < 0). Everything is deterministic: the same inputs
always give the same field, so voyage simulations are reproducible.

A scenario is the departure weather plus a schedule {step: Weather} of
updates, both consumed by rerouting.simulate().

Interactive sessions (sim_session.py) describe weather as a list of
disturbances {lat, lon, radius_km, delta_m} on top of an unchanged base
field (apply_disturbances); PRESETS are deterministic disturbance
schedules for demonstrations. Only significant wave height is changed -
wave period and direction stay as in the base field.
"""
import numpy as np

import config as C
from src.weather import Weather


def perturb_waves(weather, grid, center_latlon, radius_km, delta_m):
    """New Weather with swh changed by a Gaussian bump of `delta_m` metres
    (peak, at `center_latlon`) and width `radius_km` (1 sigma). Wave
    period and direction are left unchanged."""
    bump = _bump(grid, center_latlon, radius_km, delta_m)
    swh = np.clip(weather.swh + bump, 0.0, None).astype(np.float32)
    return Weather(swh, weather.mwp, weather.mwd_cos, weather.mwd_sin)


def _bump(grid, center_latlon, radius_km, delta_m):
    lat0, lon0 = center_latlon
    dy = (grid.lats[:, None] - lat0) * C.KM_PER_DEG
    dx = (grid.lons[None, :] - lon0) * C.KM_PER_DEG * np.cos(np.deg2rad(lat0))
    return delta_m * np.exp(-(dx ** 2 + dy ** 2) / (2.0 * radius_km ** 2))


def apply_disturbances(base, grid, disturbances):
    """New Weather = base swh + the sum of each disturbance's Gaussian bump
    (dicts with lat, lon, radius_km [1 sigma], delta_m [peak]), clipped at
    0. `base` is not modified; with no disturbances the result equals it."""
    total = None
    for d in disturbances:
        b = _bump(grid, (d["lat"], d["lon"]), d["radius_km"], d["delta_m"])
        total = b if total is None else total + b
    if total is None:
        swh = base.swh.copy()
    else:
        swh = np.clip(base.swh + total, 0.0, None).astype(np.float32)
    return Weather(swh, base.mwp, base.mwd_cos, base.mwd_sin)


def peak_change(base, updated, grid):
    """(lat, lon, delta_m) of the largest wave-height increase from `base`
    to `updated` (or the largest decrease if waves only dropped) - a simple
    way to show where a simulated update happened."""
    diff = updated.swh - base.swh
    flat = int(np.argmax(diff)) if diff.max() > 0.05 else int(np.argmin(diff))
    r, c = np.unravel_index(flat, diff.shape)
    return float(grid.lats[r]), float(grid.lons[c]), float(diff[r, c])


def _point_on(route, frac):
    """(lat, lon) of the cell `frac` of the way along a route."""
    return route.latlon[int((len(route.cells) - 1) * frac)]


def scenario(name, grid, base, route):
    """(departure Weather, {step: Weather} updates) for a named scenario.

    `route` is the route planned under `base`; storms are placed on it so
    the scenarios work for any voyage. Steps are simulation steps (see
    rerouting.RerouteConfig.cells_per_step).

      stable         : no change at all
      adverse        : a severe storm appears on the route ahead (step 2)
      worsening      : a storm on the route ahead intensifies (steps 2, 4, 6)
      improving_alt  : a storm on the direct path at departure (so the
                       initial route detours) clears at step 2, making
                       the direct alternative cheaper
      minor          : a weak, small disturbance on the route (step 2)
      shifting       : a severe storm moves every step (steps 1-12),
                       cycling between the route and lanes 1.5 deg either
                       side of it - provokes repeated rerouting
    """
    ahead = _point_on(route, 0.5)
    if name == "stable":
        return base, {}
    if name == "adverse":
        return base, {2: perturb_waves(base, grid, ahead, 120.0, 6.0)}
    if name == "worsening":
        return base, {s: perturb_waves(base, grid, ahead, 120.0, d)
                      for s, d in ((2, 1.5), (4, 3.5), (6, 6.0))}
    if name == "improving_alt":
        return perturb_waves(base, grid, ahead, 250.0, 6.0), {2: base}
    if name == "minor":
        return base, {2: perturb_waves(base, grid, ahead, 25.0, 0.4)}
    if name == "shifting":
        lat, lon = _point_on(route, 0.45)
        storms = [perturb_waves(base, grid, (lat + d, lon + d), 200.0, 6.0)
                  for d in (1.5, 0.0, -1.5)]
        return base, {s: storms[s % 3] for s in range(1, 13)}
    raise ValueError(f"unknown weather scenario {name!r}")


SCENARIOS = ("stable", "adverse", "worsening", "improving_alt", "minor",
             "shifting")


# ----------------------------------------------------------------------
# Demonstration presets for interactive sessions: {step: [disturbance]}
# A step's list replaces the preset's own disturbances from that step on
# (manual disturbances are kept). Step 0 = weather at departure.
# ----------------------------------------------------------------------
def _storm(route, frac, radius_km, delta_m):
    lat, lon = _point_on(route, frac)
    return {"lat": float(lat), "lon": float(lon),
            "radius_km": float(radius_km), "delta_m": float(delta_m)}


def preset(name, route):
    """Disturbance schedule for a named preset, placed relative to `route`
    (the route planned under the base weather). Parameters match the
    evaluated scenarios where named the same (see PRESETS)."""
    if name == "none":
        return {}
    if name == "storm_ahead":                  # = scenario "adverse"
        return {2: [_storm(route, 0.5, 120.0, 6.0)]}
    if name == "worsening":                    # = scenario "worsening"
        return {s: [_storm(route, 0.5, 120.0, d)]
                for s, d in ((2, 1.5), (4, 3.5), (6, 6.0))}
    if name == "storm_over_route":             # broad storm across the route
        return {1: [_storm(route, 0.4, 300.0, 4.0)]}
    if name == "moving_storm":                 # = scenario "shifting"
        lat, lon = _point_on(route, 0.45)
        lanes = [{"lat": float(lat + d), "lon": float(lon + d),
                  "radius_km": 200.0, "delta_m": 6.0} for d in (1.5, 0.0, -1.5)]
        return {s: [lanes[s % 3]] for s in range(1, 13)}
    if name == "storm_clears":                 # = scenario "improving_alt"
        return {0: [_storm(route, 0.5, 250.0, 6.0)], 2: []}
    if name == "minor":                        # = scenario "minor"
        return {2: [_storm(route, 0.5, 25.0, 0.4)]}
    if name == "no_useful_alternative":        # whole basin rougher
        return {2: [_storm(route, 0.5, 2500.0, 2.0)]}
    raise ValueError(f"unknown preset {name!r}")


PRESETS = {
    "none": "No preset weather (stable; add your own disturbances)",
    "storm_ahead": "Severe storm appears on the route ahead (step 2)",
    "storm_over_route": "Broad storm covers a long stretch of the route (step 1)",
    "worsening": "Storm ahead intensifies (steps 2, 4, 6)",
    "moving_storm": "Storm moves every step (steps 1-12; tests cooldown)",
    "storm_clears": "Storm blocking the direct path at departure clears (step 2)",
    "minor": "Small, weak disturbance - should not justify rerouting (step 2)",
    "no_useful_alternative": "Whole basin gets rougher - no route avoids it (step 2)",
}
