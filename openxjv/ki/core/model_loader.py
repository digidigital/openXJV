"""
Speicherabschätzung und GPU-Erkennung für den Elternprozess.

Alle llama-cpp-python-Operationen (Laden, Schließen, Tokenisierung,
Inferenz) laufen im Inferenz-Subprocess (inference_worker.py).

Öffentliche API:
    gpu_offload_active()                         → bool
    estimate_n_ctx(text, config, gpu_active)     → (n_ctx, erklärung)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .model_registry import ModelConfig

# Minimaler Kontext
_N_CTX_MIN = 2048
# Zeichen pro Token (deutsches Rechtstext-Schätzwert)
_CHARS_PER_TOKEN = 4.0


# ---------------------------------------------------------------------------
# GPU-Erkennung
# ---------------------------------------------------------------------------

def gpu_offload_active() -> bool:
    """True, wenn das kompilierte llama-cpp-python ein GPU-Backend hat."""
    try:
        from llama_cpp import llama_cpp as _lc
        return bool(_lc.llama_supports_gpu_offload())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Speicherschätzung (nur Elternprozess, kein llm erforderlich)
# ---------------------------------------------------------------------------

def _kv_bytes_per_token(config: ModelConfig) -> int:
    kv = config.kv_params
    return 2 * kv.get("n_kv_heads", 8) * kv.get("head_dim", 128) * 2


def _kv_layers(config: ModelConfig) -> int:
    return config.kv_params.get("n_layers", 28)


def _total_gpu_bytes() -> int:
    """Gesamter GPU-VRAM in Bytes (0 wenn nicht ermittelbar)."""
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(h)
        pynvml.nvmlShutdown()
        return int(info.total)
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            timeout=3, stderr=subprocess.DEVNULL,
        ).decode().split("\n")[0].strip()
        return int(out) * 1024 * 1024
    except Exception:
        return 0


def _available_memory_bytes(gpu_active: bool) -> int:
    GB = 1024 ** 3
    if gpu_active:
        try:
            import pynvml
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(h)
            pynvml.nvmlShutdown()
            return max(0, info.free - int(512 * 1024 * 1024))
        except Exception:
            pass
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                timeout=3, stderr=subprocess.DEVNULL,
            ).decode().split("\n")[0].strip()
            return max(0, int(out) * 1024 * 1024 - 512 * 1024 * 1024)
        except Exception:
            pass
        return 2 * GB

    # CPU: /proc/meminfo (Linux) oder psutil
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return max(0, kb * 1024 - 512 * 1024 * 1024)
    except Exception:
        pass
    try:
        import psutil
        return max(0, psutil.virtual_memory().available - 512 * 1024 * 1024)
    except Exception:
        return 2 * GB


def _max_ctx_from_memory(config: ModelConfig, gpu_active: bool) -> int:
    """
    Schätzt das maximale Kontextfenster aus dem verfügbaren VRAM/RAM.

    Wenn VRAM-Bedarf der Modellgewichte bekannt ist und eine GPU aktiv ist,
    wird gegen den GESAMT-VRAM gerechnet (nicht gegen den freien), da das
    Schätzen vor dem Laden geschieht und das alte Modell gleich freigegeben wird.
    """
    if gpu_active and config.vram_model_gb > 0:
        total = _total_gpu_bytes()
        if total > 0:
            reserved  = int(config.vram_model_gb * 1024 ** 3) + int(512 * 1024 * 1024)
            avail     = max(0, total - reserved)
            kv_per_token = _kv_bytes_per_token(config) * _kv_layers(config)
            if kv_per_token > 0:
                rounded = (avail // kv_per_token // 1024) * 1024
                return max(_N_CTX_MIN, rounded)

    avail = _available_memory_bytes(gpu_active)
    if config.vram_model_gb > 0:
        avail = max(0, avail - int(config.vram_model_gb * 1024 ** 3))
    kv_per_token = _kv_bytes_per_token(config) * _kv_layers(config)
    if kv_per_token <= 0:
        return 32768
    rounded = (avail // kv_per_token // 1024) * 1024
    return max(_N_CTX_MIN, rounded)


def estimate_n_ctx(text: str, config: ModelConfig,
                   gpu_active: bool = False) -> tuple[int, str]:
    """
    Schätzt den benötigten Kontext aus der Textlänge.
    Gibt (n_ctx, Erklärungstext) zurück.

    Wenn rope_scaling_max_factor > 1.0 konfiguriert ist, wird der native
    Modell-Kontext (n_ctx_max) dynamisch auf bis zu rope_scaling_max_factor×
    ausgedehnt — aber nur so weit wie der Text + Prompt es erfordern.
    """
    ctx_native     = config.n_ctx_max
    scale_factor   = max(1.0, config.rope_scaling_max_factor)
    ctx_scaled_max = int(ctx_native * scale_factor)
    ctx_mem_max    = _max_ctx_from_memory(config, gpu_active)

    estimated_tokens = int(len(text) / _CHARS_PER_TOKEN)
    required  = estimated_tokens + config.context_reserve + config.prompt_overhead
    rounded   = ((required + 1023) // 1024) * 1024
    capped    = min(rounded, ctx_scaled_max, ctx_mem_max)
    result    = max(config.n_ctx_min, capped)

    if scale_factor > 1.0 and result > ctx_native:
        actual_factor = result / ctx_native
        limit_reason  = f"RoPE-Scaling ×{actual_factor:.2f}"
        if ctx_mem_max < ctx_scaled_max and ctx_mem_max < rounded:
            limit_reason = "Speicherlimit (RoPE aktiviert)"
    else:
        limit_reason = "Modell-Maximum"
        if ctx_mem_max < ctx_native and ctx_mem_max < rounded:
            limit_reason = "Speicherlimit"

    scale_info = (
        f", RoPE-Max {ctx_scaled_max:,} (×{scale_factor:.0f})"
        if scale_factor > 1.0 else ""
    )
    explanation = (
        f"~{estimated_tokens:,} Token geschätzt, "
        f"Modell-Nativ {ctx_native:,}{scale_info}, "
        f"Speicher-Max {ctx_mem_max:,} → "
        f"{result:,} Token ({limit_reason})"
    )
    return result, explanation
