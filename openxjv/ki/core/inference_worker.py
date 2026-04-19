"""
Inferenz-Subprocess: alle llama-cpp-python-Operationen.

Läuft als separater Prozess (multiprocessing spawn). Hält das Modell
zwischen Analyseläufen im Speicher; lädt es nur neu wenn sich Pfad oder
Kontextfenster ändern.

Protokoll — Elternprozess → Subprocess (cmd_queue):
    {"cmd": "analyze", ...}   – Analyseauftrag (Parameter siehe _run_analysis)
    None                      – Shutdown-Sentinel

Protokoll — Subprocess → Elternprozess (resp_queue):
    (PROGRESS, str)           – Fortschrittsmeldung
    (TOKEN, str)              – generierter Token
    (DONE,)                   – Analyse abgeschlossen (immer zuletzt)
    (ERROR, str)              – Fehler mit Traceback
"""
from __future__ import annotations

import gc
import io
import os
import re
import sys
import time
import queue as _queue
from typing import Callable

# Modul-Level-Import sicherstellen, damit PyInstaller/AppImage die Abhängigkeit
# beim statischen Scannen findet. Ein Lazy-Import innerhalb von _split_into_chunks
# würde vom Dependency-Scanner übersehen und fehlt dann im Frozen-Bundle.
from .text_preprocessor import _find_sentence_boundary

# ---------------------------------------------------------------------------
# Protokoll-Konstanten (vom Elternprozess gelesen)
# ---------------------------------------------------------------------------

PROGRESS = "progress"
TOKEN    = "token"
DONE     = "done"
ERROR    = "error"

# Trennzeichen zwischen Instruktion und Dokumenttext im user_prompt
DOCUMENT_SEPARATOR = "\n\n---\nDOKUMENT:\n"

# ---------------------------------------------------------------------------
# Interne Konstanten
# ---------------------------------------------------------------------------

_DEFAULT_TEMPLATE_OVERHEAD   = 20
_DEFAULT_CHUNK_OVERLAP_CHARS = 800
_CONTEXT_RESERVE             = 1500


# ===========================================================================
# Subprocess-Einstiegspunkt
# ===========================================================================

def worker_main(cmd_queue, resp_queue, cancel_event) -> None:
    """
    Hauptschleife des Inferenz-Subprozesses.

    Verarbeitet "analyze"-Befehle in einer Endlosschleife und hält das
    Modell zwischen Aufrufen im Speicher (Persistenz via _ModelState).
    Beendet sich sauber beim Shutdown-Sentinel (None) oder bei einem
    Queue-Fehler.
    """
    state = _ModelState()
    while True:
        try:
            cmd = cmd_queue.get(timeout=1.0)
        except _queue.Empty:
            continue
        except Exception:
            break

        if cmd is None:
            break  # Shutdown-Sentinel

        kind = cmd.get("cmd")
        if kind == "analyze":
            cancel_event.clear()
            try:
                _run_analysis(state, cmd, resp_queue, cancel_event)
            except Exception:
                import traceback
                resp_queue.put((ERROR, traceback.format_exc()))
            resp_queue.put((DONE,))
        elif kind == "unload":
            state.evict()

    state.evict()


# ===========================================================================
# Modell-Persistenz
# ===========================================================================

class _ModelState:
    """Hält genau ein geladenes Modell zwischen Analyseläufen vor."""

    def __init__(self) -> None:
        self.llm = None
        self._key: tuple | None = None   # (model_path, n_ctx)

    def load(
        self,
        model_path: str,
        n_ctx: int,
        config: dict,
        progress_cb: Callable[[str], None],
        ki_debug: bool = False,
    ) -> None:
        """Lädt das Modell, falls (model_path, n_ctx) nicht gecacht ist."""
        key = (model_path, n_ctx)
        if self.llm is not None and self._key == key:
            progress_cb(
                f"Modell bereits geladen (Kontext: {self.llm.n_ctx():,} Token)."
            )
            return
        self.evict()
        self.llm = _load_llm(model_path, n_ctx, config, progress_cb, ki_debug=ki_debug)
        self._key = key

    def evict(self) -> None:
        """Gibt das gecachte Modell frei (VRAM/RAM)."""
        if self.llm is not None:
            _safe_close(self.llm)
            self.llm = None
            self._key = None
            gc.collect()
            gc.collect()
            gc.collect()


