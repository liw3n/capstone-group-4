"""Real subprocess lifecycle tests; no database or model-provider access."""
import os
import signal
import subprocess
import sys
import time

import pytest
import service_runner as runner


@pytest.fixture
def children(monkeypatch):
    processes = []
    popen = subprocess.Popen

    def spawn(*args, **kwargs):
        child = popen(*args, **kwargs)
        processes.append(child)
        return child

    monkeypatch.setattr(runner.subprocess, "Popen", spawn)
    yield processes
    for child in processes:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()


def command(source="import time; time.sleep(30)"):
    return [sys.executable, '-u', '-c', source]


def test_deadline_stops_both_children(children, capsys):
    start = time.monotonic()
    assert runner.supervise({'FastMCP': command(), 'FastAPI': command()},
                            lambda *_: False, timeout=.15, heartbeat=.05, interval=.01) == 1
    assert time.monotonic() - start < 3
    assert len(children) == 2 and all(p.poll() is not None for p in children)
    output = capsys.readouterr().out
    assert 'Starting FastMCP' in output and 'Starting FastAPI' in output
    assert 'Startup timed out' in output and 'waiting for: FastMCP, FastAPI' in output


@pytest.mark.parametrize('code', [0, 7])
def test_child_exit_even_zero_fails_and_stops_sibling(children, capsys, code):
    assert runner.supervise({'FastMCP': command(f'raise SystemExit({code})'),
                             'FastAPI': command()}, lambda *_: False,
                            timeout=3, interval=.01) == 1
    assert all(p.poll() is not None for p in children)
    assert f'exited unexpectedly (code {code})' in capsys.readouterr().out


def test_readiness_then_runtime_exit_is_supervised(children, capsys):
    assert runner.supervise({'FastMCP': command('import time; time.sleep(.2)'),
                             'FastAPI': command()}, lambda *_: True,
                            timeout=3, interval=.01) == 1
    output = capsys.readouterr().out
    assert 'FastMCP ready.' in output and 'FastAPI ready.' in output
    assert 'All services ready' in output
    assert all(p.poll() is not None for p in children)


def test_sigterm_stops_children_and_returns_cleanly(children, capsys):
    def probe(*_):
        os.kill(os.getpid(), signal.SIGTERM)
        return False
    assert runner.supervise({'FastMCP': command(), 'FastAPI': command()},
                            probe, timeout=3, interval=.01) == 0
    assert all(p.poll() is not None for p in children)
    assert 'Shutdown requested' in capsys.readouterr().out


def test_stubborn_child_is_killed_after_grace(children):
    child = runner.subprocess.Popen(command(
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(30)"
    ), start_new_session=True, stdout=subprocess.PIPE, text=True)
    assert child.stdout.readline().strip() == 'ready'
    runner.stop_processes({'child': child}, grace=.05)
    assert child.returncode == -signal.SIGKILL


def test_spawn_error_is_redacted_and_existing_child_cleaned(children, capsys):
    assert runner.supervise({'FastMCP': command(), 'FastAPI': ['/missing/secret-value']},
                            lambda *_: False) == 1
    output = capsys.readouterr().out
    assert 'supervisor failed' in output and 'secret-value' not in output
    assert all(p.poll() is not None for p in children)


def test_hosted_configuration_uses_supported_update_setting(monkeypatch):
    monkeypatch.setenv('PULSE_HOSTED_DEMO', 'true')
    monkeypatch.setenv('PORT', '10000')
    monkeypatch.setenv('FASTMCP_CHECK_FOR_UPDATES', 'stable')
    monkeypatch.setenv('PYTHONUNBUFFERED', '0')
    calls = []
    monkeypatch.setattr(runner, 'http_ready', lambda *args: calls.append(args) or True)
    def supervise(commands, probe):
        assert commands['FastAPI'][-2:] == ['--port', '10000']
        assert probe('FastAPI', .5)
        return 0
    monkeypatch.setattr(runner, 'supervise', supervise)
    assert runner.main() == 0
    assert calls == [(10000, '/ready', .5)]
    assert os.environ['FASTMCP_CHECK_FOR_UPDATES'] == 'off'
    # Validate against the installed, locked FastMCP release without a network call.
    from fastmcp.settings import Settings
    assert Settings().check_for_updates == 'off'


@pytest.mark.parametrize('port', ['0', '8001', '65536', 'secret-invalid-port'])
def test_invalid_port_is_rejected_without_echoing_input(monkeypatch, capsys, port):
    monkeypatch.setenv('PORT', port)
    assert runner.main() == 1
    assert 'secret-invalid-port' not in capsys.readouterr().out
