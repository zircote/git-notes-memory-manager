#!/usr/bin/env python3
"""Bootstrap module for plugin hooks - MUST BE FIRST IMPORT.

This module ensures the plugin's virtual environment is correctly set up
and that ALL hook code runs in a consistent, reliable, predictable manner
regardless of:
- Where the plugin is installed
- How it's invoked (which Python, which shell)
- What state the environment is in

CRITICAL: Import this module FIRST in every hook entry point:
    import bootstrap  # noqa: F401

The bootstrap will:
1. Detect if we're already in the correct venv -> continue
2. If venv doesn't exist -> create it with uv
3. If deps not installed -> install them
4. Re-execute the SAME script with venv Python, preserving stdin

Environment Variables:
    MEMORY_PLUGIN_SKIP_BOOTSTRAP: Set to "1" to skip (testing only)
    MEMORY_PLUGIN_BOOTSTRAPPED: Set internally to prevent loops
"""

import fcntl
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# =============================================================================
# CONSTANTS - Derived from this file's location
# =============================================================================

# Plugin root is ALWAYS parent of hooks directory (where this file lives)
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = PLUGIN_ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "bin" / "python3"
VENV_PYTHON_ALT = VENV_DIR / "bin" / "python"
PYPROJECT = PLUGIN_ROOT / "pyproject.toml"
LOCK_FILE = PLUGIN_ROOT / "uv.lock"
BOOTSTRAP_LOCK = PLUGIN_ROOT / ".bootstrap.lock"
BOOTSTRAP_MARKER = PLUGIN_ROOT / ".bootstrap_complete"


# =============================================================================
# DETECTION FUNCTIONS
# =============================================================================

def _get_current_python() -> Path:
    """Get the resolved path of the currently running Python."""
    return Path(sys.executable).resolve()


def _in_correct_venv() -> bool:
    """Check if we're running inside THIS plugin's venv.

    Must match the exact venv for this plugin installation,
    not just any venv.
    """
    current = _get_current_python()

    # Check both python3 and python symlinks
    expected_paths = [
        VENV_PYTHON.resolve() if VENV_PYTHON.exists() else None,
        VENV_PYTHON_ALT.resolve() if VENV_PYTHON_ALT.exists() else None,
    ]

    return current in [p for p in expected_paths if p is not None]


def _venv_exists() -> bool:
    """Check if a valid venv exists."""
    return VENV_PYTHON.exists() or VENV_PYTHON_ALT.exists()


def _venv_python_path() -> Path:
    """Get the path to the venv Python executable."""
    if VENV_PYTHON.exists():
        return VENV_PYTHON
    if VENV_PYTHON_ALT.exists():
        return VENV_PYTHON_ALT
    return VENV_PYTHON  # Default for creation