# ===========================================================================
# Analyse-Ablauf
# ===========================================================================

def _run_analysis(
    state: _ModelState,
    cmd: dict,
    resp_queue,
    cancel_event,
) -> None:
    """
    Vollständiger Analyse-Durchlauf für einen "analyze"-Befehl.

    Empfangene Parameter (aus cmd):
      model_path        – Pfad zur GGUF-Datei
      n_ctx             – Geschätztes Kontextfenster (vom Elternprozess)
      config            – ModelConfig-Felder als dict
      document_text     – Bereinigter, deduplizierter Dokumenttext
      system_prompt     – System-Prompt (aus ModelRegistry)
      instruction       – User-Prompt-Template ohne Dokument
      doc_name          – Dateiname (für Header im Prompt)
      max_tokens        – Maximale Ausgabelänge in Token
      generation_params – Sampling-Parameter (temperature, top_p, …)
      use_ocr           – True wenn Text via OCR extrahiert wurde
      ki_debug          – True wenn --ki-debug gesetzt: gibt llama.cpp-Details auf stderr aus
    """

    def progress(msg: str) -> None:
        resp_queue.put((PROGRESS, msg))

    def token(t: str) -> None:
        resp_queue.put((TOKEN, t))

    model_path    = cmd["model_path"]
    n_ctx         = cmd["n_ctx"]
    config        = cmd["config"]
    document_text = cmd["document_text"]
    system_prompt = cmd["system_prompt"]
    instruction   = cmd["instruction"]
    doc_name      = cmd.get("doc_name", "")
    max_tokens    = cmd["max_tokens"]
    gen_params    = dict(cmd.get("generation_params") or {})
    use_ocr       = cmd.get("use_ocr", False)
    ki_debug      = cmd.get("ki_debug", False)

    template_overhead   = config.get("template_overhead",   _DEFAULT_TEMPLATE_OVERHEAD)
    chunk_overlap_chars = config.get("chunk_overlap_chars", _DEFAULT_CHUNK_OVERLAP_CHARS)
    filter_thinking     = config.get("filter_thinking_block", False)
    n_ctx_max           = config.get("n_ctx_max",  32768)
    n_ctx_min           = config.get("n_ctx_min",  2048)

    # ------------------------------------------------------------------
    # 1. Modell laden (initial mit Schätzwert aus dem Elternprozess)
    # ------------------------------------------------------------------
    progress("Lade Modell …")
    try:
        state.load(model_path, n_ctx, config, progress, ki_debug=ki_debug)
    except FileNotFoundError as e:
        raise RuntimeError(f"Modelldatei nicht gefunden: {e}") from e

    llm        = state.llm
    actual_ctx = llm.n_ctx()
    progress(f"Modell geladen. Kontextfenster: {actual_ctx:,} Token.")

    if cancel_event.is_set():
        return

    # ------------------------------------------------------------------
    # 2. Exakten Token-Overhead messen und Kontextfenster anpassen
    # ------------------------------------------------------------------
    doc_header      = f"Dateiname: {doc_name}\n" if doc_name else ""
    prompt_prefix   = system_prompt + "\n" + instruction + DOCUMENT_SEPARATOR + doc_header
    prompt_overhead = _count_tokens(llm, prompt_prefix)

    output_reserve = max(_CONTEXT_RESERVE, max_tokens)
    real_tokens    = _count_tokens(llm, document_text)
    available      = actual_ctx - output_reserve - prompt_overhead
    progress(
        f"Dokumentgröße (exakt): {real_tokens:,} Token, "
        f"verfügbar: {available:,} Token."
    )

    ideal_ctx = max(
        n_ctx_min,
        (((real_tokens + output_reserve + prompt_overhead + 1023) // 1024) * 1024),
    )
    ideal_ctx    = min(ideal_ctx, n_ctx_max)
    ratio        = actual_ctx / max(ideal_ctx, 1)
    needs_reload = real_tokens > available
    oversized    = ratio > 2.0

    if needs_reload or oversized:
        reason = (
            f"Kontext massiv überdimensioniert "
            f"({actual_ctx:,} vs. {ideal_ctx:,} benötigt)"
            if oversized
            else f"Text passt nicht ({real_tokens:,} > {available:,} Token)"
        )
        progress(
            f"Neustart mit angepasstem Kontextfenster: {reason} → {ideal_ctx:,} Token."
        )
        try:
            state.load(model_path, ideal_ctx, config, progress, ki_debug=ki_debug)
        except Exception as e:
            raise RuntimeError(f"Neustart fehlgeschlagen: {e}") from e
        llm        = state.llm
        actual_ctx = llm.n_ctx()
        progress(f"Modell neu geladen. Kontextfenster: {actual_ctx:,} Token.")

    if cancel_event.is_set():
        return

    # ------------------------------------------------------------------
    # 3. Sampling-Parameter finalisieren
    # ------------------------------------------------------------------
    if use_ocr and gen_params.get("repeat_penalty", 1.0) < 1.2:
        gen_params["repeat_penalty"] = 1.25

    # ------------------------------------------------------------------
    # 4. Inferenz
    # ------------------------------------------------------------------
    user_prompt = (
        instruction + DOCUMENT_SEPARATOR + doc_header + document_text
    ).strip()

    _run_inference(
        llm=llm,
        document_text=document_text,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cancel_event=cancel_event,
        progress_cb=progress,
        token_cb=token,
        max_tokens=max_tokens,
        generation_params=gen_params,
        template_overhead=template_overhead,
        chunk_overlap_chars=chunk_overlap_chars,
        filter_thinking=filter_thinking,
    )


# ===========================================================================
# Inferenz mit optionalem Chunking
# ===========================================================================

def _run_inference(
    llm,
    document_text: str,
    system_prompt: str,
    user_prompt: str,
    cancel_event,
    progress_cb: Callable[[str], None],
    token_cb: Callable[[str], None],
    max_tokens: int = 1536,
    generation_params: dict | None = None,
    template_overhead: int = _DEFAULT_TEMPLATE_OVERHEAD,
    chunk_overlap_chars: int = _DEFAULT_CHUNK_OVERLAP_CHARS,
    filter_thinking: bool = False,
) -> None:
    """
    Schickt das Dokument ans Modell. Bei Überschreitung des Kontextfensters
    wird in Chunks aufgeteilt und anschließend konsolidiert.

    Kein Chunk-Marker im Ausgabestream — nur der Modell-Output erscheint in token_cb.
    """
    if generation_params is None:
        generation_params = {}

    available_tokens = llm.n_ctx() - max_tokens - template_overhead

    combined_text = system_prompt + "\n" + user_prompt
    text_tokens = _count_tokens(llm, combined_text)
    progress_cb(
        f"Anfrage: {text_tokens:,} Token, "
        f"verfügbar: {available_tokens:,} Token (Antwortpuffer: {max_tokens})."
    )

    if text_tokens <= available_tokens:
        progress_cb("Text passt ins Kontextfenster. Einzelner Durchlauf.")
        _stream_once(
            llm=llm,
            system_prompt=system_prompt,
            user_content=user_prompt,
            cancel_event=cancel_event,
            token_cb=token_cb,
            progress_cb=progress_cb,
            max_tokens=max_tokens,
            generation_params=generation_params,
            filter_thinking=filter_thinking,
        )
        return

    # --- Chunking ---
    progress_cb("Text überschreitet Kontextfenster — Chunking wird angewendet.")

    overhead = _count_tokens(llm, system_prompt) + _count_tokens(
        llm, user_prompt.replace(document_text, "")
    )
    _CHUNK_HEADER_OVERHEAD = 20
    doc_budget = available_tokens - overhead - 200 - _CHUNK_HEADER_OVERHEAD

    if doc_budget <= 0:
        progress_cb("Fehler: Prompt-Overhead überschreitet Kontextfenster. Dokument zu groß.")
        return

    chunks = _split_into_chunks(llm, document_text, doc_budget, chunk_overlap_chars)
    progress_cb(f"Dokument in {len(chunks)} Abschnitt(e) aufgeteilt.")

    if DOCUMENT_SEPARATOR in user_prompt:
        instruction = user_prompt[: user_prompt.find(DOCUMENT_SEPARATOR)]
    else:
        instruction = user_prompt.replace(document_text, "").rstrip()

    chunk_results: list[str] = []

    for i, chunk in enumerate(chunks):
        if cancel_event.is_set():
            return
        progress_cb(f"Abschnitt {i + 1}/{len(chunks)} …")
        chunk_parts: list[str] = []
        chunk_header = f"---\nDOKUMENT (Abschnitt {i + 1}/{len(chunks)}):\n"
        _stream_once(
            llm=llm,
            system_prompt=system_prompt,
            user_content=instruction + "\n\n" + chunk_header + chunk,
            cancel_event=cancel_event,
            token_cb=lambda t, _p=chunk_parts: (_p.append(t), token_cb(t)),
            progress_cb=progress_cb,
            max_tokens=max_tokens,
            generation_params=generation_params,
            filter_thinking=filter_thinking,
        )
        chunk_results.append("".join(chunk_parts))

    if cancel_event.is_set() or len(chunk_results) <= 1:
        return

    # Konsolidierungspass
    combined = "\n\n".join(
        f"[Abschnitt {i+1}]\n{s}" for i, s in enumerate(chunk_results)
    )
    combined_tokens = _count_tokens(llm, combined)
    progress_cb(
        f"Konsolidierungspass: {combined_tokens:,} Token "
        f"aus {len(chunk_results)} Abschnittsanalysen."
    )

    if combined_tokens <= available_tokens:
        _stream_once(
            llm=llm,
            system_prompt=system_prompt,
            user_content=instruction + DOCUMENT_SEPARATOR + combined,
            cancel_event=cancel_event,
            token_cb=token_cb,
            progress_cb=progress_cb,
            max_tokens=max_tokens,
            generation_params=generation_params,
            filter_thinking=filter_thinking,
        )
    else:
        progress_cb(
            "Abschnittsanalysen zu lang für Konsolidierungspass — "
            "Einzelergebnisse wurden bereits ausgegeben."
        )


def _stream_once(
    llm,
    system_prompt: str,
    user_content: str,
    cancel_event,
    token_cb: Callable[[str], None],
    progress_cb: Callable[[str], None],
    max_tokens: int = 1536,
    generation_params: dict | None = None,
    filter_thinking: bool = False,
) -> None:
    """Einzelner Streaming-Completion-Aufruf mit optionalem Think-Block-Filter."""
    if generation_params is None:
        generation_params = {}

    # Pro Aufruf eine frische Filterinstanz — jeder Chunk filtert unabhängig.
    _cb = _make_think_filter(token_cb) if filter_thinking else token_cb

    token_count = _count_tokens(llm, user_content)
    progress_cb(f"Prefill startet ({token_count:,} Token) — bitte warten …")
    t_start = time.monotonic()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_content},
    ]

    _BENCHMARK_TOKENS = 20
    first_token   = True
    t_first_token = None
    generated     = 0
    estimate_done = False

    try:
        stop_sequences = generation_params.get("stop", []) or []
        stream = llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=generation_params.get("temperature", 0.2),
            repeat_penalty=generation_params.get("repeat_penalty", 1.1),
            top_p=generation_params.get("top_p", 0.95),
            top_k=generation_params.get("top_k", 60),
            min_p=generation_params.get("min_p", 0.05),
            stop=stop_sequences if stop_sequences else None,
            stream=True,
        )
        for chunk in stream:
            if cancel_event.is_set():
                break
            delta   = chunk["choices"][0].get("delta", {})
            content = delta.get("content", "")
            if content:
                if first_token:
                    t_first_token = time.monotonic()
                    prefill_s = t_first_token - t_start
                    progress_cb(f"Prefill: {prefill_s:.1f}s — Generierung läuft …")
                    first_token = False
                generated += 1
                _cb(content)

                if not estimate_done and generated == _BENCHMARK_TOKENS:
                    elapsed     = time.monotonic() - t_first_token
                    tok_per_s   = _BENCHMARK_TOKENS / max(elapsed, 0.01)
                    remaining_s = (max_tokens - _BENCHMARK_TOKENS) / tok_per_s
                    progress_cb(
                        f"Geschwindigkeit: {tok_per_s:.1f} Token/s — "
                        f"geschätzte Restzeit: ~{_fmt_duration(remaining_s)}"
                    )
                    estimate_done = True

    except Exception as e:
        progress_cb(f"Fehler während der Generierung: {e}")
        raise

    t_end = time.monotonic()
    if t_first_token and generated > 0:
        gen_s     = t_end - t_first_token
        total_s   = t_end - t_start
        tok_per_s = generated / max(gen_s, 0.01)
        progress_cb(
            f"Fertig: {generated} Token in {gen_s:.1f}s "
            f"({tok_per_s:.1f} Token/s) — Gesamt: {_fmt_duration(total_s)}"
        )


