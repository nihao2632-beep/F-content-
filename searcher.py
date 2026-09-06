# -*- coding: utf-8 -*-
"""
searcher.py —— 按内容搜索文件的核心引擎（无第三方依赖，纯标准库）。

支持：
  * 纯文本类文件（txt/md/csv/log/json/xml/html/源码……，自动识别 UTF-8/GBK/UTF-16/Big5）
  * Office Open XML（docx / xlsx / pptx，zip 内 XML 文本提取，无需 python-docx 等库）
  * OpenDocument（odt / ods / odp）
  * PDF（若环境中装有 pypdf 则使用其提取文字；否则退回二进制扫描）
  * 其它/旧版二进制（doc/xls/ppt/exe/……）直接对文件字节流搜索 UTF-8/GB18030/UTF-16LE 编码的关键字
"""
from __future__ import annotations

import html
import os
import re
import zipfile

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".log", ".csv", ".tsv", ".json", ".xml", ".yaml",
    ".yml", ".ini", ".cfg", ".conf", ".properties", ".py", ".js", ".jsx", ".ts",
    ".tsx", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs", ".php",
    ".rb", ".lua", ".pl", ".sh", ".bat", ".cmd", ".ps1", ".vbs", ".html", ".htm",
    ".css", ".scss", ".less", ".sql", ".r", ".swift", ".kt", ".vue", ".srt",
    ".vtt", ".inf", ".reg", ".toml", ".gradle", ".tex", ".nfo", ".dart",
}

ZIP_TEXT_EXTS = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}

# 二进制内容扫描时使用的关键字编码
RAW_ENCODINGS = ("utf-8", "gb18030", "utf-16-le")

# 文本抽取/解码的最大字节数（超过则退回二进制扫描，避免超大文件占内存）
MAX_TEXT_BYTES = 64 * 1024 * 1024  # 64 MB
# 单次读取的块大小
CHUNK_SIZE = 1024 * 1024  # 1 MB

_XML_ENTITY_RE = re.compile(r"&#(x?[0-9a-fA-F]+);")

# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------


def _unescape_xml(s: str) -> str:
    """还原 XML 实体（含 &#NNNN; / &#xHHHH; 数字实体）。"""
    if "&" in s:
        s = html.unescape(s)
        s = _XML_ENTITY_RE.sub(
            lambda m: chr(int(m.group(1), 16 if m.group(1)[:1].lower() == "x" else 10)),
            s,
        )
    return s


def _norm_kw(keyword: str, case_sensitive: bool) -> str:
    if not case_sensitive:
        return keyword.casefold()
    return keyword


def _needle_bytes(kw: str) -> list[bytes]:
    """返回关键字在各编码下的字节形式（去重）。"""
    out: list[bytes] = []
    for enc in RAW_ENCODINGS:
        try:
            b = kw.encode(enc)
        except (UnicodeEncodeError, LookupError):
            continue
        if b and b not in out:
            out.append(b)
    return out


def _raw_find_in_chunk(chunk: bytes, needles: list[bytes], case_sensitive: bool) -> bool:
    """在单个字节块中查找任一 needle。"""
    if not case_sensitive:
        chunk = chunk.lower()
    return any(chunk.find(n) != -1 for n in needles)


def raw_contains(path: str, kw: str, case_sensitive: bool = True) -> bool:
    """对任意文件做分块二进制扫描：文件字节里是否包含关键字（UTF-8/GB18030/UTF-16LE）。"""
    needles = _needle_bytes(kw)
    if not needles:
        return False
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    overlap = max(len(n) - 1 for n in needles)
    try:
        with open(path, "rb") as f:
            carry = b""
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                data = carry + chunk
                if _raw_find_in_chunk(data, needles, case_sensitive):
                    return True
                carry = data[-overlap:] if overlap else b""
    except OSError:
        return False
    return False


