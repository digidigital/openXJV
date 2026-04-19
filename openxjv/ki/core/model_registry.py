"""
Modell-Registry: lädt JSON-Konfigurationen, löst Dateipfade auf, baut Prompts.

Suchpfade für GGUF-Dateien (in dieser Reihenfolge):
  A: models_dir  — vom Host übergeben (DB-Verzeichnis/models)
  B: $OPENXJVMODELPATH — Umgebungsvariable, Doppelpunkt- oder Semikolon-getrennt
  C: ~/.local/share/openxjv/models/  (Linux)
     %APPDATA%\\openxjv\\models\\     (Windows)

Download-Zielordner (Priorität):
  1. models_dir (falls beschreibbar)
  2. erster Pfad aus $OPENXJVMODELPATH (falls gesetzt und beschreibbar)
  3. plattformspezifischer User-Ordner (C)
"""
from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class ModelConfig:
    order: int
    id: str
    display_name: str
    filename: str
    download_url: str
    n_ctx_max: int
    n_ctx_min: int
    kv_params: dict        # {"n_kv_heads": int, "head_dim": int, "n_layers": int}
    chat_template_type: str
    context_reserve: int
    generation: dict       # temperature, repeat_penalty, top_p, top_k, min_p
    repeat_last_n: int     # Wiederholungs-Penalty-Fenster (Llama-Konstruktor)
    template_overhead: int # Chat-Template-Token-Overhead für Kontextbudget
    prompt_overhead: int   # Puffer für System-Prompt + Header in Token
    chunk_overlap_chars: int  # Zeichenüberlappung zwischen Chunks
    inject_date: bool
    system_prompts: dict[str, str]
    user_prompts: dict[str, str]
    license_file: str = ""
    vram_model_gb: float = 0.0            # Geschätzter VRAM-Bedarf der Modellgewichte in GB
    chat_template: str = ""               # Explizites Jinja2-Template, falls GGUF keines enthält
    rope_scaling_max_factor: float = 1.0  # Maximaler RoPE-Skalierungsfaktor (1.0 = deaktiviert)
    filter_thinking_block: bool = False   # <think>…</think>-Block aus dem Ausgabestream herausfiltern
    resolved_path: Path | None = field(default=None, compare=False)