def _make_think_filter(token_cb: Callable[[str], None]) -> Callable[[str], None]:
    """
    Filtert <think>…</think>-Blöcke still aus dem Token-Stream heraus.

    Da Tokens fragmentiert ankommen, puffert die Funktion den Anfang des
    Streams bis klar ist, ob ein <think>-Block folgt:

      INIT     → puffern; sobald der Anfang (nach Strip) kein Präfix von
                 '<think>' mehr sein kann → DONE + Puffer leeren.
                 Sobald '<think>' vollständig erkannt → IN_THINK.
      IN_THINK → alle Tokens bis '</think>' verwerfen, dann DONE.
      DONE     → alle Tokens direkt an token_cb.
    """
    _OPEN  = "<think>"
    _CLOSE = "</think>"

    state = ["INIT"]
    buf   = [""]

    def filtered(token: str) -> None:
        if state[0] == "DONE":
            token_cb(token)
            return

        buf[0] += token

        if state[0] == "INIT":
            stripped = buf[0].lstrip("\n ")
            if stripped.startswith(_OPEN):
                state[0] = "IN_THINK"
                buf[0]   = stripped[len(_OPEN):]
            elif len(stripped) > 0 and not _OPEN.startswith(stripped[: len(_OPEN)]):
                state[0] = "DONE"
                token_cb(buf[0])
                buf[0] = ""
                return
            else:
                return  # Noch puffern

        if state[0] == "IN_THINK":
            idx = buf[0].find(_CLOSE)
            if idx >= 0:
                after  = buf[0][idx + len(_CLOSE):]
                buf[0] = ""
                state[0] = "DONE"
                after = after.lstrip("\n")
                if after:
                    token_cb(after)

    return filtered


