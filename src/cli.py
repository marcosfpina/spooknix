# src/cli.py
"""CLI do Spooknix — Privacy-first STT Engine."""

import json
import logging
import os
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, BarColumn, TimeRemainingColumn

from .logging_setup import configure_logging

console = Console(stderr=True)
out_console = Console()


def _apply_verbose(verbose: int) -> None:
    """Map -v/-vv to INFO/DEBUG, no flag = WARNING (silent)."""
    if verbose >= 2:
        level = logging.DEBUG
    elif verbose == 1:
        level = logging.INFO
    else:
        level = logging.WARNING
    configure_logging(level=level, force=True)


@click.group()
def cli():
    """Spooknix — Privacy-first Speech-to-Text Engine."""
    pass


@cli.command()
@click.option("-v", "--verbose", count=True,
              help="Logs em tempo real (-v INFO, -vv DEBUG).")
def info(verbose):
    """Mostra status do sistema: GPU, VRAM e modelos disponíveis."""
    _apply_verbose(verbose)
    import torch

    table = Table(title="Spooknix — System Info", show_header=False, min_width=52)
    table.add_column("Campo", style="bold cyan")
    table.add_column("Valor")

    cuda = torch.cuda.is_available()
    table.add_row("CUDA", "✅ disponível" if cuda else "❌ não disponível")
    if cuda:
        table.add_row("GPU", torch.cuda.get_device_name(0))
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        table.add_row("VRAM", f"{vram_gb:.1f} GB")

    table.add_row(
        "Modelos",
        "tiny (~1GB) · base (~1GB) · small (~2GB) · medium (~5GB) · large-v3 (~3GB int8_float16) ← recomendado",
    )
    table.add_row("Idioma padrão", "pt (Português)")

    out_console.print(table)


@cli.command()
@click.argument("audio_path", type=click.Path(exists=True))
@click.option("--language", "-l", default="pt", show_default=True,
              help="Código do idioma (pt, en, es, …)")
@click.option("--model", "-m",
              type=click.Choice(["tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo"]),
              default="large-v3", show_default=True,
              help="Tamanho do modelo Whisper")
@click.option("--output-dir", "-o", default="outputs", show_default=True,
              type=click.Path(),
              help="Diretório raiz para os arquivos de saída")
@click.option("--format", "-f", "fmt",
              type=click.Choice(["txt", "srt", "json", "all"]),
              default="all", show_default=True,
              help="Formato(s) de saída")
@click.option("-v", "--verbose", count=True,
              help="Logs em tempo real (-v INFO, -vv DEBUG).")
def file(audio_path, language, model, output_dir, fmt, verbose):
    """Transcreve um arquivo de áudio ou vídeo."""
    _apply_verbose(verbose)
    from .transcriber import get_model, transcribe_file, generate_srt
    import torch

    stem = Path(audio_path).stem
    output_base = Path(output_dir)

    # Carrega o modelo
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Carregando modelo '{model}'…", total=None)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        m = get_model(model, device)

    console.print(
        f"[bold cyan]►[/bold cyan] Modelo [bold]{model}[/bold] "
        f"no dispositivo [bold]{device}[/bold]\n"
    )

    # Transcreve
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("Transcrevendo...", total=100.0)

        def on_progress_cb(current, total):
            if total > 0:
                progress.update(task_id, completed=(current / total) * 100.0)

        result = transcribe_file(m, audio_path, language=language, on_progress=on_progress_cb)

    # Persiste outputs
    saved = []

    if fmt in ("txt", "all"):
        out = output_base / "transcripts" / f"{stem}.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result["text"], encoding="utf-8")
        saved.append(str(out))

    if fmt in ("srt", "all"):
        out = output_base / "subtitles" / f"{stem}.srt"
        out.parent.mkdir(parents=True, exist_ok=True)
        generate_srt(result["segments"], str(out))
        saved.append(str(out))

    if fmt in ("json", "all"):
        out = output_base / "transcripts" / f"{stem}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        saved.append(str(out))

    # Resumo final
    files_list = "\n".join(f"  {p}" for p in saved)
    console.print(
        Panel(
            f"[green]Idioma:[/green]    {result['language']}\n"
            f"[green]Duração:[/green]   {result['duration']:.1f}s\n"
            f"[green]Segmentos:[/green] {len(result['segments'])}\n"
            f"[green]Arquivos:[/green]\n{files_list}",
            title="✅ Transcrição concluída",
            border_style="green",
        )
    )



@cli.command()
@click.option("--mic/--no-mic", default=False,
              help="Gravar 1s do microfone para baseline de RMS (precisa de áudio funcional).")
