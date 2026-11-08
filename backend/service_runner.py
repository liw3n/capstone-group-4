"""Bounded, observable supervision for API and MCP processes (stdlib only)."""
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


def log(message):
    print(f"[startup] {message}", flush=True)


def port_ready(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def http_ready(port, path, timeout):
    try:
        with build_opener(ProxyHandler({})).open(
            f"http://127.0.0.1:{port}{path}", timeout=timeout
        ) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def stop_processes(processes, grace=5):
    for process in processes.values():
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + grace
    for process in processes.values():
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    for process in processes.values():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def supervise(commands, probe, *, timeout=120, heartbeat=10, interval=0.25):
    processes = {}
    stopping = False

    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        started = time.monotonic()
        deadline = started + timeout
        next_heartbeat = started
        ready = set()
        for name, command in commands.items():
            if stopping:
                return 0
            log(f"Starting {name}.")
            processes[name] = subprocess.Popen(command, start_new_session=True)
        while not stopping:
            for name, process in processes.items():
                code = process.poll()
                if code is not None:
                    log(f"{name} exited unexpectedly (code {code}); stopping all services.")
                    return 1
            if len(ready) < len(processes):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    waiting = ", ".join(name for name in processes if name not in ready)
                    log(f"Startup timed out after {timeout:g}s; waiting for: {waiting}. Stopping services.")
                    return 1
                for name in processes:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or stopping:
                        break
                    if name not in ready and probe(name, min(5.0, remaining)):
                        ready.add(name)
                        log(f"{name} ready.")
                if len(ready) == len(processes):
                    log("All services ready; startup complete.")
                elif time.monotonic() >= next_heartbeat:
                    waiting = ", ".join(name for name in processes if name not in ready)
                    log(f"Waiting for {waiting} ({time.monotonic() - started:.0f}s elapsed).")
                    next_heartbeat = time.monotonic() + heartbeat
            time.sleep(interval)
        log("Shutdown requested; stopping services.")
        return 0
    except Exception:
        log("Service supervisor failed; check runtime configuration and child logs.")
        return 1
    finally:
        stop_processes(processes)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    os.chdir(Path(__file__).resolve().parent)
    try:
        port = int(os.environ.get("PORT", "4000"))
        if not 1 <= port <= 65535 or port == 8001:
            raise ValueError
    except ValueError:
        log("Invalid API PORT; expected 1–65535, excluding MCP port 8001.")
        return 1
    hosted = os.environ.get("PULSE_HOSTED_DEMO", "").lower() in {"true", "1", "yes", "on"}
    if hosted:
        os.environ["FASTMCP_CHECK_FOR_UPDATES"] = "off"
    os.environ["PYTHONUNBUFFERED"] = "1"
    commands = {
        "FastMCP": [sys.executable, "-u", "mcp/server.py"],
        "FastAPI": [sys.executable, "-u", "-m", "uvicorn", "app.main:app",
                    "--host", "0.0.0.0", "--port", str(port)],
    }
    path = "/ready" if hosted else "/live"
    log(f"API port {port}; MCP probe port 8001; API probe {path}; startup deadline 120s.")
    return supervise(commands, lambda name, remaining: (
        port_ready(8001) if name == "FastMCP" else http_ready(port, path, remaining)
    ))


if __name__ == "__main__":
    raise SystemExit(main())