def _split_into_chunks(
    llm,
    text: str,
    max_tokens: int,
    overlap_chars: int = _DEFAULT_CHUNK_OVERLAP_CHARS,
) -> list[str]:
    """Teilt Text in Chunks auf, die jeweils max_tokens nicht überschreiten."""
    total_chars     = len(text)
    total_tokens    = _count_tokens(llm, text)
    chars_per_token = total_chars / max(total_tokens, 1)
    chunk_chars     = int(max_tokens * chars_per_token * 0.88)

    if len(text) <= chunk_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        if end < len(text):
            boundary = _find_sentence_boundary(text, max(start, end - 300), end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()

        actual = _count_tokens(llm, chunk)
        if actual > max_tokens and len(chunk) > 100:
            ratio    = (max_tokens / actual) * 0.95
            new_end  = start + int((end - start) * ratio)
            boundary = _find_sentence_boundary(text, max(start, new_end - 300), new_end)
            if boundary > start:
                new_end = boundary
            chunk = text[start:new_end].strip()
            end   = new_end

        chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap_chars)

    return [c for c in chunks if c]


def _count_tokens(llm, text: str) -> int:
    return len(llm.tokenize(text.encode("utf-8", errors="replace")))


def _fmt_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60:02d}s"


# ===========================================================================
# Modell laden (nur im Subprocess)
# ===========================================================================

