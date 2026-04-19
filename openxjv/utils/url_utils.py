#!/usr/bin/env python3
# coding: utf-8
"""
URL-Öffner für openXJV.

Problem: QDesktopServices.openUrl() erbt im AppImage-Betrieb die vergiftete
Laufzeitumgebung von PyInstaller (insbesondere LD_LIBRARY_PATH zeigt auf
interne Qt-Bibliotheken). Auf Arch-basierten Systemen (Manjaro) ruft
xdg-open dabei gio/gtk-launch auf, das GLib dynamisch nachlädt — mit den
falschen Bibliotheken schlägt das lautlos fehl.

Lösung: Unter Linux + frozen/AppImage wird xdg-open direkt als Subprocess
gestartet, nachdem LD_LIBRARY_PATH aus der Umgebung entfernt wurde. Auf allen
anderen Plattformen und im Entwicklungsmodus bleibt QDesktopServices.openUrl()
als Fallback erhalten.
"""

import os
import subprocess
import sys
from typing import Union

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def is_in_bundle() -> bool:
    """True wenn die App in einem PyInstaller- oder AppImage-Bundle läuft.

    Erkennt drei Fälle:
    - sys.frozen: PyInstaller-Build
    - OPENXJV_APPIMAGE: von AppRun gesetzt (greift auch bei direktem AppRun-Aufruf)
    - APPIMAGE: vom AppImage-Runtime (ELF-Stub) gesetzt
    """
    return (
        getattr(sys, "frozen", False)
        or bool(os.environ.get("OPENXJV_APPIMAGE"))
        or bool(os.environ.get("APPIMAGE"))
    )


def open_url(url: Union[QUrl, str]) -> None:
    """Öffnet eine URL im zuständigen Standardprogramm des Systems.

    Auf Linux-AppImage/PyInstaller-Builds wird xdg-open direkt aufgerufen,
    um die vergiftete LD_LIBRARY_PATH-Umgebung zu umgehen (siehe Modul-
    Docstring). Auf allen anderen Plattformen und im Entwicklungsmodus
    wird QDesktopServices.openUrl() verwendet.

    Args:
        url: Die zu öffnende URL als QUrl-Objekt oder String.
             Unterstützt http://, https://, mailto: und file://.
    """
    url_string = url.toString() if isinstance(url, QUrl) else url

    if sys.platform.startswith("linux") and is_in_bundle():
        # WORKAROUND: QDesktopServices.openUrl() gibt LD_LIBRARY_PATH aus dem
        # AppImage-Bundle an xdg-open weiter. Auf Arch/Manjaro lädt xdg-open
        # darüber gio/gtk-launch mit inkompatiblen Bibliotheken und schlägt
        # lautlos fehl. Direkter Subprocess-Aufruf mit bereinigter Umgebung
        # vermeidet das.
        env = os.environ.copy()
        env.pop("LD_LIBRARY_PATH", None)
        subprocess.Popen(
            ["xdg-open", url_string],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        q_url = url if isinstance(url, QUrl) else QUrl(url)
        QDesktopServices.openUrl(q_url)
