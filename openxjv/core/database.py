#!/usr/bin/env python3
# coding: utf-8
"""
Datenbank-Verwaltungsmodul für openXJV.

Dieses Modul stellt eine DatabaseManager-Klasse zur Verfügung, die alle Datenbankoperationen verwaltet
im Zusammenhang mit Favoriten, Notizen und anderen persistenten Datenspeicherungen mittels SQLite.

Author: Björn Seipel
License: GPL-3.0-or-later
"""

import os
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Tuple


class DatabaseManager:
    """Verwaltet Datenbankoperationen für die openXJV-Anwendung.

    Diese Klasse verwaltet alle Interaktionen mit der SQLite-Datenbank, einschließlich:
    - Datenbankinitialisierung und Tabellenerstellung
    - Favoritenverwaltung (Laden und Speichern)
    - Notizenverwaltung (Laden und Speichern)
    - Datenbank-Bereinigungsoperationen
    - Migration von veralteter dateibasierter Speicherung zur Datenbank

    Attribute:
        db_path (Path): Pfad zur SQLite-Datenbankdatei.
    """

    def __init__(self, db_path: str | Path) -> None:
        """Initialisiert den DatabaseManager.

        Args:
            db_path: Pfad zur SQLite-Datenbankdatei. Kann ein String oder Path-Objekt sein.

        Beispiel:
            >>> db_manager = DatabaseManager("/path/to/database.db")
        """
        self.db_path = Path(db_path) if isinstance(db_path, str) else db_path
        self.create_database()

    def create_database(self) -> None:
        """Erstellt Datenbanktabellen, falls sie nicht existieren.

        Erstellt die folgenden Tabellen:
        - favorites: Speichert Favoriten des Benutzers mit ihrer Reihenfolge/Position
        - last_access: Verfolgt den letzten Zugriffszeitstempel für jedes Dokument
        - notes: Speichert Benutzernotizen, die mit Dokumenten verknüpft sind
        - plaintext: Speichert extrahierten Klartext aus Dokumenten für Suchfunktionalität

        Alle Tabellen werden mit IF NOT EXISTS-Klausel erstellt, um Fehler bei wiederholten Aufrufen zu verhindern.

        Raises:
            sqlite3.Error: Falls Datenbankverbindung oder Tabellenerstellung fehlschlägt.
        """
        with sqlite3.connect(self.db_path) as db_connection:
            db_cursor = db_connection.cursor()

            # Erstellt Favoriten-Tabelle, falls sie nicht existiert
            db_cursor.execute('''
                CREATE TABLE IF NOT EXISTS favorites (
                uuid TEXT,
                filename TEXT,
                position INTEGER
                )
            ''')

            # Erstellt last_access-Tabelle, falls sie nicht existiert
            db_cursor.execute('''
                CREATE TABLE IF NOT EXISTS last_access (
                uuid TEXT PRIMARY KEY,
                timestamp INTEGER NOT NULL
                )
            ''')

            # Erstellt Notizen-Tabelle, falls sie nicht existiert
            db_cursor.execute('''
                CREATE TABLE IF NOT EXISTS notes (
                uuid TEXT PRIMARY KEY,
                notes TEXT NOT NULL
                )
            ''')

            # Erstellt Plaintext-Tabelle für Volltextsuche, falls sie nicht existiert
            db_cursor.execute('''
                CREATE TABLE IF NOT EXISTS plaintext (
                uuid TEXT,
                filename TEXT NOT NULL,
                text NOT NULL,
                basedir NOT NULL
                )
            ''')

            db_connection.commit()

    def load_favorites(
        self,
        uuid: str,
        legacy_data_dir: Optional[str | Path] = None
    ) -> List[str]:
        """Lädt Favoriten aus der Datenbank für eine gegebene UUID.

        Diese Methode unterstützt Migration von veralteter dateibasierter Speicherung (pre-v0.8.0).
        Falls eine veraltete Favoriten-Datei existiert, wird sie in die Datenbank importiert
        und die Datei wird gelöscht.

        Args:
            uuid: Der eindeutige Bezeichner für das Dokument/den Fall.
            legacy_data_dir: Optionaler Pfad zum Verzeichnis mit veralteten Favoriten-Dateien.
                Falls angegeben, wird nach veralteten Favoriten gesucht und diese migriert.

        Returns:
            Eine Liste von Dateinamen, die als Favoriten markiert sind, in ihrer gespeicherten Reihenfolge.
            Gibt eine leere Liste zurück, falls keine Favoriten gefunden werden oder uuid None/leer ist.

        Beispiel:
            >>> db = DatabaseManager("/path/to/db.db")
            >>> favorites = db.load_favorites("abc-123-def", "/path/to/legacy/data")
            >>> print(favorites)
            ['document1.pdf', 'document2.pdf']

        Raises:
            sqlite3.Error: Falls Datenbankabfrage fehlschlägt.
        """
        favorites: List[str] = []

        if not uuid:
            return favorites

        # Prüft auf veraltete Favoriten-Datei (pre-version 0.8.0)
        if legacy_data_dir:
            legacy_data_dir = Path(legacy_data_dir) if isinstance(legacy_data_dir, str) else legacy_data_dir
            legacy_filepath = legacy_data_dir / uuid

            if legacy_filepath.exists():
                # Lädt Favoriten aus veralteter Datei
                with open(legacy_filepath, 'r', encoding='utf-8') as favorite_file:
                    for filename in favorite_file.readlines():
                        favorites.append(filename.rstrip("\n"))

                # Speichert in Datenbank
                self.save_favorites(uuid, favorites)

                # Löscht veraltete Datei nach erfolgreicher Migration
                os.remove(legacy_filepath)
                return favorites

        # Lädt Favoriten aus Datenbank
        with sqlite3.connect(self.db_path) as db_connection:
            db_cursor = db_connection.cursor()

            db_query = '''
                SELECT filename, position FROM favorites WHERE uuid = ? ORDER BY position ASC;
            '''
            db_cursor.execute(db_query, (uuid,))
            rows = db_cursor.fetchall()

            for row in rows:
                favorites.append(row[0])

        return favorites

    def save_favorites(self, uuid: str, favorites: List[str]) -> None:
        """Speichert Favoriten in der Datenbank für eine gegebene UUID.

        Diese Methode ersetzt alle existierenden Favoriten für die UUID mit der neuen Liste.
        Die Reihenfolge der Elemente in der Liste wird durch Positionswerte beibehalten.

        Args:
            uuid: Der eindeutige Bezeichner für das Dokument/den Fall.
            favorites: Liste von Dateinamen, die als Favoriten gespeichert werden sollen. Reihenfolge wird beibehalten.

        Raises:
            sqlite3.Error: Falls Datenbankoperation fehlschlägt.
            Exception: Alle anderen Exceptions werden abgefangen und können über lastExceptionString abgerufen werden.

        Beispiel:
            >>> db = DatabaseManager("/path/to/db.db")
            >>> db.save_favorites("abc-123-def", ["doc1.pdf", "doc2.pdf"])
        """
        if not uuid:
            return

        try:
            with sqlite3.connect(self.db_path) as db_connection:
                db_cursor = db_connection.cursor()

                # Löscht alle existierenden Favoriten für diese UUID
                db_query = '''
                    DELETE FROM favorites WHERE uuid = ?;
                '''
                db_cursor.execute(db_query, (uuid,))

                # Fügt neue Favoriten mit Positionswerten ein
                if favorites:
                    for filename, position in zip(favorites, range(len(favorites))):
                        db_query = '''
                            INSERT OR REPLACE INTO favorites (uuid, filename, position) VALUES (?, ?, ?);
                        '''
                        db_cursor.execute(db_query, (uuid, filename, position))

                db_connection.commit()
        except Exception as e:
            # Speichert Exception für potenzielle Fehlersuche
            self.lastExceptionString = str(e)
            raise

    def load_notes(
        self,
        uuid: str,
        legacy_data_dir: Optional[str | Path] = None
    ) -> str:
        """Lädt Notizen aus der Datenbank für eine gegebene UUID.

        Diese Methode unterstützt Migration von veralteter dateibasierter Speicherung.
        Falls eine veraltete Notizen-Datei existiert, wird sie in die Datenbank importiert
        und die Datei wird gelöscht.

        Args:
            uuid: Der eindeutige Bezeichner für das Dokument/den Fall.
            legacy_data_dir: Optionaler Pfad zum Verzeichnis mit veralteten Notizen-Dateien.
                Veraltete Notizen-Dateien haben den Namen 'notizen' + uuid.

        Returns:
            Der Notizentext als String. Gibt einen leeren String zurück, falls keine Notizen gefunden werden
            oder falls uuid None/leer ist.

        Beispiel:
            >>> db = DatabaseManager("/path/to/db.db")
            >>> notes = db.load_notes("abc-123-def", "/path/to/legacy/data")
            >>> print(notes)
            'These are my notes about the case...'

        Raises:
            sqlite3.Error: Falls Datenbankabfrage fehlschlägt.

        Hinweis:
            Veraltete Notizen-Dateien können Codierungsprobleme unter Windows haben. Diese Methode versucht
            zuerst UTF-8, fällt dann auf Standard-Systemcodierung zurück, falls das fehlschlägt.
        """
        notes_text = ''

        if not uuid:
            return notes_text

        # Prüft auf veraltete Notizen-Datei
        if legacy_data_dir:
            legacy_data_dir = Path(legacy_data_dir) if isinstance(legacy_data_dir, str) else legacy_data_dir
            legacy_filepath = legacy_data_dir / ('notizen' + uuid)

            if legacy_filepath.exists():
                # Lädt Notizen aus veralteter Datei
                try:
                    with open(legacy_filepath, 'r', encoding='utf-8') as notes_file:
                        notes_text = notes_file.read()
                except Exception:
                    # Unter Windows sind alte Notizen möglicherweise nicht UTF-8-codiert und werfen Fehler
                    with open(legacy_filepath, 'r') as notes_file:
                        notes_text = notes_file.read()

                # Speichert in Datenbank
                self.save_notes(uuid, notes_text)

                # Löscht veraltete Datei nach erfolgreicher Migration
                os.remove(legacy_filepath)
                return notes_text

        # Lädt Notizen aus Datenbank
        with sqlite3.connect(self.db_path) as db_connection:
            db_cursor = db_connection.cursor()

            db_query = '''
                SELECT notes FROM notes WHERE uuid = ?;
            '''
            db_cursor.execute(db_query, (uuid,))
            rows = db_cursor.fetchall()

            if rows:
                notes_text = rows[0][0]

        return notes_text

    def save_notes(self, uuid: str, notes: str, update_access_time: bool = True) -> None:
        """Speichert Notizen in der Datenbank für eine gegebene UUID.

        Diese Methode aktualisiert auch den letzten Zugriffszeitstempel für das Dokument, außer
        update_access_time ist auf False gesetzt.

        Args:
            uuid: Der eindeutige Bezeichner für das Dokument/den Fall.
            notes: Der zu speichernde Notizentext.
            update_access_time: Falls True (Standard), wird auch der last_access-Zeitstempel aktualisiert.

        Raises:
            sqlite3.Error: Falls Datenbankoperation fehlschlägt.
            AttributeError: Falls Notizen-Objekt erwartete Attribute nicht hat (abgefangen und durchgereicht).
            Exception: Alle anderen Exceptions werden stillschweigend abgefangen.

        Beispiel:
            >>> db = DatabaseManager("/path/to/db.db")
            >>> db.save_notes("abc-123-def", "Updated notes text")
        """
        if not uuid:
            return

        try:
            with sqlite3.connect(self.db_path) as db_connection:
                db_cursor = db_connection.cursor()

                # Speichert oder aktualisiert Notizen
                db_query = '''
                    INSERT OR REPLACE INTO notes (uuid, notes) VALUES (?, ?);
                '''
                db_cursor.execute(db_query, (uuid, notes))

                # Aktualisiert letzten Zugriffszeitstempel
                if update_access_time:
                    db_query = '''
                        INSERT OR REPLACE INTO last_access (uuid, timestamp) VALUES (?, ?);
                    '''
                    db_cursor.execute(db_query, (uuid, str(int(time.time()))))

                db_connection.commit()
        except AttributeError:
            # Erwartet in einigen Grenzfällen, stillschweigend durchreichen
            pass
        except Exception as e:
            # Speichert Exception für potenzielle Fehlersuche, wirft aber nicht
            self.lastExceptionString = str(e)

    def clear_all_data(self) -> None:
        """Löscht alle Daten aus der Datenbank durch Entfernen aller Tabellen.

        Diese Methode:
        1. Fragt alle existierenden Tabellen in der Datenbank ab
        2. Entfernt jede Tabelle
        3. Erstellt die Standard-Tabellen durch Aufruf von create_database() neu

        Warnung:
            Diese Operation ist destruktiv und kann nicht rückgängig gemacht werden. Alle Daten einschließlich
            Favoriten, Notizen und Suchindizes werden permanent gelöscht.

        Raises:
            sqlite3.Error: Falls Datenbankoperationen fehlschlagen.

        Beispiel:
            >>> db = DatabaseManager("/path/to/db.db")
            >>> db.clear_all_data()  # All data is now deleted and tables recreated
        """
        with sqlite3.connect(self.db_path) as db_connection:
            db_cursor = db_connection.cursor()

            # Ruft alle Tabellennamen ab
            db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = db_cursor.fetchall()

            # Entfernt jede Tabelle
            for table_name in tables:
                db_cursor.execute(f'DROP TABLE {table_name[0]};')

            db_connection.commit()

        # Erstellt leere Datenbank mit Standard-Tabellen neu
        self.create_database()

    def get_last_access_time(self, uuid: str) -> Optional[int]:
        """Ruft den letzten Zugriffszeitstempel für eine gegebene UUID ab.

        Args:
            uuid: Der eindeutige Bezeichner für das Dokument/den Fall.

        Returns:
            Der letzte Zugriffszeitstempel als Integer (Unix-Zeitstempel) oder None, falls nicht gefunden.

        Beispiel:
            >>> db = DatabaseManager("/path/to/db.db")
            >>> timestamp = db.get_last_access_time("abc-123-def")
            >>> if timestamp:
            ...     print(f"Last accessed: {timestamp}")
        """
        if not uuid:
            return None

        with sqlite3.connect(self.db_path) as db_connection:
            db_cursor = db_connection.cursor()

            db_query = '''
                SELECT timestamp FROM last_access WHERE uuid = ?;
            '''
            db_cursor.execute(db_query, (uuid,))
            row = db_cursor.fetchone()

            return int(row[0]) if row else None

    def delete_notes(self, uuid: str) -> None:
        """Löscht Notizen für eine gegebene UUID aus der Datenbank.

        Args:
            uuid: Der eindeutige Bezeichner für das Dokument/den Fall.

        Raises:
            sqlite3.Error: Falls Datenbankoperation fehlschlägt.

        Beispiel:
            >>> db = DatabaseManager("/path/to/db.db")
            >>> db.delete_notes("abc-123-def")
        """
        if not uuid:
            return

        with sqlite3.connect(self.db_path) as db_connection:
            db_cursor = db_connection.cursor()

            db_query = '''
                DELETE FROM notes WHERE uuid = ?;
            '''
            db_cursor.execute(db_query, (uuid,))
            db_connection.commit()

    def delete_favorites(self, uuid: str) -> None:
        """Löscht alle Favoriten für eine gegebene UUID aus der Datenbank.

        Args:
            uuid: Der eindeutige Bezeichner für das Dokument/den Fall.

        Raises:
            sqlite3.Error: Falls Datenbankoperation fehlschlägt.

        Beispiel:
            >>> db = DatabaseManager("/path/to/db.db")
            >>> db.delete_favorites("abc-123-def")
        """
        if not uuid:
            return

        with sqlite3.connect(self.db_path) as db_connection:
            db_cursor = db_connection.cursor()

            db_query = '''
                DELETE FROM favorites WHERE uuid = ?;
            '''
            db_cursor.execute(db_query, (uuid,))
            db_connection.commit()
