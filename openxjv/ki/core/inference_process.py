"""
Elternprozess-seitige Verwaltung des Inferenz-Subprozesses.

InferenceProcess startet einen separaten Python-Prozess (spawn), der alle
llama-cpp-python-Operationen übernimmt. Der Elternprozess bleibt frei von
GPU-Threads und Qt-Konflikten.

Modell-Persistenz: Der Subprocess hält das zuletzt geladene Modell im Speicher.
Ein Neustart des Subprozesses erfolgt nur dann, wenn er unerwartet beendet
wurde (Absturz, OOM) — nicht beim normalen Modellwechsel (das übernimmt der
Subprocess selbst via Cache-Eviction).

Kommunikation:
  cmd_queue  – Elternprozess → Subprocess (Analyse-Befehle, Shutdown-Sentinel)
  resp_queue – Subprocess → Elternprozess (PROGRESS, TOKEN, DONE, ERROR)
  cancel     – multiprocessing.Event für kooperativen Abbruch

PyInstaller / AppImage — WICHTIGER HINWEIS:
  Bei gefrorenen Executables (PyInstaller, cx_Freeze) muss der Einstiegspunkt
  der Anwendung (openxjv/__main__.py oder openxjv.py) folgendes aufrufen:

      if __name__ == "__main__":
          import multiprocessing
          multiprocessing.freeze_support()   # MUSS VOR jeder anderen App-Logik stehen
          ...

  Ohne diesen Aufruf öffnet jeder gespawnte Subprocess erneut die komplette
  Anwendung (inkl. GUI) anstatt nur den Worker zu starten.
  Dieser Aufruf ist im Hauptprozess eine No-Op; er schadet daher nicht, wenn die
  Anwendung normal (nicht eingefroren) gestartet wird.
"""
from __future__ import annotations

import multiprocessing as _mp
import queue as _queue
from collections.abc import Iterator

from .inference_worker import PROGRESS, TOKEN, DONE, ERROR, worker_main


class InferenceProcess:
    """
    Verwaltet einen persistenten Inferenz-Subprocess.

    Öffentliche API:
        ensure_started() – Subprocess starten (idempotent)
        stop()           – Subprocess sauber beenden (mit Kill-Fallback)
        cancel()         – Laufende Analyse kooperativ abbrechen
        analyze(params)  – Analyseauftrag senden, Nachrichten via Generator empfangen
    """

    def __init__(self) -> None:
        self._ctx     = _mp.get_context("spawn")
        self._process: "_mp.Process | None"  = None
        self._cmd_q:   "_mp.Queue | None"    = None
        self._resp_q:  "_mp.Queue | None"    = None
        self._cancel:  "_mp.Event | None"    = None

    # ------------------------------------------------------------------
    # Lebenszyklus
    # ------------------------------------------------------------------

    def ensure_started(self) -> None:
        """Startet den Subprocess, falls nicht vorhanden oder abgestürzt."""
        if self._process is not None and self._process.is_alive():
            return
        # Defensive Absicherung für PyInstaller/AppImage:
        # freeze_support() ist im Elternprozess eine No-Op; im gefrorenen Child-
        # Prozess fängt sie den Spawn-Einstiegspunkt ab, bevor App-Code läuft.
        # Eigentlich muss dieser Aufruf im __main__-Block stehen — hier als
        # zusätzliche Sicherung, falls der App-Einstiegspunkt ihn nicht enthält.
        import multiprocessing as _mp_fs
        _mp_fs.freeze_support()
        self._cmd_q  = self._ctx.Queue()
        self._resp_q = self._ctx.Queue()
        self._cancel = self._ctx.Event()
        self._process = self._ctx.Process(
            target=worker_main,
            args=(self._cmd_q, self._resp_q, self._cancel),
            daemon=True,
        )
        self._process.start()

    def stop(self) -> None:
        """
        Beendet den Subprocess sauber.

        Ablauf:
          1. Shutdown-Sentinel (None) senden — Worker beendet sich nach der
             aktuellen Hauptschleifenrunde und räumt das Modell auf.
          2. Maximal 3 Sekunden auf sauberes Ende warten.
          3. Falls immer noch lebendig: sofort per kill() beenden.
        """
        if self._process is None:
            return
        if self._process.is_alive():
            try:
                self._cmd_q.put(None)
            except Exception:
                pass
            self._process.join(timeout=3.0)
        if self._process.is_alive():
            self._process.kill()
            self._process.join(timeout=2.0)
        self._process = None
        self._cmd_q = self._resp_q = self._cancel = None

    def cancel(self) -> None:
        """
        Signalisiert dem Subprocess, die laufende Analyse abzubrechen.

        Der Subprocess prüft das Event kooperativ zwischen Token-Generierungen
        und an allen Kontrollpunkten (vor Chunk-Verarbeitung, nach Modell-Load).
        """
        if self._cancel is not None:
            self._cancel.set()

    # ------------------------------------------------------------------
    # Analyse
    # ------------------------------------------------------------------

    def analyze(self, params: dict) -> Iterator[tuple]:
        """
        Schickt einen Analyseauftrag an den Subprocess und liefert
        Nachrichten via Generator zurück.

        Yields:
            (PROGRESS, str)  – Fortschrittsmeldung
            (TOKEN, str)     – generierter Token
            (DONE,)          – Analyse abgeschlossen
            (ERROR, str)     – Fehler (mit Traceback)

        Der Generator beendet sich nach dem ersten DONE oder ERROR.
        """
        self.ensure_started()

        # Rückstände aus vorherigen (abgebrochenen) Läufen leeren
        _drain(self._resp_q)

        self._cmd_q.put({"cmd": "analyze", **params})

        while True:
            try:
                msg = self._resp_q.get(timeout=0.5)
            except _queue.Empty:
                if not self._process.is_alive():
                    yield (ERROR, "Inferenzprozess unerwartet beendet.")
                    return
                continue
            yield msg
            if msg[0] in (DONE, ERROR):
                return


# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------

def _drain(q: "_mp.Queue") -> None:
    """Leert eine Queue non-blocking (entfernt alle ausstehenden Nachrichten)."""
    while True:
        try:
            q.get_nowait()
        except _queue.Empty:
            return
