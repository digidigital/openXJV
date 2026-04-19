import os
import sys
from typing import Tuple, Optional


def _is_in_bundle() -> bool:
    """True when running inside a PyInstaller or AppImage bundle."""
    return (
        getattr(sys, "frozen", False)
        or bool(os.environ.get("OPENXJV_APPIMAGE"))
        or bool(os.environ.get("APPIMAGE"))
    )


def check_token_from_env() -> Tuple[bool, Optional[str]]:
    if _is_in_bundle():
        from openxjv.utils.token_validator.validate_binary import check_token_from_env_binary
        return check_token_from_env_binary()
    return (False, None)


def is_token_valid(settings_manager) -> bool:
    if _is_in_bundle():
        from openxjv.utils.token_validator.validate_binary import is_token_valid_binary
        return is_token_valid_binary(settings_manager)
    return False
