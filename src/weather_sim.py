"""
Simulated weather updates for dynamic-rerouting experiments.

Weather changes are applied to an existing Weather field (see weather.py)
as smooth local changes in significant wave height - a storm (delta > 0)
or a calm patch (delta < 0). Everything is deterministic: the same inputs
always give the same field, so voyage simulations are reproducible.

A scenario is the departure weather plus a schedule {step: Weather} of
updates, both consumed by rerouting.simulate().
"""
import numpy as np

import config as C
from src.weather import Weather


def perturb_waves(weather, grid, center_latlon, radius_km, delta_m):
    """New Weather with swh changed by a Gaussian bump of `delta_m` metres
    (peak, at `center_latlon`) and width `radius_km` (1 sigma). Wave
    period and direction are left unchanged."""
    lat0, lon0 = center_latlon
    dy = (grid.lats[:, None] - lat0) * C.KM_PER_DEG
    dx = (grid.lons[None, :] - lon0) * C.KM_PER_DEG * np.cos(np.deg2rad(lat0))
    bump = delta_m * np.exp(-(dx ** 2 + dy ** 2) / (2.0 * radius_km ** 2))
    swh = np.clip(weather.swh + bump, 0.0, None).astype(np.float32)
    return Weather(swh, weather.mwp, weather.mwd_cos, weather.mwd_sin)


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