def _load_llm(
    model_path: str,
    n_ctx: int,
    config: dict,
    progress_cb: Callable[[str], None],
    ki_debug: bool = False,
) -> object:  # → llama_cpp.Llama
    """
    Lädt ein GGUF-Modell mit optimalem Hardware-Setup.

    Fallback-Kette:
      1. GPU (alle Layer, KV-Cache auf GPU)
      2. CPU-only, falls GPU-Load mit OOM scheitert

    ki_debug=True: verbose=True in llama.cpp — gibt Ladedetails (Layer, KV-Cache,
    VRAM-Nutzung, Quantisierungstyp) direkt auf stderr aus. Die Ausgabe erscheint
    im Terminal, da der Subprocess seine Dateideskriptoren vom Elternprozess erbt.
    """
    _ensure_del_patched()

    from llama_cpp import Llama
    import llama_cpp.llama_chat_format as _fmt

    gpu = gpu_offload_active()
    progress_cb(
        f"Hardware: {'GPU-Offloading aktiv' if gpu else 'CPU-only'} "
        f"({'alle Layer auf GPU' if gpu else 'kein GPU-Backend kompiliert'})."
    )

    repeat_last_n  = config.get("repeat_last_n", 256)
    n_ctx_max      = config.get("n_ctx_max", 32768)
    rope_scale     = config.get("rope_scaling_max_factor", 1.0)
    n_ctx_native   = n_ctx_max if rope_scale > 1.0 else 0
    chat_template  = config.get("chat_template", "")

    orig_init, patched_init = _patch_jinja2_formatter(_fmt)
    _fmt.Jinja2ChatFormatter.__init__ = patched_init

    def _try_load(force_cpu: bool) -> object:
        kwargs = _build_kwargs(
            model_path, n_ctx,
            repeat_last_n=repeat_last_n,
            force_cpu=force_cpu,
            n_ctx_native=n_ctx_native,
            verbose=ki_debug,
        )
        # Im Debug-Modus stderr nicht umleiten: llama.cpp schreibt Ladedetails
        # direkt auf fd 2 (C-Level), was unsere Python-StringIO-Umleitung ohnehin
        # nicht erfasst. Im Normalbetrieb unterdrücken wir Python-stderr, um
        # Vulkan-OOM-Meldungen gezielt abzufangen.
        if ki_debug:
            try:
                return Llama(**kwargs)
            except Exception as exc:
                gc.collect()
                raise

        stderr_capture = io.StringIO()
        old_stderr     = sys.stderr
        sys.stderr     = stderr_capture
        try:
            llm = Llama(**kwargs)
        except Exception as exc:
            captured   = stderr_capture.getvalue()
            sys.stderr = io.StringIO()
            try:
                gc.collect()
            finally:
                sys.stderr = old_stderr
            if captured and _is_oom_error(exc, captured):
                raise MemoryError(
                    f"OOM beim Laden (Vulkan/CUDA): {captured.strip()[-200:]}"
                ) from exc
            raise
        else:
            sys.stderr = old_stderr
            return llm

    llm = None
    try:
        try:
            llm = _try_load(force_cpu=False)
        except Exception as e:
            if gpu and _is_oom_error(e):
                progress_cb(
                    f"GPU-OOM erkannt ({e}) — Neuversuch ohne GPU-Offloading …"
                )
                llm = _try_load(force_cpu=True)
            else:
                raise
    finally:
        _fmt.Jinja2ChatFormatter.__init__ = orig_init

    if chat_template:
        _apply_chat_template(llm, chat_template, _fmt)

    return llm