def _deps_installed() -> bool:
    """Check if dependencies are installed in the venv."""
    if not _venv_exists():
        return False

    venv_python = _venv_python_path()
    try:
        result = subprocess.run(
            [str(venv_python), "-c", "import git_notes_memory; print('ok')"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(PLUGIN_ROOT),
        )
        return result.returncode == 0 and "ok" in result.stdout
    except Exception:
        # Subprocess failures indicate deps not installed; return False
        return False


def _pyproject_hash() -> str:
    """Get a hash of pyproject.toml for change detection."""
    if not PYPROJECT.exists():
        return ""
    try:
        content = PYPROJECT.read_bytes()
        return hashlib.sha256(content).hexdigest()[:16]
    except Exception:
        # File read errors return empty hash; triggers re-bootstrap
        return ""


def _bootstrap_current() -> bool:
    """Check if bootstrap marker is current with pyproject.toml."""
    if not BOOTSTRAP_MARKER.exists():
        return False
    try:
        marker_hash = BOOTSTRAP_MARKER.read_text().strip()
        return marker_hash == _pyproject_hash()
    except Exception:
        # Marker read errors indicate stale bootstrap; return False
        return False


# =============================================================================
# TOOL DETECTION
# =============================================================================

def _find_uv() -> str | None:
    """Find the uv executable."""
    # Try common locations
    candidates = [
        "uv",  # In PATH
        os.path.expanduser("~/.cargo/bin/uv"),
        os.path.expanduser("~/.local/bin/uv"),
        "/usr/local/bin/uv",
        "/opt/homebrew/bin/uv",
    ]

    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
            continue

    return None


def _find_python() -> str | None:
    """Find a suitable Python for venv creation."""
    # Prefer Python 3.11+ but accept 3.9+
    candidates = [
        "python3.13", "python3.12", "python3.11", "python3.10", "python3.9",
        "python3", "python",
    ]

    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Verify it's Python 3.9+
                version = result.stdout.strip()
                if "Python 3." in version:
                    parts = version.split()[1].split(".")
                    if len(parts) >= 2 and int(parts[1]) >= 9:
                        return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
            continue

    return None


# =============================================================================
# VENV CREATION AND SETUP
# =============================================================================

def _create_venv(uv_path: str) -> bool:
    """Create the virtual environment."""
    python = _find_python()
    if not python:
        _log("No suitable Python found (need 3.9+)")
        return False

    try:
        # Remove existing broken venv
        if VENV_DIR.exists():
            shutil.rmtree(VENV_DIR)

        _log(f"Creating venv with {python}...")
        result = subprocess.run(
            [uv_path, "venv", str(VENV_DIR), "--python", python],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PLUGIN_ROOT),
        )

        if result.returncode != 0:
            _log(f"Failed to create venv: {result.stderr}")
            return False

        return _venv_exists()
    except subprocess.TimeoutExpired:
        _log("Timeout creating venv")
        return False
    except Exception as e:
        _log(f"Error creating venv: {e}")
        return False


def _install_deps(uv_path: str) -> bool:
    """Install dependencies into the venv."""
    if not _venv_exists():
        return False

    _log("Installing dependencies...")

    # Set up environment for uv
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(VENV_DIR)
    env["PATH"] = f"{VENV_DIR}/bin:{env.get('PATH', '')}"

    try:
        # Method 1: uv sync (if lock file exists)
        if LOCK_FILE.exists():
            result = subprocess.run(
                [uv_path, "sync", "--frozen"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(PLUGIN_ROOT),
                env=env,
            )
            if result.returncode == 0:
                return True

        # Method 2: uv sync without frozen
        result = subprocess.run(
            [uv_path, "sync"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PLUGIN_ROOT),
            env=env,
        )
        if result.returncode == 0:
            return True

        # Method 3: uv pip install -e .
        result = subprocess.run(
            [uv_path, "pip", "install", "-e", "."],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PLUGIN_ROOT),
            env=env,
        )
        if result.returncode == 0:
            return True

        # Method 4: uv pip install . (non-editable)
        result = subprocess.run(
            [uv_path, "pip", "install", "."],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PLUGIN_ROOT),
            env=env,
        )
        if result.returncode == 0:
            return True

        _log(f"All install methods failed: {result.stderr}")
        return False

    except subprocess.TimeoutExpired:
        _log("Timeout installing deps")
        return False
    except Exception as e:
        _log(f"Error installing deps: {e}")
        return False


def _write_bootstrap_marker() -> None:
    """Write marker indicating successful bootstrap."""
    try:
        BOOTSTRAP_MARKER.write_text(_pyproject_hash())
    except Exception:
        pass  # Non-critical


# =============================================================================
# RE-EXECUTION
# =============================================================================

def _preserve_stdin() -> str | None:
    """Read and preserve stdin content for re-exec."""
    try:
        # Check if stdin has data (non-blocking check)
        if sys.stdin.isatty():
            return None

        # Read all stdin
        return sys.stdin.read()
    except Exception:
        return None


