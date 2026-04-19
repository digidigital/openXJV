"""
KI-Labor Hauptfenster.

Integration in openXJV:
    registry = ModelRegistry(models_dir=db_dir / "models")
    window = KIMainWindow(registry=registry, app_dir=script_root)
    window.set_file_path("/pfad/zur/datei.pdf")  # optional
    window.show()
"""
from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QSignalBlocker, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QTextCursor

try:
    from platformdirs import user_documents_dir as _user_documents_dir
except ImportError:
    def _user_documents_dir() -> str:  # type: ignore[misc]
        return str(Path.home())

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ... import __version__ as _KI_VERSION
from ..model_registry import ModelRegistry, ModelConfig
from ..model_loader import estimate_n_ctx, gpu_offload_active
from ..text_preprocessor import clean
from ..text_compressor import deduplicate_paragraphs, deduplicate_short_lines
from ..inference_process import InferenceProcess
from .signals import Signals
from .download_dialog import DownloadDialog
from openxjv.utils.url_utils import open_url

# Unterstützte Dateiformate (muss mit text_extraction.py übereinstimmen)
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".odt", ".ods", ".txt", ".csv", ".xlsx", ".xml", ".html"}

_FILE_FILTER = (
    "Unterstützte Dokumente (*.pdf *.docx *.odt *.ods *.txt *.csv *.xlsx *.xml *.html);;"
    "PDF-Dateien (*.pdf);;"
    "Word-Dokumente (*.docx);;"
    "OpenDocument (*.odt *.ods);;"
    "Tabellen (*.xlsx);;"
    "Textdateien (*.txt *.csv);;"
    "XML/HTML (*.xml *.html)"
)


def _license_text_to_html(display_name: str, text: str) -> str:
    """Wandelt eine strukturierte Lizenz-Textdatei in einfaches HTML um."""
    import html as _html
    import re as _re
    lines = text.splitlines()
    parts: list[str] = [
        "<html><head><style>"
        "a { color: #0a57b8; text-decoration: underline; }"
        "a:visited { color: #7b1fa2; }"
        "</style></head>"
        "<body style='font-family: sans-serif; font-size: 10pt; "
        "margin: 12px; color: #1a1a1a; background-color: #e6e6e6;'>"
    ]
    first_line = True
    for line in lines:
        esc = _html.escape(line)
        if first_line and esc.strip():
            parts.append(f"<h2 style='margin-bottom:2px;'>{esc}</h2>")
            first_line = False
        elif set(esc.strip()) <= {"=", "-"} and esc.strip():
            continue
        elif esc.strip() == "":
            parts.append("<br>")
        elif ":" in esc and not esc.startswith("-") and not esc.startswith(" "):
            key, _, val = esc.partition(":")
            val = val.strip()
            # linkify all URL values
            val = _re.sub(
                r'(https?://\S+)',
                r"<a href='\1'>\1</a>",
                val,
            )
            if key.strip().lower() in ("wesentliche bedingungen", "zusätzliche bedingungen (gemma terms of use)"):
                parts.append(
                    f"<p style='margin-top:10px; margin-bottom:4px;'>"
                    f"<b>{key}:</b></p><ul style='margin:0; padding-left:20px;'>"
                )
            else:
                parts.append(
                    f"<p style='margin:2px 0;'>"
                    f"<b>{key}:</b> {val}</p>"
                )
        elif esc.startswith("- "):
            parts.append(f"<li style='margin:2px 0;'>{esc[2:]}</li>")
        else:
            parts.append(f"<p style='margin:2px 0;'>{esc}</p>")
    parts.append("</ul></body></html>")
    return "".join(parts)


_INDIVIDUELL = "individuell"


