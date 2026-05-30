"""Página Transcrever — GTK4.

File selection (drag-drop + button), language/model selectors,
diarization toggle, progress feedback, segment table, copy/save.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, GLib, Gtk

from src.gui.app_state import AppState
from src.gui.workers.transcribe_worker import SUPPORTED_MODELS, TranscribeWorker

LANGUAGES = [
    ("pt", "Português"),
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("zh", "中文"),
    ("ru", "Русский"),
    ("auto", "Auto-detect"),
]


def _format_time(s: float) -> str:
    m, sec = divmod(int(s), 60)
    return f"{m:02d}:{sec:02d}"


def _format_size(n_bytes: int) -> str:
    if n_bytes < 1024:
        return f"{n_bytes} B"
    elif n_bytes < 1024 * 1024:
        return f"{n_bytes / 1024:.1f} KB"
    else:
        return f"{n_bytes / (1024 * 1024):.1f} MB"


class TranscribePage(Gtk.Box):
    """Página de transcrição de arquivos."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._state = AppState.instance()
        self._file_path: str | None = None
        self._result: dict | None = None

        self.set_margin_start(20)
        self.set_margin_end(20)
        self.set_margin_top(20)
        self.set_margin_bottom(20)
        self.set_spacing(16)

        # ── Title ───────────────────────────────────────────────────────
        title = Gtk.Label(label="Transcrever Arquivo")
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        # ── Drop zone ───────────────────────────────────────────────────
        self._drop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._drop_box.add_css_class("card")
        self._drop_box.set_size_request(-1, 100)
        self._drop_box.set_halign(Gtk.Align.FILL)

        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("drop", self._on_drop)
        self._drop_box.add_controller(drop_target)

        drop_label = Gtk.Label(label="📂 Arraste um arquivo aqui ou clique para selecionar")
        drop_label.add_css_class("caption")
        drop_label.set_halign(Gtk.Align.CENTER)
        drop_label.set_valign(Gtk.Align.CENTER)
        drop_label.set_vexpand(True)
        self._drop_box.append(drop_label)

        btn = Gtk.Button(label="Selecionar arquivo…")
        btn.add_css_class("flat")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect("clicked", self._on_select_file)
        self._drop_box.append(btn)

        self.append(self._drop_box)

        # ── File info ───────────────────────────────────────────────────
        self._file_label = Gtk.Label(label="Nenhum arquivo selecionado")
        self._file_label.add_css_class("caption")
        self._file_label.set_halign(Gtk.Align.START)
        self.append(self._file_label)

        # ── Controls row ─────────────────────────────────────────────────
        controls = Gtk.Box(spacing=12)
        controls.set_halign(Gtk.Align.FILL)

        # Language
        lang_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lang_lbl = Gtk.Label(label="Idioma")
        lang_lbl.add_css_class("metric-label")
        lang_lbl.set_halign(Gtk.Align.START)
        lang_box.append(lang_lbl)
        self._lang_combo = Gtk.ComboBoxText()
        for code, name in LANGUAGES:
            self._lang_combo.append(code, name)
        self._lang_combo.set_active_id("pt")
        lang_box.append(self._lang_combo)
        controls.append(lang_box)

        # Model
        model_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        model_lbl = Gtk.Label(label="Modelo")
        model_lbl.add_css_class("metric-label")
        model_lbl.set_halign(Gtk.Align.START)
        model_box.append(model_lbl)
        self._model_combo = Gtk.ComboBoxText()
        self._model_combo.append("server", "Servidor (padrão)")
        for m in SUPPORTED_MODELS:
            self._model_combo.append(m, m)
        self._model_combo.set_active_id("server")
        model_box.append(self._model_combo)
        controls.append(model_box)

        # Diarization
        self._diarize_check = Gtk.CheckButton(label="Diarização")
        self._diarize_check.set_valign(Gtk.Align.END)
        controls.append(self._diarize_check)

        spacer = Gtk.Label()
        spacer.set_hexpand(True)
        controls.append(spacer)

        # Transcribe button
        self._transcribe_btn = Gtk.Button(label="▶ Transcrever")
        self._transcribe_btn.add_css_class("suggested-action")
        self._transcribe_btn.set_valign(Gtk.Align.END)
        self._transcribe_btn.connect("clicked", self._on_transcribe)
        self._transcribe_btn.set_sensitive(False)
        controls.append(self._transcribe_btn)

        self.append(controls)

        # ── Progress label ───────────────────────────────────────────────
        self._progress_label = Gtk.Label(label="")
        self._progress_label.add_css_class("caption")
        self._progress_label.set_halign(Gtk.Align.START)
        self.append(self._progress_label)

        # ── Results area ─────────────────────────────────────────────────
        self._results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._results_box.set_visible(False)

        # Full text
        self._full_text_label = Gtk.Label()
        self._full_text_label.set_wrap(True)
        self._full_text_label.set_selectable(True)
        self._full_text_label.set_xalign(0)
        self._full_text_label.add_css_class("card")
        self._full_text_label.set_margin_start(12)
        self._full_text_label.set_margin_end(12)
        self._full_text_label.set_margin_top(8)
        self._full_text_label.set_margin_bottom(8)
        self._results_box.append(self._full_text_label)

        # Segment header
        seg_header = Gtk.Label(label="Segmentos")
        seg_header.add_css_class("title-2")
        seg_header.set_halign(Gtk.Align.START)
        self._results_box.append(seg_header)

        # Segment list
        seg_scroll = Gtk.ScrolledWindow()
        seg_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        seg_scroll.set_min_content_height(200)
        self._seg_list = Gtk.ListBox()
        self._seg_list.add_css_class("card")
        self._seg_list.set_selection_mode(Gtk.SelectionMode.NONE)
        seg_scroll.set_child(self._seg_list)
        self._results_box.append(seg_scroll)

        # Action buttons
        actions = Gtk.Box(spacing=8)
        copy_btn = Gtk.Button(label="📋 Copiar texto")
        copy_btn.add_css_class("flat")
        copy_btn.connect("clicked", self._on_copy)
        actions.append(copy_btn)
        save_btn = Gtk.Button(label="💾 Salvar .srt")
        save_btn.add_css_class("flat")
        save_btn.connect("clicked", self._on_save_srt)
        actions.append(save_btn)
        self._results_box.append(actions)

        self.append(self._results_box)

        # ── Worker ───────────────────────────────────────────────────────
        self._worker = TranscribeWorker(
            server_url=self._state.server_url,
            on_result=self._on_result,
            on_error=self._on_error,
            on_progress=self._on_progress,
        )

    # ── File selection ──────────────────────────────────────────────────

    def _on_select_file(self, btn: Gtk.Button) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Selecionar arquivo de áudio/vídeo")
        dialog.open(
            self.get_root(),
            None,
            self._on_file_dialog_response,
        )

    def _on_file_dialog_response(self, dialog, result) -> None:
        try:
            gfile = dialog.open_finish(result)
            if gfile:
                self._set_file(gfile.get_path())
        except GLib.Error:
            pass

    def _on_drop(self, target, value, x, y) -> bool:
        files = value.get_files()
        if files:
            gfile = files.get_item(0)
            if gfile:
                self._set_file(gfile.get_path())
                return True
        return False

    def _set_file(self, path_str: str) -> None:
        path = Path(path_str)
        if not path.is_file():
            return

        self._file_path = path_str
        size = path.stat().st_size
        self._file_label.set_label(f"{path.name}  ·  {_format_size(size)}")
        self._transcribe_btn.set_sensitive(True)

        # Esconde resultados anteriores
        self._results_box.set_visible(False)

    # ── Transcribe ──────────────────────────────────────────────────────

    def _on_transcribe(self, btn: Gtk.Button) -> None:
        if not self._file_path:
            return

        lang_id = self._lang_combo.get_active_id() or "pt"
        model_id = self._model_combo.get_active_id()
        model = None if model_id == "server" else model_id
        diarize = self._diarize_check.get_active()

        self._transcribe_btn.set_sensitive(False)
        self._transcribe_btn.set_label("⏳ Transcrevendo…")
        self._progress_label.set_label("Enviando…")

        self._worker.transcribe(
            file_path=self._file_path,
            language=lang_id,
            model_size=model,
            diarize=diarize,
        )

    def _on_progress(self, msg: str) -> None:
        self._progress_label.set_label(msg)

    def _on_result(self, result: dict) -> None:
        self._transcribe_btn.set_sensitive(True)
        self._transcribe_btn.set_label("▶ Transcrever")
        self._progress_label.set_label("✅ Transcrição concluída")
        self._result = result

        # Full text
        text = result.get("text", "").strip()
        self._full_text_label.set_label(text)

        # Segments
        while True:
            row = self._seg_list.get_last_child()
            if row is None:
                break
            self._seg_list.remove(row)

        for seg in result.get("segments", []):
            seg_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            seg_box.set_margin_start(8)
            seg_box.set_margin_end(8)
            seg_box.set_margin_top(4)
            seg_box.set_margin_bottom(4)

            # Header: timestamp + speaker + confidence
            header = Gtk.Box(spacing=8)
            t_start = _format_time(float(seg.get("start", 0)))
            t_end = _format_time(float(seg.get("end", 0)))
            time_lbl = Gtk.Label(label=f"<b>{t_start} → {t_end}</b>")
            time_lbl.set_use_markup(True)
            header.append(time_lbl)

            speaker = seg.get("speaker", "")
            if speaker:
                spk = Gtk.Label(label=f"[{speaker[:20]}]")
                spk.add_css_class("caption")
                header.append(spk)

            spacer = Gtk.Label()
            spacer.set_hexpand(True)
            header.append(spacer)

            conf = seg.get("avg_confidence", 0)
            if conf:
                conf_lbl = Gtk.Label(label=f"{conf * 100:.0f}%")
                conf_lbl.add_css_class("caption")
                header.append(conf_lbl)

            seg_box.append(header)

            # Text
            seg_text = Gtk.Label(label=(seg.get("text") or "").strip())
            seg_text.set_wrap(True)
            seg_text.set_xalign(0)
            seg_text.set_selectable(True)
            seg_box.append(seg_text)

            self._seg_list.append(seg_box)

        # Show results
        self._results_box.set_visible(True)

    def _on_error(self, msg: str) -> None:
        self._transcribe_btn.set_sensitive(True)
        self._transcribe_btn.set_label("▶ Transcrever")
        self._progress_label.set_label(f"❌ Erro: {msg}")

    # ── Actions ─────────────────────────────────────────────────────────

    def _on_copy(self, btn: Gtk.Button) -> None:
        if self._result:
            text = self._result.get("text", "")
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(text)
            self._progress_label.set_label("📋 Texto copiado!")

    def _on_save_srt(self, btn: Gtk.Button) -> None:
        if not self._result:
            return

        segments = self._result.get("segments", [])
        if not segments:
            return

        # Build SRT content
        lines: list[str] = []
        for idx, seg in enumerate(segments, 1):
            start_s = float(seg.get("start", 0))
            end_s = float(seg.get("end", 0))
            text = (seg.get("text") or "").strip()
            start_ts = _srt_time(start_s)
            end_ts = _srt_time(end_s)
            lines.append(f"{idx}\n{start_ts} --> {end_ts}\n{text}\n")

        srt_content = "\n".join(lines)
        t = datetime.now().strftime("%Y%m%d-%H%M%S")
        default_name = f"spooknix-{t}.srt"

        dialog = Gtk.FileDialog()
        dialog.set_title("Salvar legenda SRT")
        dialog.set_initial_name(default_name)
        dialog.save(
            self.get_root(),
            None,
            lambda d, r: self._on_save_done(d, r, srt_content),
        )

    def _on_save_done(self, dialog, result, content: str) -> None:
        try:
            gfile = dialog.save_finish(result)
            if gfile:
                Path(gfile.get_path()).write_text(content, encoding="utf-8")
                self._progress_label.set_label(f"💾 Salvo em: {gfile.get_path()}")
        except GLib.Error:
            pass


def _srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