def _reexec_with_venv(stdin_data: str | None) -> None:
    """Re-execute the current script using the venv Python.

    This replaces the current process entirely.
    """
    venv_python = _venv_python_path()
    script = Path(sys.argv[0]).resolve()

    # Build environment
    env = os.environ.copy()
    env["MEMORY_PLUGIN_BOOTSTRAPPED"] = "1"
    env["VIRTUAL_ENV"] = str(VENV_DIR)
    env["PATH"] = f"{VENV_DIR}/bin:{env.get('PATH', '')}"

    if stdin_data:
        # Need to pass stdin to the new process
        # Use a temp file to preserve stdin across exec
        with tempfile.NamedTemporaryFile(mode='w', suffix='.stdin', delete=False) as f:
            f.write(stdin_data)
            stdin_file = f.name

        # Create a wrapper that reads from the temp file
        # and pipes to the actual script
        wrapper = f'''
import sys
import os
with open("{stdin_file}", "r") as f:
    stdin_data = f.read()
os.unlink("{stdin_file}")

import subprocess
result = subprocess.run(
    ["{venv_python}", "{script}"] + sys.argv[1:],
    input=stdin_data,
    text=True,
    capture_output=False,
    env={{**os.environ, "MEMORY_PLUGIN_BOOTSTRAPPED": "1"}},
)
sys.exit(result.returncode)
'''
        os.execve(
            str(venv_python),
            [str(venv_python), "-c", wrapper] + sys.argv[1:],
            env,
        )
    else:
        # No stdin, simple exec
        os.execve(
            str(venv_python),
            [str(venv_python), str(script)] + sys.argv[1:],
            env,
        )


# =============================================================================
# LOCKING (prevent concurrent bootstraps)
# =============================================================================

def _acquire_lock() -> int | None:
    """Acquire bootstrap lock file."""
    try:
        fd = os.open(str(BOOTSTRAP_LOCK), os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except (OSError, IOError):
        # Another process is bootstrapping, wait for it
        try:
            fd = os.open(str(BOOTSTRAP_LOCK), os.O_CREAT | os.O_RDWR)
            fcntl.flock(fd, fcntl.LOCK_EX)  # Blocking wait
            return fd
        except Exception:
            # Lock acquisition failed - proceed without lock (rare edge case)
            return None


def _release_lock(fd: int | None) -> None:
    """Release bootstrap lock file."""
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        except Exception:
            # Cleanup errors are non-fatal; fd may already be closed
            pass


# =============================================================================
# LOGGING
# =============================================================================

def _log(message: str) -> None:
    """Log a message to stderr."""
    print(f"[memory-plugin] {message}", file=sys.stderr)


# =============================================================================
# GRACEFUL EXIT
# =============================================================================

def _exit_gracefully() -> None:
    """Exit gracefully, allowing hooks to continue without blocking."""
    import json
    print(json.dumps({"continue": True}))
    sys.exit(0)


# =============================================================================
# MAIN BOOTSTRAP FUNCTION
# =============================================================================

def bootstrap() -> None:
    """Main bootstrap function - called automatically on import.

    This ensures the plugin runs in its venv with all deps installed.
    """
    # Skip if disabled (testing)
    if os.environ.get("MEMORY_PLUGIN_SKIP_BOOTSTRAP") == "1":
        return

    # Skip if already bootstrapped (re-exec completed)
    if os.environ.get("MEMORY_PLUGIN_BOOTSTRAPPED") == "1":
        return

    # Skip if already in correct venv with deps installed
    if _in_correct_venv() and _deps_installed():
        return

    # Need to bootstrap - preserve stdin first
    stdin_data = _preserve_stdin()

    # Check if bootstrap is current (already done, just need re-exec)
    if _bootstrap_current() and _venv_exists() and _deps_installed():
        _reexec_with_venv(stdin_data)
        return  # Never reached

    # Find uv
    uv_path = _find_uv()
    if not uv_path:
        _log("uv not found - cannot bootstrap")
        _log("Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh")
        _exit_gracefully()
        return

    # Acquire lock to prevent concurrent bootstraps
    lock_fd = _acquire_lock()

    try:
        # Double-check after acquiring lock (another process might have completed)
        if _venv_exists() and _deps_installed():
            _write_bootstrap_marker()
            _release_lock(lock_fd)
            _reexec_with_venv(stdin_data)
            return

        # Create venv if needed
        if not _venv_exists():
            if not _create_venv(uv_path):
                _log("Failed to create venv")
                _exit_gracefully()
                return

        # Install deps if needed
        if not _deps_installed():
            if not _install_deps(uv_path):
                _log("Failed to install deps")
                _exit_gracefully()
                return

        # Mark bootstrap complete
        _write_bootstrap_marker()

    finally:
        _release_lock(lock_fd)

    # Re-exec with venv
    _reexec_with_venv(stdin_data)


# =============================================================================
# AUTO-RUN ON IMPORT
# =============================================================================

bootstrap()
