"""Command-line interface for netbox-opennebula-sync."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import UTC
from pathlib import Path

from . import __version__
from .config import load_config
from .reconciler import run_bootstrap, run_sync


def _setup_logging(verbose: bool, json_logs: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    if json_logs:
        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                import json
                from datetime import datetime

                return json.dumps(
                    {
                        "ts": datetime.now(UTC).isoformat(),
                        "level": record.levelname,
                        "logger": record.name,
                        "msg": record.getMessage(),
                    },
                    ensure_ascii=False,
                )

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logging.root.handlers = [handler]
        logging.root.setLevel(level)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="netbox-opennebula-sync",
        description="Discover and synchronize OpenNebula inventory into NetBox Community",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-c",
        "--config",
        help="Path to YAML configuration file",
        default=None,
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--json-logs", action="store_true", help="Emit structured JSON logs")

    sub = parser.add_subparsers(dest="command", required=True)

    p_boot = sub.add_parser("bootstrap", help="Create NetBox custom fields, tags and cluster type")
    p_boot.add_argument("--dry-run", action="store_true")

    p_sync = sub.add_parser("sync", help="Run a one-shot inventory synchronization")
    p_sync.add_argument("--dry-run", action="store_true")

    p_daemon = sub.add_parser("daemon", help="Run continuous synchronization loop")
    p_daemon.add_argument("--dry-run", action="store_true")
    p_daemon.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Seconds between sync runs (default from config)",
    )

    args = parser.parse_args(argv)
    _setup_logging(args.verbose, args.json_logs)

    cfg_path = args.config
    if cfg_path is None:
        for candidate in (
            Path("/etc/netbox-opennebula-sync/config.yaml"),
            Path("config.yaml"),
        ):
            if candidate.is_file():
                cfg_path = str(candidate)
                break
    cfg = load_config(cfg_path)
    if getattr(args, "dry_run", False):
        cfg.sync.dry_run = True

    if args.command == "bootstrap":
        return run_bootstrap(cfg)
    if args.command == "sync":
        return run_sync(cfg)
    if args.command == "daemon":
        interval = args.interval or cfg.sync.interval
        stop = False

        def _stop(*_args: object) -> None:
            nonlocal stop
            stop = True
            logging.getLogger(__name__).info("shutdown requested")

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        log = logging.getLogger(__name__)
        while not stop:
            try:
                rc = run_sync(cfg)
                if rc:
                    log.warning("sync finished with errors (rc=%s)", rc)
            except Exception:
                log.exception("sync failed")
            for _ in range(interval):
                if stop:
                    break
                time.sleep(1)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
