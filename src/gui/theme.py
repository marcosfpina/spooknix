"""Tema CSS do Spooknix Desktop (GTK4 + libadwaita).

Paleta industrial escura — Catppuccin Mocha adaptada para GTK CSS.
Carregado via Gtk.CssProvider no startup.

Uso:
    from src.gui.theme import load_css
    load_css()
"""

from __future__ import annotations

from pathlib import Path

CSS = """
/* === Spooknix GTK4 Theme — Industrial Dark === */

/* ── Base palette ────────────────────────────────────────────────── */
@define-color spk_base #1e1e2e;
@define-color spk_mantle #181825;
@define-color spk_surface0 #313244;
@define-color spk_surface1 #45475a;
@define-color spk_surface2 #585b70;
@define-color spk_text #cdd6f4;
@define-color spk_subtext0 #a6adc8;
@define-color spk_subtext1 #6c7086;
@define-color spk_blue #89b4fa;
@define-color spk_green #a6e3a1;
@define-color spk_red #f38ba8;
@define-color spk_yellow #f9e2af;
@define-color spk_lavender #b4befe;
@define-color spk_teal #94e2d5;
@define-color spk_peach #fab387;

/* ── Window ──────────────────────────────────────────────────────── */
window {
    background-color: @spk_base;
    color: @spk_text;
}

/* ── Headerbar ───────────────────────────────────────────────────── */
headerbar {
    background-color: @spk_mantle;
    border-bottom: 1px solid @spk_surface1;
    min-height: 38px;
}

/* ── Stack switcher (tabs) ───────────────────────────────────────── */
stackswitcher > button {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: @spk_subtext0;
    padding: 8px 16px;
    font-weight: 500;
}

stackswitcher > button:checked {
    color: @spk_blue;
    border-bottom: 2px solid @spk_blue;
}

stackswitcher > button:hover:not(:checked) {
    color: @spk_text;
    background: alpha(@spk_blue, 0.05);
}

/* ── Cards ───────────────────────────────────────────────────────── */
.card {
    background-color: @spk_surface0;
    border: 1px solid @spk_surface1;
    border-radius: 8px;
    padding: 12px;
}

.card:hover {
    border-color: @spk_surface2;
}

/* ── Buttons ─────────────────────────────────────────────────────── */
button {
    background-color: @spk_surface0;
    color: @spk_text;
    border: 1px solid @spk_surface1;
    border-radius: 6px;
    padding: 6px 14px;
}

button:hover {
    background-color: @spk_surface1;
    border-color: @spk_surface2;
}

button.suggested-action {
    background-color: @spk_blue;
    color: @spk_base;
    border: none;
    font-weight: 600;
}

button.destructive-action {
    background-color: @spk_red;
    color: @spk_base;
    border: none;
}

button.flat {
    background: transparent;
    border: 1px solid @spk_surface2;
    color: @spk_subtext0;
}

button.flat:hover {
    background: alpha(@spk_blue, 0.1);
    border-color: @spk_blue;
    color: @spk_blue;
}

/* ── Labels ──────────────────────────────────────────────────────── */
.title-1 {
    font-size: 20pt;
    font-weight: 700;
    color: @spk_text;
}

.title-2 {
    font-size: 15pt;
    font-weight: 600;
    color: @spk_subtext0;
}

.caption {
    font-size: 10pt;
    color: @spk_subtext1;
}

.metric-value {
    font-size: 22pt;
    font-weight: 700;
    color: @spk_blue;
}

.metric-label {
    font-size: 9pt;
    color: @spk_subtext0;
}

/* ── Progress bar (VRAM) ─────────────────────────────────────────── */
.level-bar block.filled {
    background-color: @spk_blue;
}

.level-bar block.empty {
    background-color: @spk_surface1;
}

/* ── Lists ───────────────────────────────────────────────────────── */
listview, listbox {
    background-color: transparent;
}

row {
    background-color: transparent;
    border-bottom: 1px solid @spk_surface1;
    padding: 6px 0;
}

row:hover {
    background-color: alpha(@spk_blue, 0.05);
}

/* ── Scrollbar ───────────────────────────────────────────────────── */
scrollbar slider {
    background-color: @spk_surface2;
    border-radius: 4px;
    min-width: 6px;
}

scrollbar slider:hover {
    background-color: @spk_subtext1;
}

/* ── Status dot ──────────────────────────────────────────────────── */
.status-dot-online {
    background-color: @spk_green;
    border-radius: 6px;
    min-width: 10px;
    min-height: 10px;
}

.status-dot-offline {
    background-color: @spk_red;
    border-radius: 6px;
    min-width: 10px;
    min-height: 10px;
}

/* ── Monospace ───────────────────────────────────────────────────── */
.mono {
    font-family: "JetBrains Mono", "Fira Code", "Iosevka", monospace;
    font-size: 0.9em;
}
"""


def load_css() -> None:
    """Carrega o CSS customizado no Gtk.CssProvider global."""
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gdk, Gtk

    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode("utf-8"))

    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
