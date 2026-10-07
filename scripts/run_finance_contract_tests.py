"""Run finance contract tests in an owned, disposable PostgreSQL cluster.

Development evidence uses an explicit local PostgreSQL binary. It never targets
an installed service or accepts a DSN. PostgreSQL 17 target verification remains
required before production application.
"""
# ruff: noqa: E501
from __future__ import annotations

import os
import secrets
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PG_BIN = Path(r"C:\Users\gsanc\.codex\.chatgpt-projects\g-p-6aa23b54aca481919d6bea38fe3e3128\_audit_tools\pg17\pgsql\bin")


def exe(name: str) -> Path:
    candidate = Path(os.environ.get("PG_BIN", DEFAULT_PG_BIN)) / f"{name}.exe"
    if not candidate.is_file():
        raise RuntimeError(f"required PostgreSQL binary is unavailable: {candidate}")
    return candidate


def version(path: Path) -> str:
    return subprocess.check_output([str(path), "--version"], text=True, encoding="utf-8").strip()


def unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    check = kwargs.pop("check", True)
    return subprocess.run(args, check=check, text=True, encoding="utf-8", errors="strict",
                          creationflags=flags, **kwargs)


def main() -> int:
    postgres, initdb, pg_ctl, psql = (exe(name) for name in ("postgres", "initdb", "pg_ctl", "psql"))
    versions = {version(path) for path in (postgres, initdb, pg_ctl, psql)}
    majors = {match.group(1) for value in versions if (match := re.search(r"PostgreSQL\)?\s+(\d+)", value))}
    if len(majors) != 1:
        raise RuntimeError(f"PostgreSQL binary majors disagree: {sorted(versions)}")
    major = next(iter(majors))
    if major not in {"17", "18"}:
        raise RuntimeError(f"harness needs PostgreSQL 17 or 18, got {sorted(versions)}")
    print(f"finance contract harness: PostgreSQL {major} development target")

    # Retrying the bind race is safe because every attempt owns a new directory.
    for attempt in range(3):
        root = Path(tempfile.mkdtemp(prefix="txisd-finance-contract-", dir=tempfile.gettempdir())).resolve()
        data, log, pw = root / "data", root / "postgres.log", root / "pw"
        port, password = unused_port(), secrets.token_urlsafe(32)
        env = os.environ | {"PGPASSWORD": password, "FINANCE_CONTRACT_DSN": f"postgresql://postgres:{password}@127.0.0.1:{port}/postgres"}
        started = False
        cleanup_failed = False
        try:
            pw.write_text(password + "\n", encoding="utf-8")
            run([str(initdb), "-D", str(data), "-U", "postgres", "--auth-local=trust", "--auth-host=scram-sha-256", f"--pwfile={pw}"], env=env)
            # Do not capture pg_ctl start on Windows: postgres inherits that
            # pipe, keeping it open after pg_ctl exits and hanging the runner.
            start = run([str(pg_ctl), "-D", str(data), "-l", str(log), "-o", f"-h 127.0.0.1 -p {port}", "-w", "-t", "30", "start"], env=env, check=False)
            if start.returncode:
                if attempt < 2 and not port_is_open(port):
                    continue
                raise RuntimeError(f"PostgreSQL failed to start in owned cluster {root}; log={log}")
            started = True
            result = run([sys.executable, "-m", "pytest", "tests/test_finance_contract.py", "-q"], cwd=ROOT, env=env, check=False, capture_output=True)
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            if result.returncode:
                print(f"finance contract pytest failed with exit {result.returncode}; log={log}", file=sys.stderr)
            return result.returncode
        finally:
            # Never infer ownership from a port. pg_ctl is restricted to our data dir.
            if started:
                try:
                    run([str(pg_ctl), "-D", str(data), "-w", "-t", "30", "stop", "-m", "fast"], env=env)
                    if port_is_open(port):
                        raise RuntimeError(f"owned port {port} is still accepting connections")
                except Exception as exc:
                    cleanup_failed = True
                    print(f"finance contract cleanup failed; retained {root}: {exc}", file=sys.stderr)
            if not cleanup_failed and root.exists() and root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
                shutil.rmtree(root)
                print("finance contract teardown: owned cluster removed")
        if cleanup_failed:
            return 1
    raise RuntimeError("PostgreSQL port race persisted after three owned cluster attempts")


if __name__ == "__main__":
    raise SystemExit(main())
