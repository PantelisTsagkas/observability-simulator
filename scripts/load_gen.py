#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Load generator for the observability simulator.

Fires a weighted, randomised mix of requests at the backend's /simulate
endpoints so Grafana dashboards have realistic shape before recording a demo.

Two modes:

  mix   — realistic weighted traffic, for warming up dashboards (default)
  burst — floods errors to trip the HighErrorRate alert on camera

Stdlib only, so it runs with either:

    python3 scripts/load_gen.py
    uv run scripts/load_gen.py --duration 120 --workers 8
    uv run scripts/load_gen.py --mode burst

Stop early with Ctrl+C; a summary prints on exit.
"""

from __future__ import annotations

import argparse
import random
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field

# (path, weight) — higher weight means the endpoint is hit more often.
#
# mix:   mostly healthy traffic with a steady minority of errors and latency,
#        which is what makes the error-rate and P95 panels look believable.
# burst: error-dominated flood that pushes the 5m error ratio well past the
#        5% HighErrorRate threshold so the alert fires on camera.
PROFILES: dict[str, list[tuple[str, int]]] = {
    "mix": [
        ("/simulate/success", 50),
        ("/simulate/random", 25),
        ("/simulate/slow?delay=2", 10),
        ("/simulate/error", 10),
        ("/simulate/cpu", 5),
    ],
    "burst": [
        ("/simulate/error", 90),
        ("/simulate/success", 10),
    ],
}


@dataclass
class Stats:
    """Thread-safe tally of outcomes across all workers."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    by_status: Counter[int] = field(default_factory=Counter)
    by_endpoint: Counter[str] = field(default_factory=Counter)
    errors: int = 0
    total: int = 0

    def record(self, endpoint: str, status: int) -> None:
        with self.lock:
            self.total += 1
            self.by_endpoint[endpoint] += 1
            self.by_status[status] += 1
            if status >= 500 or status == 0:
                self.errors += 1


def pick_endpoint(profile: list[tuple[str, int]]) -> str:
    paths = [path for path, _ in profile]
    weights = [weight for _, weight in profile]
    return random.choices(paths, weights=weights, k=1)[0]


def hit(base_url: str, endpoint: str, timeout: float) -> int:
    """Send one request. Returns the HTTP status, or 0 on transport error."""
    url = f"{base_url}{endpoint}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        # 4xx/5xx come back here; that is expected for /simulate/error.
        return exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def worker(
    base_url: str,
    profile: list[tuple[str, int]],
    deadline: float,
    min_gap: float,
    max_gap: float,
    timeout: float,
    stats: Stats,
    stop: threading.Event,
) -> None:
    while not stop.is_set() and time.monotonic() < deadline:
        endpoint = pick_endpoint(profile)
        status = hit(base_url, endpoint, timeout)
        stats.record(endpoint, status)
        time.sleep(random.uniform(min_gap, max_gap))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("mix", "burst"),
        default="mix",
        help="Traffic profile: 'mix' for realistic load, 'burst' to trip the "
        "HighErrorRate alert (default: %(default)s)",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="How long to run, in seconds (default: 60 for mix, 120 for burst)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Concurrent request threads (default: 6 for mix, 12 for burst)",
    )
    parser.add_argument(
        "--min-gap",
        type=float,
        default=None,
        help="Min seconds a worker waits between requests "
        "(default: 0.2 for mix, 0.0 for burst)",
    )
    parser.add_argument(
        "--max-gap",
        type=float,
        default=None,
        help="Max seconds a worker waits between requests "
        "(default: 0.8 for mix, 0.05 for burst)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Per-request timeout in seconds (default: %(default)s)",
    )
    return parser.parse_args()


# Per-mode defaults, applied when the flag was left unset.
MODE_DEFAULTS: dict[str, dict[str, float]] = {
    "mix": {"duration": 60.0, "workers": 6, "min_gap": 0.2, "max_gap": 0.8},
    "burst": {"duration": 120.0, "workers": 12, "min_gap": 0.0, "max_gap": 0.05},
}


def main() -> None:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    defaults = MODE_DEFAULTS[args.mode]

    duration = args.duration if args.duration is not None else defaults["duration"]
    workers = int(args.workers if args.workers is not None else defaults["workers"])
    min_gap = args.min_gap if args.min_gap is not None else defaults["min_gap"]
    max_gap = args.max_gap if args.max_gap is not None else defaults["max_gap"]
    profile = PROFILES[args.mode]

    stats = Stats()
    stop = threading.Event()
    deadline = time.monotonic() + duration

    print(
        f"[{args.mode}] Generating load against {base_url} for {duration:.0f}s "
        f"with {workers} workers. Ctrl+C to stop early."
    )
    if args.mode == "burst":
        print(
            "Flooding /simulate/error. HighErrorRate needs the 5m error ratio "
            "above 5% for 1m, so expect the alert to fire after ~1-2 minutes. "
            "Keep the burst running until it does."
        )

    threads = [
        threading.Thread(
            target=worker,
            args=(base_url, profile, deadline, min_gap, max_gap, args.timeout, stats, stop),
            daemon=True,
        )
        for _ in range(workers)
    ]
    for thread in threads:
        thread.start()

    try:
        while any(thread.is_alive() for thread in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping...")
        stop.set()

    for thread in threads:
        thread.join(timeout=args.timeout + 1)

    print_summary(stats)


def print_summary(stats: Stats) -> None:
    print("\n─── Summary ───")
    print(f"Total requests : {stats.total}")
    error_pct = (stats.errors / stats.total * 100) if stats.total else 0.0
    print(f"Errors (5xx/0) : {stats.errors} ({error_pct:.1f}%)")
    print("By status:")
    for status, count in sorted(stats.by_status.items()):
        label = "transport error" if status == 0 else str(status)
        print(f"  {label:>15} : {count}")
    print("By endpoint:")
    for endpoint, count in stats.by_endpoint.most_common():
        print(f"  {endpoint:>22} : {count}")


if __name__ == "__main__":
    main()
