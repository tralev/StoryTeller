#!/usr/bin/env python3
"""Run one command with an aggregate process-tree RSS safety watchdog.

The soft stop is intentionally below the advertised hard ceiling.  On macOS,
RLIMIT_AS is not a reliable aggregate limit for Gradle, Xcode, Simulator, and
their helper processes, so this runner samples RSS for descendants plus
explicit helper-name patterns and terminates the suite before pressure reaches
the hard ceiling.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass

MIB = 1024 * 1024
DESKTOP_SOFT_GB = 11.0
DESKTOP_HARD_GB = 12.0


@dataclass(frozen=True)
class Process:
    pid: int
    ppid: int
    rss_kib: int
    command: str


def snapshot() -> list[Process]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,rss=,command="],
        check=True,
        capture_output=True,
        text=True,
    )
    processes: list[Process] = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 3)
        if len(fields) == 4:
            processes.append(Process(int(fields[0]), int(fields[1]), int(fields[2]), fields[3]))
    return processes


def selected(
    processes: list[Process], root_pid: int, patterns: list[re.Pattern[str]]
) -> list[Process]:
    pids = {root_pid}
    changed = True
    while changed:
        changed = False
        for process in processes:
            if process.ppid in pids and process.pid not in pids:
                pids.add(process.pid)
                changed = True
    return [
        process
        for process in processes
        if process.pid in pids or any(pattern.search(process.command) for pattern in patterns)
    ]


def terminate(process: subprocess.Popen[bytes], tracked: list[Process]) -> None:
    for item in sorted(tracked, key=lambda value: value.pid, reverse=True):
        if item.pid != os.getpid():
            try:
                os.kill(item.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--soft-gb", type=float, default=DESKTOP_SOFT_GB)
    parser.add_argument("--hard-gb", type=float, default=DESKTOP_HARD_GB)
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    parser.add_argument("--include-pattern", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    if not 0 < args.soft_gb < args.hard_gb:
        parser.error("require 0 < --soft-gb < --hard-gb")

    patterns = [re.compile(value, re.IGNORECASE) for value in args.include_pattern]
    child = subprocess.Popen(command, start_new_session=True)
    peak = 0
    soft_bytes = int(args.soft_gb * 1024 * MIB)
    try:
        while child.poll() is None:
            processes = snapshot()
            tracked = selected(processes, child.pid, patterns)
            rss_bytes = sum(item.rss_kib for item in tracked) * 1024
            peak = max(peak, rss_bytes)
            if rss_bytes >= soft_bytes:
                terminate(child, tracked)
                print(
                    json.dumps(
                        {
                            "status": "resource_blocked",
                            "soft_gb": args.soft_gb,
                            "hard_gb": args.hard_gb,
                            "peak_gb": round(peak / (1024 * MIB), 3),
                            "tracked_processes": len(tracked),
                        },
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 75
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        terminate(child, selected(snapshot(), child.pid, patterns))
        return 130
    except Exception:
        # A failed monitor must never leave an unbounded child behind.
        try:
            terminate(child, selected(snapshot(), child.pid, patterns))
        except Exception:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        raise
    print(
        json.dumps(
            {
                "status": "completed",
                "exit_code": child.returncode,
                "peak_gb": round(peak / (1024 * MIB), 3),
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return child.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
