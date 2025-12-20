#!/usr/bin/env python3
"""Bootstrap module for plugin hooks.

This module ensures the plugin's virtual environment is set up correctly
before any hook code runs. It handles:

1. Detecting if we're already running in the plugin's venv
2. Creating the venv with uv if it doesn't exist
3. Installing dependencies if needed
4. Re-executing the hook script using the venv's Python

Usage:
    Import this module at the very top of each hook entry point:

        #!/usr/bin/env python3
        import bootstrap  # noqa: F401 - side effect import
        # ... rest of hook code

    The import will either:
    - Do nothing (if already in venv)
    - Create venv, install deps, and re-exec (if not in venv)

Environment:
    MEMORY_PLUGIN_SKIP_BOOTSTRAP: Set to "1" to skip bootstrap (for testing)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Plugin root is parent of hooks directory
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = PLUGIN_ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "bin" / "python3"
PYPROJECT = PLUGIN_ROOT / "pyproject.toml"
LOCK_FILE = PLUGIN_ROOT / "uv.lock"


def _in_venv() -> bool:
    """Check if we're running inside the plugin's venv."""
    # Check if current Python is the venv Python
    current_python = Path(sys.executable).resolve()
    expected_python = VENV_PYTHON.resolve()

    # Also check for python (without 3) in case of symlinks
    venv_python_alt = VENV_DIR / "bin" / "python"

    return current_python == expected_python or current_python == venv_python_alt.resolve()


def _uv_available() -> bool:
    """Check if uv is available."""
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _create_venv() -> bool:
    """Create the virtual environment using uv.

    Returns:
        True if venv was created successfully, False otherwise.
    """
    try:
        # Create venv with uv
        result = subprocess.run(
            ["uv", "venv", str(VENV_DIR), "--python", "3.11"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(PLUGIN_ROOT),
        )
        if result.returncode != 0:
            print(f"[memory-plugin] Failed to create venv: {result.stderr}", file=sys.stderr)
            return False
        return True
    except subprocess.TimeoutExpired:
        print("[memory-plugin] Timeout creating venv", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[memory-plugin] Error creating venv: {e}", file=sys.stderr)
        return False


def _install_deps() -> bool:
    """Install dependencies into the venv using uv.

    Returns:
        True if deps were installed successfully, False otherwise.
    """
    try:
        # Try uv sync first (works if uv.lock exists)
        result = subprocess.run(
            ["uv", "sync", "--frozen"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PLUGIN_ROOT),
        )
        if result.returncode == 0:
            return True

        # Try uv sync without frozen
        result = subprocess.run(
            ["uv", "sync"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PLUGIN_ROOT),
        )
        if result.returncode == 0:
            return True

        # Fallback: use uv pip install directly
        result = subprocess.run(
            ["uv", "pip", "install", "-e", "."],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PLUGIN_ROOT),
            env={**os.environ, "VIRTUAL_ENV": str(VENV_DIR)},
        )
        if result.returncode == 0:
            return True

        # Last resort: install without editable mode
        result = subprocess.run(
            ["uv", "pip", "install", "."],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PLUGIN_ROOT),
            env={**os.environ, "VIRTUAL_ENV": str(VENV_DIR)},
        )
        if result.returncode != 0:
            print(f"[memory-plugin] Failed to install deps: {result.stderr}", file=sys.stderr)
            return False
        return True
    except subprocess.TimeoutExpired:
        print("[memory-plugin] Timeout installing deps", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[memory-plugin] Error installing deps: {e}", file=sys.stderr)
        return False


def _reexec() -> None:
    """Re-execute the current script using the venv Python.

    This replaces the current process with the venv Python running
    the same script with the same arguments.
    """
    # Get the original script that was invoked
    script = sys.argv[0]

    # Build the new command
    cmd = [str(VENV_PYTHON), script] + sys.argv[1:]

    # Set environment to indicate we've bootstrapped
    env = os.environ.copy()
    env["MEMORY_PLUGIN_BOOTSTRAPPED"] = "1"

    # Replace current process
    os.execve(str(VENV_PYTHON), cmd, env)


def _needs_install() -> bool:
    """Check if dependencies need to be installed.

    Returns:
        True if deps need installation, False if already installed.
    """
    # Check if the package is importable from the venv
    try:
        result = subprocess.run(
            [str(VENV_PYTHON), "-c", "import git_notes_memory"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode != 0
    except Exception:
        return True


def bootstrap() -> None:
    """Main bootstrap function.

    This is called automatically on module import. It ensures the venv
    exists and has deps installed, then re-execs using the venv Python.
    """
    # Skip if disabled
    if os.environ.get("MEMORY_PLUGIN_SKIP_BOOTSTRAP") == "1":
        return

    # Skip if we've already bootstrapped (prevents infinite loop)
    if os.environ.get("MEMORY_PLUGIN_BOOTSTRAPPED") == "1":
        return

    # Skip if already in venv
    if _in_venv():
        return

    # Check if uv is available
    if not _uv_available():
        print("[memory-plugin] uv not found, cannot bootstrap", file=sys.stderr)
        # Exit gracefully for hooks
        import json
        print(json.dumps({"continue": True}))
        sys.exit(0)

    # Create venv if it doesn't exist
    if not VENV_PYTHON.exists():
        print("[memory-plugin] Creating virtual environment...", file=sys.stderr)
        if not _create_venv():
            import json
            print(json.dumps({"continue": True}))
            sys.exit(0)

    # Install deps if needed
    if _needs_install():
        print("[memory-plugin] Installing dependencies...", file=sys.stderr)
        if not _install_deps():
            import json
            print(json.dumps({"continue": True}))
            sys.exit(0)

    # Re-exec with venv Python
    _reexec()


# Run bootstrap on import
bootstrap()