@click.option("--brev/--no-brev", default=False,
              help="Modo Brev: sondas STT + LLM:8080 + TTS:8001 (companion workers).")
@click.option("-v", "--verbose", count=True,
              help="Logs em tempo real (-v INFO, -vv DEBUG).")
def doctor(mic, brev, verbose):
    """Verifica ambiente: CUDA, STT server, áudio, ffmpeg, llama.cpp (ou workers Brev)."""
    _apply_verbose(verbose)
    from .doctor import run_checks, render
    checks = run_checks(include_mic=mic, brev=brev)
    render(checks, console=out_console)




@cli.command()
@click.option("--smoke-only", is_flag=True,
              help="Pular `docker compose up`, só rodar o smoke check.")
def brev(smoke_only):
    """Provisiona stack Brev (STT+LLM+TTS) e roda smoke check end-to-end."""
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = repo_root / "scripts" / ("brev-smoke.sh" if smoke_only else "brev-launch.sh")
    if not script.exists():
        console.print(f"[red]Script não encontrado: {script}[/red]")
        raise SystemExit(1)
    try:
        subprocess.run(["bash", str(script)], check=True, cwd=str(repo_root))
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode)

SERVER_URL = os.getenv("SPOOKNIX_URL", "http://localhost:8000")


@cli.command()
@click.option("--language", "-l", default="pt", show_default=True,
              help="Código do idioma (pt, en, es, …)")
@click.option("--silence", "-s", default=2.0, type=float, show_default=True,
              help="Segundos de silêncio para parar a gravação")
@click.option("--threshold", "-t", default=0.01, type=float, show_default=True,
              help="Limiar de RMS para detecção de silêncio")
@click.option("--clip/--no-clip", default=False,
              help="Copiar resultado para clipboard via wl-copy (Wayland)")
@click.option("--max-duration", default=300.0, type=float, show_default=True,
              help="Duração máxima da gravação em segundos")
@click.option("--server", default=None, show_default=True,
              help=f"URL do servidor (padrão: $SPOOKNIX_URL ou {SERVER_URL})")
@click.option("--stop-word", "-w", default="stop", show_default=True,
              help="Palavra-chave falada para parar a gravação (ex: 'stop', 'para')")
@click.option("--diarize/--no-diarize", default=False,
              help="Ativar diarização de speakers via pyannote-audio (requer HF_TOKEN)")
@click.option("--device", default=None, type=str,
              help="Índice do dispositivo de áudio (veja `spooknix doctor`)")
@click.option("--vad-neural/--no-vad-neural", "vad_neural", default=False,
              help="Usar Silero VAD ao invés de threshold RMS (mais robusto)")
@click.option("--meter/--no-meter", default=False,
              help="Mostrar widget de Peak/RMS/LUFS em tempo real")
@click.option("--out", default=None, type=click.Path(dir_okay=False, writable=True),
              help="Salvar a transcrição final em um arquivo de texto/markdown")
@click.option("-v", "--verbose", count=True,
              help="Logs em tempo real. -v = INFO (estado, stop reason), -vv = DEBUG (RMS por chunk).")
