#!/usr/bin/env python3
"""
Arabic RTL Processor - Daemon Mode

Keeps the process running in background for instant responses.
Auto-closes after 5 minutes of inactivity. Cross-platform (Linux, macOS, Windows, WSL).

Usage:
    arabic-rtl-daemon start        # Start daemon in background
    arabic-rtl-daemon stop         # Stop daemon
    arabic-rtl-daemon status       # Check if running
    arabic-rtl-daemon restart      # Restart daemon
    arabic-rtl-daemon process      # Process text from stdin
    arabic-rtl-daemon run-server   # Internal foreground server runner
"""

import os
import sys
import time
import socket
import signal
import atexit
import tempfile
import getpass
import subprocess
import struct
import threading
from pathlib import Path

# Per-user isolated directory with safe short path length for Unix domain sockets
try:
    _uid = str(os.getuid())
except AttributeError:
    _uid = getpass.getuser()

sock_dir_base = tempfile.gettempdir()
if os.name == 'posix' and os.path.exists('/tmp') and os.access('/tmp', os.W_OK):
    sock_dir_base = '/tmp'

SOCKET_DIR = Path(sock_dir_base) / f"artl-{_uid}"
SOCKET_PATH = SOCKET_DIR / "daemon.sock"
PORT_FILE = SOCKET_DIR / "daemon.port"
PID_FILE = SOCKET_DIR / "daemon.pid"
LOG_FILE = SOCKET_DIR / "daemon.log"

# Config
IDLE_TIMEOUT = 300  # 5 minutes
BUFFER_SIZE = 1024 * 1024  # 1MB buffer

# Check if AF_UNIX is available and supported on this platform
USE_UNIX_SOCKET = hasattr(socket, 'AF_UNIX') and sys.platform != 'win32'


def _configure_std_streams():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass


