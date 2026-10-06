"""
Routing engine on the navigable grid (8-connected / king moves).

  * dijkstra : shortest SAFE route by pure great-circle distance (baseline)
  * astar    : weather-aware optimal route (distance x wave-cost), with an
               admissible great-circle heuristic so it stays optimal.

Any navigable (row, col) can be the start, so re-routing from a vessel's
current position mid-voyage is just search(route.cells[i], route.cells[-1]).
RouteResult.cost / Router.path_cost give the search objective so a new
route and the remaining part of the active one can be compared fairly.

Metrics of a route (all from the same cell path):
  * distance_km : great-circle length of the path, km.
  * cost        : the search objective - km (Dijkstra), km x analytic wave
                  multiplier (a weighted penalty, NOT time), or km x ML
                  multiplier (service speed / predicted speed). Only the
                  ML cost is proportional to time: cost / (service kn x
                  1.852) = hours. Compare costs only from the same Router.
  * time_hours  : estimated travel time from the Router's time model,
                  independent of which objective chose the path:
                    "ml_speed"   - sum of segment km / ML-predicted speed
                                   (time_mult = service / predicted speed)
                    "calm_water" - km / speed_kn (no weather effect)
                  It is an en-route estimate, not a real-world arrival time.

Safety constraints (hard) and preferences (soft), per Router:
  * grid.navigable  : depth >= MIN_DEPTH_M and >= COAST_BUFFER_KM from land
                      or shallower water (coastal clearance).
  * min_depth_m     : vessel-specific depth (vessel.required_depth_m); cells
                      shallower are impassable. An endpoint or route that
                      cannot meet it gives found=False with a `reason`.
  * coast_penalty   : optional soft cost near the clearance edge
                      (config.COAST_PENALTY / COAST_SOFT_KM); changes route
                      choice and cost, never travel time.

Speed: a Router precomputes per-row step distances and per-cell weather
multipliers once, so the search hot loop is just array look-ups. Both
algorithms then finish in a fraction of a second on a laptop.
"""
import heapq
from dataclasses import dataclass, field

import numpy as np

import config as C
from src import geo

# 8-neighbour offsets (row, col)
_OFF = [(-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1)]


@dataclass
class RouteResult:
    algorithm: str
    found: bool
    cells: list = field(default_factory=list)      # [(row, col), ...]
    latlon: list = field(default_factory=list)     # [(lat, lon), ...]
    distance_km: float = 0.0
    time_hours: float = 0.0
    max_wave_m: float = 0.0
    mean_wave_m: float = 0.0
    expanded: int = 0                               # cells explored (cost proxy)
    cost: float = 0.0                               # accumulated search cost
                                                    # (km x weather multiplier)
    time_basis: str = ""                            # "ml_speed" | "calm_water"
    reason: str = ""                                # why found=False