def record(language, silence, threshold, clip, max_duration, server, stop_word, diarize,
           device, vad_neural, meter, out, verbose):
    """Grava do microfone e transcreve via servidor HTTP."""
    import os
    import subprocess
    import urllib.request
    import urllib.error
    from .recorder import record_until_silence, RecordingError

    _apply_verbose(verbose)
    base_url = server or SERVER_URL

    # device pode vir como int ("0") ou string ("default"); preserva semântica do PortAudio
    device_arg: int | str | None = None
    if device is not None:
        try:
            device_arg = int(device)
        except ValueError:
            device_arg = device

    vad_instance = None
    if vad_neural:
        try:
            from .vad_silero import SileroVAD
            vad_instance = SileroVAD()
        except ImportError as exc:
            console.print(f"[yellow]VAD neural indisponível: {exc}[/yellow]")
            console.print("[dim]  Caindo no threshold RMS.[/dim]")

    meter_instance = None
    live_ctx = None
    if meter:
        from .audio_meter import AudioMeter
        from rich.live import Live
        meter_instance = AudioMeter(sample_rate=16_000)
        live_ctx = Live(meter_instance.render(), console=console, refresh_per_second=10)

    # Verificar servidor antes de gravar
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=3) as resp:
            import json
            info = json.loads(resp.read())
            console.print(
                f"[bold cyan]►[/bold cyan] Servidor [bold]{base_url}[/bold] "
                f"| modelo [bold]{info.get('model','?')}[/bold] "
                f"| device [bold]{info.get('device','?')}[/bold]"
                f"{' | CUDA ✓' if info.get('cuda') else ''}\n"
            )
    except (urllib.error.URLError, Exception) as exc:
        console.print(f"[red]✗ Servidor não disponível em {base_url}: {exc}[/red]")
        console.print("[dim]  Inicie com: docker compose up -d[/dim]")
        return

    # Função de stop por palavra-chave — chama o servidor com os últimos segundos
    def _make_stop_check(word: str):
        boundary = "spooknix-boundary-kw"

        def check(wav_bytes: bytes) -> bool:
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="kw.wav"\r\n'
                f"Content-Type: audio/wav\r\n\r\n"
            ).encode() + wav_bytes + (
                f"\r\n--{boundary}\r\n"
                f'Content-Disposition: form-data; name="language"\r\n\r\n'
                f"{language}\r\n"
                f"--{boundary}--\r\n"
            ).encode()
            req = urllib.request.Request(
                f"{base_url}/transcribe",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    import json as _json
                    text = _json.loads(resp.read()).get("text", "").lower()
                    return word.lower() in text
            except Exception:
                return False

        return check

    # Gravar
    tmp_path: str | None = None

    def _do_record() -> str:
        return record_until_silence(
            silence_duration=silence,
            silence_threshold=threshold,
            max_duration=max_duration,
            stop_check_fn=_make_stop_check(stop_word),
            stop_check_interval=2.0,
            vad=vad_instance,
            device=device_arg,
            meter=meter_instance,
        )

    try:
        try:
            if live_ctx is not None and meter_instance is not None:
                # Modo --meter: usa Live ao invés de console.status.
                # Atualizamos o render manualmente via monitor de polling rápido
                # antes de a captação iniciar (meter.feed é chamado pelo callback do recorder).
                import threading

                stop_render = threading.Event()

                def _ticker():
                    while not stop_render.wait(0.1):
                        live_ctx.update(meter_instance.render())

                with live_ctx:
                    t = threading.Thread(target=_ticker, daemon=True)
                    t.start()
                    try:
                        tmp_path = _do_record()
                    finally:
                        stop_render.set()
                        t.join(timeout=1.0)
            else:
                with console.status(
                    f"[red bold]● Gravando… (Ctrl+C ou diga '{stop_word}' para parar)[/red bold]"
                ):
                    tmp_path = _do_record()
        except KeyboardInterrupt:
            console.print("\n[yellow]Gravação interrompida.[/yellow]")
            if tmp_path is None:
                return
        except RecordingError as exc:
            console.print(f"[red]Erro de gravação: {exc}[/red]")
            return

        if tmp_path is None:
            console.print("[red]Nenhum áudio capturado.[/red]")
            return

        console.print("[green]✓ Gravação concluída.[/green]")

        # Enviar para o servidor via multipart/form-data
        with console.status("[cyan]Transcrevendo…[/cyan]"):
            import urllib.parse
            import email.generator
            import io

            boundary = "spooknix-boundary-42"
            wav_data = Path(tmp_path).read_bytes()

            diarize_value = "true" if diarize else "false"
            body_parts = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="recording.wav"\r\n'
                f"Content-Type: audio/wav\r\n\r\n"
            ).encode() + wav_data + (
                f"\r\n--{boundary}\r\n"
                f'Content-Disposition: form-data; name="language"\r\n\r\n'
                f"{language}\r\n"
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="diarize"\r\n\r\n'
                f"{diarize_value}\r\n"
                f"--{boundary}--\r\n"
            ).encode()

            req = urllib.request.Request(
                f"{base_url}/transcribe",
                data=body_parts,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=max_duration + 120) as resp:
                    import json
                    result = json.loads(resp.read())
            except urllib.error.URLError as exc:
                console.print(f"[red]Erro na transcrição: {exc}[/red]")
                return

        text = result.get("text", "").strip()
        lang_detected = result.get("language", language)
        duration = result.get("duration", 0.0)
        diarized = result.get("diarized", False)
        model_used = result.get("model", "?")

        if diarized:
            # Exibir segmentos com speaker labels
            speaker_lines = []
            for seg in result.get("segments", []):
                spk = seg.get("speaker", "?")
                speaker_lines.append(f"{spk}: {seg['text']}")
            body = "\n".join(speaker_lines) or "(sem texto detectado)"
        else:
            body = text or "(sem texto detectado)"

        title = f"✅ Transcrição [{lang_detected}] — {duration:.1f}s — modelo {model_used}"
        if diarized:
            title += " — diarizado"

        console.print(Panel(body, title=title, border_style="green"))
        print(body)

        if out:
            try:
                Path(out).write_text(body, encoding="utf-8")
                console.print(f"[dim]💾 Salvo em: {out}[/dim]")
            except Exception as exc:
                console.print(f"[red]Erro ao salvar arquivo: {exc}[/red]")

        # Clipboard
        if clip and text:
            try:
                subprocess.run(["wl-copy", text], check=True, timeout=5)
                console.print("[dim]📋 Copiado para o clipboard.[/dim]")
            except FileNotFoundError:
                console.print("[yellow]⚠ wl-copy não encontrado — clipboard ignorado.[/yellow]")
            except subprocess.CalledProcessError as exc:
                console.print(f"[yellow]⚠ Erro ao copiar: {exc}[/yellow]")

    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


