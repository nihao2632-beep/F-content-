# -*- coding: utf-8 -*-
"""
ocr.py —— 扫描版（图片型、无文字层）PDF 的 OCR 识别。

原理：把 PDF 每页渲染成图片，再用离线 OCR 引擎识别文字并缓存结果。
依赖（打包 exe 时已附带，无需联网）：
  * pypdfium2           —— 将 PDF 页面渲染为图片
  * rapidocr_onnxruntime —— 中英文离线 OCR
若以上依赖缺失，本模块自动降级为“不可用”，不影响其它搜索功能。
"""
from __future__ import annotations

import hashlib
import os
import threading

OCR_MAX_PAGES = 60     # 单个 PDF 最多识别页数，避免超大文件卡死
OCR_DPI = 200          # 渲染分辨率（越高越清晰、越慢）

_engine = None
_engine_lock = threading.Lock()
_import_error: str | None = None


def ocr_available() -> bool:
    """OCR 依赖是否可用（避免每次调用都尝试导入）。"""
    global _import_error
    if _import_error is not None:
        return False
    try:
        import pypdfium2  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception as e:  # noqa: BLE001
        _import_error = str(e)
        return False


def _get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
    return _engine


def _cache_dir() -> str | None:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "ContentSearchOpener", "ocr_cache")
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except OSError:
        return None


def _cache_path(path: str, size: int, mtime: int) -> str | None:
    d = _cache_dir()
    if not d:
        return None
    key = hashlib.sha1(f"{path}|{size}|{mtime}".encode("utf-8", "ignore")).hexdigest()
    return os.path.join(d, key + ".txt")


def pdf_ocr_text(path: str, max_pages: int = OCR_MAX_PAGES,
                 dpi: int = OCR_DPI, stop_event=None) -> str | None:
    """
    识别扫描版 PDF，返回整篇识别文字；失败/无文字返回 None。
    结果会按“文件路径+大小+修改时间”缓存，重复搜索不会重复识别。
    """
    if not ocr_available():
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    cache_file = _cache_path(path, st.st_size, int(st.st_mtime))
    if cache_file and os.path.isfile(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = f.read()
            return cached if cached.strip() else None
        except OSError:
            pass

    try:
        import pypdfium2 as pdfium
        import numpy as np
        engine = _get_engine()
        pdf = pdfium.PdfDocument(path)
        total = len(pdf)
        n = min(total, max_pages) if max_pages and max_pages > 0 else total
        parts: list[str] = []
        for i in range(n):
            if stop_event is not None and stop_event.is_set():
                break
            try:
                page = pdf[i]
                img = page.render(scale=dpi / 72.0).to_pil()
                result, _ = engine(np.array(img.convert("RGB")))
                if result:
                    parts.append("\n".join(str(line[1]) for line in result))
            except Exception:  # noqa: BLE001  单页失败跳过，不中断整个文件
                continue
        pdf.close()
    except Exception:  # noqa: BLE001
        return None

    text = "\n".join(parts)
    if cache_file:
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass
    return text if text.strip() else None
