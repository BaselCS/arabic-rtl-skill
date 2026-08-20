#!/usr/bin/env python3
"""
Arabic RTL Processor - Daemon Mode

Keeps the process running in background for instant responses.
Auto-closes after 5 minutes of inactivity.

Usage:
    arabic-rtl-daemon start    # Start daemon in background
    arabic-rtl-daemon stop     # Stop daemon
    arabic-rtl-daemon status   # Check if running
    arabic-rtl-daemon restart  # Restart daemon

The daemon listens on a Unix socket and processes text on demand.
"""

import os
import sys
import time
import json
import socket
import signal
import atexit
import tempfile
from pathlib import Path

# Socket path
SOCKET_DIR = Path(tempfile.gettempdir()) / "arabic-rtl"
SOCKET_PATH = SOCKET_DIR / "daemon.sock"
PID_FILE = SOCKET_DIR / "daemon.pid"
LOG_FILE = SOCKET_DIR / "daemon.log"

# Config
IDLE_TIMEOUT = 300  # 5 minutes
BUFFER_SIZE = 1024 * 1024  # 1MB max message


def log(msg):
    """Write to log file."""
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except:
        pass


def is_running():
    """Check if daemon is running."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # Check if process exists
        return True
    except (ProcessLookupError, ValueError):
        # Clean up stale PID file
        try:
            PID_FILE.unlink()
        except:
            pass
        return False


def get_pid():
    """Get daemon PID."""
    try:
        return int(PID_FILE.read_text().strip())
    except:
        return None


def stop_daemon():
    """Stop the daemon."""
    if not is_running():
        print("Daemon not running")
        return

    pid = get_pid()
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        if is_running():
            os.kill(pid, signal.SIGKILL)
        print(f"Daemon stopped (PID: {pid})")
    except Exception as e:
        print(f"Error stopping daemon: {e}")

    # Clean up
    try:
        PID_FILE.unlink()
    except:
        pass
    try:
        SOCKET_PATH.unlink()
    except:
        pass


def process_text(text):
    """Process text through the Arabic RTL processor."""
    try:
        # Import the processor
        sys.path.insert(0, str(Path(__file__).parent))
        from arabic_rtl import process_text as rtl_process
        return rtl_process(text)
    except ImportError:
        # Fallback to CLI
        import subprocess
        result = subprocess.run(
            ['python3', str(Path(__file__).parent / 'arabic_rtl_cli.py'), '--quiet'],
            input=text, capture_output=True, text=True
        )
        return result.stdout


def handle_client(conn, addr):
    """Handle a client connection."""
    try:
        data = b''
        while True:
            chunk = conn.recv(BUFFER_SIZE)
            if not chunk:
                break
            data += chunk
            # Check for end marker
            if b'\n---END---\n' in data:
                break

        # Remove end marker
        text = data.decode('utf-8').replace('\n---END---\n', '')

        # Process
        result = process_text(text)

        # Send result
        conn.sendall(result.encode('utf-8'))
    except Exception as e:
        log(f"Error handling client: {e}")
        try:
            conn.sendall(f"ERROR: {e}".encode('utf-8'))
        except:
            pass
    finally:
        conn.close()


def run_daemon():
    """Run the daemon server."""
    # Create socket directory
    SOCKET_DIR.mkdir(exist_ok=True)

    # Check if already running
    if is_running():
        print(f"Daemon already running (PID: {get_pid()})")
        return

    # Create socket
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCKET_PATH))
    server.listen(5)
    server.settimeout(1.0)  # 1 second timeout for clean shutdown

    # Write PID
    PID_FILE.write_text(str(os.getpid()))

    # Register cleanup
    def cleanup():
        log("Daemon shutting down")
        server.close()
        try:
            SOCKET_PATH.unlink()
        except:
            pass
        try:
            PID_FILE.unlink()
        except:
            pass

    atexit.register(cleanup)
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    log(f"Daemon started (PID: {os.getpid()})")
    print(f"Daemon started (PID: {os.getpid()})")

    last_activity = time.time()

    while True:
        try:
            conn, addr = server.accept()
            last_activity = time.time()
            handle_client(conn, addr)
        except socket.timeout:
            # Check idle timeout
            if time.time() - last_activity > IDLE_TIMEOUT:
                log(f"Idle timeout ({IDLE_TIMEOUT}s), shutting down")
                print(f"Idle timeout, shutting down")
                break
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"Error: {e}")

    cleanup()


def send_to_daemon(text):
    """Send text to running daemon and get result."""
    if not is_running():
        # Auto-start daemon
        print("Starting daemon...", file=sys.stderr)
        pid = os.fork()
        if pid == 0:
            # Child process - become daemon
            os.setsid()
            run_daemon()
            sys.exit(0)
        else:
            # Parent process - wait for daemon to start
            time.sleep(1)
            if not is_running():
                print("Failed to start daemon", file=sys.stderr)
                sys.exit(1)

    # Connect to daemon
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(SOCKET_PATH))
        client.sendall(text.encode('utf-8') + b'\n---END---\n')

        # Receive result
        result = b''
        while True:
            chunk = client.recv(BUFFER_SIZE)
            if not chunk:
                break
            result += chunk

        client.close()
        return result.decode('utf-8')
    except Exception as e:
        print(f"Error communicating with daemon: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: arabic-rtl-daemon {start|stop|status|restart|process}")
        print("")
        print("Commands:")
        print("  start    Start daemon in background")
        print("  stop     Stop daemon")
        print("  status   Check if daemon is running")
        print("  restart  Restart daemon")
        print("  process  Process text from stdin (auto-starts daemon)")
        sys.exit(1)

    command = sys.argv[1]

    if command == "start":
        if is_running():
            print(f"Daemon already running (PID: {get_pid()})")
        else:
            pid = os.fork()
            if pid == 0:
                os.setsid()
                run_daemon()
                sys.exit(0)
            else:
                time.sleep(1)
                if is_running():
                    print(f"Daemon started (PID: {get_pid()})")
                else:
                    print("Failed to start daemon")
                    sys.exit(1)

    elif command == "stop":
        stop_daemon()

    elif command == "status":
        if is_running():
            print(f"Daemon running (PID: {get_pid()})")
            print(f"Socket: {SOCKET_PATH}")
            print(f"Log: {LOG_FILE}")
        else:
            print("Daemon not running")

    elif command == "restart":
        stop_daemon()
        time.sleep(0.5)
        pid = os.fork()
        if pid == 0:
            os.setsid()
            run_daemon()
            sys.exit(0)
        else:
            time.sleep(1)
            if is_running():
                print(f"Daemon restarted (PID: {get_pid()})")
            else:
                print("Failed to restart daemon")
                sys.exit(1)

    elif command == "process":
        # Read from stdin
        text = sys.stdin.read()
        result = send_to_daemon(text)
        print(result, end='')

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
