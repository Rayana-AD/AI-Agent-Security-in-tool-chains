#!/usr/bin/env python3
"""Double-fork daemon launcher for AgentDojo dual benchmark + monitor."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGDIR = ROOT / "runs" / "agentdojo_upstream"
PY = ROOT / ".venv" / "bin" / "python"

DEFENSES = [
    "--defense",
    "none",
    "--defense",
    "tool_filter",
    "--defense",
    "repeat_user_prompt",
    "--defense",
    "bio_idea1_provenance",
]

DEEPSEEK_DIR = LOGDIR / "benchmark_20260629_224640"


def llama_dir() -> Path:
    candidates = sorted(LOGDIR.glob("benchmark_*_llama70"), reverse=True)
    if candidates:
        return candidates[0]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return LOGDIR / f"benchmark_{stamp}_llama70"


def daemonize() -> None:
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    os.chdir(ROOT)
    os.umask(0o22)
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    # stdout/stderr redirected per worker


def spawn_worker(
    label: str,
    cmd: list[str],
    log_file: Path,
    pid_file: Path,
    use_caffeinate: bool = True,
) -> int:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    pid = os.fork()
    if pid > 0:
        pid_file.write_text(str(pid), encoding="utf-8")
        return pid

    # Child: become session leader orphan
    os.setsid()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    with log_file.open("a", encoding="utf-8") as logf:
        logf.write(f"\n=== {time.strftime('%Y-%m-%dT%H:%M:%S%z')} start {label} ===\n")
        logf.flush()
        fd = logf.fileno()
        os.dup2(fd, 1)
        os.dup2(fd, 2)

    full_cmd = cmd
    if use_caffeinate and subprocess.run(["which", "caffeinate"], capture_output=True).returncode == 0:
        full_cmd = ["caffeinate", "-dims", *cmd]

    os.execvpe(full_cmd[0], full_cmd, env)
    raise SystemExit("exec failed")


def is_alive(pid_file: Path) -> bool:
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_if_alive(pid_file: Path) -> None:
    if not is_alive(pid_file):
        return
    pid = int(pid_file.read_text(encoding="utf-8").strip())
    os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not is_alive(pid_file):
            return
        time.sleep(0.5)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def main() -> None:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    launch_log = LOGDIR / "benchmark_launch.log"
    with launch_log.open("a", encoding="utf-8") as f:
        f.write(f"=== {time.strftime('%Y-%m-%dT%H:%M:%S%z')} python daemon launch ===\n")

    ds_pid = LOGDIR / "benchmark_full_deepseek.pid"
    ll_pid = LOGDIR / "benchmark_full_llama70.pid"
    mon_pid = LOGDIR / "benchmark_monitor.pid"
    wd_pid = LOGDIR / "benchmark_watchdog.pid"

    restart_dead = os.environ.get("RESTART_DEAD", "0") == "1"
    deepseek_only = os.environ.get("DEEPSEEK_ONLY", "0") == "1"
    if deepseek_only:
        (LOGDIR / "deepseek_only.mode").write_text("1\n", encoding="utf-8")
    elif (LOGDIR / "deepseek_only.mode").exists():
        (LOGDIR / "deepseek_only.mode").unlink(missing_ok=True)
    if not restart_dead:
        stop_if_alive(ds_pid)
        if not deepseek_only:
            stop_if_alive(ll_pid)

    llama = llama_dir()
    llama.mkdir(parents=True, exist_ok=True)

    base = [str(PY), "-u", str(ROOT / "eval" / "run_agentdojo_benchmark.py"), *DEFENSES]

    if not restart_dead or not is_alive(ds_pid):
        spawn_worker(
            "DeepSeek",
            [*base, "--model-mode", "deepseek", "--run-dir", str(DEEPSEEK_DIR)],
            LOGDIR / "benchmark_full_deepseek.log",
            ds_pid,
        )
        print(f"DeepSeek PID={ds_pid.read_text().strip()}")

    if not deepseek_only and (not restart_dead or not is_alive(ll_pid)):
        spawn_worker(
            "Llama70",
            [*base, "--model-mode", "openrouter_llama70", "--run-dir", str(llama)],
            LOGDIR / "benchmark_full_llama70.log",
            ll_pid,
        )
        print(f"Llama70 PID={ll_pid.read_text().strip()}")
    elif deepseek_only:
        print("DEEPSEEK_ONLY=1 — skipping Llama worker")

    if not restart_dead:
        stop_if_alive(mon_pid)
        stop_if_alive(wd_pid)
        spawn_worker(
            "monitor",
            ["bash", str(ROOT / "scripts" / "monitor_benchmark_dual.sh")],
            LOGDIR / "benchmark_monitor.log",
            mon_pid,
            use_caffeinate=False,
        )
        spawn_worker(
            "watchdog",
            ["bash", str(ROOT / "scripts" / "benchmark_watchdog.sh")],
            LOGDIR / "benchmark_watchdog.log",
            wd_pid,
            use_caffeinate=False,
        )
        print(f"Monitor PID={mon_pid.read_text().strip()}")
        print(f"Watchdog PID={wd_pid.read_text().strip()}")


if __name__ == "__main__":
    main()
