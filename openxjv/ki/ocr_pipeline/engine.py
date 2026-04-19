"""
OCR engine wrapper around RapidOCR (>= 3.x) with onnxruntime backend.

Provider selection order (automatic, no recompilation required):
  1. CUDAExecutionProvider   (NVIDIA GPU)
  2. DmlExecutionProvider    (Windows DirectML – AMD/Intel/NVIDIA)
  3. CoreMLExecutionProvider (Apple Silicon / macOS)
  4. CPUExecutionProvider    (universal fallback)

Models are loaded from the bundled `models/` directory.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_CONF_THRESHOLD = 0.6

_PROVIDER_FLAG: dict[str, str] = {
    "CUDAExecutionProvider":   "use_cuda",
    "DmlExecutionProvider":    "use_dml",
    "CoreMLExecutionProvider": "use_coreml",
}


def _models_dir() -> Path:
    """Return path to bundled models; works both normally and under PyInstaller."""
    return Path(__file__).parent / "models"


def _detect_provider() -> str:
    """Return the best available onnxruntime provider name."""
    try:
        import onnxruntime as ort
        available = set(ort.get_available_providers())
    except Exception:
        return "CPUExecutionProvider"

    for p in ["CUDAExecutionProvider", "DmlExecutionProvider", "CoreMLExecutionProvider"]:
        if p in available:
            return p
    return "CPUExecutionProvider"


class OcrEngine:
    """
    Initialises RapidOCR with bundled models and the best available
    execution provider.
    """

    def __init__(self, conf_threshold: float = _CONF_THRESHOLD) -> None:
        models = _models_dir()
        det = str(models / "ch_PP-OCRv5_mobile_det.onnx")
        rec = str(models / "latin_PP-OCRv5_rec_mobile_infer.onnx")
        cls = str(models / "cls_infer.onnx")

        for path, label in [(det, "det"), (rec, "rec"), (cls, "cls")]:
            if not Path(path).exists():
                raise FileNotFoundError(f"OCR model file not found ({label}): {path}")

        self.active_provider = _detect_provider()

        logger.info(
            "OcrEngine initialising — provider: %s | det: %s | rec: %s",
            self.active_provider, Path(det).name, Path(rec).name,
        )

        try:
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise ImportError("rapidocr is required: pip install rapidocr") from exc

        provider_flag = _PROVIDER_FLAG.get(self.active_provider)
        params: dict = {
            "Det.model_path": det,
            "Rec.model_path": rec,
            "Cls.model_path": cls,
        }
        if provider_flag:
            params[f"EngineConfig.onnxruntime.{provider_flag}"] = True

        self._ocr = RapidOCR(params=params)
        self._conf_threshold = conf_threshold

        # Read back the provider actually used (rapidocr may silently fall back to CPU).
        try:
            actual = self._ocr.text_det.session.session.get_providers()
            self.active_provider = actual[0] if actual else self.active_provider
        except Exception:
            pass

        logger.info("Active provider (actual): %s", self.active_provider)

    def run(self, image: np.ndarray) -> Tuple[str, float, int, List[str]]:
        """
        Run OCR on a single image (H x W x 3, uint8, RGB).

        Returns:
            text        – extracted text (newline-separated lines)
            avg_conf    – average confidence (0.0–1.0); -1.0 if no blocks
            block_count – number of detected text blocks
            warnings    – list of low-confidence block warnings
        """
        warnings: List[str] = []
        try:
            result = self._ocr(image, use_cls=True)
        except Exception as exc:
            logger.error("OCR inference error: %s", exc, exc_info=True)
            return "", -1.0, 0, [f"Inference error: {exc}"]

        txts   = getattr(result, "txts",   None)
        scores = getattr(result, "scores", None)

        if not txts:
            return "", -1.0, 0, []

        lines: List[str] = []
        confidences: List[float] = []

        for i, text_str in enumerate(txts):
            conf = float(scores[i]) if scores and scores[i] is not None else 0.0
            lines.append(str(text_str))
            confidences.append(conf)
            if conf < self._conf_threshold:
                warnings.append(f"Low-confidence block ({conf:.2f}): \"{text_str[:40]}\"")

        avg_conf = sum(confidences) / len(confidences)
        return "\n".join(lines), avg_conf, len(lines), warnings