def _build_kwargs(
    model_path: str,
    n_ctx: int,
    repeat_last_n: int = 256,
    force_cpu: bool = False,
    n_ctx_native: int = 0,
    verbose: bool = False,
) -> dict:
    """
    Baut die Konstruktor-Argumente für Llama().

    n_ctx_native: nativer Trainings-Kontext. Wenn n_ctx > n_ctx_native,
                  wird YaRN-RoPE-Scaling aktiviert. 0 = kein Scaling.
    verbose:      True gibt llama.cpp-Ladedetails auf stderr aus (--ki-debug).
                  False (Standard) unterdrückt alle llama.cpp-Ausgaben.
    """
    cpu_logical  = os.cpu_count() or 4
    cpu_physical = max(1, cpu_logical // 2)

    rope_kwargs: dict = {}
    if n_ctx_native > 0 and n_ctx > n_ctx_native:
        rope_kwargs = {
            "rope_scaling_type": 2,
            "yarn_orig_ctx":     n_ctx_native,
            "yarn_ext_factor":   1.0,
        }

    if not force_cpu and gpu_offload_active():
        # use_mlock: Speicherseiten im RAM einfrieren verhindert Swapping und
        # beschleunigt Inferenz deutlich. Auf Windows erfordert mlock die
        # SeLockMemoryPrivilege — normale Nutzer haben diese nicht; llama.cpp
        # würde beim Laden scheitern. Auf Linux/macOS ist mlock ohne Privilegien
        # bis zum Systemlimit (ulimit -l) möglich.
        return dict(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=-1,
            n_threads=cpu_physical,
            n_threads_batch=cpu_logical,
            n_batch=512,
            n_ubatch=512,
            last_n_tokens_size=repeat_last_n,
            offload_kqv=True,
            use_mlock=sys.platform != "win32",
            flash_attn=not _is_vulkan_backend(),
            verbose=verbose,
            **rope_kwargs,
        )
    return dict(
        model_path=model_path,
        n_ctx=n_ctx,
        n_gpu_layers=0,
        n_threads=cpu_physical,
        n_threads_batch=cpu_logical,
        n_batch=512,
        n_ubatch=256,
        last_n_tokens_size=repeat_last_n,
        offload_kqv=False,
        use_mlock=False,
        flash_attn=True,
        verbose=verbose,
        **rope_kwargs,
    )


def _is_oom_error(e: Exception, captured_stderr: str = "") -> bool:
    """True wenn e oder der mitgeschnittene stderr auf OOM hindeutet."""
    combined = (str(e) + " " + captured_stderr).lower()
    return any(kw in combined for kw in (
        "out of memory", "oom", "cuda error", "vram",
        "failed to allocate", "device memory", "allocation of size",
        "outofdevicememory", "erroroutofdevicememory",
        "allocatememory", "vk_allocate",
        "failed to load model from file",
    ))


def _apply_chat_template(llm: object, chat_template: str, fmt_module) -> None:
    """
    Wendet ein explizit konfiguriertes Jinja2-Chat-Template an, wenn das GGUF
    kein eigenes Template enthält.
    """
    if getattr(llm, "chat_handler", None) is not None:
        return
    try:
        metadata      = getattr(llm, "metadata", {})
        eos_token_id  = int(metadata.get("tokenizer.ggml.eos_token_id", 2))
        bos_token_id  = int(metadata.get("tokenizer.ggml.bos_token_id", 1))
        try:
            eos_token = llm._model.token_get_text(eos_token_id)
            bos_token = llm._model.token_get_text(bos_token_id)
        except Exception:
            eos_token = "</s>"
            bos_token = "<s>"
        formatter = fmt_module.Jinja2ChatFormatter(
            template=chat_template,
            eos_token=eos_token,
            bos_token=bos_token,
            stop_token_ids=[eos_token_id],
        )
        llm.chat_handler = formatter.to_chat_handler()
    except Exception:
        pass


def _patch_jinja2_formatter(fmt_module) -> tuple:
    """
    Patcht Jinja2ChatFormatter.__init__ um HuggingFace-spezifische Template-Tags
    ({% generation %}, strftime_now()) zu entfernen.
    """
    orig_init = fmt_module.Jinja2ChatFormatter.__init__

    def _safe_init(self, template: str = "", **kw):
        cleaned = re.sub(
            r"\{%-?\s*generation\s*-?%\}|\{%-?\s*endgeneration\s*-?%\}",
            "", template,
        )
        cleaned = re.sub(r"strftime_now\([^)]*\)", '"(Datum)"', cleaned)
        try:
            orig_init(self, template=cleaned, **kw)
        except Exception:
            chatml = (
                "{% for message in messages %}"
                "{{ '<|im_start|>' + message['role'] + '\\n' "
                "+ message['content'] + '<|im_end|>\\n' }}"
                "{% endfor %}"
                "{% if add_generation_prompt %}"
                "{{ '<|im_start|>assistant\\n' }}{% endif %}"
            )
            orig_init(self, template=chatml, **kw)

    return orig_init, _safe_init


_del_patch_applied: bool = False


def _ensure_del_patched() -> None:
    """
    Patcht LlamaModel.__del__ einmalig, damit Exceptions bei unvollständig
    initialisierten Objekten nicht unkontrolliert auf stderr landen.
    """
    global _del_patch_applied
    if _del_patch_applied:
        return
    try:
        import llama_cpp._internals as _int
        if not getattr(_int.LlamaModel, "_del_patched", False):
            _orig_del = _int.LlamaModel.__del__

            def _guarded_del(self):
                try:
                    old = sys.stderr
                    sys.stderr = io.StringIO()
                    try:
                        _orig_del(self)
                    except Exception:
                        pass
                    finally:
                        sys.stderr = old
                except Exception:
                    pass

            _int.LlamaModel.__del__ = _guarded_del
            _int.LlamaModel._del_patched = True
        _del_patch_applied = True
    except Exception:
        pass


def _safe_close(llm: object) -> None:
    """Ruft llm.close() explizit auf und unterdrückt alle Exceptions."""
    _ensure_del_patched()
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        close_fn = getattr(llm, "close", None)
        if close_fn is not None:
            close_fn()
    except Exception:
        pass
    finally:
        sys.stderr = old_stderr


# ===========================================================================
# GPU-Erkennung (im Subprocess verfügbar)
# ===========================================================================

_vulkan_backend: bool | None = None


def gpu_offload_active() -> bool:
    """True, wenn das kompilierte llama-cpp-python ein GPU-Backend hat."""
    try:
        from llama_cpp import llama_cpp as _lc
        return bool(_lc.llama_supports_gpu_offload())
    except Exception:
        return False


def _is_vulkan_backend() -> bool:
    """True wenn Vulkan das aktive GPU-Backend ist (gecacht)."""
    global _vulkan_backend
    if _vulkan_backend is None:
        try:
            from llama_cpp import llama_cpp as _lc
            info = _lc.llama_print_system_info() or b""
            _vulkan_backend = b"ggml_vulkan" in info
        except Exception:
            _vulkan_backend = False
    return _vulkan_backend