class ModelRegistry:
    """
    Lädt alle configs/*.json und bietet Pfadauflösung + Prompt-Generierung.
    """

    def __init__(self, models_dir: Path | None = None, config_dir: Path | None = None) -> None:
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "configs"
        self._config_dir = Path(config_dir)
        self._app_dir = Path(__file__).parent.parent
        self._license_dir = self._app_dir / "licenses"
        self._models_dir: Path | None = Path(models_dir) if models_dir else None
        self._models: dict[str, ModelConfig] = {}
        self._master_system_prompt: str = ""
        self._master_user_prompts: dict[str, str] = {}
        self._master_template_overhead: int = 20
        self._master_prompt_overhead: int = 400
        self._master_chunk_overlap_chars: int = 800
        self._load_errors: list[str] = []
        self._load_master()
        self._load_configs()
        self.cleanup_part_files()
        self.resolve_paths()

    def _load_master(self) -> None:
        master_file = self._config_dir / "master.json"
        if not master_file.is_file():
            return
        try:
            with master_file.open(encoding="utf-8") as f:
                data = json.load(f)
            self._master_system_prompt = data.get("master_system_prompt", "").strip()
            self._master_user_prompts = data.get("master_user_prompts", {})
            self._master_template_overhead = int(data.get("template_overhead", 20))
            self._master_prompt_overhead = int(data.get("prompt_overhead", 400))
            self._master_chunk_overlap_chars = int(data.get("chunk_overlap_chars", 800))
        except (json.JSONDecodeError, OSError):
            pass

    # ------------------------------------------------------------------
    # Konfiguration laden
    # ------------------------------------------------------------------

    def _load_configs(self) -> None:
        if not self._config_dir.is_dir():
            return
        for json_file in sorted(self._config_dir.glob("*.json")):
            if json_file.name == "master.json":
                continue
            try:
                with json_file.open(encoding="utf-8") as f:
                    data = json.load(f)
                raw_gen = data.get("generation", {})
                # repeat_last_n gehört zum Llama-Konstruktor, nicht zu create_chat_completion.
                # Es kann im generation-Block oder direkt auf oberster Ebene stehen.
                repeat_last_n = int(
                    data.get("repeat_last_n")
                    or raw_gen.pop("repeat_last_n", None)
                    or 256
                )
                cfg = ModelConfig(
                    order=int(data.get("order", 99)),
                    id=data["id"],
                    display_name=data["display_name"],
                    filename=data["filename"],
                    download_url=data.get("download_url", ""),
                    n_ctx_max=int(data.get("n_ctx_max", 32768)),
                    n_ctx_min=int(data.get("n_ctx_min", 2048)),
                    kv_params=data.get("kv_params", {"n_kv_heads": 8, "head_dim": 128, "n_layers": 28}),
                    chat_template_type=data.get("chat_template_type", "jinja2_from_gguf"),
                    context_reserve=int(data.get("context_reserve", 1500)),
                    generation=raw_gen or {"temperature": 0.2, "repeat_penalty": 1.1},
                    repeat_last_n=repeat_last_n,
                    template_overhead=int(data.get("template_overhead", self._master_template_overhead)),
                    prompt_overhead=int(data.get("prompt_overhead", self._master_prompt_overhead)),
                    chunk_overlap_chars=int(data.get("chunk_overlap_chars", self._master_chunk_overlap_chars)),
                    inject_date=bool(data.get("inject_date_in_system_prompt", True)),
                    system_prompts=data.get("system_prompts", {}),
                    user_prompts=data.get("user_prompts", {}),
                    license_file=data.get("license_file", ""),
                    vram_model_gb=float(data.get("vram_model_gb", 0.0)),
                    chat_template=data.get("chat_template", ""),
                    rope_scaling_max_factor=float(data.get("rope_scaling_max_factor", 1.0)),
                    filter_thinking_block=bool(data.get("filter_thinking_block", False)),
                )
                self._models[cfg.id] = cfg
            except (KeyError, ValueError, json.JSONDecodeError, OSError) as e:
                self._load_errors.append(f"{json_file.name}: {e}")

    # ------------------------------------------------------------------
    # Pfadauflösung
    # ------------------------------------------------------------------

    def _search_paths(self) -> list[Path]:
        """Gibt alle Suchpfade in Prioritätsreihenfolge zurück."""
        paths: list[Path] = []

        # A: vom Host übergebener models_dir
        if self._models_dir is not None:
            paths.append(self._models_dir)

        # B: Umgebungsvariable OPENXJVMODELPATH (Doppelpunkt- oder Semikolon-getrennt)
        env = os.environ.get("OPENXJVMODELPATH", "").strip()
        if env:
            sep = ";" if ";" in env else ":"
            for entry in env.split(sep):
                entry = entry.strip()
                if entry:
                    paths.append(Path(entry))

        # C: plattformspezifischer User-Ordner
        paths.append(_user_model_dir())

        return paths

    def cleanup_part_files(self) -> None:
        """
        Löscht alle *.part-Dateien aus den Modell-Suchordnern.
        Wird beim Start der Anwendung aufgerufen.
        """
        for search_dir in self._search_paths():
            if not search_dir.is_dir():
                continue
            try:
                part_files = list(search_dir.glob("*.part"))
            except OSError:
                continue
            for part in part_files:
                try:
                    part.unlink()
                except OSError:
                    pass

    def resolve_paths(self) -> None:
        """
        Sucht für jedes Modell die GGUF-Datei in den Suchpfaden.
        Eine vorhandene Datei ohne .part-Suffix gilt als vollständig.
        """
        for cfg in self._models.values():
            cfg.resolved_path = None
            for search_dir in self._search_paths():
                candidate = search_dir / cfg.filename
                if candidate.is_file():
                    cfg.resolved_path = candidate
                    break

    # ------------------------------------------------------------------
    # Download-Zielordner
    # ------------------------------------------------------------------

    def download_destination(self) -> Path:
        """
        Gibt den beschreibbaren Ordner zurück, in den ein Modell gespeichert werden soll.
        Priorität:
          1. models_dir          (falls beschreibbar)
          2. erster OPENXJVMODELPATH-Eintrag (falls gesetzt und beschreibbar)
          3. plattformspezifischer User-Ordner
        Wirft OSError, wenn keiner der Ordner beschreibbar ist.
        """
        candidates: list[Path] = []
        if self._models_dir is not None:
            candidates.append(self._models_dir)

        env = os.environ.get("OPENXJVMODELPATH", "").strip()
        if env:
            sep = ";" if ";" in env else ":"
            first = env.split(sep)[0].strip()
            if first:
                candidates.append(Path(first))

        candidates.append(_user_model_dir())

        for d in candidates:
            try:
                d.mkdir(parents=True, exist_ok=True)
                test = d / ".write_test"
                test.touch()
                test.unlink()
                return d
            except OSError:
                continue

        raise OSError(
            "Kein beschreibbarer Zielordner für Modell-Downloads gefunden.\n"
            f"Geprüft: {', '.join(str(c) for c in candidates)}"
        )

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def get_load_errors(self) -> list[str]:
        """Gibt Liste der beim Laden aufgetretenen Konfigurationsfehler zurück."""
        return list(self._load_errors)

    def all_models(self) -> list[ModelConfig]:
        return sorted(self._models.values(), key=lambda c: c.order)

    def get(self, model_id: str) -> ModelConfig:
        if model_id not in self._models:
            raise KeyError(f"Unbekanntes Modell: {model_id!r}")
        return self._models[model_id]

    def get_system_prompt(self, model_id: str, stil: str) -> str:
        """
        Gibt den System-Prompt für model_id + stil zurück.
        Fällt auf _default zurück, falls stil nicht konfiguriert ist.
        Nutzt master_system_prompt nur als Fallback wenn kein Modell-Prompt vorhanden.
        """
        cfg = self.get(model_id)
        prompts = cfg.system_prompts
        template = prompts.get(stil) or prompts.get("_default", "")
        if cfg.inject_date and "{date}" in template:
            today = _format_date_german(date.today())
            from collections import defaultdict
            template = template.format_map(defaultdict(str, date=today))
        if not template and self._master_system_prompt:
            template = self._master_system_prompt
        return template

    def get_user_prompt(self, model_id: str, stil: str) -> str:
        """
        Gibt den User-Prompt-Template zurück (ohne Dokument).

        Priorität:
          1. Modell-eigener Eintrag für stil
          2. master_user_prompts[stil]
          3. Modell-eigener _default
        """
        cfg = self.get(model_id)
        model_prompts = cfg.user_prompts
        return (
            model_prompts.get(stil)
            or self._master_user_prompts.get(stil)
            or model_prompts.get("_default", "")
        )

    def get_stile(self) -> list[str]:
        """Gibt alle Prompt-Vorlagen-Namen aus master_user_prompts sortiert zurück.
        Interne Schlüssel (beginnen mit '_') werden ausgeschlossen."""
        return sorted(k for k in self._master_user_prompts if not k.startswith("_"))

    def get_license_text(self, model_id: str) -> str:
        """
        Gibt den Lizenztext für model_id zurück.
        Leerer String, wenn keine Lizenzdatei konfiguriert oder nicht lesbar.
        """
        cfg = self.get(model_id)
        if not cfg.license_file:
            return ""
        path = self._license_dir / cfg.license_file
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _user_model_dir() -> Path:
    """Gibt den plattformspezifischen User-Modellordner zurück."""
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "openxjv" / "models"
    else:
        xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return Path(xdg) / "openxjv" / "models"


def _format_date_german(d: date) -> str:
    """Formatiert ein date-Objekt als deutsches Datum, z.B. '29. März 2026'."""
    months = [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    ]
    return f"{d.day}. {months[d.month - 1]} {d.year}"