SERVER_WS_URL = os.getenv("SPOOKNIX_WS_URL", "ws://localhost:8000")


@cli.command()
@click.option("--language", "-l", default="pt", show_default=True,
              help="Código do idioma (pt, en, es, …)")
@click.option("--window", default=3.0, type=float, show_default=True,
              help="Janela de flush em segundos")
@click.option("--clip/--no-clip", default=False,
              help="Copiar resultado final para clipboard via wl-copy (Wayland)")
@click.option("--stop-word", "-w", default=None,
              help="Palavra-chave no texto parcial acumulado para encerrar automaticamente")
@click.option("--server", default=None,
              help=f"URL base do servidor WebSocket (padrão: $SPOOKNIX_WS_URL ou {SERVER_WS_URL})")
@click.option("--max-duration", default=300.0, type=float, show_default=True,
              help="Duração máxima da sessão em segundos")
@click.option("--out", default=None, type=click.Path(dir_okay=False, writable=True),
              help="Salvar a transcrição final em um arquivo de texto/markdown")
@click.option("-v", "--verbose", count=True,
              help="Logs em tempo real (-v INFO, -vv DEBUG).")
def stream(language, window, clip, stop_word, server, max_duration, out, verbose):
    """Stream do microfone com transcrição parcial em tempo real via WebSocket."""
    import asyncio
    _apply_verbose(verbose)
    asyncio.run(_stream_async(language, window, clip, stop_word, server, max_duration, out))


