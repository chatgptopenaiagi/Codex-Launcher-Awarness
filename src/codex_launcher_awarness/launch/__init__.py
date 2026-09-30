"""Child-only Windows launch. No GUI dependency and no launch on import."""
from .manager import LaunchError, LaunchManager, LaunchRequest, PreparedLaunch, create_desktop_shortcut

__all__ = ["LaunchError", "LaunchManager", "LaunchRequest", "PreparedLaunch", "create_desktop_shortcut"]