class Router:
    """Holds the grid + precomputed costs and runs the searches."""

    def __init__(self, grid, weather=None, mult_dir=None, speed_kn=None,
                 time_mult=None, min_depth_m=None, coast_penalty=None):
        """mult_dir (nlat,nlon,8), if given, overrides the analytic weather
        multiplier - used to plug in the ML speed-based cost.

        Travel-time model (does not affect route search):
          speed_kn  : vessel calm-water service speed (default
                      config.SHIP_SPEED_KN).
          time_mult : (nlat,nlon,8) service speed / predicted speed per move,
                      i.e. ml_model.build_multiplier_grid for the same
                      vessel. None -> calm-water time at speed_kn.

        Constraints: min_depth_m (vessel-specific minimum water depth, m);
        coast_penalty (soft cost near the coastal clearance edge; default
        0 = off - application code passes config.COAST_PENALTY)."""
        self.speed_kn = float(speed_kn or C.SHIP_SPEED_KN)
        self.time_mult = time_mult
        self.grid = grid
        self.weather = weather
        self.nlat, self.nlon = grid.nlat, grid.nlon
        self.base_nav = grid.navigable.ravel()
        self.min_depth_m = float(min_depth_m) if min_depth_m else None
        if self.min_depth_m:
            self.nav = self.base_nav & (-grid.elevation.ravel() >= self.min_depth_m)
        else:
            self.nav = self.base_nav
        self.coast_penalty = float(coast_penalty or 0.0)     # explicit opt-in
        self.cell_pen = None
        if self.coast_penalty and grid.dist_to_barrier_km is not None:
            span = max(1e-6, C.COAST_SOFT_KM - C.COAST_BUFFER_KM)
            near = np.clip((C.COAST_SOFT_KM - grid.dist_to_barrier_km) / span, 0.0, 1.0)
            self.cell_pen = (1.0 + self.coast_penalty * near).ravel()
        self.lats = grid.lats
        self.lons = grid.lons
        self._coslat0 = float(np.cos(np.deg2rad(grid.lats.mean())))

        # Per-row, per-direction step distance (km). Depends only on the
        # latitude of the FROM row and the (dr, dc) offset, not on longitude.
        res = C.GRID_RES
        self.dist_dir = np.zeros((self.nlat, 8), dtype=np.float64)
        self.head_dir = np.zeros((self.nlat, 8), dtype=np.float64)
        for r in range(self.nlat):
            la = grid.lats[r]
            for k, (dr, dc) in enumerate(_OFF):
                r2 = min(max(r + dr, 0), self.nlat - 1)
                la2 = grid.lats[r2] if r2 != r else la + dr * res
                self.dist_dir[r, k] = geo.haversine_km(la, 0.0, la2, dc * res)
                self.head_dir[r, k] = geo.bearing_deg(la, 0.0, la2, dc * res)

        # Per-cell, per-direction weather multiplier.
        #   * mult_dir passed in  -> ML speed-based cost (preferred)
        #   * else weather given  -> analytic wave multiplier
        if mult_dir is not None:
            self.mult_dir = mult_dir
        elif weather is not None:
            self.mult_dir = self._build_multipliers(weather)
        else:
            self.mult_dir = None

    def _build_multipliers(self, w):
        wave_from = w.mwd_deg()                     # (nlat, nlon)
        period_pen = np.clip((8.0 - w.mwp) / 8.0, 0.0, None)
        base = 1.0 + C.W_WAVE_HEIGHT * w.swh + C.W_PERIOD * period_pen
        mult = np.empty((self.nlat, self.nlon, 8), dtype=np.float32)
        for k in range(8):
            theta = np.deg2rad(self.head_dir[:, k][:, None] - wave_from)
            head_factor = (1.0 + np.cos(theta)) / 2.0
            m = base + C.W_HEAD_SEAS * w.swh * head_factor
            mult[:, :, k] = np.clip(m, 1.0, C.MAX_WEATHER_MULT)
        return mult

    # -- heuristic ------------------------------------------------------
    def _heuristic(self, r, c, glat, glon):
        # Fast equirectangular distance, scaled <1 so it never overestimates
        # the true great-circle remaining cost (keeps A* optimal).
        dlat = (self.lats[r] - glat) * C.KM_PER_DEG
        dlon = (self.lons[c] - glon) * C.KM_PER_DEG * self._coslat0
        return 0.999 * np.hypot(dlat, dlon)

    # -- validation -----------------------------------------------------
    def _check_cell(self, cell, what):
        r, c = cell
        if not (0 <= r < self.nlat and 0 <= c < self.nlon):
            raise ValueError(f"{what} cell {(r, c)} is outside the grid "
                             f"({self.nlat} x {self.nlon})")
        if not self.base_nav[r * self.nlon + c]:
            raise ValueError(f"{what} cell {(r, c)} is not navigable")

    def depth_m(self, cell):
        return float(-self.grid.elevation[cell[0], cell[1]])

    def _infeasible(self, use_weather, reason, expanded=0):
        return RouteResult(algorithm="A*" if use_weather else "Dijkstra",
                           found=False, expanded=expanded, reason=reason)

    # -- core search ----------------------------------------------------
    def search(self, start, goal, use_weather, use_heuristic, extra_cost=None):
        """Route from `start` to `goal` (both (row, col) cells).

        Raises ValueError if either cell is outside the grid or not
        navigable on the grid; found=False (with `reason`) if a cell is too
        shallow for this Router's min_depth_m or no feasible path exists.
        extra_cost: optional per-cell multiplier (>= 1, flat array) used for
        this search only (e.g. a route-change penalty); it is included in
        the returned cost - recompute with path_cost() for the true cost.
        """
        self._check_cell(start, "start")
        self._check_cell(goal, "goal")
        for cell, what in ((start, "start"), (goal, "destination")):
            if not self.nav[cell[0] * self.nlon + cell[1]]:
                return self._infeasible(use_weather,
                    f"{what} water depth {self.depth_m(cell):.0f} m is less than "
                    f"the required {self.min_depth_m:.1f} m")
        nlon = self.nlon
        nav = self.nav
        dist_dir = self.dist_dir
        mult_dir = self.mult_dir if use_weather else None
        cellm = self.cell_pen
        if extra_cost is not None:
            cellm = extra_cost if cellm is None else cellm * extra_cost

        N = self.nlat * nlon
        g_score = np.full(N, np.inf)
        came = np.full(N, -1, dtype=np.int64)
        visited = np.zeros(N, dtype=bool)

        s_idx = start[0] * nlon + start[1]
        g_idx = goal[0] * nlon + goal[1]
        glat, glon = self.lats[goal[0]], self.lons[goal[1]]

        g_score[s_idx] = 0.0
        pq = [(0.0, 0.0, s_idx)]
        expanded = 0

        while pq:
            f, g, idx = heapq.heappop(pq)
            if visited[idx]:
                continue
            visited[idx] = True
            expanded += 1
            if idx == g_idx:
                return self._finalize(came, g_idx, use_weather, expanded, g)

            r, c = divmod(idx, nlon)
            for k, (dr, dc) in enumerate(_OFF):
                nr, nc = r + dr, c + dc
                if nr < 0 or nr >= self.nlat or nc < 0 or nc >= nlon:
                    continue
                nidx = nr * nlon + nc
                if not nav[nidx] or visited[nidx]:
                    continue
                cost = dist_dir[r, k]
                if mult_dir is not None:
                    cost *= mult_dir[r, c, k]
                if cellm is not None:
                    cost *= cellm[idx]
                ng = g + cost
                if ng < g_score[nidx]:
                    g_score[nidx] = ng
                    came[nidx] = idx
                    h = self._heuristic(nr, nc, glat, glon) if use_heuristic else 0.0
                    heapq.heappush(pq, (ng + h, ng, nidx))

        need = (f" and at least {self.min_depth_m:.1f} m deep"
                if self.min_depth_m else "")
        return self._infeasible(use_weather,
            f"no route stays {C.COAST_BUFFER_KM:g} km from land/shoals{need}",
            expanded)

    def path_cost(self, cells, use_weather):
        """Search cost of an existing path under this router's cost model -
        e.g. the remaining part of an active route, for comparison with a
        freshly computed alternative. Uses the same step costs as search()."""
        return self._path_sum(cells, self.mult_dir if use_weather else None,
                              self.cell_pen)

    def path_hours(self, cells):
        """Estimated travel time (h) of a path under this router's time
        model: each segment's km / its speed, summed (see module doc)."""
        return self._path_sum(cells, self.time_mult) / (self.speed_kn * 1.852)

    @property
    def time_basis(self):
        return "ml_speed" if self.time_mult is not None else "calm_water"

    def _path_sum(self, cells, mult_dir, cellm=None):
        """Sum of segment km, each times mult_dir[r, c, k] (and the
        per-cell multiplier cellm[from cell]) if given."""
        total = 0.0
        for (r, c), (nr, nc) in zip(cells, cells[1:]):
            k = _OFF.index((nr - r, nc - c))    # ValueError if not adjacent
            step = self.dist_dir[r, k]
            if mult_dir is not None:
                step *= mult_dir[r, c, k]
            if cellm is not None:
                step *= cellm[r * self.nlon + c]
            total += step
        return float(total)

    def _finalize(self, came, g_idx, use_weather, expanded, cost):
        nlon = self.nlon
        idx = g_idx
        path = []
        while idx != -1:
            path.append(divmod(idx, nlon))
            idx = came[idx]
        path.reverse()

        latlon = [(float(self.lats[r]), float(self.lons[c])) for r, c in path]
        dist = 0.0
        for (la1, lo1), (la2, lo2) in zip(latlon, latlon[1:]):
            dist += float(geo.haversine_km(la1, lo1, la2, lo2))

        if use_weather and self.weather is not None:
            waves = [float(self.weather.swh[r, c]) for r, c in path]
        else:
            waves = [0.0]

        return RouteResult(
            algorithm="A*" if use_weather else "Dijkstra",
            found=True, cells=path, latlon=latlon,
            distance_km=round(dist, 1),
            time_hours=round(self.path_hours(path), 1),
            max_wave_m=round(max(waves), 2),
            mean_wave_m=round(float(np.mean(waves)), 2),
            expanded=expanded,
            cost=float(cost),
            time_basis=self.time_basis,
        )


# -- module-level convenience API ---------------------------------------
def dijkstra(grid, start, goal):
    return Router(grid).search(start, goal, use_weather=False, use_heuristic=False)


def astar(grid, weather, start, goal):
    return Router(grid, weather).search(start, goal, use_weather=True, use_heuristic=True)


def route_between(grid, weather, start_latlon, goal_latlon, algorithm="astar"):
    """Snap coordinates to sea cells and run an algorithm."""
    start = grid.nearest_cell(*start_latlon)
    goal = grid.nearest_cell(*goal_latlon)
    if algorithm == "dijkstra":
        return dijkstra(grid, start, goal)
    return astar(grid, weather, start, goal)
