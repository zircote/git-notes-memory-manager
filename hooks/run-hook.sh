#!/usr/bin/env bash
# Hook runner with automatic venv bootstrap
# Usage: run-hook.sh <hook-script.py>
#
# This wrapper ensures the virtual environment exists and dependencies
# are installed before running any hook script. It handles:
# - venv creation via uv
# - dependency installation
# - stdin passthrough for hook input
# - proper error handling

set -euo pipefail

# Get the plugin root (parent of hooks directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="${SCRIPT_DIR%/hooks}"
VENV_DIR="${PLUGIN_ROOT}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python3"
HOOK_SCRIPT="${1:-}"
BOOTSTRAP_MARKER="${PLUGIN_ROOT}/.bootstrap_complete"

# Logging helper
log() {
    echo "[memory-plugin] $*" >&2
}

# Check if we need to bootstrap
needs_bootstrap() {
    # No venv = needs bootstrap
    [[ ! -d "${VENV_DIR}" ]] && return 0

    # No python = needs bootstrap
    [[ ! -x "${VENV_PYTHON}" ]] && return 0

    # No marker = needs bootstrap
    [[ ! -f "${BOOTSTRAP_MARKER}" ]] && return 0

    # Check if pyproject.toml is newer than marker
    if [[ -f "${PLUGIN_ROOT}/pyproject.toml" ]]; then
        if [[ "${PLUGIN_ROOT}/pyproject.toml" -nt "${BOOTSTRAP_MARKER}" ]]; then
            return 0
        fi
    fi

    return 1
}

# Find uv binary
find_uv() {
    # Check common locations
    for candidate in \
        "$(command -v uv 2>/dev/null)" \
        "${HOME}/.local/bin/uv" \
        "${HOME}/.cargo/bin/uv" \
        "/usr/local/bin/uv" \
        "/opt/homebrew/bin/uv"; do
        if [[ -x "$candidate" ]]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

# Bootstrap the virtual environment
bootstrap() {
    local uv_path

    # Find uv
    if ! uv_path=$(find_uv); then
        log "Error: uv not found. Install from https://docs.astral.sh/uv/"
        # Exit gracefully so hooks don't block Claude
        echo '{}'
        exit 0
    fi

    log "Bootstrapping plugin environment..."

    # Create venv if needed
    if [[ ! -d "${VENV_DIR}" ]]; then
        log "Creating virtual environment..."
        if ! "$uv_path" venv "${VENV_DIR}" --quiet 2>&1; then
            log "Failed to create venv"
            echo '{}'
            exit 0
        fi
    fi

    # Install dependencies into the venv
    log "Installing dependencies..."
    if ! "$uv_path" pip install --python "${VENV_PYTHON}" -e "${PLUGIN_ROOT}" --quiet 2>&1; then
        log "Failed to install dependencies"
        echo '{}'
        exit 0
    fi

    # Write bootstrap marker
    date -u +%Y-%m-%dT%H:%M:%SZ > "${BOOTSTRAP_MARKER}"

    log "Bootstrap complete"
}

# Main execution
main() {
    # Validate hook script argument
    if [[ -z "${HOOK_SCRIPT}" ]]; then
        log "Error: No hook script specified"
        echo '{}'
        exit 0
    fi

    # Resolve hook script path
    if [[ ! "${HOOK_SCRIPT}" = /* ]]; then
        HOOK_SCRIPT="${SCRIPT_DIR}/${HOOK_SCRIPT}"
    fi

    if [[ ! -f "${HOOK_SCRIPT}" ]]; then
        log "Error: Hook script not found: ${HOOK_SCRIPT}"
        echo '{}'
        exit 0
    fi

    # Bootstrap if needed
    if needs_bootstrap; then
        bootstrap
    fi

    # DEBUG: Capture stdin to debug file for troubleshooting
    local debug_dir="${PLUGIN_ROOT}/.debug"
    mkdir -p "${debug_dir}"
    local hook_name
    hook_name=$(basename "${HOOK_SCRIPT}" .py)
    local debug_file="${debug_dir}/${hook_name}_$(date +%s).json"

    # Read stdin into variable, write to debug file, then pipe to hook
    local stdin_content
    stdin_content=$(cat)
    echo "${stdin_content}" > "${debug_file}"
    echo "[DEBUG] Saved hook input to: ${debug_file}" >&2

    # Run the hook script with captured stdin
    echo "${stdin_content}" | exec "${VENV_PYTHON}" "${HOOK_SCRIPT}"
}

main "$@"