def _decode_text(data: bytes) -> str | None:
    """按常见编码顺序尝试解码，返回第一个可无损解码的文本。"""
    for enc in ("utf-8-sig", "utf-16", "gb18030", "big5"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    # 最后兜底：latin-1 永远可解码
    return data.decode("latin-1")


def _contains_in_text(text: str, kw: str) -> bool:
    return kw in text


def _extract_blocks(xml: str, block_pat: str, run_pat: str) -> list[str]:
    """把 XML 按“块”（段落/单元格）切分，块内拼接 run 文本，块之间用换行分隔。"""
    lines: list[str] = []
    for block in re.findall(block_pat, xml, flags=re.S):
        runs = re.findall(run_pat, block, flags=re.S)
        if runs:
            lines.append("".join(_unescape_xml(t) for t in runs))
    return lines


def _read_zip_texts(path: str, include_prefixes: tuple[str, ...],
                    block_pat: str, run_pat: str) -> str | None:
    """从 zip（docx/xlsx/pptx）中抽取文字：按块切分避免跨段误命中。"""
    parts: list[str] = []
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                low = name.lower()
                if not low.endswith(".xml"):
                    continue
                if include_prefixes and not low.startswith(include_prefixes):
                    continue
                try:
                    xml = z.read(name).decode("utf-8", "ignore")
                except Exception:
                    continue
                parts.extend(_extract_blocks(xml, block_pat, run_pat))
    except (zipfile.BadZipFile, OSError):
        return None
    text = "\n".join(parts)
    return text if text.strip() else None


def _docx_text(path: str) -> str | None:
    # Word 段落 <w:p>…</w:p>，段内文字 <w:t>…</w:t>（含页眉页脚/批注等 word/ 下所有 xml）
    return _read_zip_texts(
        path, ("word/",),
        block_pat=r"<w:p\b[^>]*>.*?</w:p>",
        run_pat=r"<w:t[^>]*>(.*?)</w:t>",
    )


def _xlsx_text(path: str) -> str | None:
    # 共享字符串项 <si>…</si> 与单元格内联串 <is>…</is>，取其中 <t>…</t>
    text = _read_zip_texts(
        path, ("xl/",),
        block_pat=r"<(?:si|is)\b[^>]*>.*?</(?:si|is)>",
        run_pat=r"<t[^>]*>(.*?)</t>",
    )
    if text:
        return text
    # 部分导出文件没有共享字符串，退回整文件 <t> 扫描（保留换行边界）
    return _read_zip_texts(
        path, ("xl/",),
        block_pat=r"<t[^>]*>(.*?)</t>",
        run_pat=r"<t[^>]*>(.*?)</t>",
    )


def _pptx_text(path: str) -> str | None:
    # PowerPoint 段落 <a:p>…</a:p>，段内文字 <a:t>…</a:t>
    return _read_zip_texts(
        path, ("ppt/",),
        block_pat=r"<a:p\b[^>]*>.*?</a:p>",
        run_pat=r"<a:t[^>]*>(.*?)</a:t>",
    )


def _odf_text(path: str) -> str | None:
    """OpenDocument：抽取 content.xml 的正文文本。"""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("content.xml").decode("utf-8", "ignore")
    except Exception:
        return None
    # 只保留标签之间的文字（去除所有标签与属性）
    text = re.sub(r"<[^>]+>", "", xml)
    text = _unescape_xml(text)
    return text if text.strip() else None


def _pdf_text(path: str) -> str | None:
    """PDF 文本抽取：优先 pypdf，失败返回 None（调用方再退回二进制扫描）。"""
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return None
    try:
        reader = PdfReader(path)
        out: list[str] = []
        for page in reader.pages[:400]:  # 最多 400 页，避免超大 PDF 卡死
            try:
                t = page.extract_text() or ""
                if t.strip():
                    out.append(t)
            except Exception:
                continue
        text = "\n".join(out)
        return text if text.strip() else None
    except Exception:
        return None


def extract_text(path: str) -> str | None:
    """按扩展名抽取可读文本；无法抽取或类型未知时返回 None。"""
    ext = os.path.splitext(path)[1].lower()
    try:
        size = os.path.getsize(path)
    except OSError:
        return None

    if ext in ZIP_TEXT_EXTS:
        try:
            with zipfile.ZipFile(path) as z:
                pass  # 校验是否为合法 zip
        except zipfile.BadZipFile:
            return None
        if ext == ".docx":
            return _docx_text(path)
        if ext == ".xlsx":
            return _xlsx_text(path)
        if ext == ".pptx":
            return _pptx_text(path)
        return _odf_text(path)

    if ext == ".pdf":
        return _pdf_text(path)

    if ext in TEXT_EXTS or size <= 4 * 1024 * 1024:  # 小文件也尝试当文本读
        if size > MAX_TEXT_BYTES:
            return None
        try:
            with open(path, "rb") as f:
                data = f.read(MAX_TEXT_BYTES)
        except OSError:
            return None
        return _decode_text(data)

    return None


# ---------------------------------------------------------------------------
# 遍历目录 + 搜索
# ---------------------------------------------------------------------------


def iter_files(root: str, recursive: bool = True, include_hidden: bool = False):
    """遍历目录得到文件绝对路径列表。"""
    if os.path.isfile(root):
        yield root
        return
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            if not include_hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                yield os.path.join(dirpath, fn)
    else:
        try:
            names = os.listdir(root)
        except OSError:
            return
        for fn in names:
            p = os.path.join(root, fn)
            if os.path.isfile(p):
                if not include_hidden and fn.startswith("."):
                    continue
                yield p


def _pdf_ocr_match(path: str, kw: str, stop_event=None) -> bool:
    """扫描版（无文字层）PDF：渲染页面 OCR 后查找关键字。"""
    try:
        import ocr
        if not ocr.ocr_available():
            return False
        text = ocr.pdf_ocr_text(path, stop_event=stop_event)
        if text:
            return _contains_in_text(_norm_kw(text, False), kw)
    except Exception:  # noqa: BLE001
        pass
    return False


def file_matches(path: str, keyword: str, case_sensitive: bool = True,
                 ocr_pdf: bool = False, stop_event=None) -> bool:
    """判断单个文件内容是否包含关键字（先结构化抽取，再二进制兜底）。"""
    kw = _norm_kw(keyword, case_sensitive)
    if not kw:
        return False

    ext = os.path.splitext(path)[1].lower()
    text = None
    if ext in ZIP_TEXT_EXTS or ext == ".pdf":
        text = extract_text(path)
        if text is not None:
            if _contains_in_text(_norm_kw(text, case_sensitive), kw):
                return True
        # PDF：提取文字很少/为空 => 疑似扫描版，用 OCR 识别后再查
        if ext == ".pdf" and ocr_pdf and (text is None or len(text.strip()) < 20):
            if _pdf_ocr_match(path, kw, stop_event=stop_event):
                return True
        # 结构化抽取失败/未命中 -> 继续二进制扫描兜底
        return raw_contains(path, keyword, case_sensitive)

    if ext in TEXT_EXTS:
        text = extract_text(path)
        if text is not None:
            return _contains_in_text(_norm_kw(text, case_sensitive), kw)
        # 大文件解码失败 -> 二进制
        return raw_contains(path, keyword, case_sensitive)

    # 其它（doc/xls/ppt/二进制等）直接二进制扫描
    return raw_contains(path, keyword, case_sensitive)


def search_folder(
    folder: str,
    keyword: str,
    recursive: bool = True,
    case_sensitive: bool = False,
    include_hidden: bool = False,
    extensions: str = "",
    max_file_size_mb: float = 0,
    match_filename: bool = False,
    ocr_pdf: bool = False,
    on_progress=None,
    stop_event=None,
) -> list[str]:
    """
    搜索文件夹，返回内容包含关键字的文件绝对路径列表（按路径排序）。

    extensions: 形如 ".docx,.txt,.pdf" 的空字符串表示不限制。
    match_filename: 同时把“文件名包含关键字”也算命中。
    ocr_pdf: 对疑似扫描版（无文字层）PDF 用 OCR 识别后再搜索（较慢，结果会缓存）。
    on_progress: 回调 (当前文件数, 已命中数, 当前文件名)。
    stop_event: threading.Event，置位则停止。
    """
    keyword = (keyword or "").strip()
    # 支持多关键词：每行一个关键词，命中任意一行即算（空行忽略）
    keywords = [ln.strip() for ln in keyword.splitlines()]
    keywords = [k for k in keywords if k] or [keyword]
    if not keywords:
        return []
    if not os.path.isdir(folder):
        return []

    allowed: set[str] | None = None
    if extensions and extensions.strip():
        allowed = {e.strip().lower() if e.strip().startswith(".") else "." + e.strip().lower()
                   for e in extensions.split(",") if e.strip()}

    max_bytes = 0.0
    try:
        max_bytes = float(max_file_size_mb) * 1024 * 1024
    except (TypeError, ValueError):
        max_bytes = 0.0

    hits: list[str] = []
    count = 0
    for path in iter_files(folder, recursive=recursive, include_hidden=include_hidden):
        if stop_event is not None and stop_event.is_set():
            break
        count += 1
        if on_progress:
            on_progress(count, len(hits), path)
        try:
            if not os.path.isfile(path):
                continue
            if os.path.islink(path):
                continue
            size = os.path.getsize(path)
            if max_bytes > 0 and size > max_bytes:
                continue
            ext = os.path.splitext(path)[1].lower()
            if allowed is not None and ext not in allowed:
                continue
        except OSError:
            continue

        matched = False
        base_low = os.path.basename(path).casefold()
        if match_filename and any(k.casefold() in base_low for k in keywords):
            matched = True
        if not matched:
            for k in keywords:
                try:
                    if file_matches(path, k, case_sensitive=case_sensitive,
                                    ocr_pdf=ocr_pdf, stop_event=stop_event):
                        matched = True
                        break
                except Exception:
                    continue
        if matched:
            hits.append(path)

    hits.sort(key=lambda p: p.casefold())
    return hits


# ---------------------------------------------------------------------------
# 命令行自测
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="按内容搜索文件（命令行测试模式）")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--no-recursive", action="store_true")
    ap.add_argument("--case-sensitive", action="store_true")
    ap.add_argument("--extensions", default="")
    ap.add_argument("--max-size-mb", type=float, default=0.0)
    args = ap.parse_args()

    results = search_folder(
        args.dir,
        args.text,
        recursive=not args.no_recursive,
        case_sensitive=args.case_sensitive,
        extensions=args.extensions,
        max_file_size_mb=args.max_size_mb,
    )
    for r in results:
        print(r)
    print(f"\n共命中 {len(results)} 个文件", file=sys.stderr)