class KIMainWindow(QMainWindow):
    def __init__(
        self,
        registry: ModelRegistry | None = None,
        app_dir: str | Path | None = None,
        ki_debug: bool = False,
    ) -> None:
        super().__init__()
        self._ki_debug = ki_debug
        self._registry = registry or ModelRegistry()
        self._cancel_flag: list[bool] = [False]
        self._manual_window: "QDialog | None" = None
        self._ocr_process: object | None = None  # multiprocessing.Process während OCR
        self._text_cache: dict[tuple[str, str], str] = {}  # (file_path, ocr_mode) → raw text
        self._cpu_warning_shown = False
        self._last_open_dir: str = _user_documents_dir()
        # Inferenz-Subprocess: hält das Modell zwischen Analysen im Speicher.
        # Daemon-Prozess — wird automatisch beendet, wenn der Elternprozess endet.
        self._inference_proc = InferenceProcess()
        self._signals = Signals()
        self._signals.progress.connect(self._on_progress)
        self._signals.token.connect(self._on_token)
        self._signals.error.connect(self._on_error)
        self._signals.started.connect(self._on_started)
        self._signals.finished.connect(self._on_finished)

        # App-Verzeichnis: für Icons, Fonts, Docs
        if app_dir is not None:
            self._app_dir = Path(app_dir)
        else:
            # PyInstaller: sys._MEIPASS, sonst openXJV.py-Verzeichnis
            if getattr(sys, "frozen", False):
                self._app_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]
            else:
                # Gehe drei Ebenen hoch: ki/core/ui → ki/core → ki → openxjv → Projektroot
                self._app_dir = Path(__file__).parent.parent.parent.parent.parent

        self._load_font()
        self._load_icon()

        self.setWindowTitle(f"KI-Labor (Dokumentanalyse) v{_KI_VERSION}")
        self.resize(1050, 740)
        self._build_ui()
        self._on_model_changed()
        self._check_models_on_startup()

    # ------------------------------------------------------------------
    # Font & Icon laden (analog zu openXJV)
    # ------------------------------------------------------------------

    def _load_font(self) -> None:
        font_dir = self._app_dir / "fonts"
        font_files = [
            "ubuntu-font-family-0.83/Ubuntu-L.ttf",
            "ubuntu-font-family-0.83/Ubuntu-R.ttf",
        ]
        for rel in font_files:
            fp = str(font_dir / rel)
            if QFontDatabase.addApplicationFont(fp) == -1:
                pass  # Font schon geladen oder nicht vorhanden — kein Abbruch
        self._app_font = QFont("Ubuntu")

    def _load_icon(self) -> None:
        try:
            icon_dir = self._app_dir / "icons"
            if (icon_dir / "openxjv_desktop.ico").exists():
                self._app_icon = QIcon(str(icon_dir / "openxjv_desktop.ico"))
            else:
                icon = QIcon()
                from PySide6.QtCore import QSize
                for size, name in [(16, "appicon16.png"), (32, "appicon32.png"),
                                   (64, "appicon64.png"), (128, "appicon128.png"),
                                   (256, "appicon256.png")]:
                    p = icon_dir / name
                    if p.exists():
                        icon.addFile(str(p), QSize(size, size))
                self._app_icon = icon
            self.setWindowIcon(self._app_icon)
        except Exception:
            self._app_icon = QIcon()  # leeres Icon als Fallback

    # ------------------------------------------------------------------
    # Host-API
    # ------------------------------------------------------------------

    def set_file_path(self, path: str | Path) -> None:
        """
        Setzt den Dokumentpfad — genau wie wenn der Nutzer auf 'Öffnen' geklickt hätte.
        Aktualisiert auch den Startordner für den Dateidialog.
        """
        path = str(path)
        if path != self._file_edit.text().strip():
            self._text_cache.clear()
        self._file_edit.setText(path)
        self._last_open_dir = str(Path(path).parent)

    # ------------------------------------------------------------------
    # UI-Aufbau
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        # --- Dokument ---
        self._doc_group = QGroupBox("Dokument")
        doc_layout = QHBoxLayout(self._doc_group)
        self._file_edit = QLineEdit()
        self._file_edit.setReadOnly(True)
        self._file_edit.setFont(self._app_font)
        self._file_edit.setPlaceholderText("Keine Datei ausgewählt …")
        self._file_edit.setToolTip(
            "Pfad der zu analysierenden Datei.\n"
            "Unterstützte Formate: PDF, DOCX, ODT, ODS, XLSX, TXT, CSV, XML, HTML"
        )
        btn_open = QPushButton("Öffnen …")
        btn_open.setFont(self._app_font)
        btn_open.setToolTip("Dokument auswählen, das analysiert werden soll")
        btn_open.clicked.connect(self._pick_file)
        doc_layout.addWidget(self._file_edit)
        doc_layout.addWidget(btn_open)
        root.addWidget(self._doc_group)

        # --- Modell + Prompt-Vorlage + Max. Ausgabe ---
        ctrl_group = QGroupBox("Einstellungen")
        ctrl_layout = QHBoxLayout(ctrl_group)

        lbl_modell = QLabel("Modell:")
        lbl_modell.setFont(self._app_font)
        ctrl_layout.addWidget(lbl_modell)

        self._model_combo = QComboBox()
        self._model_combo.setFont(self._app_font)
        self._model_combo.setMinimumWidth(160)
        self._model_combo.setToolTip(
            "KI-Modell auswählen. Ist das Modell noch nicht heruntergeladen, "
            "startet beim Klick auf 'Analyse starten' automatisch ein Download-Dialog."
        )
        for cfg in self._registry.all_models():
            self._model_combo.addItem(cfg.display_name, userData=cfg.id)
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        ctrl_layout.addWidget(self._model_combo, stretch=2)

        self._btn_license = QPushButton("\u24d8")
        self._btn_license.setFixedSize(24, 24)
        self._btn_license.setToolTip("Lizenzinformation anzeigen")
        self._btn_license.setFlat(True)
        self._btn_license.clicked.connect(self._show_license)
        ctrl_layout.addWidget(self._btn_license)

        self._model_status = QLabel("")
        self._model_status.setFont(self._app_font)
        self._model_status.setMinimumWidth(120)
        self._model_status.setToolTip("Zeigt an, ob die Modelldatei lokal vorhanden ist")
        ctrl_layout.addWidget(self._model_status)

        ctrl_layout.addSpacing(16)

        lbl_ocr = QLabel("OCR:")
        lbl_ocr.setFont(self._app_font)
        ctrl_layout.addWidget(lbl_ocr)

        self._ocr_combo = QComboBox()
        self._ocr_combo.setFont(self._app_font)
        self._ocr_combo.addItem("keine",      userData="none")
        self._ocr_combo.addItem("erzwungen",  userData="force")
        self._ocr_combo.setToolTip(
            "Steuert die KI-gestützte Texterkennung (OCR) für PDF-Dokumente."
        )
        ctrl_layout.addWidget(self._ocr_combo)

        btn_ocr_info = QPushButton("\u24d8")
        btn_ocr_info.setFixedSize(24, 24)
        btn_ocr_info.setFlat(True)
        btn_ocr_info.setToolTip("Lizenz- und Quellinformationen der eingesetzten OCR-Modelle anzeigen")
        btn_ocr_info.clicked.connect(self._show_ocr_license)
        ctrl_layout.addWidget(btn_ocr_info)

        ctrl_layout.addSpacing(16)

        lbl_stil = QLabel("Prompt-Vorlage:")
        lbl_stil.setFont(self._app_font)
        ctrl_layout.addWidget(lbl_stil)

        self._stil_combo = QComboBox()
        self._stil_combo.setFont(self._app_font)
        self._stil_combo.setToolTip(
            "Analyse-Vorlage auswählen. Bestimmt Struktur und Schwerpunkt der KI-Ausgabe.\n"
            "'individuell': eigenen Prompt im Textfeld darunter eingeben."
        )
        for s in self._registry.get_stile():
            self._stil_combo.addItem(s)
        self._stil_combo.addItem(_INDIVIDUELL)
        self._stil_combo.setCurrentText(_INDIVIDUELL)
        self._stil_combo.currentIndexChanged.connect(self._on_stil_changed)
        ctrl_layout.addWidget(self._stil_combo, stretch=2)

        ctrl_layout.addSpacing(16)

        lbl_max = QLabel("Max. Ausgabe:")
        lbl_max.setFont(self._app_font)
        ctrl_layout.addWidget(lbl_max)

        self._max_tokens_combo = QComboBox()
        self._max_tokens_combo.setFont(self._app_font)
        self._max_tokens_combo.setToolTip(
            "Maximale Anzahl Token (Wortteile), die das Modell ausgeben darf.\n"
            "Grosse Werte erhoehen die Analysezeit. Standard: 1536."
        )
        for tokens in [1024, 1536, 2048, 3072, 4092]:
            self._max_tokens_combo.addItem(f"{tokens} Token", userData=tokens)
        self._max_tokens_combo.setCurrentIndex(1)
        ctrl_layout.addWidget(self._max_tokens_combo)

        root.addWidget(ctrl_group)

        # --- Prompt-Editor ---
        prompt_group = QGroupBox("Prompt")
        prompt_layout = QVBoxLayout(prompt_group)
        self._prompt_edit = QPlainTextEdit()
        self._prompt_edit.setFont(self._app_font)
        self._prompt_edit.setPlaceholderText("Fragen und Anweisungen bitte hier eingeben …")
        self._prompt_edit.setToolTip(
            "Anweisung an die KI. Bei Auswahl einer Vorlage wird dieses Feld automatisch\n"
            "befuellt. Manuelle Aenderungen schalten die Vorlage auf 'individuell' um."
        )
        self._prompt_edit.setMinimumHeight(60)
        self._prompt_edit.textChanged.connect(self._on_prompt_edited)
        prompt_layout.addWidget(self._prompt_edit)
        root.addWidget(prompt_group)

        self._prompt_loading = False
        self._load_prompt_template()

        # --- Splitter: Log oben, Ergebnis unten ---
        splitter = QSplitter(Qt.Vertical)

        log_group = QGroupBox("Fortschritt")
        log_layout = QVBoxLayout(log_group)
        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setToolTip("Statusmeldungen des laufenden Analyse-Vorgangs")
        mono = QFont("Monospace", 9)
        mono.setStyleHint(QFont.Monospace)
        self._log_edit.setFont(mono)
        self._log_edit.setMaximumBlockCount(500)
        log_layout.addWidget(self._log_edit)
        splitter.addWidget(log_group)

        result_group = QGroupBox("Zusammenfassung / Analyse")
        result_layout = QVBoxLayout(result_group)
        self._result_edit = QTextEdit()
        self._result_edit.setFont(self._app_font)
        self._result_edit.setReadOnly(True)
        self._result_edit.setToolTip("KI-generierte Zusammenfassung oder Analyse des Dokuments")
        self._result_edit.document().setHtml(
            "<p style='color: gray;'>Die Analyse erscheint hier Token für Token …</p>"
            "<p style='color: gray;'>Alle Berechnungen und Eingaben werden ausschließlich "
            "lokal auf diesem Computer verarbeitet und verlassen diesen nicht.</p>"
        )
        result_layout.addWidget(self._result_edit)
        splitter.addWidget(result_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        log_group.setMinimumHeight(80)
        result_group.setMinimumHeight(100)
        root.addWidget(splitter)

        # --- Fortschrittsbalken ---
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(False)
        root.addWidget(self._progress_bar)

        # --- Buttons ---
        btn_row = QHBoxLayout()

        self._btn_start = QPushButton("Analyse starten")
        self._btn_start.setFont(self._app_font)
        self._btn_start.setFixedHeight(36)
        self._btn_start.setToolTip(
            "Dokument analysieren. Ist das Modell nicht vorhanden, startet zuerst ein Download."
        )
        self._btn_start.clicked.connect(self._start)

        self._btn_cancel = QPushButton("Abbrechen")
        self._btn_cancel.setFont(self._app_font)
        self._btn_cancel.setFixedHeight(36)
        self._btn_cancel.setToolTip("Laufende Analyse abbrechen")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._cancel)

        btn_manual = QPushButton("Anleitung")
        btn_manual.setFont(self._app_font)
        btn_manual.setFixedHeight(36)
        btn_manual.setToolTip("Bedienungsanleitung öffnen")
        btn_manual.clicked.connect(self._open_manual)

        btn_clear = QPushButton("Löschen")
        btn_clear.setFont(self._app_font)
        btn_clear.setFixedHeight(36)
        btn_clear.setToolTip("Fortschrittslog und Analyseergebnis leeren")
        btn_clear.clicked.connect(self._clear)

        btn_row.addWidget(self._btn_start)
        btn_row.addWidget(self._btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(btn_manual)
        btn_row.addStretch()
        btn_row.addWidget(btn_clear)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _load_prompt_template(self) -> None:
        stil = self._stil_combo.currentText()
        if stil == _INDIVIDUELL:
            return
        model_id = self._model_combo.currentData() or ""
        try:
            tmpl = self._registry.get_user_prompt(model_id, stil)
        except KeyError:
            tmpl = ""
        self._prompt_loading = True
        self._prompt_edit.setPlainText(tmpl)
        self._prompt_loading = False

    def _on_stil_changed(self) -> None:
        self._load_prompt_template()

    def _on_prompt_edited(self) -> None:
        if self._prompt_loading:
            return
        if self._stil_combo.currentText() != _INDIVIDUELL:
            with QSignalBlocker(self._stil_combo):
                self._stil_combo.setCurrentText(_INDIVIDUELL)

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Dokument öffnen", self._last_open_dir, _FILE_FILTER
        )
        if path:
            self.set_file_path(path)

    def _on_model_changed(self) -> None:
        self._registry.resolve_paths()
        model_id = self._model_combo.currentData() or ""
        if not model_id:
            return
        try:
            cfg = self._registry.get(model_id)
        except KeyError:
            return

        if cfg.resolved_path is not None:
            self._model_status.setText("\u2713 verfügbar")
            self._model_status.setStyleSheet("color: green;")
        else:
            self._model_status.setText("\u2717 nicht gefunden")
            self._model_status.setStyleSheet("color: red;")

        if hasattr(self, "_prompt_edit"):
            self._load_prompt_template()

    def _show_license(self) -> None:
        model_id = self._model_combo.currentData() or ""
        if not model_id:
            return
        try:
            cfg = self._registry.get(model_id)
            raw = self._registry.get_license_text(model_id)
        except KeyError:
            return

        if not raw:
            dlg = QMessageBox(self)
            dlg.setWindowIcon(self._app_icon)
            dlg.setWindowTitle("Lizenz")
            dlg.setText("Keine Lizenzinformation verfügbar.")
            dlg.exec()
            return

        html = _license_text_to_html(cfg.display_name, raw)

        dlg = QDialog(self)
        dlg.setWindowIcon(self._app_icon)
        dlg.setWindowTitle(f"Lizenz – {cfg.display_name}")
        dlg.setFixedSize(580, 400)
        dlg.setWindowFlags(
            dlg.windowFlags()
            & ~Qt.WindowMaximizeButtonHint
            & ~Qt.WindowMinimizeButtonHint
        )
        layout = QVBoxLayout(dlg)
        view = QTextBrowser()
        view.setFont(self._app_font)
        view.setOpenExternalLinks(False)
        view.setOpenLinks(False)
        view.anchorClicked.connect(open_url)
        view.setStyleSheet("background-color: #e6e6e6;")
        view.setHtml(html)
        layout.addWidget(view)

        btn_row = QHBoxLayout()
        btn_delete = QPushButton("Modell löschen")
        btn_delete.setFont(self._app_font)
        btn_delete.setEnabled(cfg.resolved_path is not None)
        btn_delete.setToolTip(
            str(cfg.resolved_path) if cfg.resolved_path else "Modell nicht heruntergeladen"
        )

        def _delete_model() -> None:
            confirm = QMessageBox(dlg)
            confirm.setWindowIcon(self._app_icon)
            confirm.setWindowTitle("Modell löschen")
            confirm.setIcon(QMessageBox.Warning)
            confirm.setText(
                f"Soll <b>{cfg.display_name}</b> wirklich gelöscht werden?<br><br>"
                f"<small>{cfg.resolved_path}</small>"
            )
            confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
            confirm.button(QMessageBox.Yes).setText("Löschen")
            confirm.button(QMessageBox.Cancel).setText("Abbrechen")
            if confirm.exec() != QMessageBox.Yes:
                return
            path = cfg.resolved_path
            if path is None:
                return
            try:
                path.unlink()
            except OSError as e:
                err = QMessageBox(dlg)
                err.setWindowIcon(self._app_icon)
                err.setWindowTitle("Fehler")
                err.setText(f"Datei konnte nicht gelöscht werden:\n{e}")
                err.exec()
                return
            self._registry.resolve_paths()
            self._on_model_changed()
            btn_delete.setEnabled(False)
            btn_delete.setToolTip("Modell nicht heruntergeladen")

        btn_delete.clicked.connect(_delete_model)
        btn_row.addWidget(btn_delete)
        btn_row.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.button(QDialogButtonBox.Close).setText("Schließen")
        btns.button(QDialogButtonBox.Close).setFont(self._app_font)
        btns.rejected.connect(dlg.reject)
        btn_row.addWidget(btns.button(QDialogButtonBox.Close))
        layout.addLayout(btn_row)
        dlg.exec()

    def _show_ocr_license(self) -> None:
        """Zeigt Lizenz- und Quellinformationen der eingebetteten PaddleOCR-Modelle."""
        license_path = Path(__file__).parent.parent.parent / "licenses" / "paddleocr_models.txt"
        if not license_path.exists():
            license_path = self._app_dir / "openxjv" / "ki" / "licenses" / "paddleocr_models.txt"

        if not license_path.exists():
            dlg = QMessageBox(self)
            dlg.setWindowIcon(self._app_icon)
            dlg.setWindowTitle("OCR-Lizenz")
            dlg.setText("Lizenzinformation nicht gefunden.")
            dlg.exec()
            return

        raw = license_path.read_text(encoding="utf-8")
        html = _license_text_to_html("PaddleOCR – OCR-Modelle (PP-OCRv5 Latin)", raw)

        dlg = QDialog(self)
        dlg.setWindowIcon(self._app_icon)
        dlg.setWindowTitle("OCR-Modelle – Lizenz & Quellen")
        dlg.setFixedSize(600, 440)
        dlg.setWindowFlags(
            dlg.windowFlags()
            & ~Qt.WindowMaximizeButtonHint
            & ~Qt.WindowMinimizeButtonHint
        )
        layout = QVBoxLayout(dlg)
        view = QTextBrowser()
        view.setFont(self._app_font)
        view.setOpenExternalLinks(False)
        view.setOpenLinks(False)
        view.anchorClicked.connect(open_url)
        view.setStyleSheet("background-color: #e6e6e6;")
        view.setHtml(html)
        layout.addWidget(view)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.button(QDialogButtonBox.Close).setText("Schließen")
        btns.button(QDialogButtonBox.Close).setFont(self._app_font)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    def _open_manual(self) -> None:
        """Öffnet die KI-Labor Anleitung im eingebetteten Betrachter.

        Pfad-Auflösung für verschiedene Umgebungen:
          - Normalstart:    ki/core/ui/main_window.py → ki/ via __file__
          - PyInstaller:    sys._MEIPASS/_internal enthält ki/ (DATA-Dateien)
          - Snap/AppImage:  analog PyInstaller — sys._MEIPASS oder _app_dir

        Die Anleitung wird in einem moduslosen QDialog mit QWebEngineView
        angezeigt. Externer Browser entfällt damit vollständig — keine
        Sandbox-Restriktionen durch Snap/Flatpak-Firefox.
        """
        # Nur ein Fenster gleichzeitig öffnen
        if self._manual_window is not None and self._manual_window.isVisible():
            self._manual_window.activateWindow()
            self._manual_window.raise_()
            return

        # 1. Versuch: relativ zu __file__ (normaler Quellcode-Start)
        candidate = Path(__file__).parent.parent.parent / "manual" / "manual.html"
        if not candidate.exists():
            # 2. Versuch: _app_dir (gesetzt auf sys._MEIPASS bei PyInstaller/Snap)
            candidate = self._app_dir / "openxjv" / "ki" / "manual" / "manual.html"
        if not candidate.exists():
            # 3. Versuch: _app_dir/ki/manual (flachere Bundle-Struktur)
            candidate = self._app_dir / "ki" / "manual" / "manual.html"
        manual_path = candidate

        if not manual_path.exists():
            dlg = QMessageBox(self)
            dlg.setWindowIcon(self._app_icon)
            dlg.setWindowTitle("Anleitung")
            dlg.setText(f"Die Anleitung wurde nicht gefunden:\n{manual_path}")
            dlg.exec()
            return

        from PySide6.QtWebEngineCore import QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from openxjv.ui.helpers import CustomWebEnginePage

        dlg = QDialog(self)
        dlg.setWindowTitle("KI-Labor – Anleitung")
        dlg.setWindowIcon(self._app_icon)
        dlg.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        dlg.resize(1200, 720)

        # Namenloses (off-the-record) Profil ohne Disk-Cache — analog pdfjs_viewer
        profile = QWebEngineProfile(dlg)
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)

        view = QWebEngineView(dlg)
        view.setPage(CustomWebEnginePage(view, profile=profile))
        view.setUrl(QUrl.fromLocalFile(str(manual_path)))

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

        self._manual_window = dlg
        dlg.show()

    def _check_models_on_startup(self) -> None:
        # Konfigurationsfehler anzeigen
        load_errors = self._registry.get_load_errors()
        if load_errors:
            err_dlg = QMessageBox(self)
            err_dlg.setWindowIcon(self._app_icon)
            err_dlg.setWindowTitle("Konfigurationsfehler")
            err_dlg.setIcon(QMessageBox.Warning)
            err_dlg.setText(
                "Folgende Modell-Konfigurationen konnten nicht geladen werden:\n\n"
                + "\n".join(f"  \u2022 {e}" for e in load_errors)
            )
            err_dlg.exec()

        available = [c for c in self._registry.all_models() if c.resolved_path is not None]
        if available:
            return
        all_models = self._registry.all_models()
        if not all_models:
            return  # Alle Configs defekt — Fehler wurde oben schon gezeigt
        names = "\n".join(f"  \u2022 {c.display_name}" for c in all_models)
        dlg = QMessageBox(self)
        dlg.setWindowIcon(self._app_icon)
        dlg.setWindowTitle("Keine Modelle vorhanden")
        dlg.setText(
            f"Es wurden keine KI-Modelle gefunden.\n\n"
            f"Konfigurierte Modelle:\n{names}\n\n"
            f"Wählen Sie ein Modell aus der Liste und klicken Sie auf "
            f"\u201eAnalyse starten\u201c \u2014 der Download startet dann automatisch."
        )
        dlg.exec()

    def _start(self) -> None:
        model_id = self._model_combo.currentData() or ""
        if not model_id:
            self._log("Kein Modell ausgewählt.")
            return

        try:
            cfg = self._registry.get(model_id)
        except KeyError:
            self._log(f"Unbekanntes Modell: {model_id}")
            return

        if cfg.resolved_path is None:
            try:
                dest_dir = self._registry.download_destination()
            except OSError as e:
                dlg = QMessageBox(self)
                dlg.setWindowIcon(self._app_icon)
                dlg.setWindowTitle("Fehler")
                dlg.setText(str(e))
                dlg.exec()
                return
            dest_path = dest_dir / cfg.filename
            dlg = DownloadDialog(cfg, dest_path, parent=self)
            if dlg.exec() != DownloadDialog.Accepted:
                return
            self._registry.resolve_paths()
            self._on_model_changed()
            cfg = self._registry.get(model_id)
            if cfg.resolved_path is None:
                warn = QMessageBox(self)
                warn.setWindowIcon(self._app_icon)
                warn.setWindowTitle("Download fehlgeschlagen")
                warn.setText("Das Modell konnte nicht gefunden werden.")
                warn.exec()
                return

        file_path = self._file_edit.text().strip()
        if not file_path:
            self._log("Bitte zuerst ein Dokument auswählen.")
            return

        ext = Path(file_path).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            self._log(f"Dateiformat nicht unterstützt: {ext}")
            return

        if not self._cpu_warning_shown and not gpu_offload_active():
            self._cpu_warning_shown = True
            warn = QMessageBox(self)
            warn.setWindowIcon(self._app_icon)
            warn.setWindowTitle("Keine GPU-Beschleunigung erkannt")
            warn.setText(
                "Das KI-Modell wird auf dem Prozessor ausgeführt.\n\n"
                "Die Analyse kann dadurch erhebliche Zeit in Anspruch nehmen "
                "(mehrere Minuten bis Stunden je nach Dokumentgröße).\n\n"
                "Für praxistaugliche Antwortzeiten wird eine dedizierte, "
                "moderne Grafikkarte mit 8GB bis 12GB RAM und Vulkan-Unterstützung benötigt."
            )
            warn.exec()

        stil = self._stil_combo.currentText()
        custom_prompt = self._prompt_edit.toPlainText().strip()
        max_tokens = self._max_tokens_combo.currentData()
        ocr_mode = self._ocr_combo.currentData()   # "none" | "force"

        self._cancel_flag[0] = False
        self._signals.started.emit()
        threading.Thread(
            target=self._worker,
            args=(file_path, cfg, stil, max_tokens, custom_prompt, ocr_mode),
            daemon=True,
        ).start()

    def _cancel(self) -> None:
        self._cancel_flag[0] = True
        self._log("Abbruch angefordert …")
        # OCR-Subprocess sofort beenden falls aktiv
        proc = self._ocr_process
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
        # Inferenz-Subprocess kooperativ abbrechen (setzt cancel_event)
        self._inference_proc.cancel()

    def _clear(self) -> None:
        self._result_edit.clear()
        self._log_edit.clear()

    # ------------------------------------------------------------------
    # Worker (Hintergrundthread)
    # ------------------------------------------------------------------

    def _extract_via_ocr(self, file_path: str) -> str | None:
        """
        Führt OCR in einem separaten Python-Prozess (multiprocessing spawn) durch.

        Der Subprozess ist vollständig von Qt und llama_cpp isoliert — keine
        Threading-Konflikte mit onnxruntime oder OpenMP möglich.
        Fortschrittsmeldungen kommen via Queue und werden als Signale weitergegeben.
        """
        import multiprocessing as _mp
        import queue as _queue

        try:
            from ...ocr_pipeline.subprocess_worker import run as _ocr_run
            from ...ocr_pipeline.subprocess_worker import PROGRESS, RESULT, ERROR
        except ImportError as e:
            self._signals.error.emit(
                f"OCR-Modul nicht verfügbar: {e}\n"
                "Bitte 'rapidocr' und passende onnxruntime-Variante installieren."
            )
            return None

        ctx = _mp.get_context("spawn")
        msg_queue = ctx.Queue()
        process = ctx.Process(
            target=_ocr_run,
            args=(file_path, 200, msg_queue, self._ki_debug),
            daemon=True,
        )
        process.start()
        self._ocr_process = process

        result_text: str | None = None

        try:
            while True:
                # Abbruch durch Nutzer
                if self._cancel_flag[0]:
                    process.terminate()
                    process.join(timeout=5)
                    return None

                try:
                    msg = msg_queue.get(timeout=0.2)
                except _queue.Empty:
                    if not process.is_alive():
                        break
                    continue

                kind = msg[0]
                if kind == PROGRESS:
                    self._signals.progress.emit(msg[1])
                elif kind == RESULT:
                    _, text, summary, warnings, page1_conf = msg
                    conf_str = (
                        f" (Ø Konfidenz Seite 1: {page1_conf:.0%})"
                        if page1_conf >= 0 else ""
                    )
                    self._signals.progress.emit(f"OCR: {summary}{conf_str}")
                    for w in warnings[:10]:
                        self._signals.progress.emit(f"OCR-Hinweis: {w}")
                    if len(warnings) > 10:
                        self._signals.progress.emit(
                            f"OCR: … {len(warnings) - 10} weitere Hinweise unterdrückt."
                        )
                    result_text = text
                    break
                elif kind == ERROR:
                    self._signals.error.emit(f"OCR fehlgeschlagen: {msg[1]}")
                    process.join(timeout=5)
                    return None
        finally:
            self._ocr_process = None

        process.join(timeout=5)

        if not result_text or not result_text.strip():
            self._signals.error.emit(
                "OCR ergab keinen Text. Möglicherweise enthält das Dokument "
                "keine erkennbaren Zeichen oder ist beschädigt."
            )
            return None

        self._signals.progress.emit(
            f"OCR abgeschlossen: {len(result_text):,} Zeichen extrahiert."
        )
        return result_text

    def _worker(
        self,
        file_path: str,
        cfg: ModelConfig,
        stil: str,
        max_tokens: int,
        custom_prompt: str = "",
        ocr_mode: str = "none",
    ) -> None:
        try:
            # 1. Text extrahieren (mit Cache)
            is_pdf  = file_path.lower().endswith(".pdf")
            use_ocr = is_pdf and ocr_mode == "force"
            cache_key = (file_path, ocr_mode)

            if cache_key in self._text_cache:
                raw = self._text_cache[cache_key]
                self._signals.progress.emit(
                    f"Text aus Cache: {len(raw):,} Zeichen "
                    f"({'OCR' if use_ocr else 'Textlayer'})."
                )
            elif use_ocr:
                raw = self._extract_via_ocr(file_path)
                if raw is None:
                    return  # Fehler bereits per Signal gemeldet
                self._text_cache[cache_key] = raw
            else:
                self._signals.progress.emit("Extrahiere Dokumenttext …")
                try:
                    from openxjv.utils.text_extraction import get_document_text
                    raw = get_document_text(file_path)
                except Exception as e:
                    self._signals.error.emit(f"Textextraktion fehlgeschlagen: {e}")
                    return
                self._text_cache[cache_key] = raw

            if not raw or not raw.strip():
                self._signals.error.emit("Das Dokument enthält keinen lesbaren Text.")
                return

            doc_name = Path(file_path).stem

            # 2. Bereinigen
            # Bei OCR-Text nur echte Satzgrenzen zu Absatzgrenzen machen.
            # Blindes \n→\n\n verhindert, dass clean() Zeilenfortsetzungen (z.B.
            # "veral\nlgemeinert") zu Leerzeichen zusammenführt → Buchstabendreher.
            if use_ocr:
                import re as _re
                raw = _re.sub(r'([.!?])\n([A-ZÄÖÜ])', r'\1\n\n\2', raw)
            text = clean(raw)
            self._signals.progress.emit(f"Text: {len(text):,} Zeichen.")

            if self._cancel_flag[0]:
                return

            # 3. Duplikate entfernen
            if use_ocr:
                text = deduplicate_short_lines(text)
            deduped = deduplicate_paragraphs(text)
            saved = len(text) - len(deduped)
            if saved > 100:
                self._signals.progress.emit(
                    f"Duplikate entfernt: {len(text):,} → {len(deduped):,} Zeichen "
                    f"(−{saved:,} / {saved * 100 // max(len(text), 1)} %)."
                )

            # Debug-Output
            if self._ki_debug:
                import tempfile, datetime
                ts        = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                debug_dir = Path(tempfile.gettempdir())
                stem      = Path(file_path).stem
                for suffix, content in [
                    ("1_raw", raw), ("2_clean", text), ("3_deduped", deduped)
                ]:
                    out = debug_dir / f"ki_debug_{stem}_{ts}_{suffix}.txt"
                    out.write_text(content, encoding="utf-8")
                self._signals.progress.emit(
                    f"[DEBUG] Preprocessing-Stufen geschrieben nach {debug_dir}"
                )

            if self._cancel_flag[0]:
                return

            # 4. Kontextfenster schätzen (Heuristik; exakte Messung im Subprocess)
            gpu = gpu_offload_active()
            n_ctx, ctx_info = estimate_n_ctx(deduped, cfg, gpu_active=gpu)
            self._signals.progress.emit(f"Kontextfenster: {ctx_info}.")

            # Sicherstellen, dass n_ctx für die angeforderte Ausgabelänge ausreicht.
            _min_ctx_for_output = (
                (max_tokens + cfg.template_overhead + cfg.prompt_overhead + 1023) // 1024
            ) * 1024
            _min_ctx_for_output = min(max(_min_ctx_for_output, cfg.n_ctx_min), cfg.n_ctx_max)
            if n_ctx < _min_ctx_for_output:
                n_ctx = _min_ctx_for_output
                self._signals.progress.emit(
                    f"Kontextfenster auf {n_ctx:,} Token angepasst "
                    f"(Mindestgröße für max. {max_tokens:,} Token Ausgabe)."
                )

            if self._cancel_flag[0]:
                return

            # 5. Prompts aufbauen (Registry-Zugriff bleibt im Elternprozess)
            system_prompt = self._registry.get_system_prompt(cfg.id, stil)
            instruction   = (
                custom_prompt
                if (custom_prompt and stil == _INDIVIDUELL)
                else self._registry.get_user_prompt(cfg.id, stil)
            )

            # 6. Analyse an Inferenz-Subprocess delegieren
            config_data = {
                "template_overhead":    cfg.template_overhead,
                "chunk_overlap_chars":  cfg.chunk_overlap_chars,
                "filter_thinking_block": cfg.filter_thinking_block,
                "repeat_last_n":        cfg.repeat_last_n,
                "n_ctx_max":            cfg.n_ctx_max,
                "n_ctx_min":            cfg.n_ctx_min,
                "rope_scaling_max_factor": cfg.rope_scaling_max_factor,
                "chat_template":        cfg.chat_template,
                "generation":           cfg.generation,
            }
            params = {
                "model_path":       str(cfg.resolved_path),
                "n_ctx":            n_ctx,
                "config":           config_data,
                "document_text":    deduped,
                "system_prompt":    system_prompt,
                "instruction":      instruction,
                "doc_name":         doc_name,
                "max_tokens":       max_tokens,
                "generation_params": dict(cfg.generation),
                "use_ocr":          use_ocr,
                "ki_debug":         self._ki_debug,
            }

            for msg in self._inference_proc.analyze(params):
                if self._cancel_flag[0]:
                    break
                kind = msg[0]
                if kind == "progress":
                    self._signals.progress.emit(msg[1])
                elif kind == "token":
                    self._signals.token.emit(msg[1])
                elif kind == "error":
                    self._signals.error.emit(msg[1])
                # "done" beendet den Generator

        except Exception:
            import traceback
            self._signals.error.emit(traceback.format_exc())
        finally:
            self._signals.finished.emit()

    # ------------------------------------------------------------------
    # Signal-Handler
    # ------------------------------------------------------------------

    def _on_progress(self, msg: str) -> None:
        self._log(msg)

    def _on_token(self, token: str) -> None:
        self._result_edit.moveCursor(QTextCursor.End)
        self._result_edit.insertPlainText(token)
        self._result_edit.moveCursor(QTextCursor.End)

    def _on_error(self, msg: str) -> None:
        self._log(f"FEHLER:\n{msg}")

    def _on_started(self) -> None:
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._progress_bar.setVisible(True)
        self._result_edit.clear()
        self._log_edit.clear()

    def _on_finished(self) -> None:
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._progress_bar.setVisible(False)
        self._on_model_changed()
        self._normalize_result()
        if self._result_edit.toPlainText().strip():
            self._result_edit.append(
                "\n\n<i style='color:gray;font-size:small;'>"
                "\u26a0 KI-generierte Ausgabe \u2014 experimentell. "
                "Fehler sind möglich. Es wird keine Gewähr für die korrekte Wiedergabe "
                "des Sachverhalts oder einzelner Details übernommen."
                "</i>"
            )

    def _normalize_result(self) -> None:
        """Bereinigt die Ausgabe nach Abschluss der Generierung:
        Zeilen, die nur Leerzeichen/Tabs enthalten, werden geleert;
        mehr als eine aufeinanderfolgende Leerzeile wird auf eine reduziert."""
        import re
        text = self._result_edit.toPlainText()
        if not text.strip():
            return
        # Zeilen, die nur Whitespace (aber keinen Zeilenumbruch) enthalten, leeren
        text = re.sub(r"^[ \t]+$", "", text, flags=re.MULTILINE)
        # Drei oder mehr aufeinanderfolgende Zeilenumbrüche → zwei (= eine Leerzeile)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
        self._result_edit.setPlainText(text)
        self._result_edit.moveCursor(QTextCursor.End)

    def closeEvent(self, event) -> None:
        """
        Beim Schließen des KI-Fensters den Inferenz-Subprocess beenden.

        Der Subprocess ist ein Daemon-Prozess: Er wird automatisch beendet,
        sobald der Elternprozess endet. stop() stellt sicher, dass er auch
        beim isolierten Schließen des KI-Fensters (innerhalb einer noch
        laufenden openXJV-Instanz) freigegeben wird.

        Da alle GPU-Operationen im Subprocess stattfinden, hängt Python-
        Shutdown nicht mehr an CUDA-Threads im Hauptprozess.
        """
        self._inference_proc.stop()
        super().closeEvent(event)

    def _log(self, msg: str) -> None:
        self._log_edit.appendPlainText(msg)
        self._log_edit.verticalScrollBar().setValue(
            self._log_edit.verticalScrollBar().maximum()
        )