def log(msg):
    """Write to log file."""
    try:
        SOCKET_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def is_running():
    """Check if daemon is running."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_INFORMATION = 0x0400
            process = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
            if process != 0:
                exit_code = wintypes.DWORD()
                success = kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code))
                kernel32.CloseHandle(process)
                if success and exit_code.value == 259:  # STILL_ACTIVE
                    return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except PermissionError:
        return True
    except (ProcessLookupError, ValueError, OSError):
        for p in (PID_FILE, SOCKET_PATH, PORT_FILE):
            try:
                p.unlink()
            except OSError:
                pass
        return False


def get_pid():
    """Get daemon PID."""
    try:
        return int(PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return None


def stop_daemon():
    """Stop the daemon."""
    if not is_running():
        print("Daemon not running")
        return

    pid = get_pid()
    if pid is not None:
        try:
            if sys.platform == 'win32':
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                sig_term = getattr(signal, 'SIGTERM', 15)
                sig_kill = getattr(signal, 'SIGKILL', 9)
                os.kill(pid, sig_term)
                time.sleep(0.5)
                if is_running():
                    os.kill(pid, sig_kill)
            print(f"Daemon stopped (PID: {pid})")
        except Exception as e:
            print(f"Error stopping daemon: {e}")

    # Clean up files
    for p in (PID_FILE, SOCKET_PATH, PORT_FILE):
        try:
            p.unlink()
        except OSError:
            pass


# Import processor engine
_pkg_dir = str(Path(__file__).parent)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

try:
    from arabic_rtl import process_text as _rtl_process
    _USE_CYTHON = True
except ImportError:
    _USE_CYTHON = False
    _rtl_process = None


def process_text(text, smart_mode=True):
    """Process text through the Arabic RTL processor."""
    if _USE_CYTHON:
        return _rtl_process(text, smart_mode)

    import arabic_rtl_cli
    return arabic_rtl_cli.py_process_text(text, smart_mode)


def handle_client(conn, addr):
    """Handle a client connection using length-prefix framing."""
    try:
        # Read 4-byte length prefix
        raw_len = b''
        while len(raw_len) < 4:
            chunk = conn.recv(4 - len(raw_len))
            if not chunk:
                return
            raw_len += chunk
        payload_length = struct.unpack('>I', raw_len)[0]
        MAX_PAYLOAD = 100 * 1024 * 1024  # 100MB
        if payload_length > MAX_PAYLOAD:
            err_bytes = b"ERROR: Payload exceeds max limit"
            conn.sendall(struct.pack('>I', len(err_bytes)) + err_bytes)
            return

        # Read exact payload
        data = b''
        while len(data) < payload_length:
            to_read = min(BUFFER_SIZE, payload_length - len(data))
            chunk = conn.recv(to_read)
            if not chunk:
                break
            data += chunk

        payload = data.decode('utf-8', errors='replace')
        smart_mode = True
        if payload.startswith('SMART:0\n'):
            smart_mode = False
            payload = payload[8:]
        elif payload.startswith('SMART:1\n'):
            payload = payload[8:]

        result = process_text(payload, smart_mode)
        resp_bytes = result.encode('utf-8')
        conn.sendall(struct.pack('>I', len(resp_bytes)) + resp_bytes)
    except Exception as e:
        log(f"Error handling client: {e}")
        try:
            err_bytes = f"ERROR: {e}".encode('utf-8')
            conn.sendall(struct.pack('>I', len(err_bytes)) + err_bytes)
        except OSError:
            pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def run_daemon():
    """Run the daemon server."""
    SOCKET_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)

    if is_running():
        print(f"Daemon already running (PID: {get_pid()})")
        return

    server = None
    if USE_UNIX_SOCKET:
        try:
            if SOCKET_PATH.exists():
                SOCKET_PATH.unlink()
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(SOCKET_PATH))
        except OSError as e:
            log(f"AF_UNIX bind failed ({e}), falling back to TCP socket")
            server = None

    if server is None:
        if PORT_FILE.exists():
            PORT_FILE.unlink()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('127.0.0.1', 0))
        port = server.getsockname()[1]
        PORT_FILE.write_text(str(port))

    server.listen(128)
    server.settimeout(1.0)

    PID_FILE.write_text(str(os.getpid()))

    def cleanup():
        log("Daemon shutting down")
        try:
            server.close()
        except OSError:
            pass
        for p in (SOCKET_PATH, PORT_FILE, PID_FILE):
            try:
                p.unlink()
            except OSError:
                pass

    atexit.register(cleanup)
    try:
        signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
        signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    except (ValueError, AttributeError):
        pass

    log(f"Daemon started (PID: {os.getpid()})")
    print(f"Daemon started (PID: {os.getpid()})")

    last_activity = [time.time()]

    while True:
        try:
            conn, addr = server.accept()
            last_activity[0] = time.time()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
        except socket.timeout:
            if time.time() - last_activity[0] > IDLE_TIMEOUT:
                log(f"Idle timeout ({IDLE_TIMEOUT}s), shutting down")
                print(f"Idle timeout, shutting down")
                break
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"Error: {e}")

    cleanup()


def spawn_daemon_bg():
    """Spawn daemon in background detaching std file descriptors cross-platform."""
    SOCKET_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
    if hasattr(os, 'fork'):
        pid = os.fork()
        if pid > 0:
            return  # Parent process returns

        os.setsid()
        pid2 = os.fork()
        if pid2 > 0:
            os._exit(0)

        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        if devnull > 2:
            os.close(devnull)
        run_daemon()
        os._exit(0)
    else:
        cmd = [sys.executable, str(Path(__file__).resolve()), 'run-server']
        creationflags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
        subprocess.Popen(cmd, creationflags=creationflags, close_fds=True)


def send_to_daemon(text, smart_mode=True, _retry=True):
    """Send text to running daemon and get result using length-prefix framing."""
    if not is_running():
        # Ensure stale artifacts cleared before spawn
        for p in (SOCKET_PATH, PORT_FILE):
            try:
                p.unlink()
            except OSError:
                pass
        spawn_daemon_bg()
        for _ in range(30):
            time.sleep(0.1)
            if is_running() and (SOCKET_PATH.exists() or (PORT_FILE.exists() and PORT_FILE.stat().st_size > 0)):
                break
        if not is_running():
            raise RuntimeError("Failed to start daemon")

    header = b'SMART:1\n' if smart_mode else b'SMART:0\n'
    payload = header + text.encode('utf-8')
    len_prefix = struct.pack('>I', len(payload))

    try:
        if SOCKET_PATH.exists():
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(str(SOCKET_PATH))
        else:
            port = None
            for _ in range(10):
                try:
                    txt = PORT_FILE.read_text().strip()
                    if txt:
                        port = int(txt)
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(0.1)
            if port is None:
                raise RuntimeError("Daemon socket/port unavailable")
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(('127.0.0.1', port))

        client.sendall(len_prefix + payload)

        # Read response length
        raw_len = b''
        while len(raw_len) < 4:
            chunk = client.recv(4 - len(raw_len))
            if not chunk:
                break
            raw_len += chunk

        if len(raw_len) < 4:
            client.close()
            return ""

        resp_len = struct.unpack('>I', raw_len)[0]
        resp_data = b''
        while len(resp_data) < resp_len:
            to_read = min(BUFFER_SIZE, resp_len - len(resp_data))
            chunk = client.recv(to_read)
            if not chunk:
                break
            resp_data += chunk

        client.close()
        return resp_data.decode('utf-8', errors='replace')
    except Exception as e:
        if _retry:
            stop_daemon()
            time.sleep(0.2)
            return send_to_daemon(text, smart_mode=smart_mode, _retry=False)
        raise RuntimeError(f"Error communicating with daemon: {e}")


def main():
    _configure_std_streams()
    if len(sys.argv) < 2:
        print("Usage: arabic-rtl-daemon {start|stop|status|restart|process|run-server}")
        print("")
        print("Commands:")
        print("  start       Start daemon in background")
        print("  stop        Stop daemon")
        print("  status      Check if daemon is running")
        print("  restart     Restart daemon")
        print("  process     Process text from stdin (auto-starts daemon)")
        print("  run-server  Run server in foreground")
        sys.exit(1)

    command = sys.argv[1]

    if command in ("start", "run-server"):
        if command == "start":
            if is_running():
                print(f"Daemon already running (PID: {get_pid()})")
            else:
                spawn_daemon_bg()
                for _ in range(20):
                    time.sleep(0.1)
                    if is_running():
                        break
                if is_running():
                    print(f"Daemon started (PID: {get_pid()})")
                else:
                    print("Failed to start daemon")
                    sys.exit(1)
        else:
            run_daemon()

    elif command == "stop":
        stop_daemon()

    elif command == "status":
        if is_running():
            print(f"Daemon running (PID: {get_pid()})")
            if USE_UNIX_SOCKET:
                print(f"Socket: {SOCKET_PATH}")
            else:
                try:
                    print(f"Port: {PORT_FILE.read_text().strip()}")
                except OSError:
                    pass
            print(f"Log: {LOG_FILE}")
        else:
            print("Daemon not running")

    elif command == "restart":
        stop_daemon()
        time.sleep(0.5)
        spawn_daemon_bg()
        for _ in range(20):
            time.sleep(0.1)
            if is_running():
                break
        if is_running():
            print(f"Daemon restarted (PID: {get_pid()})")
        else:
            print("Failed to restart daemon")
            sys.exit(1)

    elif command == "process":
        smart_mode = "--no-smart" not in sys.argv[2:]
        text = sys.stdin.read()
        result = send_to_daemon(text, smart_mode=smart_mode)
        print(result, end='')

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
