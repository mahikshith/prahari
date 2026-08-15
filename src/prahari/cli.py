"""Prahari CLI.

    prahari validate  -c prahari.yaml     check config and credentials, touch nothing
    prahari verify    -c prahari.yaml     confirm each connector's credentials work
    prahari collect   -c prahari.yaml     one collection cycle, then exit
    prahari run       -c prahari.yaml     the daemon
    prahari status    -c prahari.yaml     what is in the store

`validate` and `verify` exist because the first fifteen minutes of an install decide
whether a design partner keeps going. A missing scope should be a clear message now,
not a silent overnight no-op.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from prahari.collector.daemon import Daemon, build_connector, run_daemon
from prahari.core import config as config_module
from prahari.core.fx import format_inr
from prahari.notify.router import Router
from prahari.store.duck import Store


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        cfg = config_module.load(args.config)
    except Exception as exc:
        print(f"INVALID  {exc}", file=sys.stderr)
        return 1

    print(f"OK       config parses: {args.config}")
    print(f"         store          {cfg.store.path}")
    print(f"         collectors     {len(cfg.enabled_collectors)} enabled "
          f"of {len(cfg.collectors)}")
    for collector in cfg.collectors:
        flag = " " if collector.enabled else "-"
        print(f"           {flag} {collector.name}  every {collector.poll_interval}")
    print(f"         budgets        {len(cfg.budgets)}")
    for budget in cfg.budgets:
        scope = ", ".join(f"{k}={v}" for k, v in budget.scope.items()) or "organisation-wide"
        print(f"             {budget.id:<24} {format_inr(budget.amount):>16}  [{scope}]")

    if missing := cfg.missing_env():
        print("\nMISSING environment variables:")
        for name in missing:
            print(f"           {name}")
        print("\nConfig is valid but the collector cannot authenticate.")
        return 2

    print("\nAll referenced environment variables are set.")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Make one cheap authenticated call per connector."""
    cfg = config_module.load(args.config)

    async def check() -> int:
        failures = 0
        for collector in cfg.enabled_collectors:
            try:
                connector = build_connector(collector)
                ok = await connector.verify_credentials()
            except Exception as exc:
                print(f"ERROR    {collector.name}: {type(exc).__name__}: {exc}")
                failures += 1
                continue
            print(f"{'OK      ' if ok else 'DENIED  '} {collector.name}")
            failures += 0 if ok else 1
        return failures

    failures = asyncio.run(check())
    if failures:
        print(f"\n{failures} connector(s) could not authenticate.")
    return 1 if failures else 0


def cmd_collect(args: argparse.Namespace) -> int:
    cfg = config_module.load(args.config)
    with Store(cfg.store.path) as store:
        daemon = Daemon(cfg, store, Router.from_config(cfg.alerts))
        result = asyncio.run(daemon.cycle())

        print(f"collected  {result.collected} records")
        print(f"alerts     {result.alerts_raised} raised, {result.alerts_notified} delivered")
        print(f"budgets    {result.budget_notifications} notification(s)")
        for failure in result.failures:
            print(f"FAILED     {failure}")
        return 1 if result.failures else 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = config_module.load(args.config)
    with Store(cfg.store.path) as store:
        asyncio.run(run_daemon(cfg, store, Router.from_config(cfg.alerts)))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = config_module.load(args.config)
    with Store(cfg.store.path) as store:
        now = datetime.now(UTC)
        print(f"store      {cfg.store.path}")
        print(f"records    {store.count():,}")

        print("\nwatermarks")
        for collector in cfg.collectors:
            mark = store.watermark(collector.name)
            if mark is None:
                print(f"  {collector.name:<32} never collected")
            else:
                lag = now - mark
                print(f"  {collector.name:<32} {mark:%Y-%m-%d %H:%M}Z  "
                      f"({lag.total_seconds() / 3600:.1f}h behind)")

        pending = store.pending_alerts(limit=10)
        print(f"\nundelivered alerts  {len(pending)}")
        for alert in pending:
            print(f"  [{alert['occurred_at']:%m-%d %H:%M}] {alert['rule']} "
                  f"{alert['credential']}")

        recent = store.records(start=now - timedelta(days=30), end=now)
        print(f"\nrecords in last 30d {len(recent):,}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prahari", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, handler, help_text in (
        ("validate", cmd_validate, "check config and environment, touch nothing"),
        ("verify", cmd_verify, "confirm each connector can authenticate"),
        ("collect", cmd_collect, "run one collection cycle and exit"),
        ("run", cmd_run, "run the collector daemon"),
        ("status", cmd_status, "show store contents and watermarks"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("-c", "--config", type=Path, default=Path("prahari.yaml"))
        p.set_defaults(handler=handler)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        return args.handler(args)
    except FileNotFoundError as exc:
        print(f"ERROR    {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
