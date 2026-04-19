"""
validate_binary.py — token validation via the compiled openxjv_validator binary.

Called from maintenance_token.py (check_token_from_env / is_token_valid) and
directly from maintenance_dialog.py (check_token_via_binary).
Only active in frozen AppImage / PyInstaller builds.

Binary location discovery (in priority order)
----------------------------------------------
1. PyInstaller frozen build  — same directory as sys.executable
     Windows: dist/openXJV/openxjv_validator.exe
2. AppImage                  — $HERE/usr/bin/ is prepended to PATH by AppRun,
                               so shutil.which() finds it automatically.
3. Development / local build — same directory as this file
                               (after running build.sh locally)
"""
import os
import shutil
import subprocess
import sys
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------

def _binary_name() -> str:
    return "openxjv_validator.exe" if sys.platform == "win32" else "openxjv_validator"


def _find_validator() -> Optional[str]:
    """Returns the absolute path to openxjv_validator, or None if not found."""
    name = _binary_name()

    # 1. PyInstaller: binaries with dest '.' land in sys._MEIPASS (_internal/).
    #    Older PyInstaller placed them next to sys.executable — check both.
    if getattr(sys, "frozen", False):
        for base in filter(None, [getattr(sys, "_MEIPASS", None),
                                  os.path.dirname(sys.executable)]):
            candidate = os.path.join(base, name)
            if os.path.isfile(candidate):
                return candidate

    # 2. AppImage: AppRun exports $HERE/usr/bin at the front of PATH.
    found = shutil.which(name)
    if found:
        return found

    # 3. Development: binary built locally next to this file.
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(here, name)
    if os.path.isfile(candidate):
        return candidate

    return None


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

def check_token_via_binary(email: str, token: str) -> bool:
    """Calls the validator binary and returns True if the pair is valid.

    Falls back to False (not an exception) if the binary is missing or crashes,
    so the caller can decide whether to try the Python fallback.
    """
    binary = _find_validator()
    if binary is None:
        return False
    try:
        kwargs: dict = {"capture_output": True, "timeout": 5}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            [binary, email.strip().lower(), token.strip()],
            **kwargs,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Public API — same signatures as maintenance_token.py
# ---------------------------------------------------------------------------

def check_token_from_env_binary() -> Tuple[bool, Optional[str]]:
    """Reads OPENXJV_MAINTENANCE_TOKEN and validates via the compiled binary."""
    env_value = os.environ.get("OPENXJV_MAINTENANCE_TOKEN", "")
    if "," in env_value:
        parts = env_value.split(",", 1)
        email = parts[0].strip()
        token = parts[1].strip()
        if email and token and check_token_via_binary(email, token):
            return (True, email)
    return (False, None)


def check_token_from_settings_binary(settings_manager) -> Tuple[bool, Optional[str]]:
    """Reads token from QSettings and validates via the compiled binary."""
    email = settings_manager.get_string("maintenance_email", "")
    token = settings_manager.get_string("maintenance_token", "")
    if email and token and check_token_via_binary(email, token):
        return (True, email)
    return (False, None)


def is_token_valid_binary(settings_manager) -> bool:
    """Full validation via binary: env var first, then QSettings."""
    valid, _ = check_token_from_env_binary()
    if valid:
        return True
    valid, _ = check_token_from_settings_binary(settings_manager)
    return valid
