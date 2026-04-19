#!/usr/bin/env python3
# coding: utf-8
"""
openXJV_modular.py - Migrated UI class for XJustiz-Data Viewer
2022 - 2026 Björn Seipel

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; mitout even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along mit this program.  If not, see <https://www.gnu.org/licenses/>.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from openxjv.ki.core.ui.main_window import KIMainWindow

# For Ubuntu package: sudo apt install libxcb-cursor0 in case of xcb-error

import traceback

import os
import re
import sys
import urllib.request
#import subprocess
#if os.name == 'nt':
#    from subprocess import CREATE_NO_WINDOW
import platform
import darkdetect
import multiprocessing
from uuid import uuid4
from time import sleep
from shutil import rmtree
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir

# Plattformspezifische Imports für File-Locking
_HAS_MSVCRT = False
_HAS_FCNTL = False

try:
    if sys.platform == 'win32':
        import msvcrt
        _HAS_MSVCRT = True
    else:
        import fcntl
        _HAS_FCNTL = True
except ImportError:
    # Fallback falls Imports nicht verfügbar sind
    pass


# QT-Imports
from PySide6.QtCore import (
    qVersion,
    QEventLoop,
    QSettings,
    QCoreApplication,
    QUrl,
    Qt,
    QSize,
    QRect,
    QLibraryInfo,
    QThread,
    QEvent,
    QTranslator,
    QLocale,
    QTimer,
)

from PySide6.QtGui import (
    QScreen,
    QStandardItemModel,
    QCursor,
    QIcon,
    QFont,
    QColor,
    QPalette,
    QPainter,
    QShortcut,
    QKeySequence,
    QFontDatabase,
    QDesktopServices,
    QPixmap,
)

from PySide6.QtWidgets import (
    QToolTip,
    QHeaderView,
    QDialog,
    QMenu,
    QFrame,
    QFileDialog,
    QApplication,
    QTableWidgetItem,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QComboBox,
    QSpinBox,
    QLabel,
    QPushButton,
    QFormLayout,
    QSplashScreen,
    QStyledItemDelegate,
)

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile

# PDF Viewer Widget
from pdfjs_viewer import (
    PDFViewerWidget,
    PDFViewerConfig,
    PDFFeatures,
    PDFSecurityConfig,
    PrintHandler,
    configure_global_stability,
    freeze_support as pdfjs_freeze_support,
)

from PySide6.QtCore import QFile
## Ende QT-Imports

from PIL import Image
from PIL.ImageQt import ImageQt
from platformdirs import PlatformDirs as AppDirs

# Modulare Komponenten
from openxjv import __version__ as MODULAR_VERSION
from openxjv.core import DatabaseManager, OCRHandler, PDFocr
from openxjv.core.database import FavoriteEntry
from openxjv.core.pdf_operations import (
    PDFExportConfig,
    PDFExportError,
    export_pdf,
    export_notes_to_pdf,
)
from openxjv.core.pdf_cover_page_template import CreateDeckblatt
from openxjv.ui import Ui_MainWindow, TextObject, XJustizDisplayRenderer, CustomWebEnginePage, StandardItem
from openxjv.utils import SearchFilterManager, FileManager, SettingsManager, open_url, is_in_bundle
from openxjv.parsers import (
    parser240,
    parser321,
    parser331,
    parser341,
    parser351,
    parser362,
)
from openxjv.validators import XSDValidatorDialog
from openxjv.ui.maintenance_dialog import MaintenanceTokenDialog
from openxjv.ui.maintenance_banner import MaintenanceBanner
from openxjv.utils.maintenance_token import is_token_valid, check_token_from_env
# KI-Module werden lazy beim ersten Öffnen des KI-Labors geladen,
# damit llama_cpp nicht schon beim App-Start initialisiert wird.
VERSION = MODULAR_VERSION


class SingleInstance:
    """
    Stellt sicher, dass nur eine Instanz der Anwendung gleichzeitig läuft.

    Verwendet plattformspezifisches File-Locking (Windows, Linux, macOS).
    Die Lock-Datei wird automatisch vom Betriebssystem freigegeben, wenn
    die Anwendung beendet wird - auch bei unerwartetem Absturz.

    """

    def __init__(self, app_name):
        """
        Initialisiert die SingleInstance-Prüfung.

        Args:
            app_name (str): Eindeutiger Name der Anwendung für die Lock-Datei
        """
        self.app_name = app_name
        self.lockfile_path = Path(gettempdir()) / f"{app_name}.lock"
        self.fp = None
        self._is_locked = False

    def acquire(self):
        """
        Versucht, die Anwendungs-Sperre zu erwerben.

        Returns:
            bool: True wenn erfolgreich (keine andere Instanz läuft),
                  False wenn bereits eine Instanz läuft oder bei Fehler
        """
        # Fallback: Wenn File-Locking nicht verfügbar ist, immer erlauben
        if sys.platform == 'win32' and not _HAS_MSVCRT:
            return True
        if sys.platform != 'win32' and not _HAS_FCNTL:
            return True

        try:
            # Lock-Datei öffnen/erstellen
            self.fp = open(self.lockfile_path, 'w')

            # Plattformspezifisches Locking
            if sys.platform == 'win32' and _HAS_MSVCRT:
                # Windows: msvcrt.locking
                try:
                    msvcrt.locking(self.fp.fileno(), msvcrt.LK_NBLCK, 1)
                except (OSError, IOError):
                    # Lock konnte nicht erworben werden - andere Instanz läuft
                    self.fp.close()
                    self.fp = None
                    return False
            elif _HAS_FCNTL:
                # Linux/macOS: fcntl
                try:
                    fcntl.flock(self.fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (OSError, IOError):
                    # Lock konnte nicht erworben werden - andere Instanz läuft
                    self.fp.close()
                    self.fp = None
                    return False

            # Lock erfolgreich - PID in Datei schreiben
            self.fp.write(str(os.getpid()))
            self.fp.flush()
            self._is_locked = True
            return True

        except Exception as e:
            # Bei jedem unerwarteten Fehler: Anwendung starten lassen
            print(f"Warnung: SingleInstance-Prüfung fehlgeschlagen: {e}")
            if self.fp:
                try:
                    self.fp.close()
                except:
                    pass
                self.fp = None
            return True

    def release(self):
        """
        Gibt die Anwendungs-Sperre frei.

        Wird automatisch beim Beenden aufgerufen, kann aber auch
        manuell aufgerufen werden.
        """
        if not self._is_locked or not self.fp:
            return

        try:
            # Plattformspezifisches Unlock (optional, OS macht das automatisch)
            if sys.platform != 'win32' and _HAS_FCNTL:
                try:
                    fcntl.flock(self.fp.fileno(), fcntl.LOCK_UN)
                except:
                    pass

            # Datei schließen
            self.fp.close()
            self.fp = None

            # Lock-Datei löschen
            try:
                self.lockfile_path.unlink()
            except:
                pass

        except Exception:
            # Fehler beim Release ignorieren
            pass
        finally:
            self._is_locked = False

    def __enter__(self):
        """Context Manager Support: Eintritt"""
        return self.acquire()

    def __exit__(self, *_args):
        """Context Manager Support: Austritt"""
        self.release()
        return False

    def __del__(self):
        """Destruktor: Sperre freigeben beim Löschen des Objekts"""
        self.release()


class UI(QMainWindow, Ui_MainWindow):
    """Haupt-UI-Klasse für die openXJV-Anwendung.

    Diese Klasse stellt die Hauptbenutzeroberfläche bereit for viewing and managing XJustiz legal data files.
    It uses a modular architecture mit functionality delegated to specialized components:

    - DatabaseManager: Handles all database operations (favorites, notes, search index)
    - SearchFilterManager: Manages search and filtering operations
    - OCRHandler: Handles OCR (text recognition) operations
    - FileManager: Manages file operations (open, export, ZIP handling)
    - XJustizDisplayRenderer: Renders XJustiz data templates
    - SettingsManager: Type-safe settings management

    """
    # ========================================
    # ABSCHNITT 1: INITIALISIERUNG & LEBENSZYKLUS
    # ========================================
    def __init__(self, app: QApplication, file=None, ziplist=None, ki_debug: bool = False):
        """Initialisiert das openXJV-Hauptfenster.

        Argumente:
            file: Optionaler Pfad zu einer XJustiz-Datei zum Laden beim Start
            ziplist: Optionale Liste von ZIP-Dateien zum Extrahieren und Laden
            app: QApplication-Instanz
            ki_debug: KI-Debug-Modus aktivieren (schreibt Preprocessing-Zwischenstände in Temp-Ordner)
        """
        self._ki_debug = ki_debug
        super(UI, self).__init__()
        self.setupUi(self)

        # Maintenance-Banner zwischen Toolbar und Tabs einfügen
        self.maintenanceBanner = MaintenanceBanner(self)
        self.maintenanceBanner.setVisible(False)
        self.gridLayout_13.removeWidget(self.tabs)
        self.gridLayout_13.addWidget(self.maintenanceBanner, 0, 0, 1, 1)
        self.gridLayout_13.addWidget(self.tabs, 1, 0, 1, 1)

        self.lastExceptionString=''
        
        self.supportMail = os.environ.get('OPENXJVSUPPORT', "support@digidigital.de")

        self.app=app
        
        # System /tmp-Ordner nicht zugänglich für SNAP Libreoffice
        if sys.platform.lower().startswith(("linux", "win")):
            tmpdir = AppDirs("OpenXJV", "digidigital", version="0.1").user_cache_dir
        else:
            tmpdir = None
        print(f"[Init] tmpdir: {tmpdir}")

        # Verzeichnis prüfen und ggf. erzeugen + ggf. alten Inhalt
        # for data protection reasons
        if tmpdir is not None:
            try:
                try:
                    os.makedirs(tmpdir, exist_ok=True)
                except OSError as e:
                    if getattr(e, 'winerror', None) != 183:  # 183 = Existiert bereits (Race condition / OneDrive)
                        raise
                for entry in os.listdir(tmpdir):
                    path = os.path.join(tmpdir, entry)
                    if os.path.isfile(path) or os.path.islink(path):
                        os.remove(path)
                    elif os.path.isdir(path):
                        rmtree(path)
            except Exception as e:
                self.lastExceptionString=f"Konnte 'tmpdir' nicht erzeugen: {str(e)}"
                print(f"[Init] WARNUNG: tmpdir nicht nutzbar, Fallback auf System-tmp: {e}")
                tmpdir = None

        self.tempDir = TemporaryDirectory(dir=tmpdir) if tmpdir else TemporaryDirectory()
        print(f"[Init] tempDir: {self.tempDir.name}")

        self.scriptRoot = os.path.dirname(os.path.realpath(__file__))
      
        windowIcon = QIcon()
        for size, name in [(16, 'appicon16.png'), (32, 'appicon32.png'), (64, 'appicon64.png'),
                           (128, 'appicon128.png'), (256, 'appicon256.png')]:
            windowIcon.addFile(os.path.join(self.scriptRoot, 'icons', name), QSize(size, size))
        self.setWindowIcon(windowIcon)

        # Initialisiere Search/Filter Manager (Phase 2 Migration)
        self.search_filter_manager = SearchFilterManager()
        # Erhalte Rückwärtskompatibilität mit direktem Attributzugriff
        self.searchStore = self.search_filter_manager.search_store
        self.searchLock = self.search_filter_manager.search_lock
        self.leereDateien = self.search_filter_manager.empty_files
        self.leerePDF = self.search_filter_manager.empty_pdf

        self.loadedPDFpath=''
        self.loadedPDFfilename=''

        self.column_preferences={}
        self._ki_window: KIMainWindow | None = None
        
        self.dirs = AppDirs("OpenXJV", "digidigital", version="0.1")
        print(f"[Init] user_data_dir: {self.dirs.user_data_dir}")

        try:
            os.makedirs(self.dirs.user_data_dir, exist_ok=True)
        except OSError as e:
            if getattr(e, 'winerror', None) != 183:  # 183 = Existiert bereits (Race condition / OneDrive)
                raise

        self.db_name = 'openXJV_data.db'
        self.db_path = os.path.join(self.dirs.user_data_dir, self.db_name)
        db_is_new = not os.path.exists(self.db_path)
        print(f"[Init] Datenbank: {self.db_path} ({'neu' if db_is_new else 'vorhanden'})")
        try:
            self.db_manager = DatabaseManager(self.db_path)
        except Exception as e:
            print(f"[Init] FEHLER: Datenbankinitialisierung fehlgeschlagen: {e}")
            raise

        # Übersetzungen
        translation_path = os.path.normcase(os.path.join(QLibraryInfo.path(QLibraryInfo.LibraryPath(10)),  "qtbase_de.qm"))
        translator = QTranslator(app)

        if translator.load(translation_path):
            app.installTranslator(translator)
            print(f"[Init] Qt-Übersetzung geladen: {translation_path}")
        else:
            print(f"[Init] Qt-Übersetzung nicht gefunden: {translation_path}")

        # Path.home() nicht direkt verwenden, falls wir in einem Snap-Paket sind
        self.homedir = os.environ.get('SNAP_REAL_HOME', Path.home())

        ### Lade Schriftarten ###
        self.fontDir = self.scriptRoot + '/fonts/'

        fontFiles=[
            "materialicons/MaterialIcons-Regular.ttf",
            "ubuntu-font-family-0.83/Ubuntu-L.ttf",
            "ubuntu-font-family-0.83/Ubuntu-R.ttf"
        ]

        for font in fontFiles:
            font_path = self.fontDir + font
            if QFontDatabase.addApplicationFont(font_path) == -1:
                print(f"[Init] WARNUNG: Schriftart nicht geladen: {font_path}")

        # Setze Schriftarten
        self.buttonFont=QFont('Material Icons')
        self.buttonFont.setWeight(QFont.Weight.Thin)
        self.iconFont=QFont('Material Icons')
        self.iconFont.setWeight(QFont.Weight.Thin)
        self.appFont=QFont('Ubuntu')
        self.__setFontsizes()
       
        self.setWindowTitle(f'openXJV {VERSION}')

        # Verstecke "Neue Version"-Symbol
        self.newVersionIndicator=self.toolBar.actions()[15]
        self.newVersionIndicator.setVisible(False)

        # Füge temporär tesseract, jbig2dec zum Windows-PATH hinzu
        if os.name == 'nt':
            #if os.path.exists(os.path.join(self.scriptRoot,'bin','search_tool', 'search_tool.exe')):
            #        os.environ['PATH'] += f";{os.path.join(self.scriptRoot,'bin','search_tool')}"
            gocr_path = os.path.join(self.scriptRoot,'bin','gocr', 'gocr049.exe')
            if os.path.exists(gocr_path):
                os.environ['PATH'] += f";{os.path.join(self.scriptRoot,'bin','gocr')}"
                print(f"[Init] gocr gefunden: {gocr_path}")
            else:
                print(f"[Init] gocr nicht gefunden: {gocr_path}")
            if not PDFocr.tesseractAvailable():
                jbig2_path = os.path.join(self.scriptRoot,'bin','jbig2dec', 'jbig2dec.exe')
                tess_path  = os.path.join(self.scriptRoot,'bin','tesseract', 'tesseract.exe')
                if os.path.exists(jbig2_path):
                    os.environ['PATH'] += f";{os.path.join(self.scriptRoot,'bin','jbig2dec')}"
                    print(f"[Init] jbig2dec gefunden: {jbig2_path}")
                else:
                    print(f"[Init] jbig2dec nicht gefunden: {jbig2_path}")
                if os.path.exists(tess_path):
                    os.environ['PATH'] += f";{os.path.join(self.scriptRoot,'bin','tesseract')}"
                    os.environ['TESSDATA_PREFIX'] = f"{os.path.join(self.scriptRoot,'bin','tesseract', 'tessdata')}"
                    print(f"[Init] tesseract (Bundle) gefunden: {tess_path}")
                else:
                    print(f"[Init] tesseract nicht gefunden: {tess_path}")
            os.environ['PATH'] += f";{self.scriptRoot}"

        # Begrenze Tesseract Multithreading
        os.environ['OMP_THREAD_LIMIT']='2'

        # Verstecke OCR-Optionen, falls Tesseract nicht verfügbar
        if not PDFocr.tesseractAvailable():
            self.OCRenabled=False
            self.actionTexterkennungAktuellesPDF.setVisible(False)
            self.actionTexterkennung.setVisible(False)
            print("[Init] OCR: Tesseract nicht verfügbar, OCR deaktiviert")
        else:
            self.OCRenabled=True
            print("[Init] OCR: Tesseract verfügbar")
        
        self.actionOCRall.setVisible(False)
            
        ###Bereite Einstellungen vor###
        self.settings_manager = SettingsManager('digidigital', 'openXJV')
        # Erhalte Rückwärtskompatibilität - settings-Attribut zeigt nun auf die zugrundeliegenden QSettings
        self.settings = self.settings_manager.settings
        
        ### Initialisiere PDF-Viewer Widget ###
        # Lese gespeicherte Annotationseinstellung
        saved_annotation_action = self.settings_manager.get_string('annotationAction', 'auto_save')
        if saved_annotation_action not in ('disabled', 'prompt', 'auto_save'):
            saved_annotation_action = 'auto_save'

        pdf_config = PDFViewerConfig(
            features=PDFFeatures(
                print_enabled=True,
                save_enabled=True,
                load_enabled=False,  # Laden wird von openXJV gesteuert
                highlight_enabled=True,
                freetext_enabled=True,
                ink_enabled=True,
                stamp_enabled=False,
                unsaved_changes_action=saved_annotation_action,
            ),
            security=PDFSecurityConfig(
                allow_external_links=True,
                confirm_before_external_link=True,
                block_remote_content=True,
                allowed_protocols=["http", "https", "mailto"],
                open_url_handler=open_url,
            ),
            print_handler=PrintHandler.QT_DIALOG,
            print_dpi=200,
            print_fit_to_page=True,
            disable_context_menu=True,
        )
        self.pdf_viewer = PDFViewerWidget(config=pdf_config)

        # Ersetze das alte browser-Widget im Splitter durch das neue PDFViewerWidget
        old_browser = self.browser
        old_browser_index = self.splitter_9.indexOf(old_browser)
        self.splitter_9.replaceWidget(old_browser_index, self.pdf_viewer)
        old_browser.deleteLater()

        # Verwende das interne QWebEngineView für Nicht-PDF-Dateien und Chromium-Modus
        self.browser = self.pdf_viewer.backend.web_view

        # Verbinde PDF-Viewer Signale
        self.pdf_viewer.error_occurred.connect(lambda msg: self.statusBar.showMessage(msg))

        # Setze Splitter-Eigenschaften für gleichmäßige Aufteilung
        self.splitter_9.setStretchFactor(0, 1)  # Linke Seite (Dokumentenliste)
        self.splitter_9.setStretchFactor(1, 1)  # Rechte Seite (PDF-Viewer)

        # Browser-Einstellungen für Nicht-PDF-Inhalte (Bilder, HTML, etc.)
        self.browser.settings().setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        self.browser.settings().setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, False)
        self.browser.settings().setAttribute(QWebEngineSettings.WebAttribute.NavigateOnDropEnabled, False)
                      
        ###set toolbarButtonwidth###        
        for child in self.toolBar.children():
            if child.__class__.__name__ == 'QToolButton':
                child.setFixedWidth(25)
        
        #Passe table header Style an         
        self.docTableView.horizontalHeader().setHighlightSections(False)
        self.favTableView.horizontalHeader().setHighlightSections(False)
        self.termineTableView.horizontalHeader().setHighlightSections(False)  
        
        # printLock no longer needed - pdfjs_viewer handles print state internally

        ###initial ocr lock state####
        # Initialisiere OCR-Handler
        self.ocr_handler = OCRHandler(
            status_bar=self.statusBar,
            app=self.app,
            home_dir=Path(self.homedir),
            settings=self.settings,
            display_message_callback=self.__displayMessage
        )
        # Erhalte Rückwärtskompatibilität mit direktem Attributzugriff
        self.ocrLock = self.ocr_handler.ocr_lock

        # Initialisiere Schlüsselattribute - erforderlich bevor __readSettings() aufgerufen wird
        # Diese werden aktualisiert, wenn eine Datei tatsächlich geladen wird
        self.basedir = ''
        self.akte = {}  # Wird gefüllt, wenn eine XJV-Datei geladen wird
        self._xsd_validator_dialog = None  # Einzelinstanz des Validierungsdialogs
        self.favorites = []
        self.loadedPDFfilename = ''
        self.loadedPDFpath = ''

        # Initialisiere Dateimanager
        self.file_manager = FileManager(
            app=self.app,
            settings=self.settings,
            homedir=str(self.homedir),
            basedir=self.basedir,
            temp_dir=self.tempDir
        )

        # viewerPaths no longer needed - pdfjs_viewer handles PDF.js paths internally
        # Chromium mode uses direct file:// URLs            
        
        ###Spalten/Sortierreihenfolge für die Anzeige in der Dokumentenansicht###
        self.docTableAttributes = [
            'nummerImUebergeordnetenContainer',
            'nurMetadaten', 
            'datumDesSchreibens',
            'erstellungszeitpunkt',
            'posteingangsdatum',
            'posteingangszeitpunkt',
            'veraktungsdatum',
            'scanDatum',
            'ersetzenderScan',
            'anzeigename',
            'dokumententyp',
            'dokumentklasse',
            'bestandteil',
            'ruecksendungEEB.erforderlich',
            'fremdesGeschaeftszeichen',
            'akteneinsicht',
            'absenderAnzeigename',
            'adressatAnzeigename',
            'justizkostenrelevanz',
            'zustellung41StPO',
            'vertraulichkeitsstufe',
            'vertraulichZuBehandeln',
            'geheimhaltungsgrad',
            'eingestuftAm',
            'einstufungEndetAm',
            'einstufungsfrist',
            'herausgeber',
            'bemerkung',            
            'dateiname.bezugsdatei',
            'versionsnummer',
            'ersteSeitennummer',
            'letzteSeitennummer', 
            'dateiname',
            
        ]

        self.docHeaderColumnsSettings={
            #Schlüssel                        Kopfzeilentext                           Aktion für Menüeintrag/Konfiguration              Standard-Sichtbarkeit Spaltenbreite (kein echter Effekt - wird auf auto gesetzt, falls nicht None)                 
            ''                               :{'headertext':''                       ,'setting':None                                   ,'default':True    ,'width':10},
            ''                               :{'headertext':''                       ,'setting':None                                   ,'default':True    ,'width':10},
            'nummerImUebergeordnetenContainer':{'headertext':'#'                       ,'setting':None                                   ,'default':True    ,'width':45},
            'ersteSeitennummer'               :{'headertext':'Erste\nSeitennr.'        ,'setting':self.actionErste_SnrColumn             ,'default':False   ,'width':45},
            'letzteSeitennummer'              :{'headertext':'Letzte\nSeitennr.'       ,'setting':self.actionLetzte_SnrColumn            ,'default':False   ,'width':45},            
            'dateiname'                       :{'headertext':'Dateiname'               ,'setting':None                                   ,'default':True    ,'width':None},
            'anzeigename'                     :{'headertext':'Anzeige-\nname'          ,'setting':None                                   ,'default':True    ,'width':200},
            'nurMetadaten'                    :{'headertext':'Nur\nMetadaten'          ,'setting':self.actionNur_MetadatenColumn         ,'default':False   ,'width':45},
            'datumDesSchreibens'              :{'headertext':'Datum'                   ,'setting':self.actionDatumColumn                 ,'default':True    ,'width':95},
            'erstellungszeitpunkt'            :{'headertext':'Erstellungs-\nzeitpunkt' ,'setting':self.actionErstellungszeitpunktColumn  ,'default':True    ,'width':195},
            'posteingangsdatum'               :{'headertext':'Eingangs-\ndatum'        ,'setting':self.actionEingangsdatumColumn         ,'default':False   ,'width':195},
            'posteingangszeitpunkt'           :{'headertext':'Eingangs-\nzeit'         ,'setting':self.actionEingangsdatumColumn         ,'default':False   ,'width':195},
            'veraktungsdatum'                 :{'headertext':'Veraktung'               ,'setting':self.actionVeraktungsdatumColumn       ,'default':True    ,'width':95},
            'scanDatum'                       :{'headertext':'Scandatum'               ,'setting':self.actionScandatumColumn             ,'default':False   ,'width':95},
            'ersetzenderScan'                 :{'headertext':'Ersetzender\nScan'       ,'setting':self.actionErsetzenderScanColumn       ,'default':False   ,'width':40},
            'dokumententyp'                   :{'headertext':'Typ'                     ,'setting':self.actionDokumententypColumn         ,'default':True    ,'width':None},
            'dokumentklasse'                  :{'headertext':'Klasse'                  ,'setting':self.actionDokumentenklasseColumn      ,'default':True    ,'width':200},
            'bestandteil'                     :{'headertext':'Bestandteil'             ,'setting':self.actionBestandteilColumn           ,'default':True    ,'width':None},
            'versionsnummer'                  :{'headertext':'Version-\nnr.'           ,'setting':self.actionVersionsnummerColumn        ,'default':False   ,'width':None},
            'dateiname.bezugsdatei'           :{'headertext':'Bezug\nzu'               ,'setting':self.actionBezugsdateinameColumn       ,'default':False   ,'width':None},
            'ruecksendungEEB.erforderlich'    :{'headertext':'EEB'                     ,'setting':self.actionEEB_HinweisColumn           ,'default':True    ,'width':45},
            'zustellung41StPO'                :{'headertext':'§41\nStPO'               ,'setting':self.actionZustellung_StPO_41Column    ,'default':False   ,'width':40},
            'akteneinsicht'                   :{'headertext':'Akten-\neinsicht'        ,'setting':self.actionAkteneinsichtColumn         ,'default':False   ,'width':60},
            'absenderAnzeigename'             :{'headertext':'Absender'                ,'setting':self.actionAbsenderColumn              ,'default':False   ,'width':None},
            'adressatAnzeigename'             :{'headertext':'Adressat'                ,'setting':self.actionAdressatColumn              ,'default':False   ,'width':None},
            'justizkostenrelevanz'            :{'headertext':'Kosten-\nrele-\nvanz'    ,'setting':self.actionJustizkostenrelevanzColumn  ,'default':False   ,'width':58},
            'fremdesGeschaeftszeichen'        :{'headertext':'fr. Gz.'                 ,'setting':self.actionfrGeschaeftszeichenColumn   ,'default':False   ,'width':None},
            'vertraulichkeitsstufe'           :{'headertext':'Vertraulich-\nkeitsstufe','setting':self.actionVertraulichkeitsstufeColumn ,'default':False   ,'width':None},
            'vertraulichZuBehandeln'          :{'headertext':'Vertraulich-\nkeit'      ,'setting':self.actionVertraulichZuBehandelnColumn,'default':False   ,'width':None},           
            'geheimhaltungsgrad'              :{'headertext':'Geheim-\nhaltungsgrad'   ,'setting':self.actionGeheimhaltungsgradColumn    ,'default':False   ,'width':None},           
            'einstufungsfrist'                :{'headertext':'Einstufungs-\nfrist'     ,'setting':self.actionEinstufungsfristColumn      ,'default':False   ,'width':None},    
            'eingestuftAm'                    :{'headertext':'Einstufungs-\ndatum'     ,'setting':self.actionEinstufungsdatumColumn      ,'default':False   ,'width':None},           
            'herausgeber'                     :{'headertext':'Herausgeber'             ,'setting':self.actionHerausgeberColumn           ,'default':False   ,'width':None},           
            'einstufungEndetAm'               :{'headertext':'Einstufungs-\nende'      ,'setting':self.actionEinstufungsendeColumn       ,'default':False   ,'width':None},           
            'bemerkung'                       :{'headertext':'Bemerkung'               ,'setting':self.actionGeheimBemerkungColumn       ,'default':False   ,'width':None},                  

        }
         
        self.isDocColumnEmpty={}
        
        ####Initiale Einstellungen####
        self.inhaltView.setHeaderHidden(True)
        
        self.plusFilter.setText(self.settings_manager.get_string("plusFilter", ''))
        self.minusFilter.setText(self.settings_manager.get_string("minusFilter", ''))
        self.__readSettings()

        
        # Maintenance-Token prüfen 
        # Sei fair ;)
        if is_in_bundle():
            if check_token_from_env()[0]:
                self.actionMaintenance_Token.setVisible(False)
            elif not is_token_valid(self.settings_manager):
                from datetime import date
                if date.today().day % 2 == 1:
                    self.maintenanceBanner.setVisible(True)
        else:
            self.actionMaintenance_Token.setVisible(False)
            
        #TODO: In späterer Version entfernen
        ####Chromium als PDF-Viewer verbergen (Deprecated)####
        self.actionChromium.setVisible(False) 
          
        # Bessere Lesbarkeit inaktiver items unter Windows 10 / 11
        if sys.platform.lower().startswith('win'):
            xjvPalette = self.palette()
            xjvPalette.setColor(QPalette.ColorRole.Highlight, QColor(150, 150, 255, 255))
            xjvPalette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255, 255))
            self.setPalette(xjvPalette)
        
        #Behebe Problem mit Palette unter Gnome / Ubuntu - setze inaktive Farben auf aktive Farben
        if sys.platform.lower() == 'linux': 
            self.__fixGnomeDarkPalette() 
             
        #### Lade leeren Viewer ####
        self.__loadEmptyViewer()  

        #### Kontextmenü für Dateitabelle erstellen ####
        self.docTableView.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.docTableView.customContextMenuRequested.connect(self.__showDocsContextMenu)
        #### Shortcut erstellen ####
        shortcutAddDocToFav2 = QShortcut(QKeySequence("INS"), self.docTableView)
        shortcutAddDocToFav2.activated.connect(self.__addDocToFavorites)
        shortcutDelDocFromFav = QShortcut(QKeySequence("Del"), self.docTableView)
        shortcutDelDocFromFav.setContext(Qt.ShortcutContext.WidgetShortcut) 
        shortcutDelDocFromFav.activated.connect(self.__removeFavorite)
        
        #### Kontextmenü für Favoriten erstellen ####
        self.favTableView.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.favTableView.customContextMenuRequested.connect(self.__showFavContextMenu)
        #### Shortcut erstellen ####
        shortcutMoveFavUp = QShortcut(QKeySequence("Ctrl+Up"), self.favTableView)
        shortcutMoveFavUp.activated.connect(lambda:self.__moveFav('up'))
        shortcutMoveFavDown = QShortcut(QKeySequence("Ctrl+Down"), self.favTableView)
        shortcutMoveFavDown.activated.connect(lambda:self.__moveFav('down'))
        shortcutDelFav = QShortcut(QKeySequence("Del"), self.favTableView)
        shortcutDelFav.setContext(Qt.ShortcutContext.WidgetShortcut) 
        shortcutDelFav.activated.connect(self.__removeFavorite)                
        
        shortcutSearch = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcutSearch.activated.connect(self.suchbegriffeText.setFocus)
        
        # Unerwünschte Shortcuts blockieren
        shortcutBlocker = QShortcut(QKeySequence("Ctrl+Left"), self.favTableView)
        shortcutBlocker = QShortcut(QKeySequence("Ctrl+Right"), self.favTableView)     
        #########self.favoriteniew##########
        self.favorites = list()

        #########self.favoriteniew##########
        self.downloadFolder = ''
        
        #######Lade Browser-Verlauf ##### 
        self.browsingHistory = self.__loadHistory()

        self.actionHistorieVor.setAutoRepeat(False)  
        self.actionHistorieZurück.setAutoRepeat(False)     
        ####Verbindungen####
        self.actionOeffnen.triggered.connect(lambda:self.getFile())
        self.actionNachrichtSchliessen.triggered.connect(self.__resetAll)
        self.actionVerlaufLoeschen.triggered.connect(self.__deleteHistory)
        self.actionNotizUndSuchdatenbankLoeschen.triggered.connect(self.__notizUndSuchdatenbankLoeschen)
        self.actionPDFExport.triggered.connect(lambda:self.__exportPDF(self.docTableView))
        self.actionFavPDFExport.triggered.connect(lambda:self.__exportPDF(self.favTableView))
        self.actionNotesPDFExport.triggered.connect(self.__notizPdfExport)
        self.actionTexterkennung.triggered.connect(self.__texterkennung)
        self.actionTexterkennungAktuellesPDF.triggered.connect(self.__texterkennungLoadedPDF)
        self.actionOCRall.clicked.connect(self.__texterkennungAll)
        self.actionHistorieVor.triggered.connect(lambda:self.__fileHistory('forward'))
        self.actionHistorieZurück.triggered.connect(lambda:self.__fileHistory('backward'))
        self.actionZIP_ArchiveOeffnen.triggered.connect(self.__selectZipFiles)
        self.actionUeberOpenXJV.triggered.connect(self.__displayInfo)
        self.actionAnleitung.triggered.connect(self.__openManual)
        self.actionDatenschutzerklaerung.triggered.connect(self.__openDatenschutzerklaerung)
        self.actionSupport_anfragen.triggered.connect(self.__supportAnfragen)       
        self.actionAktenverzeichnis_festlegen.triggered.connect(lambda:self.__chooseStartFolder())
        # self.inhaltView.clicked.connect(self.__updateSelectedInhalt) # führt zu bounce mit connect in __setInhaltView()
        self.docTableView.clicked.connect(self.__browseDocTableAction)
        self.docTableView.doubleClicked.connect(self.__dClickDocTableAction)
        self.docTableView.selectionModel().selectionChanged.connect(self.__browseDocTableAction)
        self.termineTableView.clicked.connect(self.__setTerminDetailView)
        self.plusFilter.textChanged.connect(lambda:self.__filtersTriggered())
        self.minusFilter.textChanged.connect(lambda:self.__filtersTriggered())
        self.suchbegriffeText.textChanged.connect(self.__performSearch)
        self.filterLeeren.clicked.connect(self.__resetFilters)
        self.filterMagic.clicked.connect(self.__magicFilters)
        self.favTableView.clicked.connect(self.__getFavoriteViewAction)
        self.favTableView.doubleClicked.connect(self.__getDClickFavoriteViewAction)
        self.favTableView.selectionModel().selectionChanged.connect(self.__getFavoriteViewAction)
        self.deleteFavoriteButton.clicked.connect(self.__removeFavorite)
        self.saveFavouritesButton.clicked.connect(self.__exportToFolderAction)
        self.exportFavoritesButton.clicked.connect(self.__exportZipAction)
        self.exportFavsToPdfButton.clicked.connect(lambda:self.__exportPDF(self.favTableView))
        self.actionZuruecksetzen.triggered.connect(self.__resetSettings)   
        self.actionnativ.triggered.connect(self.__viewerSwitch)
        self.actionPDF_js.triggered.connect(self.__viewerSwitch)
        self.actionChromium.triggered.connect(self.__viewerSwitch) #TODO: In späterer Version entfernen
        self.actionAlleSpaltenAbwaehlen.triggered.connect(self.__uncheckAllColumns)
        self.actionAlleSpaltenMarkieren.triggered.connect(self.__checkAllColumns)
        self.browser.page().profile().downloadRequested.connect(self.__downloadRequested) #TODO Gemeinsam mit Chromiumvieweroption entfernen
        self.actionNeueVersion.triggered.connect(lambda triggered: open_url("https://openxjv.de"))
        self.actionXML_Validierung_XSD.triggered.connect(self.__openXSDValidator)
        self.actionAktion_erfragen.triggered.connect(self.__annotationSettingsSwitch)
        self.actionAutomatisch_speichern.triggered.connect(self.__annotationSettingsSwitch)
        self.actionVerwerfen.triggered.connect(self.__annotationSettingsSwitch)
        self.actionMaintenance_Token.triggered.connect(self.__showMaintenanceDialog)
        self.actionKI_Labor.triggered.connect(self.__openKILabor)

        if "OPENXJV_NO_AI" in os.environ:
            self.actionKI_Labor.setVisible(False)

        self.empfaengerText.customContextMenuRequested.connect(lambda event:self.__copyToClipboard(self.empfaengerText.text()))         
        self.erstellungszeitpunktText.customContextMenuRequested.connect(lambda event:self.__copyToClipboard(self.erstellungszeitpunktText.text()))
        self.absenderAktenzeichenText.customContextMenuRequested.connect(lambda event:self.__copyToClipboard(self.absenderAktenzeichenText.text()))
        self.empfaengerAktenzeichenText.customContextMenuRequested.connect(lambda event:self.__copyToClipboard(self.empfaengerAktenzeichenText.text()))
        self.sendungsprioritaetText.customContextMenuRequested.connect(lambda event:self.__copyToClipboard(self.sendungsprioritaetText.text()))
        self.absenderText.customContextMenuRequested.connect(lambda event:self.__copyToClipboard(self.absenderText.text()))
        
        # Verbinde mit screen change event
        if self.windowHandle():
            self.windowHandle().screenChanged.connect(self.__onScreenChanged)       

        # Weitere Einstellungen       
        self.settingItems =[
            self.actionGrosse_Schrift, 
            self.actionOnlineAufUpdatesPruefen,
            self.actionLeereSpaltenAusblenden,
            self.actionNotizen,
            self.actionMetadaten,
            self.actionFavoriten,
            self.actionNurFavoritenExportieren,
            self.actionFavoritenExportieren,
            self.actionDateidatumExportieren,
            self.actionDeckblattBeiExport,
            self.actionAnwendungshinweise,
            self.actionNachrichtenkopf,
            self.actionPDFnachExportOeffnen,
            self.actionNotizenaufDeckblattausgeben,
            self.actionSucheAnzeigen,
            self.actionDateitabelleLinksbuendig
            ]
        
        for setting in self.settingItems:
            setting.triggered.connect(self.__updateSettings)    
        
        for columnSetting in self.docHeaderColumnsSettings.values():
            if columnSetting['setting']:
                columnSetting['setting'].triggered.connect(self.__updateSettings)
        
        # Workaround für sich nicht aktualisierenden Tabelleninhalt unter Fedora 35 & Ubuntu 22.04 -> Wayland ???
        self.docTableView.horizontalHeader().sectionClicked.connect(self.docTableView.viewport().update)       
        self.favTableView.horizontalHeader().sectionClicked.connect(self.favTableView.viewport().update)       
          
        #Prüfe auf Updates
        if self.actionOnlineAufUpdatesPruefen.isChecked():
            self.__checkForUpdates(updateIndicator=self.newVersionIndicator)
        
        #########Speichere initiale Dateien für verzögertes Laden##########
        self._initial_file = file
        self._initial_ziplist = ziplist
 
    def __del__(self):
        if os.path.isdir(self.tempDir.name):
            rmtree(self.tempDir.name)

    def setInitialSplitterSizes(self):
        """Setzt die initialen Splitter-Größen, sodass der PDF-Viewer die Hälfte des Bildschirms einnimmt."""
        total_width = self.splitter_9.width()
        if total_width > 0:
            self.splitter_9.setSizes([total_width // 2, total_width // 2])

    def loadInitialFiles(self):
        """Lädt die beim Start übergebenen oder zuletzt verwendeten Dateien."""
        QApplication.processEvents()
        if self._initial_file and self._initial_file.lower().endswith('xml'):
            self.getFile(self._initial_file)
        elif self._initial_ziplist:
            # Validiere ZIP-Dateien
            for zf in self._initial_ziplist:
                if not zf.lower().endswith('zip'):
                    message = f'Fehler: Die übergebene Liste enthält nicht ausschließlich ZIP-Dateien: {zf}'
                    self.statusBar.showMessage(message)
                    self.lastExceptionString = message
            self.getZipFiles(files=self._initial_ziplist)
        else:
            lastfile = self.settings_manager.get_string("lastFile", None)
            if lastfile:
                self.getFile(lastfile)

    def cleanUp(self):
        """Speichert Notizen und Einstellungen, löscht temporäres Verzeichnis vor dem Beenden des Programms."""
        self.__saveNotes()
        self.settings.sync()
        self.tempDir.cleanup()

    def closeEvent(self, event):
        if self._ki_window is not None:
            self._ki_window.close()
            self._ki_window = None
        annotation_action = self.__getAnnotationAction()
        if annotation_action in ('prompt', 'auto_save'):
            try:
                self.pdf_viewer.exit_annotation_edit_mode()
                if self.pdf_viewer.has_unsaved_changes():
                    reply = QMessageBox.question(
                        self,
                        "Ungespeicherte Annotationen",
                        "Das aktuell angezeigte PDF enthält ungespeicherte Annotationen.\n"
                        "Sollen die Änderungen vor dem Beenden gespeichert werden?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes,
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self.__trigger_pdf_unsaved_changes()
                        QMessageBox.information(
                            self,
                            "Annotationen gespeichert",
                            "Die Annotationen wurden gespeichert.",
                        )
            except Exception:
                pass
        super().closeEvent(event)

    # ========================================
    # ABSCHNITT 2: DATEIOPERATIONEN
    # ========================================
    def __loadFile(self, file):
        """Lädt einen XJustiz-Datensatz und aktualisiert die Ansicht. Delegiert an FileManager."""
        # Definiere Parser-Map für XJustiz-Versionen
        parser_map = {
            "2.4.0": parser240,
            "3.2.1": parser321,
            "3.3.1": parser331,
            "3.4.1": parser341,
            "3.5.1": parser351,
            "default": parser362
        }

        # Success callback
        def on_success(akte, file_path, version):
            self.akte = akte
            # Initialisiere XJustizDisplayRenderer mit geladener Akte
            self.display_renderer = XJustizDisplayRenderer(self.akte)
            self.__setDocumentTable('Alle_Dokumente')
            self.__setInhaltView(self.akte.schriftgutobjekte)
            self.__setNachrichtenkopf(self.akte.absender, self.akte.empfaenger, self.akte.nachricht)
            self.__setMetadata(self.akte)
            self.__filtersTriggered()
            self.__loadFavorites()
            self.__loadNotes()
            self.__setInstanzenView()
            self.__setBeteiligteView()
            self.__setTerminTable(self.akte.termine)
            self.terminDetailView.setHtml('')
            self.basedir = os.path.dirname(os.path.realpath(file_path))
            self.xmlFile = os.path.basename(file_path)
            self.file_manager.set_basedir(self.basedir)
            self.__loadEmptyViewer()
            self.settings_manager.set_value("lastFile", file_path)
            self.__addToHistory(file_path)
            self.statusBar.showMessage(f'Eingelesene Datei: {file_path} - XJustiz-Version: {version}')
            if not self.__prepareSearchStore():
                self.actionOCRall.setVisible(False)

        # Error callback
        def on_error(file_path, exception):
            self.statusBar.showMessage('Fehler beim Öffnen der Datei: %s' % file_path)
            self.lastExceptionString = str(exception)

        # Delegiere an FileManager
        result = self.file_manager.load_file(
            file_path=file,
            parser_map=parser_map,
            on_success=on_success,
            on_error=on_error
        )

        if result is None:
            return None

    def getFile(self, file=None, folder=None):
        """Lädt XJustiz-Datei nach Auswahl oder direkter Angabe. Delegiert an FileManager."""
        # Notizen eines ggf. geöffneten Datensatzes speichern
        self.__saveNotes()

        if file and os.path.exists(file):
            self.__loadFile(file)
        elif file and not os.path.exists(file):
            pass
        elif file is None:
            # Delegate file selection to FileManager
            file = self.file_manager.select_file_dialog(
                folder=folder,
                file_filter="XJustiz-Dateien (*.xml *.XML)"
            )

            if file:
                self.__loadFile(file)
                self.__checkFiltersAndRows()

            # Windows verliert Fokus beim Laden von ZIP-Dateien
            self.activateWindow()

    def getZipFiles(self, files=None):
        """Entpackt ZIP-Dateien in temporäres Verzeichnis. Delegiert an FileManager."""
        if files:
            # Error callback
            def on_error(file_path, exception):
                self.statusBar.showMessage(file_path + ' konnte nicht entpackt werden.')
                self.lastExceptionString = str(exception)

            # Delegate extraction to FileManager
            tempPath = self.file_manager.extract_zip_files(
                zip_files=files,
                on_error=on_error
            )

            if tempPath:
                self.getFile(folder=tempPath)    
  
    def __selectZipFiles(self):
        """Wählt ZIP-Archive aus und entpackt sie. Delegiert an FileManager."""
        # Delegate file selection to FileManager
        files = self.file_manager.select_zip_files()

        if files:
            self.getZipFiles(files)    
            
    def __openDocExternal(self):
        """Öffnet aktuell markierte Datei mit externem Standardprogramm."""
        if self.docTableView.currentRow()!=-1:
            filenameColumn=self.docTableAttributes.index('dateiname')+2
            filename=self.docTableView.item(self.docTableView.currentRow(), filenameColumn).text()
            self.__openFileExternal(filename)  

    def __openFileExternal(self, filename, ignoreWarnings=False, absolutePath=False):
        """Öffnet Datei mit externem Programm. Delegiert an FileManager."""
        # Aktualisiere FileManager's basedir auf aktuellen Status
        self.file_manager.set_basedir(self.basedir)

        # Delegiere an FileManager
        success = self.file_manager.open_file_external(
            filename=filename,
            ignore_warnings=ignoreWarnings,
            absolute_path=absolutePath
        )

        # Zeige Fehlermeldung, wenn Datei nicht existiert
        if not success and not ignoreWarnings:
            self.statusBar.showMessage('Datei existiert nicht: ' + filename) 

    def __trigger_pdf_unsaved_changes(self):
        """Löst den async Save-Prozess für ungespeicherte PDF-Annotationen aus.

        Nur noch von closeEvent verwendet: Nachdem der Nutzer im eigenen
        QMessageBox-Dialog "Ja" gewählt hat, wird der async Save über
        backend._handle_unsaved_before_action() angestoßen.

        HINWEIS: Alle anderen früheren Aufrufstellen wurden nach den upstream-Fixes
        in pdfjs_viewer entfernt — show_blank_page() behandelt ungespeicherte
        Änderungen nun intern.

        HINWEIS: Die öffentliche handle_unsaved_changes() ist hier NICHT geeignet, da sie
        _close_deferred=True setzt und nach dem async Save widget.close() aufruft.
        """
        try:
            self.pdf_viewer.backend._handle_unsaved_before_action(
                {'type': 'show_blank_page'}
            )
        except Exception:
            pass

    def __openFileInBrowser(self, filename):
        """Öffnet Datei im Browser-Viewer."""
        # Bestimme vollständigen Pfad - filename kann bereits absolut sein (z.B. konvertierte TIFF-Dateien)
        if os.path.isabs(filename):
            filepath = filename
        else:
            filepath = os.path.join(self.basedir, filename)

        if not os.path.exists(filepath):
            self.statusBar.showMessage(f'Datei existiert nicht: {filename}')
            return
        
        # Bereits geladenes Dokument nicht erneut laden
        if self.loadedPDFpath == filepath:
            return

        self.loadedPDFpath = filepath
        self.loadedPDFfilename = os.path.basename(filename)

        # Plattformspezifische Pfadbehandlung
        if sys.platform.lower().startswith('win'):
            filePath = filepath.replace("\\", "/")
        else:
            filePath = filepath

        if filename.lower().endswith(".pdf"):
            viewer_mode = self.settings_manager.get_pdf_viewer()
            if viewer_mode == 'PDFjs':
                # Verwende pdfjs_viewer für PDF.js-Modus
                self.pdf_viewer.load_pdf(filepath)
            
            #TODO: In späterer Version als PDF-Viewer entfernen    
            elif viewer_mode == 'chromium': 
                # Verwende Chromiums nativen PDF-Viewer (deprecated)
                self.browser.setUrl(QUrl.fromLocalFile(filepath))
            else:
                # Native - extern öffnen
                self.__openFileExternal(filepath)
                return
        else:
            # Nicht-PDF-Dateien: Bilder, HTML, XML, Text - über Browser laden
            # show_blank_page() behandelt ungespeicherte Annotationen und leert den PDF-Viewer.
            self.pdf_viewer.show_blank_page()
            winslash = '/' if sys.platform.lower().startswith('win') else ''
            self.url = "file://%s%s" % (winslash, filePath)
            self.browser.setUrl(QUrl.fromUserInput(self.url))

        self.statusBar.showMessage(f'Angezeigte Datei: {os.path.basename(filename)}')  
    
    def __openManual(self):
        manualPath = os.path.join(self.scriptRoot , 'docs', 'openXJV_Benutzerhandbuch.pdf')
        self.__openFileExternal(manualPath, True, True)

    def __openDatenschutzerklaerung(self):
        datenschutzPath = os.path.join(self.scriptRoot , 'docs', 'openXJV_Datenschutzerklärung.pdf')
        self.__openFileExternal(datenschutzPath, True, True)

    def __openKILabor(self):
        """Öffnet das KI-Labor. Es kann immer nur ein KI-Labor gleichzeitig geöffnet sein."""
        if self._ki_window is not None and self._ki_window.isVisible():
            self._ki_window.activateWindow()
            self._ki_window.raise_()
            return
        from openxjv.ki.core.ui.main_window import KIMainWindow
        from openxjv.ki.core.model_registry import ModelRegistry as KIModelRegistry
        models_dir = Path(self.dirs.user_data_dir) / "models"
        registry = KIModelRegistry(models_dir=models_dir)
        self._ki_window = KIMainWindow(registry=registry, app_dir=self.scriptRoot, ki_debug=self._ki_debug)
        current_path = self.__getKISupportedFilePath()
        if current_path:
            self._ki_window.set_file_path(current_path)
        self._ki_window.show()

    def __getKISupportedFilePath(self) -> str:
        """
        Gibt den Originalpfad der aktuell in der Vorschau geladenen Datei zurück,
        sofern das Format von der KI-Textextraktion unterstützt wird.
        Gibt leeren String zurück, wenn keine passende Datei geladen ist.
        """
        from openxjv.ki.core.ui.main_window import SUPPORTED_EXTENSIONS as KI_SUPPORTED_EXTENSIONS
        path = self.loadedPDFpath
        if path and Path(path).suffix.lower() in KI_SUPPORTED_EXTENSIONS:
            return path
        return ""

    def __passFileToKILabor(self, filepath: str) -> None:
        """Übergibt einen Dateipfad an ein geöffnetes KI-Labor."""
        from openxjv.ki.core.ui.main_window import SUPPORTED_EXTENSIONS as KI_SUPPORTED_EXTENSIONS
        if self._ki_window is not None and self._ki_window.isVisible():
            if Path(filepath).suffix.lower() in KI_SUPPORTED_EXTENSIONS:
                self._ki_window.set_file_path(filepath)

    def __exportZipAction(self):
        """Exportiert Dateien aus der Favoritenliste nach Auswahl eines Dateinamens in eine ZIP-Datei. Delegiert an FileManager."""
        message = ''

        if not self.favorites:
            message = 'Aktion nicht verfügbar. Die Favoritenliste ist leer!'
            self.__displayMessage(message)
        else:
            # Aktualisiere FileManager basedir
            self.file_manager.set_basedir(self.basedir)

            # Hole ZIP-Dateipfad vom Benutzer
            zipPath = self.file_manager.save_file_dialog(
                title="In ZIP-Datei exportieren",
                file_filter="ZIP-Dateien (*.zip *.ZIP)",
                default_extension=".zip"
            )

            if zipPath and self.favorites:
                try:
                    # Delegiere an FileManager
                    self.file_manager.export_to_zip(
                        zip_path=zipPath,
                        file_list=list(dict.fromkeys(e.filename for e in self.favorites)),
                        include_xml=True,
                        xml_file=self.settings_manager.get_string("lastFile", None)
                    )
                    message = 'Die Dateien wurden erfolgreich exportiert - %s' % zipPath
                    self.__displayMessage(message)
                except Exception as e:
                    message = 'Bei der Erzeugung der Zip-Datei ist ein Fehler aufgetreten.'
                    self.__displayMessage(message, title='Fehler', icon=QMessageBox.Icon.Warning)
                    self.lastExceptionString = str(e)
                    self.__debugOutput('__exportToZipAction')
            else:
                return

        self.statusBar.showMessage(message)
     
    def __exportToFolderAction(self):
        """Fragt Zielordner ab in Dialog und exportiert Dateien. Delegiert an FileManager."""
        message = ''

        if not self.favorites:
            message = 'Aktion nicht verfügbar. Die Favoritenliste ist leer!'
            self.__displayMessage(message)
        else:
            # Aktualisiere FileManager basedir
            self.file_manager.set_basedir(self.basedir)

            # Hole Ordner vom Benutzer
            folder = self.file_manager.select_folder_dialog(title="Exportverzeichnis wählen")

            if folder and self.favorites:
                try:
                    # Delegiere an FileManager
                    self.file_manager.export_to_folder(
                        folder_path=folder,
                        file_list=list(dict.fromkeys(e.filename for e in self.favorites)),
                        include_xml=True,
                        xml_file=self.settings_manager.get_string("lastFile", None)
                    )
                    message = 'Die Dateien wurden erfolgreich nach %s kopiert.' % folder
                    self.__displayMessage(message)
                except Exception as e:
                    message = 'Es ist ein Fehler während des Kopiervorgangs aufgetreten.'
                    self.__displayMessage(message, title='Fehler', icon=QMessageBox.Icon.Warning)
                    self.lastExceptionString = str(e)
                    self.__debugOutput('__exportToFolderAction')
            else:
                return

        self.statusBar.showMessage(message)
    
    #TODO Gemeinsam mit Chromiumvieweroption entfernen
    def __downloadRequested(self, download):
        if self.downloadFolder != '':
            startFolder = self.downloadFolder
        else:
            startFolder = download.downloadDirectory()

        folder = QFileDialog.getExistingDirectory(self, 
                                "Speicherort wählen",
                                startFolder,
                                QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks)
    
        if folder:
            download.setDownloadDirectory(folder)
            self.downloadFolder = folder
            download.accept()
     
    # ========================================
    # ABSCHNITT 3: VERLAUFSVERWALTUNG
    # ========================================
    def __fileHistory(self, direction):
        """Blättert durch die Dateihistorie und lädt die nächste/vorherige Datei in der Liste."""

        if len(self.browsingHistory)>0:
            
            if direction == 'forward':
                self.browsingHistory.insert(0, self.browsingHistory.pop())
            else:
                self.browsingHistory.append(self.browsingHistory.pop(0))
            

            while len(self.browsingHistory)>0:
                if os.path.exists(self.browsingHistory[0]):
                    self.getFile(self.browsingHistory.pop(0))
                    break
                else:
                    self.browsingHistory.pop(0)

            self.__checkFiltersAndRows()

    def __addToHistory(self, file):
        """Fügt die zuletzt geöffnete XJustiz-Datei zur Verlaufsliste hinzu."""
        if file in self.browsingHistory:
            self.browsingHistory.remove(file)
        self.browsingHistory.insert(0,file)

        while len(self.browsingHistory)>10:
            self.browsingHistory.pop()
        
        historyString=''
        for filepath in self.browsingHistory:
            historyString+=filepath + "\x07"
        historyString=historyString.strip("\x07")
        
        self.settings_manager.set_value("history", historyString)

    def __deleteHistory(self):
        self.browsingHistory = []
        self.settings_manager.set_value("history", '')
        self.settings_manager.set_value("lastFile", None)
        self.__updateSettings()
        self.statusBar.showMessage('Der Verlauf wurde gelöscht.')

    def __loadHistory(self):
        """Lädt die zuletzt geladenen XJustiz-Dateien in Verlaufsliste."""
        browsingHistory=self.settings_manager.get_string("history", '').split('\x07')
        return browsingHistory
     
    # ========================================
    # ABSCHNITT 4: FAVORITENVERWALTUNG
    # ========================================      
    def __addFavorite(self, filename, anzeigename=''):
        """Fügt eine Datei zu den Favoriten hinzu und markiert die neue Zeile."""
        entry = FavoriteEntry(filename=filename, anzeigename=anzeigename)
        if entry not in self.favorites:
            self.favorites.append(entry)
            self.__setFavorites()
            self.__saveFavorites()

        # Zeile in favTableView selektieren; Suche via UserRole-Daten ist robust
        # gegenüber mehrfach vorkommendem Dateinamen mit unterschiedlichen Anzeigenamen.
        for row_idx in range(self.favTableView.rowCount()):
            if self.favTableView.item(row_idx, 0).data(Qt.ItemDataRole.UserRole) == entry:
                self.favTableView.selectRow(row_idx)
                break

    def __addDocToFavorites(self):
        """Fügt das aktuell in der Dokumentenansicht markierte Dokument zu den Favoriten hinzu."""
        filename = self.__getCurrentDocTableFilename()
        if not filename:
            return
        anzeigenameColumn = self.docTableAttributes.index('anzeigename') + 2
        az_item = self.docTableView.item(self.docTableView.currentRow(), anzeigenameColumn)
        anzeigename = az_item.text() if az_item is not None else ''
        self.__addFavorite(filename, anzeigename)
          
    def __addAllDocsToFavorites(self):
        """Fügt den Favoriten alle Dokumente der Dokumentenansicht hinzu."""
        if self.docTableView.rowCount() > 0:
            filenameColumn = self.docTableAttributes.index('dateiname') + 2
            anzeigenameColumn = self.docTableAttributes.index('anzeigename') + 2
            for row in range(self.docTableView.rowCount()):
                if not self.docTableView.isRowHidden(row):
                    fn_item = self.docTableView.item(row, filenameColumn)
                    az_item = self.docTableView.item(row, anzeigenameColumn)
                    if fn_item is None:
                        continue
                    filename = fn_item.text()
                    anzeigename = az_item.text() if az_item is not None else ''
                    entry = FavoriteEntry(filename=filename, anzeigename=anzeigename)
                    if entry not in self.favorites:
                        self.favorites.append(entry)
            self.__setFavorites()
            self.__saveFavorites()
           
    def __removeFavorite(self):
        """Entfernt den markierten Eintrag in der aktuell active view aus der Favoritenliste."""
        focusWidget = self.focusWidget()
        if focusWidget in (self.favTableView, self.docTableView):
            entry = self.__getCurrentItemEntry(focusWidget)
        elif focusWidget == self.deleteFavoriteButton:
            entry = self.__getCurrentItemEntry(self.favTableView)
        else:
            return

        if entry and entry in self.favorites:
            if self.favTableView.currentRow() <= self.favTableView.rowCount() - 2:
                next_row = self.favTableView.currentRow()
            else:
                next_row = self.favTableView.rowCount() - 2

            self.favorites.remove(entry)
            self.__setFavorites()
            self.__saveFavorites()

            self.favTableView.selectRow(next_row)
            self.statusBar.showMessage(entry.filename + ' aus Favoriten entfernt.')

    def __moveFav(self, direction='up'):
        if self.favTableView.currentItem():
            row = self.favTableView.currentRow()
            col0 = self.favTableView.item(row, 0)
            if col0 is None:
                return
            entry = col0.data(Qt.ItemDataRole.UserRole)
            if entry is None:
                return

            try:
                position = self.favorites.index(entry)
                self.favorites.remove(entry)
                if direction == 'up' and position != 0:
                    position -= 1
                elif direction == 'down':
                    position += 1
                self.favorites.insert(position, entry)
                self.__setFavorites()
                if position == len(self.favorites):
                    position -= 1
                self.favTableView.selectRow(position)
                self.__saveFavorites()
            except ValueError:
                pass
                        
    def __delAllFavorites(self):
        """Löscht alle Favoriten und aktualisiert die Favoritenansicht."""
        self.favorites.clear()
        self.__setFavorites()
        self.__saveFavorites() 
            
    def __loadFavorites(self):
        self.favorites.clear()
        # Lade Favoriten nur, wenn eine Datei geladen ist (akte hat nachricht-Attribut)
        if self.akte and hasattr(self.akte, 'nachricht'):
            eigeneID = self.akte.nachricht.get('eigeneID')
            if eigeneID:
                try:
                    self.favorites = self.db_manager.load_favorites(eigeneID, self.dirs.user_data_dir)
                    # TODO (Version 1.5+): Diesen Block entfernen, sobald keine Legacy-Einträge
                    # (anzeigename='') mehr in der Datenbank zu erwarten sind.
                    # Schreibt Legacy-Einträge sofort im neuen Format zurück, damit die
                    # Datenbank konsistent bleibt (anzeigename-Spalte vorhanden, Wert '').
                    if any(not e.anzeigename for e in self.favorites):
                        self.__saveFavorites()
                except Exception as e:
                    self.lastExceptionString = str(e)
                    self.__debugOutput('__loadFavorites')
        self.__setFavorites()

    def __saveFavorites(self):
        # Speichere Favoriten nur, wenn eine Datei geladen ist (akte hat nachricht-Attribut)
        if not self.akte or not hasattr(self.akte, 'nachricht'):
            return

        eigeneID = self.akte.nachricht.get('eigeneID')
        if eigeneID:
            try:
                self.db_manager.save_favorites(eigeneID, self.favorites)
            except Exception as e:
                self.lastExceptionString = str(e)
                self.__debugOutput('__saveFavorites')

    # ========================================
    # ABSCHNITT 5: NOTIZEN/DATENBANKOPERATIONEN
    # ========================================
    def __loadNotes(self):
        self.notizenText.clear()
        # Lade Notizen nur, wenn eine Datei geladen ist (akte hat nachricht-Attribut)
        if self.akte and hasattr(self.akte, 'nachricht'):
            eigeneID = self.akte.nachricht.get('eigeneID')
            if eigeneID:
                notes_text = self.db_manager.load_notes(eigeneID, self.dirs.user_data_dir)
                if notes_text:
                    self.notizenText.setPlainText(notes_text)

    def __saveNotes(self):
        # Speichere Notizen nur, wenn eine Datei geladen ist (akte hat nachricht-Attribut)
        if not self.akte or not hasattr(self.akte, 'nachricht'):
            return

        eigeneID = self.akte.nachricht.get('eigeneID')
        if eigeneID:
            notes_text = self.notizenText.toPlainText()
            self.db_manager.save_notes(eigeneID, notes_text)
    
    # ========================================
    # ABSCHNITT 6: SUCH- UND FILTEROPERATIONEN
    # ========================================    
    def __prepareSearchStore(self, reset_searchStore = True):
        """Bereitet den Suchindex vor. Delegiert an SearchFilterManager."""
        # UUID sicher abrufen – akte kann ein leeres Dict {} sein
        # oder ein Parser-Objekt mit .nachricht-Attribut
        # Leeren String als Fallback verwenden, da SearchFilterManager einen String erwartet
        if self.akte and hasattr(self.akte, 'nachricht'):
            uuid = self.akte.nachricht.get('eigeneID', '')
        else:
            uuid = ''

        # Verwende SearchFilterManager's prepare_search_store-Methode
        result = self.search_filter_manager.prepare_search_store(
            app=self.app,
            basedir=self.basedir,
            db_path=self.db_path,
            uuid=uuid,
            script_root=self.scriptRoot,
            status_callback=lambda msg: self.statusBar.showMessage(msg),
            ready_callback=self.__searchStoreReady,
            reset_search_store=reset_searchStore,
            search_visible=self.actionSucheAnzeigen.isChecked(),
            table_has_header=True
        )

        # Aktualisiere lokale Referenzen auf Manager-Status
        self.searchStore = self.search_filter_manager.search_store
        self.searchLock = self.search_filter_manager.search_lock

        # Lösche Sucheingabe beim Vorbereiten
        if result:
            self.suchbegriffeText.clear()

        return result

    def __searchStoreReady(self, result):
        """Callback wenn Suchindex bereit ist. Aktualisiert lokale Referenzen."""
        # Aktualisiere lokale Referenzen auf Manager-Status
        self.leereDateien = self.search_filter_manager.empty_files
        self.leerePDF = self.search_filter_manager.empty_pdf
        self.searchStore = self.search_filter_manager.search_store
        self.searchLock = self.search_filter_manager.search_lock

        # Speichere Fehler, falls vorhanden
        if result[3]:
            self.lastExceptionString = result[3] 
        
        if self.leerePDF == 0:
            self.actionOCRall.setVisible(False)
        elif self.OCRenabled:
            self.actionOCRall.setVisible(True)
 
    def __performSearch(self):
        """Führt Volltextsuche durch. Delegiert an SearchFilterManager."""
        # Verwende SearchFilterManager's perform_search-Methode
        self.search_filter_manager.perform_search(
            table=self.docTableView,
            search_terms_text=self.suchbegriffeText.text(),
            app=self.app,
            filename_column_name="Dateiname",
            status_callback=lambda msg: self.statusBar.showMessage(msg),
            clear_callback=lambda: (self.suchbegriffeText.clearFocus(), self.suchbegriffeText.clear()),
            filters_callback=self.__filtersTriggered,
            message_callback=self.__displayMessage
        )

        # Aktualisiere lokale Referenzen
        self.searchStore = self.search_filter_manager.search_store
        self.searchLock = self.search_filter_manager.search_lock
        self.leereDateien = self.search_filter_manager.empty_files
        self.leerePDF = self.search_filter_manager.empty_pdf  
    
    def __filtersTriggered(self, keepSearchTerms=False):
        """Wendet Inklusiv- und Exklusivfilter an. Delegiert an SearchFilterManager."""
        # Verwende SearchFilterManager's apply_filters-Methode
        SearchFilterManager.apply_filters(
            table=self.docTableView,
            plus_filter_text=self.plusFilter.text(),
            minus_filter_text=self.minusFilter.text(),
            settings=self.settings,
            clear_search_callback=lambda: self.suchbegriffeText.clear(),
            keep_search_terms=keepSearchTerms
        )

    def __magicFilters(self):
        """Fügt dem Filter Dateiendungen bekannter technischer Dokumente hinzu. Delegiert an SearchFilterManager."""
        # Verwende SearchFilterManager's apply_magic_filters-Methode
        SearchFilterManager.apply_magic_filters(
            minus_filter_text=self.minusFilter.text(),
            update_minus_filter_callback=lambda text: self.minusFilter.setText(text),
            filters_callback=self.__filtersTriggered
        )

    def __resetFilters(self):
        """Leert die Filterfelder und Suchbegriffe. Delegiert an SearchFilterManager."""
        # Verwende SearchFilterManager's reset_filters-Methode
        SearchFilterManager.reset_filters(
            clear_search_callback=lambda: self.suchbegriffeText.clear(),
            clear_plus_filter_callback=lambda: self.plusFilter.clear(),
            clear_minus_filter_callback=lambda: self.minusFilter.clear(),
            filters_callback=self.__filtersTriggered
        )
    
    # ========================================
    # ABSCHNITT 7: OCR/TEXTERKENNUNG
    # ========================================    
    def __texterkennung(self, sourcepath=None):
        """Texterkennung für beliebige Dateien. Delegiert an OCRHandler."""
        # Verwende OCRHandler's perform_ocr-Methode
        self.ocr_handler.perform_ocr(source_path=sourcepath, parent_widget=self)

        # Aktualisiere lokale Referenz auf ocr_lock
        self.ocrLock = self.ocr_handler.ocr_lock 
        
    def __texterkennungLoadedPDF(self):
        """Texterkennung für das aktuell in der Vorschau angezeigte PDF-Dokument. Delegiert an OCRHandler."""
        # Verwende OCRHandler's perform_ocr_on_loaded_pdf-Methode
        self.ocr_handler.perform_ocr_on_loaded_pdf(
            loaded_pdf_filename=self.loadedPDFfilename,
            loaded_pdf_path=self.loadedPDFpath,
            parent_widget=self
        )

        # Aktualisiere lokale Referenz auf ocr_lock
        self.ocrLock = self.ocr_handler.ocr_lock
        # Aktualisiere letzten Exception-String, falls gesetzt
        if self.ocr_handler.last_exception_string:
            self.lastExceptionString = self.ocr_handler.last_exception_string        
    
    def __texterkennungAll(self):
        """Texterkennung für alle nicht durchsuchbaren Dateien. Delegiert an OCRHandler."""
        # Verwende OCRHandler's perform_batch_ocr-Methode
        self.ocr_handler.perform_batch_ocr(
            base_dir=self.basedir,
            search_store=self.searchStore,
            parent_widget=self,
            action_ocr_all=self.actionOCRall
        )

        # Aktualisiere lokale Referenzen
        self.ocrLock = self.ocr_handler.ocr_lock
        if hasattr(self.ocr_handler, 'scan_folder_after_ocr') and self.ocr_handler.scan_folder_after_ocr:
            self.scan_folder_after_ocr = self.ocr_handler.scan_folder_after_ocr

    # ========================================
    # ABSCHNITT 8: PDF-EXPORTOPERATIONEN
    # ========================================
    def __exportPDF(self, tableWidget):
        """Exportiert die unter 'Dateien' angezeigten Dateien 'Files' in eine einzelne PDF-Datei. Delegiert an pdf_operations."""
        if self.akte == {} or tableWidget.columnCount() == 0 or tableWidget.rowCount() == 0:
            return

        if (self.actionNurFavoritenExportieren.isChecked() or tableWidget == self.favTableView) and len(self.favorites) == 0:
            self.__displayMessage('Der PDF-Export ist für die aktuelle Nachricht momentan nicht möglich.\n\nEs wurden bisher keine Favoriten gesetzt.\n\nEntweder Sie versuchen, die Faviten zu exportieren oder unter "Optionen" wurde festgelegt, dass lediglich Favoriten exportiert werden sollen.\n\nBitte fügen Sie den Favoriten Dateien hinzu oder passen Sie die Exporteinstellungen an.')
            return
        # Hole Export-Dateinamen vom Benutzer
        exportFilename, extension = QFileDialog.getSaveFileName(
            self,
            "Zieldatei wählen",
            self.settings_manager.get_string("defaultFolder", str(self.homedir)),
            "PDF-Dateien (*.pdf *.PDF)"
        )

        if not exportFilename:
            return

        if not exportFilename.lower().endswith('.pdf'):
            exportFilename = exportFilename + '.pdf'

        # Konfiguriere Export-Einstellungen
        config = PDFExportConfig(
            include_cover_page=self.actionDeckblattBeiExport.isChecked(),
            include_favorites_only=self.actionNurFavoritenExportieren.isChecked(),
            include_favorites_section=self.actionFavoritenExportieren.isChecked() and tableWidget != self.favTableView,
            include_file_dates=self.actionDateidatumExportieren.isChecked(),
            open_after_export=self.actionPDFnachExportOeffnen.isChecked(),
            font_dir=self.fontDir,
        )

        # Definiere Deckblatt-Ersteller-Callback
        # Hinweis: cover_path ist der vollständige Pfad zur Ausgabedatei, nicht nur ein Verzeichnis
        def create_cover_page(cover_path: str) -> str:
            return CreateDeckblatt(self).output(cover_path)

        # Definiere Status-Callback
        def status_callback(message: str):
            self.statusBar.showMessage(message)
            self.statusBar.repaint()

        try:
            self.app.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

            # Delegate to pdf_operations module
            success, not_supported = export_pdf(
                table_widget=tableWidget,
                base_dir=self.basedir,
                export_filename=exportFilename,
                config=config,
                favorites=self.favorites,
                cover_page_creator=create_cover_page if config.include_cover_page else None,
                status_callback=status_callback,
            )

            self.app.restoreOverrideCursor()

            # Zeige Ergebnisse an
            if success:
                if len(not_supported) != 0:
                    msgText = 'Nicht alle in der Tabelle "Dateien" angezeigten Dokumente konnten nach PDF konvertiert werden.\n\nEntweder wird ein externes Programm zur Konvertierung benötigt, es handelt sich nicht um Text- bzw. Bilddateien, die Dateien konnten nicht gefunden werden oder sind verschlüsselt.\n\nFolgende Dateien wurden daher nicht exportiert:\n'
                    for item in not_supported:
                        msgText += str(item) + "\n"
                    msgText +='\nKonvertierte Dateien können von ihren Originalen abweichen und Informationen verlieren!\n\nVerbindlich sind ausschließlich die Originaldateien!'    
                else:
                    msgText = 'Alle in der Tabelle "Dateien" angezeigten Dokumente\n(ggf. mit Ausnahme von Signaturdateien) wurden erfolgreich exportiert. Zum Ändern der Auswahl Filter setzen oder anderen "Inhalt" auswählen.\n\nKonvertierte Dateien können von ihren Originalen abweichen und Informationen verlieren!\n\nVerbindlich sind ausschließlich die Originaldateien.'

                self.statusBar.showMessage('PDF-Export abgeschlossen.')
                self.__displayMessage(msgText)

                if config.open_after_export:
                    self.__openFileExternal(exportFilename, ignoreWarnings=True, absolutePath=True)
            else:
                if self.actionNurFavoritenExportieren.isChecked():
                    self.__displayMessage('Der PDF-Export war nicht erfolgreich.\n\nUnter "Optionen" wurde festgelegt, dass von den unter "Dateien" sichtbaren Dateien lediglich Favoriten exportiert werden sollen.\n\nAlternativ kann es sein, dass die Dateiformate der gewählten Dateien nicht unterstützt werden oder die Dateien nicht gefunden werden konnten.')
                else:
                    self.__displayMessage('Es wurde keine PDF-Datei erstellt. Es werden keine Dateien angezeigt, die Dateiformate der gewählten Dateien werden nicht unterstützt oder die Dateien konnten nicht gefunden werden.')
                self.statusBar.showMessage('PDF-Export abgebrochen.')

        except PDFExportError as e:
            self.app.restoreOverrideCursor()
            msgText = 'Bei der Erzeugung der PDF-Datei ist ein Fehler aufgetreten.'
            self.statusBar.showMessage(msgText)
            self.__displayMessage(msgText, title='Fehler', icon=QMessageBox.Icon.Warning)
            self.lastExceptionString = str(e)
            self.__debugOutput('__exportPDF')

    def __notizPdfExport(self):
        """Exportiert die Notizen in eine PDF-Datei. Delegiert an pdf_operations."""
        notizenText = self.notizenText.toPlainText()

        if not notizenText:
            message = 'Es werden aktuell keine Notizen angezeigt, die exportiert werden könnten.'
            self.__displayMessage(message)
            self.statusBar.showMessage(message)
            return

        exportFilename, extension = QFileDialog.getSaveFileName(
            self,
            "Zieldatei wählen",
            self.settings_manager.get_string("defaultFolder", str(self.homedir)),
            "PDF-Dateien (*.pdf *.PDF)"
        )

        if exportFilename:
            try:
                if not exportFilename.lower().endswith('.pdf'):
                    exportFilename = exportFilename + '.pdf'

                self.app.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

                # Delegate to pdf_operations module
                export_notes_to_pdf(
                    notes_text=notizenText,
                    export_filename=exportFilename,
                    font_dir=self.fontDir,
                    title=Path(exportFilename).stem
                )

                self.app.restoreOverrideCursor()

                if self.actionPDFnachExportOeffnen.isChecked():
                    self.__openFileExternal(exportFilename, ignoreWarnings=True, absolutePath=True)

            except PDFExportError as e:
                self.app.restoreOverrideCursor()
                message = 'Das Speichern der Notizen ist fehlgeschlagen.'
                self.__displayMessage(message)
                self.lastExceptionString = str(e) + message
                self.statusBar.showMessage(message)
                self.__debugOutput('__notizPdfExport')

    # ========================================
    # ABSCHNITT 10: ANSICHTS-/UI-AKTUALISIERUNGSMETHODEN
    # ========================================
    def __setDocumentTable(self, akteID=None):      
       
        #Leere tableWidget
        self.docTableView.setRowCount(0)
        self.docTableView.setColumnCount(0)  
        
        data=[]
        if akteID == 'Alle_Dokumente':
            rows = self.akte.getFileRows()
            for singleID in self.akte.alleAktenIDs:
                rows.extend(self.akte.getFileRows(singleID))
        else:
            rows = self.akte.getFileRows(akteID)
        

        seen_filenames = set()
        
        #Sortiere Daten & füge Aktions-Icons hinzu
        for row in rows:
            
            # TODO: ggf. als Option anbieten. Filtert unter Umständen 
            # zu viele Dateien aus. Transfervermerke können sich z.B. 
            # mit unterschiedlichen Anzeigenamen und Veraktungsdaten
            # in der Akte befinden.
            #
            # Duplikate überspringen
            #if row['dateiname'] in seen_filenames:
            #    continue
            
            seen_filenames.add(row['dateiname'])

            rowData = []
            
            #Lesezeichen+ Icon, Extern-öffnen Icon in "Material Font"
            actionIcons= ['','']
            
            #Icons zuerst
            rowData+=actionIcons
            #Daten als zweites
            rowData+=self.__arrangeData(row, self.docTableAttributes)
            
            #add row
            data.append(rowData)
                   
        #set data
        if data:

            self.docTableView.setRowCount(len(data))
            self.docTableView.setColumnCount(len(data[0]))
            
            #Füge Spalten mit Icons für "Zu Favoriten hinzufügen" und "Extern öffnen" hinzu
            self.docTableView.setHorizontalHeaderItem(0, self.__tableItem('', self.buttonFont))
            if self.docHeaderColumnsSettings['']['width']:
                self.docTableView.setColumnWidth(0, self.docHeaderColumnsSettings['']['width'])
                self.docTableView.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            self.docTableView.setHorizontalHeaderItem(1,  self.__tableItem('', self.buttonFont))
            if self.docHeaderColumnsSettings['']['width']:
                self.docTableView.setColumnWidth(1, self.docHeaderColumnsSettings['']['width'])
                self.docTableView.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
            
            columnCount=2
            for item in self.docTableAttributes:
                headerText=self.docHeaderColumnsSettings[item]['headertext']
                self.docTableView.setHorizontalHeaderItem(columnCount, self.__tableItem(headerText, self.appFont))

                # set width to auto for items that have a width defined (due to option to adjust font size width is ignored)...
                if self.docHeaderColumnsSettings[item]['width']:
                    self.docTableView.horizontalHeader().setSectionResizeMode(columnCount, QHeaderView.ResizeMode.ResizeToContents)
            
                columnCount+=1
                
            rowNo=0
            self.isDocColumnEmpty={}
            for row in data:
                itemNo=0
                for item in row:
                    #Material Icons-Schriftart für erste zwei Spalten
                    if itemNo > 1:
                        font=self.appFont 
                        alignment = self.DocumentTableAlignment 
                    else: 
                        font=self.buttonFont
                        alignment = Qt.AlignmentFlag.AlignCenter

                    #Leading zeros fo '#'-Items that are not empty   
                    if itemNo==2 and item:
                        item=item.zfill(4) 
                           
                    tempItem=self.__tableItem(item, font)
                    tempItem.setTextAlignment(alignment)

                    if itemNo==0:
                        tempItem.setToolTip('Doppelklick fügt Datei den Favoriten hinzu.')
                    elif itemNo==1:
                        tempItem.setToolTip('Doppelklick öffnet Datei mit Standardprogramm.') 
                    
                    self.docTableView.setItem(rowNo, itemNo, tempItem) 
                    
                    #Set column to not empty (False) if item has content
                    #Set to empty (True) if value for column does not exist 
                    #or has any other value than False  
                    if item!='':
                        self.isDocColumnEmpty[itemNo]=False
                    elif self.isDocColumnEmpty.get(itemNo) != False:
                        self.isDocColumnEmpty[itemNo]=True                
                    itemNo+=1
                rowNo+=1
            self.__updateVisibleColumns()
            self.statusBar.showMessage('Der ausgewählte Inhalt enthält %s Dateien' % rowNo)
            
        else:
            self.statusBar.showMessage('Der ausgewählte Inhalt enthält keine Dateien')
            if self.actionAnwendungshinweise.isChecked():
                self.__informIfNoDocsVisible()  
    
    def __setTerminTable (self, termine):
        
        #Leere tableWidget
        self.termineTableView.setRowCount(0)
        self.termineTableView.setColumnCount(0)  
        self.isTerminColumnEmpty={}
        
        self.terminTableColumnsHeader=[
            'UUID',
            'Datum',
            'Zeit',
            'Öffent-\nlich',
            'Haupt- oder\nFolgetermin',
            'Terminsart',
            'Spruchkörper'
        ]
        
        if len(termine):
            self.termineTableView.setRowCount(len(termine))
            self.termineTableView.setColumnCount(7) 
            
            #set header
            self.termineTableView.horizontalHeader().setStretchLastSection(True)
            self.termineTableView.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.termineTableView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
                                                     
            columnCount=0
            for item in self.terminTableColumnsHeader:
                headerItem=self.__tableItem(item, self.appFont)
                headerItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setHorizontalHeaderItem(columnCount, headerItem)
                columnCount+=1
            #add rows
            rowNo=0    
            
            for termin in termine:
                
                tempItem=self.__tableItem(termin['uuid'], self.appFont)
                self.termineTableView.setItem(rowNo, 0, tempItem)    
                
                datum=zeit=termin['terminszeit']['terminsdatum']
                tempItem=self.__tableItem(datum, self.appFont)
                tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setItem(rowNo, 1, tempItem)
                
                zeit=termin['terminszeit']['auswahl_terminszeit']['terminsuhrzeit'] + termin['terminszeit']['auswahl_terminszeit']['terminszeitangabe']
                tempItem=self.__tableItem(zeit, self.appFont)
                tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setItem(rowNo, 2, tempItem)
                
                oeffentlich=self.__replaceTrueFalse(termin['oeffentlich'])
                tempItem=self.__tableItem(oeffentlich, self.appFont)
                tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setItem(rowNo, 3, tempItem)
                
                if termin.get('hauptterminsdatum') or termin.get('terminskategorie')=='Fortsetzungstermin':
                    terminTyp='Fortsetzung'
                elif termin.get('terminskategorie')=='Umladung':
                    terminTyp='Umladung'
                else:
                    terminTyp='Haupttermin'
                tempItem=self.__tableItem(terminTyp, self.appFont)
                tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setItem(rowNo, 4, tempItem)
                
                terminsart=termin['terminsart']
                tempItem=self.__tableItem(terminsart, self.appFont)
                tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setItem(rowNo, 5, tempItem)
                
                spruchkoerper=termin['spruchkoerper']
                tempItem=self.__tableItem(spruchkoerper, self.appFont)
                tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setItem(rowNo, 6, tempItem)
                
                rowNo+=1
                           
            self.termineTableView.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            self.termineTableView.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    
            self.termineTableView.setColumnWidth(3,40)
            self.termineTableView.setColumnWidth(4,115)
            self.termineTableView.sortItems(1)
            self.termineTableView.hideColumn(0)
            self.termineTableView.clearSelection()   

    def __setInstanzenView(self):
        try:
            if self.akte.erweiterungen.get('openXJV_instanzdaten_klartext'):         
                self.beteiligteText.setPlainText(self.akte.erweiterungen['openXJV_instanzdaten_klartext']['text'])
                return
        except AttributeError:
            pass
        
        text=TextObject()
        singleValues=[        
            ['abteilung','<b>Abteilung:</b> %s<br>'],
            ['kurzrubrum','<b>Kurzrubrum:</b> %s<br>'],
            ['verfahrensinstanznummer','<b>Verfahrensinstanznummer:</b> %s<br>'],
            ['sachgebiet','<b>Sachgebiet:</b> %s<br>'],
            ['sachgebietszusatz','<b>Sachgebietszusatz:</b> %s<br>']     
        ]
                
        if self.akte.grunddaten.get('verfahrensnummer'):
            text.add_line('<b><i>Verfahrensnummer</i></b>', self.akte.grunddaten['verfahrensnummer'])
            
        keys=list(self.akte.grunddaten['instanzen'].keys())
        for key in keys:
            instanz=self.akte.grunddaten['instanzen'][key]
            hr='_______________________________________<br><br>'
            text.add_raw("%s<b>Instanz %s</b><br>%s<b><i>Instanzdaten</i></b><br>" % (hr, key, hr))       
            if instanz.get('auswahl_instanzbehoerde'):
                text.add_line('<b>Behörde</b>', instanz['auswahl_instanzbehoerde'].get('name'))
            
            if instanz.get('aktenzeichen'):
                text.add_line('<b>Aktenzeichen</b>', instanz['aktenzeichen'].get('aktenzeichen.freitext'))      
                text.add_line('<b>Sammelvorgangsnummer</b>', instanz['aktenzeichen'].get('sammelvorgangsnummer'))
            
            for value in singleValues:
                if instanz.get(value[0]):
                    text.add_raw(value[1] % instanz[value[0]])
            
            for gegenstand in instanz['verfahrensgegenstand']:
                setBR=False
                if gegenstand.get('gegenstand'):
                   text.add_raw('<b>Gegenstand:</b> %s' % gegenstand['gegenstand'])
                   setBR=True
                if gegenstand.get('gegenstandswert').strip():
                   text.add_raw(', Streitwert: %s' % gegenstand['gegenstandswert'])
                   setBR=True
                if gegenstand.get('auswahl_zeitraumDesVerwaltungsaktes').strip():
                   text.add_raw(', Datum/Zeitraum: %s' % (gegenstand['auswahl_zeitraumDesVerwaltungsaktes']))   
                   setBR=True 
                if setBR:
                    text.add_raw('<br>')
            
            text.add_raw(self.display_renderer.render_telecommunications(instanz['telekommunikation']))
            
        self.instanzenText.setHtml(text.get_text())

    def __setBeteiligteView(self):
        """Lädt Beteiligtendaten in die Beteiligtenansicht. Wenn Daten als Klartext verfügbar sind in anwendungsspezifischen Erweiterungen, werden diese angezeigt."""
        try:
            if self.akte.erweiterungen.get('openXJV_beteiligung_klartext'):         
                self.beteiligteText.setPlainText(self.akte.erweiterungen['openXJV_beteiligung_klartext']['text'])
                return
        except AttributeError:
            pass
        
        text=TextObject()            
        for beteiligung in self.akte.grunddaten['beteiligung']:
            text.add_line('<b>Beteiligtennummer</b>', beteiligung.get('beteiligtennummer'))
            
            if beteiligung['rolle']:
                text.add_raw(self.display_renderer.render_roles(beteiligung['rolle']))
                
            beteiligter=beteiligung['beteiligter']
      
            beteiligtentyp=beteiligter.get('type')
            if beteiligtentyp=='GDS.Organisation':
                text.add_raw(self.display_renderer.render_organization(beteiligter))
            elif beteiligtentyp=='GDS.RA.Kanzlei':
                text.add_raw(self.display_renderer.render_law_office(beteiligter))
            elif beteiligtentyp=='GDS.NatuerlichePerson':
                text.add_raw(self.display_renderer.render_natural_person(beteiligter))
            text.add_raw('_______________________________________<br><br>')
           
        self.beteiligteText.setHtml(text.get_text())
       
    def __setInhaltView(self, schriftgutobjekte):
        """Aktualisiert die 'Inhalt' view."""
        treeModel = QStandardItemModel()
        rootNode = treeModel.invisibleRootItem()
        
        if (len(schriftgutobjekte['dokumente'])>0 or len(schriftgutobjekte['akten'])>0):
            alle_dokumente = StandardItem('Alle Inhalte anzeigen')
            alle_dokumente.setIcon(QIcon(os.path.join(self.scriptRoot, 'icons', 'double_arrow_down_icon.png')))
            alle_key       = StandardItem('Alle_Dokumente')
            rootNode.appendRow([alle_dokumente, alle_key])            
                
        if len(schriftgutobjekte['dokumente'])>0:
            dokumente = StandardItem('Einzeldokumente')
            dokumente.setIcon(QIcon(os.path.join(self.scriptRoot, 'icons', 'dokument_icon.png')))
            key       = StandardItem(None)
            rootNode.appendRow([dokumente, key])
        
        if len(schriftgutobjekte['akten'])>0:
            self.__getAktenSubBaum(schriftgutobjekte['akten'], rootNode) 
            
        self.inhaltView.setModel(treeModel)
        self.inhaltView.setColumnHidden(1, True)
        self.inhaltView.expandAll()
        self.inhaltView.setCurrentIndex(treeModel.index(0,0))
        # Verbinde neu nach jedem Laden / Setzen eines Models
        self.inhaltView.selectionModel().selectionChanged.connect(self.__updateSelectedInhalt)

    def __setFavorites(self):
        """Aktualisiert die Einträge in der Favoritenansicht und initiiert das Speichern der Werte."""
        # Ggf. angepasste Spaltenbreite auslesen, um sie nach Update der Ansicht wieder setzen zu können
        column_zero_width = self.favTableView.columnWidth(0)
        column_one_width = self.favTableView.columnWidth(1)
        
        self.favTableView.clear()
        self.favTableView.setRowCount(0)
        self.favTableView.setColumnCount(0) 
        rows = self.akte.getFileRows()
        for singleID in self.akte.alleAktenIDs:
            rows.extend(self.akte.getFileRows(singleID))

        data = []
        entries = []  # Parallel zu data: welcher FavoriteEntry gehört zu welcher Tabellenzeile

        for favorite in self.favorites:
            for row in rows:
                # TODO (Version 1.5+): Den Legacy-Zweig (not favorite.anzeigename) entfernen,
                # sobald keine Einträge mit anzeigename='' mehr vorkommen.
                # Dann nur noch exakten Match per (anzeigename, dateiname) verwenden.
                if favorite.anzeigename:
                    # Neues Format: exakter Abgleich per (anzeigename, dateiname)
                    if row['dateiname'] != favorite.filename or row['anzeigename'] != favorite.anzeigename:
                        continue
                else:
                    # Legacy-Abgleich: nur per Dateiname (anzeigename war bei Anlage unbekannt)
                    if row['dateiname'] != favorite.filename:
                        continue

                rowData = self.__arrangeData(row, ('anzeigename', 'dateiname', 'datumDesSchreibens', 'veraktungsdatum', 'dokumentklasse'))
                data.append(rowData)
                entries.append(favorite)
                break  # Pro Favorit-Eintrag nur die erste passende Zeile verwenden

        if data:
            self.favTableView.setRowCount(len(data))
            self.favTableView.setColumnCount(len(data[0]))

            self.favTableView.setHorizontalHeaderItem(0, self.__tableItem('Anzeigename', self.appFont))
            self.favTableView.setHorizontalHeaderItem(1, self.__tableItem('Dateiname', self.appFont))
            self.favTableView.setHorizontalHeaderItem(2, self.__tableItem('Datum', self.appFont))
            self.favTableView.setHorizontalHeaderItem(3, self.__tableItem('Veraktung', self.appFont))
            self.favTableView.setHorizontalHeaderItem(4, self.__tableItem('Klasse', self.appFont))
            self.favTableView.hideColumn(2)
            self.favTableView.hideColumn(3)
            self.favTableView.hideColumn(4)

            if column_zero_width:
                self.favTableView.setColumnWidth(0, column_zero_width)
            if column_one_width:
                self.favTableView.setColumnWidth(1, column_one_width)

            for rowNo, (row, entry) in enumerate(zip(data, entries)):
                for itemNo, item in enumerate(row):
                    tempItem = self.__tableItem(item, self.appFont)
                    tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.favTableView.setItem(rowNo, itemNo, tempItem)
                # FavoriteEntry als UserRole-Datum speichern; ermöglicht zuverlässiges
                # Wiederfinden des Eintrags bei Entfernen/Verschieben unabhängig vom Anzeigetext.
                col0 = self.favTableView.item(rowNo, 0)
                if col0 is not None:
                    col0.setData(Qt.ItemDataRole.UserRole, entry)
      
    def __setMetadata(self, nachricht, aktenID=None):
        
        text=TextObject(newline='\n')
        if aktenID is None or aktenID=='' or aktenID == 'Alle_Dokumente':
            
            if nachricht.nachricht.get('vertraulichkeit'):
                text.add_line('Vertraulichkeit / Geheimhaltung', nachricht.nachricht['vertraulichkeit'].get('vertraulichkeitsstufe'))
                text.add_line('Vertraulichkeitsgrund', nachricht.nachricht['vertraulichkeit'].get('vertraulichkeitsgrund'))
            
            labelList =[
                ['nachrichtenNummer','Nachricht Nr.'],
                ['nachrichtenAnzahl','Von Nachrichten gesamt'],
                ['ereignisse','Ereignis'],
                ['eigeneID','Abs. Nachr.-ID'],
                ['fremdeID','Empf. Nachr.-ID'],
                ['prozessID','Prozess-ID'],
                ['routingInformationAusSafe', 'Routinginformation'],
                ['produktName','Software'],
                ['produktHersteller','Hersteller'],
                ['produktVersion','Version'],
            ]
            for label in labelList:
                if nachricht.nachricht.get(label[0]):
                    text.add_line(label[1], nachricht.nachricht[label[0]])
        else:
            akte=nachricht.getAkte(nachricht.schriftgutobjekte['akten'], aktenID)    
    
            if akte:


                if akte.get('ruecksendungEEB.erforderlich'):                
                    eeb = 'Abgabe nicht erforderlich'
                    if akte['ruecksendungEEB.erforderlich'].lower() == 'true':
                        eeb = 'Abgabe angefordert'
                    text.add_line('EEB', eeb)
                
                if akte.get('hybridakte'):
                    text.add_line('Hybridakte', 'Teile der elektronischen Akte liegen in Papierform vor')    

                for aktenzeichen in akte['aktenzeichen']:
                    text.add_line('Aktenzeichen', aktenzeichen['aktenzeichen.freitext'])
            
                for person in akte['personen']:
                    name=self.akte.beteiligtenverzeichnis.get(person)
                    if name:
                        text.add_line('Personenbezug', name)
                
                for referenz in akte['aktenreferenzen']:
                    text.add_line('ReferenzaktenID ('+referenz['aktenreferenzart']+')', referenz['id.referenzierteAkte'])
                    
                labelList =[
                ['anzeigename','Anzeigename'],    
                ['aktentyp','Aktentyp'],
                ['teilaktentyp','Teilaktentyp'],
                ['id','Akten-ID'],
                ['weiteresOrdnungskriteriumBehoerde','Weiteres Ordnungskriterium'],              
                ['abgebendeStelle','Abgebende Stelle'], 
                ['letztePaginierungProTeilakte', 'Letzte Paginierung'],
                ['erstellungszeitpunktAkteVersand','Erstellungszeitpunkt'], 
                        
                ]
            for label in labelList:
                text.add_line(label[1], akte[label[0]])
            
            if akte.get('vertraulichkeitsstufe'):
                text.add_line('Vertraulichkeitsstufe', akte['vertraulichkeitsstufe'])    

            if akte.get('vertraulichkeit'):
                text.add_raw(akte['vertraulichkeit'] + "\n")

            if akte.get('laufzeit'):
                text.add_line('Laufzeit ab', akte['laufzeit'].get('beginn'))        
                text.add_line('Laufzeit bis', akte['laufzeit'].get('ende'))
            
            if akte.get('justizinterneDaten'):
                if akte.get('roemischPaginiert'):
                    text.add_line('Römisch Paginiert',  self.__replaceTrueFalse(akte['justizinterneDaten']['roemischPaginiert']))
                    
            if akte['zustellung41StPO'].lower() == 'true':
                text.add_line('Zustellung gem. §41StPO', 'ja')        
            elif akte['zustellung41StPO'].lower() == 'false':    
                text.add_line('Zustellung gem. §41StPO', 'nein')
                
            if akte.get('uebergabeAktenfuehrungsbefugnis') == 'true':
                text.add_line('Übergabe der Aktenführungsbefugnis', 'erteilt')     
           
        self.metadatenText.setPlainText(text.get_text())
                        
    def __setNachrichtenkopf (self, absender, empfaenger, nachrichtenkopf):
        """Setzt Inhalte der Nachrichtenkopf-Box."""
        self.absenderText.setText(absender['name'])
        self.absenderAktenzeichenText.setText(absender['aktenzeichen'])
        self.empfaengerText.setText(empfaenger['name'])
        self.empfaengerAktenzeichenText.setText(empfaenger['aktenzeichen'])
        self.erstellungszeitpunktText.setText(nachrichtenkopf['erstellungszeitpunkt'])
        self.sendungsprioritaetText.setText(self.__isSet(nachrichtenkopf['sendungsprioritaet']))
               
        ###Cursor auf erstes Zeichen setzen###
        self.absenderText.setCursorPosition(0)
        self.absenderAktenzeichenText.setCursorPosition(0)
        self.empfaengerText.setCursorPosition(0)
        self.empfaengerAktenzeichenText.setCursorPosition(0)
                
    def __setTerminDetailView(self, val):
        text=''
        uuid=self.termineTableView.item( val.row(), 0).text()
        for termin in self.akte.termine:
            if termin['uuid']==uuid:
                text+=self.display_renderer.render_appointment(termin)

        self.terminDetailView.setHtml(text) 
         
    def __loadEmptyViewer(self, unknown = None):
        """Lädt einen leeren Viewer in das Vorschaufenster."""

        self.loadedPDFfilename=''
        self.loadedPDFpath=''

        viewer_mode = self.settings_manager.get_pdf_viewer()

        if viewer_mode == 'PDFjs':
            # show_blank_page() behandelt ungespeicherte Annotationen intern.
            self.pdf_viewer.show_blank_page()
        ''' TODO: In späterer Version entfernen
        else:
            # Für Chromium/Native-Modi: Lade HTML-Leerseite
            urlPath = self.scriptRoot.replace("\\","/")
            winslash = '/' if sys.platform.lower().startswith('win') else ''
            blankPage = "file://%s%s/html/blank/blank.html" % (winslash, urlPath)

            self.url = blankPage

            separators = ('?','&')
            req_strings = []
            if darkdetect.isDark():
                req_strings.append('darkmode=True')

            if unknown:
                req_strings.append('unknown=True')

            for req, no in zip(req_strings, range(len(req_strings))):
                self.url += f'{separators[no]}{req}'

            self.browser.setUrl(QUrl.fromUserInput(self.url))
        '''
              
    def __updateSelectedInhalt(self):
        val = self.inhaltView.currentIndex() 
        akte = self.akte 
    
        aktenID=val.siblingAtColumn(val.column()+1).data()
        self.__setMetadata(akte, aktenID)
        self.__setDocumentTable(aktenID)
        self.__filtersTriggered()   
   
    def __updateVisibleColumns(self):
        for columnNo in range(self.docTableView.columnCount()):
            self.docTableView.setColumnHidden(columnNo, False)
        
        columnNo=2
        for attribute in self.docTableAttributes:
            if self.docHeaderColumnsSettings[attribute]['setting']:
               self.docTableView.setColumnHidden(columnNo, not self.docHeaderColumnsSettings[attribute]['setting'].isChecked())     
            columnNo+=1  
        
        if self.actionLeereSpaltenAusblenden.isChecked():       
            self.__hideEmptyColumns() 

    def __hideEmptyColumns(self):
        """Blendet leere Spalten aus."""
        for columnNo, isEmpty in self.isDocColumnEmpty.items():
            if isEmpty:
                self.docTableView.setColumnHidden(columnNo, True)       
              
    def __updateVisibleViews(self):
        self.nachrichtenkopf.setVisible(self.actionNachrichtenkopf.isChecked())
        self.favoriten.setVisible(self.actionFavoriten.isChecked())
        self.metadaten.setVisible(self.actionMetadaten.isChecked())
        self.notizen.setVisible(self.actionNotizen.isChecked())
        
        # Suche
        self.fakeSpacer.setVisible(self.actionSucheAnzeigen.isChecked())
        self.suchbegriffeText.setVisible(self.actionSucheAnzeigen.isChecked())
                         
    def __updateDoctableViewOrientation(self):
        """Setzt die horizontale Ausrichtung der Dateitabelle."""
        if self.actionDateitabelleLinksbuendig.isChecked():
            alignment = Qt.AlignLeft | Qt.AlignVCenter      
        else:
            alignment = Qt.AlignmentFlag.AlignCenter    
        
        self.DocumentTableAlignment = alignment
        
        try:            
            self.__updateSelectedInhalt()
        except:
            pass

    def __checkFiltersAndRows(self):
        if self.actionAnwendungshinweise.isChecked():
                self.__informIfFiltersSet()           
                if self.docTableView.rowCount() == 0: 
                    self.__informIfNoDocsVisible()        
           
    def __informIfNoDocsVisible(self):
        """Überprüft, ob Dokumente angezeigt werden und gibt einen Hinweis aus."""
        if not self.docTableView.rowCount():
             self.__displayMessage("Es werden aktuell keine Dateien angezeigt, da der ausgewählte Inhalt keine Dateien enthält.\n\nBitte wählen Sie einen anzuzeigenden Inhalt in der Box 'Inhalt' durch Anklicken aus.\n\n(Anwendungshinweise können unter 'Optionen' ausgeschaltet werden.", "Anwendungshinweis", modal=False)
   
    def __informIfFiltersSet(self):
        """Überprüft, ob Filterbegriffe gesetzt wurden und informiert per Pop-up."""
        minusFilterText=self.minusFilter.text().replace(" ","")

        #Ausnahme für Filter für technische Dateien
        for extension in [".pks",".p7s",".xml",".pkcs7"]:
            minusFilterText=minusFilterText.replace(extension, "")

        if minusFilterText or self.plusFilter.text():
            self.__displayMessage("Es sind eigene Filterbegriffe gesetzt.\n\nDaher werden ggf. nicht alle Dokumente angezeigt.\nBei Bedarf den Button 'Filter leeren' anklicken, um die Filter zu löschen.\n\n(Anwendungshinweise können unter 'Optionen' ausgeschaltet werden.)", "Anwendungshinweis", modal=False)

    def __setFontsizes(self, appFontsize=15, buttonFontSize=17, iconFontSize=24,
                       appFontWeight=QFont.Weight.Normal):
        """Setzt Schriftarten in Punktgrößen basierend auf der aktuellen Bildschirm‑DPI."""

        # Hole den Bildschirm, auf dem dieses Fenster angezeigt wird
        screen = self.window().screen() if self.window() else QApplication.primaryScreen()
        dpi = screen.logicalDotsPerInch() if screen else 96  # Fallback

        def px_to_pt(px):
            return px * 72.0 / dpi

        # Konvertiere zu Punktgrößen
        self.iconFont.setPointSizeF(px_to_pt(iconFontSize))
        self.buttonFont.setPointSizeF(px_to_pt(buttonFontSize))
        self.appFont.setPointSizeF(px_to_pt(appFontsize))
        self.appFont.setWeight(appFontWeight)

        # Wende auf Fenster und App an
        self.setFont(self.appFont)
        QApplication.instance().setFont(self.appFont)

        # Aktualisiere docTableView
        docTableRows = self.docTableView.rowCount()
        docTableColumns = self.docTableView.columnCount()
        if docTableRows > 0 and docTableColumns > 0:
            for column in range(docTableColumns):
                font = self.appFont if column > 1 else self.buttonFont
                item = self.docTableView.horizontalHeaderItem(column)
                if item:
                    item.setFont(font)
            for row in range(docTableRows):
                for column in range(docTableColumns):
                    font = self.appFont if column > 1 else self.buttonFont
                    item = self.docTableView.item(row, column)
                    if item:
                        item.setFont(font)

        # Aktualisiere termineTableView
        termineTableRows = self.termineTableView.rowCount()
        termineTableColumns = self.termineTableView.columnCount()
        if termineTableRows > 0 and termineTableColumns > 0:
            for column in range(termineTableColumns):
                item = self.termineTableView.horizontalHeaderItem(column)
                if item:
                    item.setFont(self.appFont)
            for row in range(termineTableRows):
                for column in range(termineTableColumns):
                    item = self.termineTableView.item(row, column)
                    if item:
                        item.setFont(self.appFont)

        # Aktualisiere favTableView
        favTableRows = self.favTableView.rowCount()
        favTableColumns = self.favTableView.columnCount()
        if favTableRows > 0 and favTableColumns > 0:
            for column in range(favTableColumns):
                item = self.favTableView.horizontalHeaderItem(column)
                if item:
                    item.setFont(self.appFont)
            for row in range(favTableRows):
                for column in range(favTableColumns):
                    item = self.favTableView.item(row, column)
                    if item:
                        item.setFont(self.appFont)

        # Aktualisiere andere Widgets
        self.deleteFavoriteButton.setFont(self.buttonFont)
        self.filterMagic.setFont(self.buttonFont)
        self.toolBar.setFont(self.iconFont)

    def __toggleFontsizes(self):
        """Schaltet die Schriftgröße für Anwendung und Schaltflächen um."""
        if self.actionGrosse_Schrift.isChecked():
            self.__setFontsizes(appFontsize=20, buttonFontSize=20, iconFontSize=28)
        else:
            self.__setFontsizes()           
 
 
    def __resetAll(self):
        self.__saveNotes() 
        self.settings.sync()
        widgets = (self.termineTableView,
                   self.terminDetailView,
                   self.instanzenText,
                   self.beteiligteText,    
                   self.metadatenText,
                   self.favTableView,
                   self.docTableView,
                   self.suchbegriffeText,
                   self.absenderText,
                   self.empfaengerText,
                   self.erstellungszeitpunktText,
                   self.absenderAktenzeichenText,
                   self.empfaengerAktenzeichenText,
                   self.sendungsprioritaetText,
                   self.notizenText
        )
        for widget in widgets:
            widget.clear()
        self.inhaltView.setModel(QStandardItemModel())
        
        table_widgets = (self.termineTableView,
                         self.favTableView,
                         self.docTableView,                                 
        )
        
        for table in table_widgets:
            table.setRowCount(0)
            table.setColumnCount(0)  
            
        self.loadedPDFfilename = ''
        self.loadedPDFpath = ''
        self.favorites = []
        self.searchStore = {}
        self.akte = {}    
        self.__loadEmptyViewer()

    # ========================================
    # ABSCHNITT 11: EINSTELLUNGSVERWALTUNG
    # ========================================    
    def __readSettings(self):
        for key, value in self.docHeaderColumnsSettings.items(): 
            if value['setting']:
                setTo = str(self.settings_manager.get_string(key, 'default'))
                if setTo.lower() == "true":
                    value['setting'].setChecked(True)
                elif setTo.lower() == "false":
                    value['setting'].setChecked(False)
                else:
                    value['setting'].setChecked(self.docHeaderColumnsSettings[key]['default'])
                         
        self.actionNachrichtenkopf.setChecked            (self.settings_manager.get_bool('nachrichtenkopf'))
        self.actionFavoriten.setChecked                  (self.settings_manager.get_bool('favoriten'))
        self.actionMetadaten.setChecked                  (self.settings_manager.get_bool('metadaten'))
        self.actionNotizen.setChecked                    (self.settings_manager.get_bool('notizen'))
        self.actionLeereSpaltenAusblenden.setChecked     (self.settings_manager.get_bool('leereSpalten'))
        self.actionChromium.setChecked                   (self.settings_manager.get_pdf_viewer() == 'chromium') #TODO: In späterer Version entfernen
        self.actionnativ.setChecked                      (self.settings_manager.get_pdf_viewer() == 'nativ')
        self.actionGrosse_Schrift.setChecked             (self.settings_manager.get_bool('grosseSchrift'))
        self.actionAnwendungshinweise.setChecked         (self.settings_manager.get_bool('anwendungshinweise'))
        self.actionOnlineAufUpdatesPruefen.setChecked    (self.settings_manager.get_bool('checkUpdates'))
        self.actionDeckblattBeiExport.setChecked         (self.settings_manager.get_bool('deckblatt'))
        self.actionDateidatumExportieren.setChecked      (self.settings_manager.get_bool('dateidatumExportieren'))
        self.actionFavoritenExportieren.setChecked       (self.settings_manager.get_bool('favoritenExportieren'))
        self.actionNurFavoritenExportieren.setChecked    (self.settings_manager.get_bool('nurFavoritenExportieren'))
        self.actionPDFnachExportOeffnen.setChecked       (self.settings_manager.get_bool('PDFnachExportOeffnen'))
        self.actionNotizenaufDeckblattausgeben.setChecked(self.settings_manager.get_bool('NotizenaufDeckblatt'))
        self.actionSucheAnzeigen.setChecked              (self.settings_manager.get_bool('sucheAnzeigen'))
        self.actionDateitabelleLinksbuendig.setChecked   (self.settings_manager.get_bool('dateiansichtLinksbuendig'))

        # Annotationseinstellungen wiederherstellen.
        # Ist der Key nicht vorhanden (Neuinstallation / nach Migration), gilt 'auto_save' als Default.
        if self.settings_manager.settings.contains('annotationAction'):
            saved_annotation = self.settings_manager.get_string('annotationAction', 'auto_save')
        else:
            saved_annotation = 'auto_save'
        self.actionAktion_erfragen.setChecked(saved_annotation == 'prompt')
        self.actionAutomatisch_speichern.setChecked(saved_annotation == 'auto_save')
        self.actionVerwerfen.setChecked(saved_annotation == 'disabled' or saved_annotation == 'default')

        self.__updateDoctableViewOrientation()
        self.__viewerSwitch()
        self.__annotationSettingsSwitch()
        self.__updateVisibleViews()
        self.__toggleFontsizes()
        
    def __updateSettings(self):
        for key, value in self.docHeaderColumnsSettings.items():
            if value['setting']:
                self.settings_manager.set_value(key, value['setting'].isChecked())
        self.settings_manager.set_value('nachrichtenkopf', self.actionNachrichtenkopf.isChecked())
        self.settings_manager.set_value('favoriten', self.actionFavoriten.isChecked())
        self.settings_manager.set_value('metadaten', self.actionMetadaten.isChecked())
        self.settings_manager.set_value('notizen', self.actionNotizen.isChecked())
        self.settings_manager.set_value('leereSpalten', self.actionLeereSpaltenAusblenden.isChecked())
        self.settings_manager.set_value('grosseSchrift', self.actionGrosse_Schrift.isChecked())
        self.settings_manager.set_value('anwendungshinweise', self.actionAnwendungshinweise.isChecked())
        self.settings_manager.set_value('deckblatt', self.actionDeckblattBeiExport.isChecked())
        self.settings_manager.set_value('dateidatumExportieren', self.actionDateidatumExportieren.isChecked())
        self.settings_manager.set_value('favoritenExportieren', self.actionFavoritenExportieren.isChecked())
        self.settings_manager.set_value('nurFavoritenExportieren', self.actionNurFavoritenExportieren.isChecked())
        self.settings_manager.set_value('PDFnachExportOeffnen', self.actionPDFnachExportOeffnen.isChecked())
        self.settings_manager.set_value('NotizenaufDeckblatt', self.actionNotizenaufDeckblattausgeben.isChecked())
        self.settings_manager.set_value('sucheAnzeigen', self.actionSucheAnzeigen.isChecked())
        self.settings_manager.set_value('dateiansichtLinksbuendig', self.actionDateitabelleLinksbuendig.isChecked())

        if self.actionChromium.isChecked(): #TODO: In späterer Version entfernen
            self.settings_manager.set_pdf_viewer('chromium')
        elif self.actionnativ.isChecked():
            self.settings_manager.set_pdf_viewer('nativ')
        else:
            self.settings_manager.set_pdf_viewer('PDFjs')

        self.settings_manager.set_value('checkUpdates', self.actionOnlineAufUpdatesPruefen.isChecked())
        self.settings_manager.set_value('annotationAction', self.__getAnnotationAction())

        self.__updateDoctableViewOrientation() 
        self.__updateVisibleColumns()
        self.__updateVisibleViews()
        self.__prepareSearchStore(reset_searchStore=False)
        self.__toggleFontsizes()
   
    def __resetSettings(self):
        """Setzt Spalten und Anzeigeoptionen auf die Standardwerte zurück."""
        for key, value in self.docHeaderColumnsSettings.items():
            if value['setting']:
                value['setting'].setChecked(self.docHeaderColumnsSettings[key]['default'])
        self.actionNachrichtenkopf.setChecked       (True)
        self.actionFavoriten.setChecked             (True)
        self.actionMetadaten.setChecked             (False)
        self.actionNotizen.setChecked               (False)
        self.actionLeereSpaltenAusblenden.setChecked(True)  
        self.actionPDF_js.setChecked                (True)
        self.actionVerwerfen.setChecked(False)
        self.actionAktion_erfragen.setChecked(False)
        self.actionAutomatisch_speichern.setChecked(True)
        self.__viewerSwitch()
        self.__annotationSettingsSwitch()
        self.__updateSettings()
         
    def __viewerSwitch(self):
        """Activiert/Deaktiviert viewer selection options je nach ausgelöstem Ereignis."""
        #TODO: Chromium in späterer Version entfernen
        if self.actionChromium.isChecked() and self.actionChromium.isEnabled():
            self.actionChromium.setEnabled(False)
            self.actionPDF_js.setChecked(False)
            self.actionPDF_js.setEnabled(True)
            self.actionnativ.setChecked(False)
            self.actionnativ.setEnabled(True)
            self.pdf_viewer.setVisible(True)

        elif self.actionnativ.isChecked() and self.actionnativ.isEnabled():
            self.actionnativ.setEnabled(False)
            self.actionPDF_js.setChecked(False)
            self.actionPDF_js.setEnabled(True)
            self.actionChromium.setChecked(False) #TODO: In späterer Version entfernen
            self.actionChromium.setEnabled(True) #TODO: In späterer Version entfernen
            # Load blank page to handle unsaved annotations before hiding
            self.pdf_viewer.show_blank_page()
            self.pdf_viewer.setVisible(False)

        else:
            self.actionPDF_js.setChecked(True)
            self.actionPDF_js.setEnabled(False)
            self.actionChromium.setChecked(False) #TODO: In späterer Version entfernen
            self.actionChromium.setEnabled(True) #TODO: In späterer Version entfernen
            self.actionnativ.setChecked(False)
            self.actionnativ.setEnabled(True)
            self.pdf_viewer.setVisible(True)

        self.__updateSettings()

    def __getAnnotationAction(self) -> str:
        """Gibt die aktuelle Annotationseinstellung als String zurueck."""
        if self.actionAktion_erfragen.isChecked():
            return "prompt"
        elif self.actionAutomatisch_speichern.isChecked():
            return "auto_save"
        return "disabled"

    def __annotationSettingsSwitch(self):
        """Setzt die Annotationseinstellungen (nur eine Option aktiv)."""
        if self.actionAktion_erfragen.isChecked() and self.actionAktion_erfragen.isEnabled():
            self.actionAktion_erfragen.setEnabled(False)
            self.actionAutomatisch_speichern.setChecked(False)
            self.actionAutomatisch_speichern.setEnabled(True)
            self.actionVerwerfen.setChecked(False)
            self.actionVerwerfen.setEnabled(True)

        elif self.actionAutomatisch_speichern.isChecked() and self.actionAutomatisch_speichern.isEnabled():
            self.actionAutomatisch_speichern.setEnabled(False)
            self.actionAktion_erfragen.setChecked(False)
            self.actionAktion_erfragen.setEnabled(True)
            self.actionVerwerfen.setChecked(False)
            self.actionVerwerfen.setEnabled(True)

        else:
            self.actionVerwerfen.setChecked(True)
            self.actionVerwerfen.setEnabled(False)
            self.actionAktion_erfragen.setChecked(False)
            self.actionAktion_erfragen.setEnabled(True)
            self.actionAutomatisch_speichern.setChecked(False)
            self.actionAutomatisch_speichern.setEnabled(True)

        # EXPERIMENTAL: Direkter Zugriff auf self.pdf_viewer.backend.config.features.unsaved_changes_action
        # DIES VERWENDET NICHT DIE DOKUMENTIERTE API VON pdfjs-viewer-pyside6.
        # DER BACKEND LIEST DIESEN WERT LAZY IN handle_unsaved_changes().
        # KANN BEI AENDERUNGEN AM PACKAGE-BACKEND BRECHEN.
        action = self.__getAnnotationAction()
        self.pdf_viewer.backend.config.features.unsaved_changes_action = action

        self.__updateSettings()

    def __checkAllColumns(self):
        """Setzt das Häkchen in den Anzeigeoptionen für alle Spalten."""
        for key, value in self.docHeaderColumnsSettings.items():
            if value['setting']:
                value['setting'].setChecked(True)       
        self.__updateSettings()
        
    def __uncheckAllColumns(self):
        """Entfernt das Häkchen in den Anzeigeoptionen für alle Spalten."""
        for key, value in self.docHeaderColumnsSettings.items():
            if value['setting']:
                value['setting'].setChecked(False)       
        self.__updateSettings()

    def __chooseStartFolder(self):
        """Öffnet Dialog zum Festlegen eines Standardverzeichnisses. Delegiert an FileManager."""
        # Delegiert Ordnerauswahl an FileManager
        folder = self.file_manager.select_folder_dialog(title="Standardverzeichnis wählen")

        if folder:
            self.settings_manager.set_value("defaultFolder", folder)
          
    # ========================================
    # ABSCHNITT 12: EVENT-HANDLER
    # ========================================
    def __openAllFavsExternalAction(self, extension = None):
        """Öffnet alle Favoriten gleichzeitig in externen Standardprogrammen."""
        if self.favTableView.rowCount():
            for row_no in range(self.favTableView.rowCount()):
                filename = self.favTableView.item(row_no,1).text() 
                if extension and not filename.lower().endswith(extension):
                    if os.path.exists(os.path.join(self.basedir, filename + extension)):
                        filename = filename + extension                     
                    else:
                        continue    
                self.__openFileExternal(filename)
        
    def __showDocsContextMenu(self, pos):
        """Fügt Kontextmenü zur Dokmentsnansicht nd zeigt es an.."""
        contextMenu = QMenu(self)

        # Menüoptionen hinzufügen
        addDocToFavoritesAction = contextMenu.addAction("Auswahl zu Favoriten hinzufügen (Einfg)")
        addDocToFavoritesAction.triggered.connect(self.__addDocToFavorites)

        addAllDocsToFavoritesAction = contextMenu.addAction("Alle Angezeigten zu Favoriten hinzufügen")
        addAllDocsToFavoritesAction.triggered.connect(self.__addAllDocsToFavorites)

        delDocsFromFavoritesAction = contextMenu.addAction("Auswahl aus Favoriten entfernen (Entf)")
        delDocsFromFavoritesAction.triggered.connect(self.__removeFavorite)
        
        openDocExternalAction = contextMenu.addAction("Auswahl extern öffnen")
        openDocExternalAction.triggered.connect(self.__openDocExternal)
        
        # Kontextmenü anzeigen
        contextMenu.exec(self.docTableView.mapToGlobal(pos))
          
    def __showFavContextMenu(self, pos):
        """Fügt Kontextmenü zur Favoritenansicht hinzu und zeigt es an."""
        contextMenu = QMenu(self)

        # Menüoptionen hinzufügen
        moveFavUpAction = contextMenu.addAction("Nach oben verschieben (Strg + Pfeiltaste 'hoch')")
        moveFavUpAction.triggered.connect(lambda:self.__moveFav('up'))

        moveFavDownAction = contextMenu.addAction("Nach unten verschieben (Strg + Pfeiltaste 'runter')")
        moveFavDownAction.triggered.connect(lambda:self.__moveFav('down'))
        
        # Horizontaler Strich (Spacer) hinzufügen
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setLineWidth(1)  # Optional: Setzen Sie die Linienbreite

        contextMenu.addSeparator()  # Fügt horizontalen Strich hinzu
        
        openFavExternalAction = contextMenu.addAction("Auswahl extern öffnen")
        openFavExternalAction.triggered.connect(self.__getDClickFavoriteViewAction)
        
        openAllPdfFavsExternalAction = contextMenu.addAction("Alle PDF-Dateien extern öffnen")
        openAllPdfFavsExternalAction.triggered.connect(lambda:self.__openAllFavsExternalAction('.pdf'))
        
        openAllFavsExternalAction = contextMenu.addAction("Alle Dateien extern öffnen")
        openAllFavsExternalAction.triggered.connect(self.__openAllFavsExternalAction)
        
        contextMenu.addSeparator()  # Fügt horizontalen Strich hinzu
        
        removeFavoriteAction = contextMenu.addAction("Markierten Eintrag entfernen (Entf)")
        removeFavoriteAction.triggered.connect(self.__removeFavorite)
        
        delAllFavoritesAction = contextMenu.addAction("Alle Favoriten entfernen")
        delAllFavoritesAction.triggered.connect(self.__delAllFavorites)
        
        # Kontextmenü anzeigen
        contextMenu.exec(self.favTableView.mapToGlobal(pos))
        
    def __dClickDocTableAction(self, val):
        filenameColumn = self.docTableAttributes.index('dateiname') + 2
        fn_item = self.docTableView.item(val.row(), filenameColumn)
        if fn_item is None:
            return
        filename = fn_item.text()

        if val.column() == 0:
            anzeigenameColumn = self.docTableAttributes.index('anzeigename') + 2
            az_item = self.docTableView.item(val.row(), anzeigenameColumn)
            anzeigename = az_item.text() if az_item is not None else ''
            self.__addFavorite(filename, anzeigename)
        elif self.settings_manager.get_pdf_viewer() == 'nativ' or val.column() == 1 or not filename.lower().endswith(".pdf"):
            self.__openFileExternal(filename)
            
    def __browseDocTableAction (self, val):
        currentIndex=self.docTableView.currentIndex()

        if currentIndex.row() == -1:
            return
        filenameColumn=self.docTableAttributes.index('dateiname')+2
        filename=self.docTableView.item(currentIndex.row(), filenameColumn).text()

        self.__passFileToKILabor(os.path.join(self.basedir, filename))

        if self.settings_manager.get_pdf_viewer()!='nativ':
            supportedFiles=('.pdf','.jpg', '.jpeg', '.png', '.gif', '.txt', '.xml', '.html')
            # Prüfen, ob eine Vorschau-Datei im PDF-Format existiert,
            # falls sie als Viewer für exportierte Falldateien verwendet wird
            # sicherstellen, dass die Vorschau-Datei im Browser geladen wird
            if not filename.lower().endswith(supportedFiles):
                previewFilepath = os.path.join(self.basedir , filename + '.pdf')
                if os.path.exists(previewFilepath): 
                    filename = filename + '.pdf'
                
                elif filename.lower().endswith(('.tiff', '.tif')):
                    try:
                        with Image.open(os.path.join(self.basedir , filename)) as im:
                            convertedImage = os.path.join(self.tempDir.name , filename + '.png')
                            if not os.path.exists(convertedImage):
                                im.save (convertedImage, "PNG")
                    except Exception as e:
                        self.lastExceptionString = str(e)
                        self.statusBar.showMessage(f'Fehler beim Öffnen der Datei: {filename}')
                        return None
                    
                    filename = convertedImage
                        
            if filename.lower().endswith(supportedFiles):
                self.__openFileInBrowser(filename)
            else:
                self.__loadEmptyViewer(unknown = True) 
                self.statusBar.showMessage(f'Der Dateityp {Path(filename).suffix} ist zur Anzeige in der Vorschau nicht geeignet.')  

    def __getFavoriteViewAction (self, val):
        filename = self.favTableView.item(self.favTableView.currentRow(),1).text()

        if self.loadedPDFfilename == filename:
            return

        self.__passFileToKILabor(os.path.join(self.basedir, filename))

        if self.settings_manager.get_pdf_viewer()!='nativ':
            supportedFiles=('.pdf','.jpg', '.jpeg', '.png', '.gif', '.txt', '.xml', '.html')
            # Prüfen, ob eine Vorschau-Datei im PDF-Format existiert,
            # falls sie als Viewer für exportierte Falldateien verwendet wird
            # sicherstellen, dass die Vorschau-Datei im Browser geladen wird         
            if not filename.lower().endswith(supportedFiles):
                previewFilepath = os.path.join(self.basedir , filename + '.pdf')
                if os.path.exists(previewFilepath): 
                    filename = filename + '.pdf'

                elif filename.lower().endswith(('.tiff', 'tif')):
                    try:
                        with Image.open(os.path.join(self.basedir , filename)) as im:
                            convertedImage = os.path.join(self.tempDir.name , filename + '.png')
                            if not os.path.exists(convertedImage):
                                im.save (convertedImage, "PNG")
                    except Exception as e:
                        self.lastExceptionString = str(e)
                        self.statusBar.showMessage(f'Fehler beim Öffnen der Datei: {filename}') 
                        return None
                        
                    filename = convertedImage
                    
            if filename.lower().endswith(supportedFiles):
                try:
                    self.__openFileInBrowser(filename)
                except Exception as e:
                    self.lastExceptionString = str(e)
                    self.statusBar.showMessage(f'(Temporärer) Fehler beim Laden der Datei: {filename}')
            else:
                self.statusBar.showMessage(f'Der Dateityp {Path(filename).suffix} ist zur Anzeige in der Vorschau nicht geeignet.')

    def __getDClickFavoriteViewAction(self):
        """Öffnet eine doppelt angeklickte Datei im externen Standardprogramm."""
        filename = self.favTableView.item(self.favTableView.currentRow(),1).text()     
        self.__openFileExternal(filename)
              
    # __on_load_finished entfernt - pdfjs_viewer übernimmt PDF.js-Initialisierung und Rendering intern

    def __supportAnfragen(self):
        """Öffnet Mailprogramm und befüllt Inhalt mit den wichtigsten Informationen zu Einstellungen, letzten Fehlern und Installationsumgebung."""
        mailbody="\n\n------ Ihre Anfrage bitte oberhalb dieser Linie einfügen ------\n\nEinstellungen\n"
        
        for key in self.settings.allKeys():
            if key not in ['history', 'lastFile', 'defaultFolder']:  
                mailbody+=f"{key} - {str(self.settings.value(key))}\n" 
        
        if len(self.lastExceptionString)>0:
            mailbody+='\n\nLetzte Fehlermeldung\n' + self.lastExceptionString
        
        open_url(QUrl("mailto:%s?subject=Supportanfrage zu openXJV %s unter %s&body=%s" % (self.supportMail, VERSION, platform.platform() ,str(mailbody)), QUrl.ParsingMode.TolerantMode ))
 
    def changeEvent(self, event):
        if event.type() == QEvent.Type.PaletteChange:  
            # Workaround für Gnome Palette / Ubuntu
            if sys.platform.lower() == 'linux':
                self.__fixGnomeDarkPalette()    
               
        return super(UI, self).changeEvent(event)

    def __onScreenChanged(self, screen: QScreen):
        """Getrigget wenn Fenster auf anderenm Screen gezogen wird"""
        self.__setFontsizes()
                  
    # ========================================
    # ABSCHNITT 13: HILFS-/UNTERSTÜTZUNGSMETHODEN
    # ========================================
    def __getCurrentDocTableFilename(self):
        """Gibt den Dateinamen der aktuell markierten Datei zurück in the document view."""
        if self.docTableView.currentRow()!=-1:
            filenameColumn=self.docTableAttributes.index('dateiname')+2
            filename=self.docTableView.item(self.docTableView.currentRow(), filenameColumn).text()
            return filename
                
    def __getCurrentItemEntry(self, focusWidget):
        """Gibt den FavoriteEntry der aktuell markierten Zeile zurück.

        Für die favTableView wird das in __setFavorites gespeicherte UserRole-Datum
        ausgelesen, das den exakten FavoriteEntry enthält (inkl. Leerstring für
        Legacy-Einträge). Für die docTableView wird per aktuellem Anzeigenamen und
        Dateinamen gesucht, mit Legacy-Fallback falls kein exakter Treffer gefunden wird.
        """
        if focusWidget == self.favTableView:
            if self.favTableView.currentItem():
                row = self.favTableView.currentRow()
                col0 = self.favTableView.item(row, 0)
                col1 = self.favTableView.item(row, 1)
                if col0 is None or col1 is None:
                    return None
                entry = col0.data(Qt.ItemDataRole.UserRole)
                if entry is not None:
                    return entry
                # TODO (Version 1.5+): Fallback entfernen – tritt nur auf, wenn
                # favTableView ohne UserRole-Daten befüllt wurde (sollte nie passieren).
                return FavoriteEntry(filename=col1.text(), anzeigename=col0.text())

        elif focusWidget == self.docTableView:
            if self.docTableView.currentRow() != -1:
                row = self.docTableView.currentRow()
                filenameColumn = self.docTableAttributes.index('dateiname') + 2
                anzeigenameColumn = self.docTableAttributes.index('anzeigename') + 2
                fn_item = self.docTableView.item(row, filenameColumn)
                az_item = self.docTableView.item(row, anzeigenameColumn)
                if fn_item is None or az_item is None:
                    return None
                entry = FavoriteEntry(filename=fn_item.text(), anzeigename=az_item.text())
                if entry in self.favorites:
                    return entry
                # TODO (Version 1.5+): Legacy-Fallback entfernen, sobald keine
                # Einträge mit anzeigename='' mehr in self.favorites vorkommen.
                # Sucht nach Legacy-Eintrag mit passendem Dateinamen.
                return next(
                    (e for e in self.favorites if e.filename == fn_item.text() and not e.anzeigename),
                    None
                )
        return None

    def __replaceTrueFalse(self, value):
       """Ersetzt Strings 'True' mit 'yes' and 'False' mit 'no'. Nicht case-sensitiv."""
       if value.lower()=='true':
           return 'ja' 
       elif value.lower()=='false':
           return 'nein'
       return value

    def __isSet(self, value):
        """Ersetzt einen leeren String '' mit 'not specified'."""
        if value == '':
            return 'nicht angegeben'
        else:
            return value

    def __tableItem (self, text, font=QFont('Ubuntu', 11, 50)):
        """Erstellt Tabellenelement und setzt Schrift dafür."""
        item = QTableWidgetItem(text)
        item.setFont(font)
        return item
    
    def __getAktenSubBaum(self, akten, node):    
        for einzelakte in akten.values():
           
            if einzelakte['aktentyp']:
                name = einzelakte['anzeigename'] if not einzelakte['anzeigename'] in ('', None) else einzelakte['aktentyp']
            elif einzelakte['teilaktentyp'] != '': 
                name = einzelakte['anzeigename'] if not einzelakte['anzeigename'] in ('', None) else einzelakte['teilaktentyp']             
            else:
                name = "Akte"
            
            for aktenzeichen in einzelakte['aktenzeichen']:
                    if aktenzeichen['aktenzeichen.freitext']:
                        name += ' ' + aktenzeichen['aktenzeichen.freitext']
                     
            value = StandardItem(name)
            value.setIcon(QIcon(os.path.join(self.scriptRoot, 'icons', 'aktenbox_icon.png')))
            key   = StandardItem(einzelakte['id'])
            
            if len(einzelakte['teilakten'])>0:
                self.__getAktenSubBaum(einzelakte['teilakten'], value)
            
            node.appendRow([value, key])
              
    def __arrangeData(self, dictOfMetadata, attributes):
        """Gibt die Werte eines Dictionaries zurück in der Reihenfolge einer übergebenen Schlüsselliste. Wenn für einen Schlüssel kein Eintrag vorhanden ist, wird ein leeres Listenelement eingefügt."""
        arrangedRow=[]      
        for attribute in attributes:
            value = dictOfMetadata.get(attribute)
            if isinstance(value, str):
                arrangedRow.append(self.__replaceTrueFalse(value))
            elif isinstance(value, list):
                text=''
                newline='' # Optional setzen, um Werte in mehreren Zeilen anzeigen lassen zu können 
                for item in value:
                    if item:
                        text+=newline + item
                        newline=' '
                arrangedRow.append(text)
            elif value is None:
                arrangedRow.append('')
            else:
                arrangedRow.append(str(value))  # Fallback für alle anderen Typen
            
        return arrangedRow
    
    def __copyToClipboard(self, text):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.statusBar.showMessage("Inhalt wurde in die Zwischenablage kopiert.")        

    def __displayInfo(self):
        """Blendet Info-Fenster ein (About)."""
        QMessageBox.information(self, "Information",
        "openXJV " + VERSION + "\n"
        "Lizenz: GPL v3\n"
        "2022 - 2026 Björn Seipel\nKontakt: " + self.supportMail + "\nWebsite: https://openXJV.de\n\n"
        "Die Anwendung nutzt folgende Komponenten:\n"
        "jbig2dec - AGPL License\n"
        "Qt6 - LGPLv3\n"
        "fpdf2 - LGPLv3\n"
        "pyinstaller - GPLv2 or later\n"
        "PySide6 - LGPLv3\n"
        "PDF.js - Apache 2.0 License\n"
        "pdfjs-viewer-pyside6 - LGPLv3+ License\n"
        "Tesseract - Apache 2.0 License\n"
        "Material Icons Font - Apache 2.0 License\n"
        "NumPy - BSD License\n"
        "orjson - Apache 2.0 / MIT Licenses\n"
        "pypdfium2 - Apache 2.0 / BSD 3 Clause\n"
        "darkdetect - BSD license\n"
        "lxml - BSD License\n"
        "Pillow - The open source HPND License\n"
        "pikepdf - MPL-2.0 License\n"
        "platformdirs - MIT License\n"
        "docx2txt - MIT License\n"
        "gocr - GNU GPL\n"
        "Ubuntu Font - UBUNTU FONT LICENCE Version 1.0\n"
        "python 3.x - PSF License\n\n"
        "KI-Labor — zusätzliche Komponenten:\n"
        "llama-cpp-python - MIT License\n"
        "rapidocr - Apache 2.0 License\n"
        "onnxruntime - MIT License\n"
        "opencv-python-headless - Apache 2.0 License\n\n"
        "Lizenztexte und Quellcode-Links können dem Benutzerhandbuch entnommen werden.\n"
        "Die im KI-Labor verwendeten KI-Modelle und OCR-Modelle sowie deren Lizenzen\n"
        "sind dort jeweils über die ⓘ-Schaltflächen abrufbar."
        )
  
    def __displayMessage(self, message, title = 'Hinweis', icon = QMessageBox.Icon.Information, modal=True):
        """Zeigt ein Info-Pop-up an."""
        msgBox=QMessageBox(self)
        msgBox.setIcon(icon)
        msgBox.setWindowTitle(title)
        msgBox.setStandardButtons(QMessageBox.StandardButton.Ok)       
        msgBox.setText(message)
        if modal:
            msgBox.exec()
        else:
            msgBox.setModal(False)
            msgBox.show()

    def __debugOutput(self, origin: str) -> None:
        """Gibt den aktuellen Traceback nach stderr aus, wenn --debug aktiv ist."""
        if '--debug' in sys.argv:
            print(f'DEBUG {origin}: {traceback.format_exc()}', file=sys.stderr)

    def __fixGnomeDarkPalette(self):
        xjvPalette = self.palette()
        for role in QPalette.ColorRole:
            if not role.name in ('NColorRoles', 'ToolTipBase', 'ToolTipText'):
                xjvPalette.setColor(QPalette.ColorGroup.Inactive, role, xjvPalette.color(QPalette.ColorGroup.Active, role))
            xjvPalette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipText,  QColor(0, 0, 0, 255))          
        self.setPalette(xjvPalette)                
        QToolTip.setPalette(xjvPalette)
                
    # ========================================
    # ABSCHNITT 14: XSD-VALIDIERUNG
    # ========================================
    def __showMaintenanceDialog(self):
        dialog = MaintenanceTokenDialog(self.settings_manager, parent=self)
        dialog.token_validated.connect(lambda: self.maintenanceBanner.setVisible(False))
        dialog.exec()

    def __openXSDValidator(self):
        """Oeffnet den XSD-Validierungsdialog fuer die geladene XML-Datei.

        Prueft, ob eine Datei geladen ist, und stellt sicher, dass nur
        eine Instanz des Dialogs gleichzeitig geoeffnet ist.
        """
        # Pruefen, ob eine Datei geladen ist
        if self.akte == {}:
            self.__displayMessage(
                'Es ist keine Datei geladen.\n\n'
                'Bitte öffnen Sie zuerst eine XJustiz-Datei.',
                title='Hinweis'
            )
            return

        # Einzelinstanz-Pruefung: Falls Dialog bereits offen, in den Vordergrund bringen
        if (self._xsd_validator_dialog is not None
                and self._xsd_validator_dialog.isVisible()):
            self._xsd_validator_dialog.raise_()
            self._xsd_validator_dialog.activateWindow()
            return

        # Vollstaendigen Pfad zur XML-Datei zusammensetzen
        xml_path = os.path.join(self.basedir, self.xmlFile)

        # Dialog erstellen und anzeigen
        self._xsd_validator_dialog = XSDValidatorDialog(
            xml_path=xml_path,
            app_base_path=self.scriptRoot,
            detect_version_callback=self.file_manager.detect_xjustiz_version,
            parent=self
        )
        self._xsd_validator_dialog.show()

    # ========================================
    # ABSCHNITT 15: UPDATE-PRÜFUNGEN
    # ========================================    
    def __checkForUpdates(self, updateIndicator=None):
        """Prüft online, ob eine neue Programmversion veröffentlicht wurde."""
        updateAvailable=False

        # Download Versionsinfo für unterstützte Plattformen / Verstecke die Option auf nicht unterstützten Systemen
        if os.environ.get('APPIMAGE'):
            updateAvailable=self.__checkUrlforNewVersion('https://openXJV.de/latestAppImage.xml')
        elif sys.platform.lower().startswith('win'):
            updateAvailable=self.__checkUrlforNewVersion('https://openXJV.de/latestWinInstaller.xml')
        else:
            self.actionOnlineAufUpdatesPruefen.setVisible(False)
        
        if updateAvailable:
            if updateIndicator:
                updateIndicator.setVisible(True)
            self.statusBar.showMessage('Es steht eine neue Version der Software zum Download bereit.')
            return True
        else:
            return False
        
    def __checkUrlforNewVersion(self, url=None):
        if url: 
            try:
                with urllib.request.urlopen(url) as content:
                    for line in content.readlines():
                        result=(re.findall('<version>.+?</version>',str(line))) 
                        if result and result[0]: 
                            for newVer , oldVer in zip(result[0][9:-10].split('.'), VERSION.split('.')):
                                if newVer > oldVer:
                                    return True   
                                elif newVer < oldVer:
                                    return False
            except Exception as e:
                self.statusBar.showMessage('Online-Überprüfung auf neue Version konnte nicht durchgeführt werden.')
                self.lastExceptionString = str(e)
        return False
    
    # ========================================
    # ABSCHNITT 16: DATENBANKVERWALTUNG
    # ========================================     
    def __notizUndSuchdatenbankLoeschen(self):
        self.db_manager.clear_all_data()
        self.statusBar.showMessage('Die Datenbank wurde gelöscht und eine neue, leere Datenbank wurde angelegt.')
        
    # ========================================
    # ENDE DER ABSCHNITTE
    # ========================================               
                                              

def launchApp():
    """
    Startet openXJV

    Diese Funktion initialisiert die Qt-Anwendung mit den richtigen Einstellungen
    und startet das Hauptfenster der Benutzeroberfläche.
    """
    
    # Unter Windows stdout und stderr in Log umleiten, wenn mit PyInstaller gefroren,
    # da stdout und stderr nicht (mehr) in der aufrufenden Konsole dargesetllt weren
    if getattr(sys, 'frozen', False) and os.name == 'nt':
        import tempfile
        _log_path = os.path.join(tempfile.gettempdir(), 'openXJV.log')
        _log_file = open(_log_path, 'w', encoding='utf-8', buffering=1)
        sys.stdout = _log_file
        sys.stderr = _log_file
        
    # Prüfe, ob bereits eine Instanz läuft, wenn nicht im Print Process
    if not os.environ.get("_PDFJS_PRINT_PROCESS") == "1":
        single_instance = SingleInstance('openXJV')
        if not single_instance.acquire():
            print("openXJV läuft bereits! Es kann nur eine Instanz gleichzeitig gestartet werden.")
            sys.exit(1)

    print("QT Version (PySide): %s" % qVersion())
    print(f'openXJV Version: {VERSION}')
    print(f'Modulpaket-Version: {MODULAR_VERSION}')
    print('Deaktiviere Chromium-Sandbox aus Kompatibilitätsgründen.')
    # Deaktiviere Sandbox 
    os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

    # Chromium-Flags
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join([
        "--log-level=3",                 # Weniger Logging
        #"--disable-web-security",        
        "--num-raster-threads=4",        # Mehrere Raster-Threads
        "--disk-cache-size=268435456",   # 256 MB Cache
        "--media-cache-size=134217728",  # 128 MB Medien-Cache
    ])

    # Automatische DPI-Skalierung
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    if sys.platform.lower().startswith('win'):
        os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=2"

    # Globale WebEngine-Stabilitaetseinstellungen (muss vor QApplication aufgerufen werden)
    configure_global_stability(
        disable_gpu=True,
        disable_webgl=True,
        disable_gpu_compositing=True,
    )

    pdfjs_freeze_support()
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setObjectName('openXJV')
    app.setApplicationName('OpenXJV')
    app.setApplicationDisplayName(f'openXJV {VERSION}')
    app.setApplicationVersion(VERSION)
    app.setDesktopFileName('de.openxjv.viewer')


    # Set German locale
    QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))

    # Splash Screen mit Mindestanzeigedauer
    import time
    MIN_SPLASH_TIME = 2.0  # Sekunden

    splash_screen = QPixmap(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'icons', 'SplashScreen.png'))
    splash = QSplashScreen(splash_screen, Qt.WindowType.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()
    splash_start = time.time()

    # Parse sys.argv
    file = None
    ziplist = None
    ki_debug = '--ki-debug' in sys.argv
    debug = '--debug' in sys.argv

    remaining = [a for a in sys.argv[1:] if a not in ('--ki-debug', '--debug')]
    if len(remaining) == 1 and remaining[0].lower().endswith('xml'):
        file = remaining[0]
    elif remaining:
        ziplist = [f for f in remaining if f.lower().endswith('zip')]

    widget = UI(app, file=file, ziplist=ziplist, ki_debug=ki_debug)
    widget.setWindowFlags(
        (widget.windowFlags() & ~Qt.WindowType.WindowFullscreenButtonHint)
        | Qt.WindowType.CustomizeWindowHint
    )
    app.aboutToQuit.connect(widget.cleanUp)

    # Funktion zum Anzeigen des Hauptfensters nach Splash
    def showMainWindow():
        splash.close()
        widget.showMaximized()
        # Splitter-Größen setzen und Dateien laden nach dem Anzeigen des Fensters
        QTimer.singleShot(50, lambda: (widget.setInitialSplitterSizes(), widget.loadInitialFiles()))

    # Berechne verbleibende Zeit für Mindestanzeigedauer
    elapsed = time.time() - splash_start
    remaining_ms = int(max(0, (MIN_SPLASH_TIME - elapsed) * 1000))

    if remaining_ms > 0:
        QTimer.singleShot(remaining_ms, showMainWindow)
    else:
        showMainWindow()

    sys.exit(app.exec())

if __name__ == "__main__":
    multiprocessing.freeze_support()
    _debug = '--debug' in sys.argv
    try:
        launchApp()
    except Exception as e:
        if _debug:
            traceback.print_exc()
        else:
            print(e)