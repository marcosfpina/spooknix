"""Entry point do Spooknix Desktop (GTK4).

Gtk.Application com single-instance via Gio.ApplicationFlags.
"""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from src.gui.main_window import MainWindow
from src.gui.theme import load_css


class SpooknixApp(Adw.Application):
    """Aplicação GTK4 principal."""

    def __init__(self) -> None:
        super().__init__(
            application_id="io.voidnxlabs.spooknix",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self) -> None:
        load_css()
        window = MainWindow(app=self)
        window.present()

    def do_shutdown(self) -> None:
        super().do_shutdown()


def main() -> None:
    app = SpooknixApp()
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