async def _stream_async(
    language: str,
    window: float,
    clip: bool,
    stop_word: str | None,
    server: str | None,
    max_duration: float,
    out: str | None,
):
    import asyncio
    import json as _json
    import subprocess

    import numpy as np
    import sounddevice as sd
    import websockets  # type: ignore
    from rich.live import Live
    from rich.text import Text

    from .recorder import BLOCKSIZE, SAMPLE_RATE

    ws_base = (server or SERVER_WS_URL).rstrip("/")
    url = f"{ws_base}/ws/stream?language={language}&window={window}"

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def sd_callback(indata: np.ndarray, frames: int, t, status) -> None:
        data = indata[:, 0].copy().astype(np.float32)
        loop.call_soon_threadsafe(queue.put_nowait, data.tobytes())

    confirmed: list[str] = []
    partial_buf = ""
    # Mutable container — acessível de closures aninhadas sem nonlocal
    state = {"stop": False}

    def _render() -> Text:
        txt = Text()
        if confirmed:
            txt.append(" ".join(confirmed), style="dim")
            txt.append(" ")
        if partial_buf:
            txt.append(partial_buf.lstrip(), style="bold cyan")
        return txt

    try:
        async with websockets.connect(url, max_size=2**23) as ws:
            # session_start
            raw = await ws.recv()
            info = _json.loads(raw)
            console.print(
                f"[dim]WS conectado | modelo [bold]{info.get('model')}[/bold] "
                f"| device {info.get('device')} | janela {info.get('window_s')}s[/dim]\n"
            )

            deadline = loop.time() + max_duration

            async def _send_loop() -> None:
                with sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype="float32",
                    blocksize=BLOCKSIZE,
                    callback=sd_callback,
                ):
                    while loop.time() < deadline and not state["stop"]:
                        try:
                            chunk = await asyncio.wait_for(queue.get(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                        if chunk is None:
                            break
                        await ws.send(chunk)
                # Sinaliza encerramento
                await queue.put(None)

            send_task = asyncio.create_task(_send_loop())

            with Live(console=console, refresh_per_second=10) as live:
                try:
                    async for raw_msg in ws:
                        if not isinstance(raw_msg, str):
                            continue
                        data = _json.loads(raw_msg)
                        t = data.get("type")

                        if t == "partial":
                            partial_buf += data.get("text", "")
                            if stop_word and stop_word.lower() in partial_buf.lower():
                                state["stop"] = True
                                await ws.send(_json.dumps({"cmd": "stop"}))
                                break
                            live.update(_render())

                        elif t == "final":
                            seg_text = data.get("text", "").strip()
                            if seg_text:
                                confirmed.append(seg_text)
                            partial_buf = ""
                            live.update(_render())

                except websockets.exceptions.ConnectionClosed:
                    pass

            send_task.cancel()
            try:
                await send_task
            except asyncio.CancelledError:
                pass

    except Exception as exc:
        console.print(f"[red]Erro WebSocket: {exc}[/red]")

    full_text = " ".join(confirmed).strip()
    if full_text:
        console.print(Panel(full_text, title="✅ Transcrição final", border_style="green"))
        print(full_text)
        if out:
            try:
                from pathlib import Path
                Path(out).write_text(full_text, encoding="utf-8")
                console.print(f"[dim]💾 Salvo em: {out}[/dim]")
            except Exception as exc:
                console.print(f"[red]Erro ao salvar arquivo: {exc}[/red]")

        if clip:
            try:
                import subprocess as _sp
                _sp.run(["wl-copy", full_text], check=True, timeout=5)
                console.print("[dim]Copiado para o clipboard.[/dim]")
            except FileNotFoundError:
                console.print("[yellow]wl-copy não encontrado.[/yellow]")
            except Exception:
                pass
    else:
        console.print("[yellow]Nenhum texto transcrito.[/yellow]")


@cli.command()
@click.option("--language", "-l", default="en", show_default=True,
              help="Código do idioma (padrão: en para simulação de inglês)")
@click.option("--silence", "-s", default=2.5, type=float, show_default=True,
              help="Segundos de silêncio para detectar fim do turno")
@click.option("--threshold", "-t", default=0.01, type=float, show_default=True,
              help="Nível RMS mínimo para considerar como voz")
@click.option("--server", default=None,
              help="URL base do servidor HTTP STT (padrão: http://localhost:8000)")
@click.option("--model", default=None,
              help="Modelo do LLM a ser utilizado (ex: gpt-4o, llama-3)")
@click.option("--persona", "persona_name", default="sarah", show_default=True,
              help="Nome da persona em personas/<name>.yaml")
@click.option("--scenario", "scenario_name", default="system_design", show_default=True,
              help="Cenário em scenarios/<name>.yaml")
@click.option("--difficulty", default="standard", show_default=True,
              type=click.Choice(["easy", "standard", "hard"]))
@click.option("--list", "list_sessions", is_flag=True,
              help="Listar sessões anteriores no SQLite e sair")
@click.option("--show", "show_id", type=int, default=None,
              help="Imprimir detalhes da sessão com este ID e sair")
@click.option("--diff", "diff_ids", nargs=2, type=int, default=None,
              help="Comparar duas sessões por ID")
@click.option("--out", default=None, type=click.Path(dir_okay=False, writable=True),
              help="Caminho do relatório (default: outputs/interviews/<ts>-<persona>/feedback.md)")
@click.option("-v", "--verbose", count=True,
              help="Logs do orquestrador. -v = transições de estado, -vv = RMS por chunk.")
def interview(language, silence, threshold, server, model, persona_name, scenario_name,
              difficulty, list_sessions, show_id, diff_ids, out, verbose):
    """Simulador interativo de entrevistas profissionais com feedback via LLM (Full-Duplex TTS)."""
    import asyncio
    _apply_verbose(verbose)

    # Comandos read-only: --list, --show, --diff (não rodam orchestrator)
    if list_sessions:
        _interview_list()
        return
    if show_id is not None:
        _interview_show(show_id)
        return
    if diff_ids:
        _interview_diff(diff_ids[0], diff_ids[1])
        return

    try:
        asyncio.run(_interview_async(
            language, silence, threshold, server, model,
            persona_name, scenario_name, difficulty, out,
        ))
    except KeyboardInterrupt:
        pass


def _interview_list():
    from rich.table import Table
    from . import sessions_db

    records = sessions_db.list_all()
    if not records:
        out_console.print("[dim]Nenhuma sessão registrada ainda.[/dim]")
        return

    table = Table(title="Sessões de entrevista", show_header=True, header_style="bold")
    table.add_column("ID", justify="right", style="bold cyan")
    table.add_column("Quando")
    table.add_column("Persona")
    table.add_column("Cenário")
    table.add_column("Difficulty")
    table.add_column("Duração (s)", justify="right")
    for r in records:
        table.add_row(
            str(r.id), r.ts, r.persona, r.scenario, r.difficulty, f"{r.duration_s:.0f}",
        )
    out_console.print(table)


def _interview_show(session_id: int):
    from rich.json import JSON
    from rich.panel import Panel as RPanel
    from . import sessions_db

    r = sessions_db.get(session_id)
    if r is None:
        out_console.print(f"[red]Sessão #{session_id} não encontrada.[/red]")
        return
    out_console.print(RPanel.fit(
        f"[bold]Persona:[/] {r.persona}\n"
        f"[bold]Cenário:[/] {r.scenario} ({r.difficulty})\n"
        f"[bold]Quando:[/] {r.ts}\n"
        f"[bold]Duração:[/] {r.duration_s:.0f}s\n"
        f"[bold]Transcript:[/] {r.transcript_path or '—'}\n"
        f"[bold]Audio:[/] {r.audio_path or '—'}",
        title=f"Sessão #{r.id}",
    ))
    if r.rubric_json:
        out_console.print(RPanel(JSON(r.rubric_json), title="Rubric"))


def _interview_diff(id_a: int, id_b: int):
    from rich.table import Table
    from . import sessions_db
    from .rubric import AXES

    a = sessions_db.get(id_a)
    b = sessions_db.get(id_b)
    if not a or not b:
        out_console.print(f"[red]Sessão #{id_a} ou #{id_b} não encontrada.[/red]")
        return
    da = sessions_db.rubric_dict(a)
    db = sessions_db.rubric_dict(b)

    table = Table(title=f"Diff: #{id_a} vs #{id_b}", show_header=True, header_style="bold")
    table.add_column("Eixo", style="bold cyan")
    table.add_column(f"#{id_a}", justify="right")
    table.add_column(f"#{id_b}", justify="right")
    table.add_column("Δ", justify="right")
    for axis in AXES:
        sa = (da.get(axis) or {}).get("score", 0)
        sb = (db.get(axis) or {}).get("score", 0)
        delta = sb - sa
        delta_str = f"[green]+{delta}[/]" if delta > 0 else f"[red]{delta}[/]" if delta < 0 else "0"
        table.add_row(axis, str(sa), str(sb), delta_str)
    out_console.print(table)


async def _interview_async(
    language, silence, threshold, server_url, model,
    persona_name, scenario_name, difficulty, out_path,
):
    import os
    import time
    from pathlib import Path

    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    from .llm_client import LLMClient, InterviewSession, load_template
    from .tts_client import LocalTTSClient
    from .orchestrator import Orchestrator, build_system_prompt
    from . import personas as personas_mod
    from . import scenarios as scenarios_mod
    from . import sessions_db
    from .rubric import parse_rubric
    from .types import SessionRecord, outputs_path_for

    console = Console()
    console.print(Panel.fit(
        "[bold green]Iniciando Orchestrator Full-Duplex...[/]\n"
        "[dim]Pressione Ctrl+C para encerrar e gerar o relatório.[/]"
    ))

    SERVER_HTTP_URL = "http://localhost:8000"
    base_url = (server_url or SERVER_HTTP_URL).rstrip("/")
    if base_url.startswith("ws://"):
        base_url = "http://" + base_url[5:]
    stt_endpoint = f"{base_url}/transcribe"

    # --- Persona / Scenario via YAML ---
    try:
        persona = personas_mod.load_persona(persona_name)
        scn = scenarios_mod.load_scenario(scenario_name, difficulty)
    except (personas_mod.PersonaNotFound, scenarios_mod.ScenarioNotFound, ValueError) as exc:
        console.print(f"[bold red]Configuração inválida:[/] {exc}")
        return

    # Voz da persona pode vir via env (compatibilidade com o setup atual)
    voice_env = os.getenv("SPOOKNIX_PERSONA_VOICE")
    if voice_env and any(sep in voice_env for sep in ("/", ".")):
        if Path(voice_env).exists():
            persona.voice_ref_audio = voice_env

    # --- LLM/TTS ---
    try:
        llm = LLMClient(model=model)
        tts = LocalTTSClient()
    except Exception as e:
        console.print(f"[bold red]Erro ao inicializar Clients (LLM/TTS):[/] {e}")
        return

    # --- Diretório de saída por sessão ---
    session_dir = outputs_path_for(persona.name)
    session_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = session_dir / "transcript.md"
    rubric_path = session_dir / "rubric.json"
    out_path_obj = Path(out_path) if out_path else session_dir / "feedback.md"

    # --- System prompt enriquecido com addenda do cenário ---
    base_prompt = build_system_prompt(persona, scn.scenario)
    addenda = "\n".join(filter(None, [scn.base_prompt_addendum, scn.prompt_addendum]))
    prompt = base_prompt + ("\n\nAdditional context:\n" + addenda if addenda else "")
    session = InterviewSession(prompt)

    orchestrator = Orchestrator(
        llm=llm, tts=tts, stt_endpoint=stt_endpoint, language=language,
    )

    from . import metrics as m
    m.interviews_total.inc({
        "persona": persona_name,
        "scenario": scenario_name,
        "difficulty": difficulty,
    })



    started_at = time.monotonic()
    await orchestrator.run_session(
        session=session, persona=persona,
        silence_s=silence, threshold=threshold, model=model,
    )
    duration_s = time.monotonic() - started_at
    m.interview_duration_seconds.observe(duration_s)

    transcript = session.get_transcript_text()
    transcript_path.write_text(transcript, encoding="utf-8")

    if len(transcript.split()) < 10:
        console.print("[dim]Conversa muito curta. Relatório não gerado.[/]")
        _persist(persona.name, scenario_name, difficulty, duration_s,
                 transcript_path, rubric_json=None)
        return

    # --- Avaliação (Rubric) ---
    console.print("\n[dim]Gerando rubric estruturada via LLM…[/]")
    try:
        evaluator_prompt = load_template("evaluator_rubric.md")
    except FileNotFoundError:
        try:
            evaluator_prompt = load_template("evaluator.md")
        except FileNotFoundError:
            evaluator_prompt = (
                "You are an expert technical interview evaluator. "
                "Return strict JSON with the 5-axis rubric."
            )

    evaluator_session = InterviewSession(evaluator_prompt)
    evaluator_session.add_user_message(transcript)
    raw_report = await llm.generate(evaluator_session.get_messages(), model)

    rubric = parse_rubric(raw_report)
    rubric_json = rubric.to_json()
    rubric_path.write_text(rubric_json, encoding="utf-8")
    out_path_obj.write_text(raw_report, encoding="utf-8")

    sid = _persist(persona.name, scenario_name, difficulty, duration_s,
                   transcript_path, rubric_json=rubric_json,
                   feedback_path=out_path_obj)

    console.print(Panel(Markdown(raw_report), title=f"Feedback da Entrevista (sessão #{sid})", expand=False))
    console.print(f"\n[bold green]Artefatos:[/]\n  {transcript_path}\n  {rubric_path}\n  {out_path_obj}")


def _persist(persona_name, scenario_name, difficulty, duration_s,
             transcript_path, rubric_json=None, feedback_path=None) -> int:
    from . import sessions_db
    from .types import SessionRecord

    rec = SessionRecord.new(persona=persona_name, scenario=scenario_name, difficulty=difficulty)
    rec.duration_s = float(duration_s)
    rec.transcript_path = str(transcript_path)
    rec.audio_path = None  # MVP: o orchestrator ainda não dumpa o WAV consolidado
    rec.rubric_json = rubric_json
    return sessions_db.insert(rec)

@cli.command()
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--template", "template_name", default="summary", show_default=True,
              type=click.Choice(["summary", "lecture", "meeting", "notes", "study_guide"]))
@click.option("--language", "-l", default="pt", show_default=True)
@click.option("--model", "-m",
              type=click.Choice(["tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo"]),
              default="large-v3", show_default=True)
@click.option("--format", "-f", "fmt",
              type=click.Choice(["md", "json", "srt-summary"]),
              default="md", show_default=True)
@click.option("--diarize/--no-diarize", default=False,
              help="Atribuir speakers via pyannote (requer HF_TOKEN)")
@click.option("--max-tokens", default=3000, type=int, show_default=True,
              help="Tokens por chunk no LLM")
@click.option("--out", default=None, type=click.Path(dir_okay=False, writable=True),
              help="Caminho de saída (default: outputs/summaries/<stem>.<fmt>)")
@click.option("-v", "--verbose", count=True)
def summarize(input_path, template_name, language, model, fmt, diarize, max_tokens, out, verbose):
    """Sumariza vídeo/áudio/lecture com timestamps clicáveis."""
    import asyncio
    _apply_verbose(verbose)
    try:
        asyncio.run(_summarize_async(
            input_path, template_name, language, model, fmt, diarize, max_tokens, out,
        ))
    except KeyboardInterrupt:
        pass


async def _summarize_async(input_path, template_name, language, model, fmt,
                            diarize, max_tokens, out):
    import json as _json
    from pathlib import Path

    from .transcriber import get_model, transcribe_file
    from .media import extract_audio, is_video_or_compressed
    from .summarizer import chunk_segments, stitch, render_template
    from .timestamp_links import format_mmss
    from .llm_client import LLMClient, InterviewSession

    src = Path(input_path)
    stem = src.stem
    output_path = Path(out) if out else Path("outputs/summaries") / f"{stem}.{fmt if fmt != 'srt-summary' else 'srt'}"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Transcrição (faster-whisper consome mp4/mkv via ffmpeg interno;
    #    para diarização precisamos de WAV explícito).
    audio_for_diar: Path | None = None
    if diarize and is_video_or_compressed(src):
        console.print("[dim]Extraindo áudio para diarização…[/]")
        audio_for_diar = extract_audio(src)

    console.print(f"[bold cyan]►[/] Carregando modelo Whisper [bold]{model}[/]…")
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    m = get_model(model, device)

    console.print(f"[bold cyan]►[/] Transcrevendo…")
    transcribe_target = str(audio_for_diar) if audio_for_diar else str(src)
    result = transcribe_file(m, transcribe_target, language=language)

    segments = result["segments"]
    if diarize:
        from .diarizer import diarize as run_diarize, assign_speakers
        console.print("[bold cyan]►[/] Diarizando…")
        diar = run_diarize(str(audio_for_diar or src))
        segments = assign_speakers(segments, diar, split_at_boundaries=True)

    # 2. Chunking + LLM
    source_uri = str(src)
    chunks = chunk_segments(segments, max_tokens=max_tokens, source_uri=source_uri)
    console.print(f"[dim]Dividido em {len(chunks)} chunks ({sum(len(c.text.split()) for c in chunks)} palavras totais)[/]")

    from . import metrics as m
    m.summaries_total.inc({"template": template_name})
    m.summary_chunks_total.inc(n=len(chunks))

    try:
        llm = LLMClient(model=model)
    except Exception as exc:
        console.print(f"[red]LLM indisponível: {exc}[/red]")
        return

    chunk_summaries: list[str] = []
    for i, ch in enumerate(chunks, 1):
        console.print(f"[dim]  ↳ Sumarizando chunk {i}/{len(chunks)} ({format_mmss(ch.start)}–{format_mmss(ch.end)})…[/]")
        prompt = (
            "You are summarizing one chunk of a longer media transcript. "
            "Preserve the original [mm:ss] timestamps in your bullets. "
            "Be terse and concrete; no preamble. Markdown only."
        )
        session = InterviewSession(prompt)
        session.add_user_message(ch.text)
        s = await llm.generate(session.get_messages(), model)
        chunk_summaries.append(s)

    stitched = stitch(chunk_summaries)

    # 3. Renderização final
    if fmt == "md":
        template_path = Path(__file__).resolve().parent.parent / "templates" / f"{template_name}.md"
        if template_path.exists():
            rendered = render_template(
                template_path,
                title=stem,
                source=source_uri,
                duration=format_mmss(result.get("duration", 0.0)),
                language=result.get("language"),
                tldr=stitched.split("\n\n---")[0],
                key_points=stitched,
                quotes="",
                followups="",
                chapters=stitched,
                concepts="",
                examples="",
                decisions="",
                action_items="",
                participants="",
                highlights=stitched,
                memorize="",
                glossary="",
                questions="",
                exercises="",
            )
        else:
            rendered = stitched
        output_path.write_text(rendered, encoding="utf-8")
    elif fmt == "json":
        payload = {
            "source": source_uri,
            "duration": result.get("duration"),
            "language": result.get("language"),
            "chunks": [
                {"start": c.start, "end": c.end, "summary": s}
                for c, s in zip(chunks, chunk_summaries)
            ],
        }
        output_path.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    elif fmt == "srt-summary":
        from .transcriber import generate_srt
        # Gera SRT clássico do transcript completo; o sumário fica num .md sibling.
        srt_path = output_path
        generate_srt(result["segments"], str(srt_path))
        md_sibling = srt_path.with_suffix(".summary.md")
        md_sibling.write_text(stitched, encoding="utf-8")

    console.print(f"[bold green]✓ Salvo em {output_path}[/]")

    if audio_for_diar and audio_for_diar.exists():
        try:
            audio_for_diar.unlink()
        except OSError:
            pass



if __name__ == "__main__":
    cli()
