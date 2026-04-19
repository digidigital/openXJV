"""
Download-Dialog: warnt vor IP-Sichtbarkeit, zeigt Download-URL,
bietet Fortschrittsanzeige und Abbruchmöglichkeit.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QSize, Signal
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
)

from ..downloader import download_model, DownloadError
from ..model_registry import ModelConfig
from openxjv.utils import open_url


class _DownloadSignals(QObject):
    progress = Signal(float, float)  # (mb_done, mb_total)
    finished = Signal()
    error    = Signal(str)


class DownloadDialog(QDialog):
    """
    Zeigt eine Warnung zur Datenschutzlage, die Download-URL sowie
    Fortschrittsanzeige und Abbruchmöglichkeit.
    """

    def __init__(self, config: ModelConfig, dest_path: Path,
                 parent=None, app_icon: QIcon | None = None,
                 app_font: QFont | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._dest_path = dest_path
        self._cancel_flag: list[bool] = [False]
        self._downloading = False
        self._sigs = _DownloadSignals()
        self._sigs.progress.connect(self._on_progress)
        self._sigs.finished.connect(self._on_finished)
        self._sigs.error.connect(self._on_error)

        # Icon vom Parent übernehmen oder direkt übergeben
        if app_icon is not None:
            self.setWindowIcon(app_icon)
        elif parent is not None and hasattr(parent, "_app_icon"):
            self.setWindowIcon(parent._app_icon)

        # Font vom Parent übernehmen oder direkt übergeben
        if app_font is not None:
            self._app_font = app_font
        elif parent is not None and hasattr(parent, "_app_font"):
            self._app_font = parent._app_font
        else:
            self._app_font = QFont("Ubuntu")

        self.setWindowTitle("Modell herunterladen")
        self.setFixedSize(580, 470)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowMaximizeButtonHint
            & ~Qt.WindowMinimizeButtonHint
        )
        self.setModal(True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # Datenschutz-Warnung
        warn = QLabel(
            "<b>Datenschutzhinweis:</b><br>"
            "Durch den Download wird Ihre IP-Adresse und ggf. weitere Metadaten "
            "(Browser-Kennung, Zeitstempel) für den Download-Server sichtbar.<br>"
            "Bitte stellen Sie sicher, dass dies mit Ihren Datenschutzanforderungen vereinbar ist.<br>"
            "Datenschutzerklärung des Anbieters: "
            "<a href='https://huggingface.co/privacy'>https://huggingface.co/privacy</a>"
        )
        warn.setFont(self._app_font)
        warn.setWordWrap(True)
        warn.setOpenExternalLinks(False)
        warn.linkActivated.connect(open_url)
        warn.setStyleSheet(
            "background: #fff3cd; color: #1a1a1a; border: 1px solid #ffc107; padding: 8px;"
            "a { color: #1a1a1a; }"
        )
        layout.addWidget(warn)

        # Modell-Informationen
        info_group = QGroupBox("Modell")
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(4)

        name_label = QLabel(
            f"<b>{self._config.display_name}</b> ({self._config.filename})"
        )
        name_label.setFont(self._app_font)
        name_label.setWordWrap(True)
        info_layout.addWidget(name_label)

        url_label = QLabel(self._config.download_url)
        url_label.setWordWrap(True)
        url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(9)
        url_label.setFont(mono)
        info_layout.addWidget(url_label)

        dest_label = QLabel(f"Zielordner: {self._dest_path.parent}")
        dest_label.setFont(self._app_font)
        dest_label.setWordWrap(True)
        info_layout.addWidget(dest_label)

        layout.addWidget(info_group)

        # Fortschritt
        progress_group = QGroupBox("Fortschritt")
        progress_layout = QVBoxLayout(progress_group)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setVisible(False)
        progress_layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setFont(self._app_font)
        self._status_label.setVisible(False)
        progress_layout.addWidget(self._status_label)

        layout.addWidget(progress_group)

        # Schaltflächen
        btn_row = QHBoxLayout()
        self._btn_download = QPushButton("Download starten")
        self._btn_download.setFont(self._app_font)
        self._btn_download.setFixedHeight(36)
        self._btn_download.clicked.connect(self._start_download)
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.setFont(self._app_font)
        btn_cancel.setFixedHeight(36)
        btn_cancel.clicked.connect(self._cancel)
        btn_row.addWidget(self._btn_download)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _start_download(self) -> None:
        self._btn_download.setEnabled(False)
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(True)
        self._status_label.setText("Download läuft …")
        self._status_label.setStyleSheet("")
        self._status_label.setVisible(True)
        self._cancel_flag[0] = False
        self._downloading = True

        def _run():
            try:
                download_model(
                    url=self._config.download_url,
                    dest_path=self._dest_path,
                    progress_cb=lambda done, total: self._sigs.progress.emit(
                        done / (1024 * 1024), total / (1024 * 1024) if total > 0 else -1.0
                    ),
                    cancel_flag=self._cancel_flag,
                )
                self._sigs.finished.emit()
            except DownloadError as e:
                self._sigs.error.emit(str(e))
            except Exception as e:
                self._sigs.error.emit(f"Unerwarteter Fehler: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def _cancel(self) -> None:
        self._cancel_flag[0] = True
        if self._downloading:
            self._btn_download.setEnabled(False)
            self._status_label.setText("Wird abgebrochen …")
            self._status_label.setStyleSheet("")
            self._status_label.setVisible(True)
        else:
            self.reject()

    def _on_progress(self, mb_done: float, mb_total: float) -> None:
        if mb_total > 0:
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(int(mb_done * 100 / mb_total))
            self._status_label.setText(f"{mb_done:.1f} / {mb_total:.1f} MB")
        else:
            self._progress_bar.setRange(0, 0)
            self._status_label.setText(f"{mb_done:.1f} MB heruntergeladen …")

    def _on_finished(self) -> None:
        self._downloading = False
        if self._cancel_flag[0]:
            part_path = self._dest_path.with_suffix(self._dest_path.suffix + ".part")
            try:
                part_path.unlink(missing_ok=True)
            except OSError:
                pass
            self.reject()
        else:
            self._status_label.setText("Download abgeschlossen.")
            self.accept()

    def _on_error(self, msg: str) -> None:
        self._downloading = False
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        if self._cancel_flag[0]:
            part_path = self._dest_path.with_suffix(self._dest_path.suffix + ".part")
            try:
                part_path.unlink(missing_ok=True)
            except OSError:
                pass
            self.reject()
            return
        self._status_label.setText(f"Fehler: {msg}")
        self._status_label.setStyleSheet("color: #cc0000;")
        self._btn_download.setText("Erneut versuchen")
        self._btn_download.setEnabled(True)
