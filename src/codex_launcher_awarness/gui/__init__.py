"""Optional desktop interface; the headless package never imports Qt."""


def main(argv=None):
    from .app import main as run
    return run(argv)


__all__ = ["main"]
