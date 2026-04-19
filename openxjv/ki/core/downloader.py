"""
Modell-Download mit Fortschrittsmeldung und Abbruchmöglichkeit.

Öffentliche API:
    download_model(url, dest_path, progress_cb, cancel_flag) → None

Wirft DownloadError bei Netzwerk-, HTTP- oder Schreibfehlern.
Schreibt zunächst in eine .part-Datei und benennt sie erst bei Erfolg um
(verhindert unvollständige GGUF-Dateien, die als gültig erkannt werden könnten).
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CONTEXT = ssl.create_default_context()


class DownloadError(Exception):
    """Einheitlicher Fehler für alle Download-Operationen."""
    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


def download_model(
    url: str,
    dest_path: Path,
    progress_cb: Callable[[int, int], None],
    cancel_flag: list[bool],
) -> None:
    """
    Lädt url in dest_path herunter.

    progress_cb wird mit (bytes_downloaded, total_bytes) aufgerufen.
    total_bytes kann -1 sein, wenn der Server keine Content-Length schickt.
    cancel_flag[0] = True bricht den Download ab (.part-Datei bleibt liegen
    und wird beim nächsten App-Start durch cleanup_part_files() gelöscht).

    Raises:
        DownloadError: bei HTTP-Fehler, Netzwerkfehler oder Schreibfehler.
    """
    dest_path = Path(dest_path)
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")

    # Zielordner anlegen
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise DownloadError(
            f"Zielordner konnte nicht erstellt werden: {dest_path.parent}", cause=e
        ) from e

    # Bereits vorhandene .part-Datei löschen (abgebrochener vorheriger Download)
    if part_path.exists():
        try:
            part_path.unlink()
        except OSError:
            pass

    headers = {"User-Agent": "generic/1.0 (python)"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as response:
            status = response.status if hasattr(response, "status") else 200
            if status >= 400:
                raise DownloadError(f"HTTP-Fehler {status} beim Herunterladen von {url}")

            total_raw = response.headers.get("Content-Length", "")
            try:
                total_bytes = int(total_raw)
            except (ValueError, TypeError):
                total_bytes = -1

            downloaded = 0
            _CHUNK = 64 * 1024  # 64 KB

            try:
                with part_path.open("wb") as f:
                    while True:
                        if cancel_flag[0]:
                            progress_cb(downloaded, total_bytes)
                            return

                        data = response.read(_CHUNK)
                        if not data:
                            break
                        f.write(data)
                        downloaded += len(data)
                        progress_cb(downloaded, total_bytes)
            except OSError as e:
                raise DownloadError(
                    f"Schreibfehler beim Download (Speicher voll?): {part_path}", cause=e
                ) from e

    except urllib.error.HTTPError as e:
        # Versuche den HuggingFace-Fehlertext aus dem JSON-Body zu lesen
        hf_msg = _read_hf_error(e)
        if hf_msg:
            hint = (
                " — HuggingFace-Token erforderlich oder ungültig."
                if e.code in (401, 403) else ""
            )
            raise DownloadError(
                f"HTTP-Fehler {e.code}: {hf_msg}{hint}", cause=e
            ) from e
        raise DownloadError(
            f"HTTP-Fehler {e.code} beim Herunterladen von {url}", cause=e
        ) from e
    except urllib.error.URLError as e:
        raise DownloadError(
            f"Netzwerkfehler beim Herunterladen: {e.reason}", cause=e
        ) from e
    except DownloadError:
        raise
    except Exception as e:
        raise DownloadError(f"Unerwarteter Fehler beim Download: {e}", cause=e) from e

    # Erfolg: .part → finale Datei umbenennen
    if cancel_flag[0]:
        return

    try:
        if dest_path.exists():
            dest_path.unlink()
        part_path.rename(dest_path)
    except OSError as e:
        raise DownloadError(
            f"Konnte heruntergeladene Datei nicht umbenennen: {part_path} → {dest_path}",
            cause=e,
        ) from e


def _read_hf_error(e: urllib.error.HTTPError) -> str:
    """
    Versucht den 'error'-Text aus dem JSON-Body einer HuggingFace-HTTPError
    zu lesen. Gibt leeren String zurück wenn der Body kein verwertbares JSON ist.
    """
    try:
        body = e.read(4096).decode("utf-8", errors="replace")
        data = json.loads(body)
        return str(data.get("error", "")).strip()
    except Exception:
        return ""
