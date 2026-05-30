"""Páginas placeholder GTK4 para os Sprints 2-7."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


def _make_placeholder(title: str, subtitle: str, sprint: str) -> Gtk.Box:
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    page.set_margin_start(20)
    page.set_margin_end(20)
    page.set_margin_top(40)
    page.set_margin_bottom(40)

    badge = Gtk.Label(label=f"Sprint {sprint}")
    badge.add_css_class("caption")
    badge.set_halign(Gtk.Align.START)
    page.append(badge)

    tl = Gtk.Label(label=title)
    tl.add_css_class("title-1")
    tl.set_halign(Gtk.Align.START)
    page.append(tl)

    sl = Gtk.Label(label=subtitle)
    sl.add_css_class("caption")
    sl.set_wrap(True)
    sl.set_halign(Gtk.Align.START)
    page.append(sl)

    spacer = Gtk.Label()
    spacer.set_vexpand(True)
    page.append(spacer)

    icon = Gtk.Label(label="🚧")
    icon.set_halign(Gtk.Align.CENTER)
    page.append(icon)

    coming = Gtk.Label(label="Em desenvolvimento — próximo sprint")
    coming.set_halign(Gtk.Align.CENTER)
    coming.add_css_class("caption")
    page.append(coming)

    spacer2 = Gtk.Label()
    spacer2.set_vexpand(True)
    page.append(spacer2)

    return page


def create_record_page() -> Gtk.Box:
    return _make_placeholder(
        "Gravar Microfone",
        "Gravação ao vivo com audio meter, VAD neural (Silero) ou RMS, streaming WebSocket e transcrição em tempo real.",
        "3",
    )


def create_transcribe_page() -> Gtk.Box:
    return _make_placeholder(
        "Transcrever Arquivo",
        "Transcrição de arquivos de áudio e vídeo com suporte a diarização de speakers e exportação SRT/Markdown.",
        "2",
    )


def create_interview_page() -> Gtk.Box:
    return _make_placeholder(
        "Simulador de Entrevista",
        "Modo conversacional full-duplex com personas, cenários, LLM streaming e TTS local.",
        "5",
    )


def create_summarize_page() -> Gtk.Box:
    return _make_placeholder(
        "Summarizar Mídia",
        "Sumarização de vídeos, aulas e reuniões com timestamps clicáveis e templates Jinja2.",
        "6",
    )


def create_history_page() -> Gtk.Box:
    return _make_placeholder(
        "Histórico de Sessões",
        "Navegação pelo histórico de entrevistas salvas com diff side-by-side e relatórios detalhados.",
        "4",
    )
