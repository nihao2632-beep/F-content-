# -*- coding: utf-8 -*-
"""
main.py —— 创可贴制作-内容搜索打开工具（GUI 主程序）

功能：输入一段文字 -> 选择一个文件夹 -> 找出文件夹下“内容包含这段文字”的所有文件
      -> 用系统默认程序全部打开。
打包目标：Windows 双击运行的 .exe（详见 README.md / build_exe.bat）。
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from searcher import search_folder

APP_NAME = "创可贴制作-内容搜索打开工具"
APP_VERSION = "1.01"
APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))


def resource_path(name: str) -> str:
    """取资源文件路径：PyInstaller 单文件打包时资源在 _MEIPASS 临时目录中。"""
    base = getattr(sys, "_MEIPASS", None) or APP_DIR
    return os.path.join(base, name)


# ---------------------------------------------------------------------------
# 打开文件（跨平台）
# ---------------------------------------------------------------------------

def open_file(path: str) -> bool:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def open_paths(paths: list[str]) -> tuple[int, int]:
    ok = 0
    for p in paths:
        if open_file(p):
            ok += 1
    return ok, len(paths)


# ---------------------------------------------------------------------------
# 配置读写（记住上次使用的文件夹/关键词）
# ---------------------------------------------------------------------------

def config_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "ContentSearchOpener")
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        folder = APP_DIR
    return os.path.join(folder, "config.json")


def load_config() -> dict:
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        self.stop_event = threading.Event()
        self.search_thread: threading.Thread | None = None
        self.result_paths: list[str] = []
        self.result_items: list[str] = []
        self._status_job: str | None = None

        root.title(f"{APP_NAME} V{APP_VERSION}")
        root.geometry("860x640")
        root.minsize(720, 540)
        try:
            root.iconbitmap(default=resource_path("app.ico"))
        except Exception:
            pass

        font = ("Microsoft YaHei UI", 10)
        self._build_ui(font)
        self._load_ui_state()

    # ---------------- UI ----------------

    def _build_ui(self, font):
        pad = {"padx": 10, "pady": 4}
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        # 搜索内容
        f1 = ttk.LabelFrame(outer, text=" ① 输入要查找的内容 ", padding=6)
        f1.pack(fill="x", **pad)
        self.txt_keyword = tk.Text(f1, height=3, font=font, wrap="word",
                                   undo=True, relief="solid", bd=1)
        self.txt_keyword.pack(fill="x")
        ttk.Label(f1, text="提示：查找“内容包含以上文字”的文件；多个关键词请换行，命中任意一行即算。",
                  foreground="#666666").pack(anchor="w", pady=(3, 0))

        # 搜索文件夹
        f2 = ttk.LabelFrame(outer, text=" ② 选择要搜索的文件夹 ", padding=6)
        f2.pack(fill="x", **pad)
        row = ttk.Frame(f2)
        row.pack(fill="x")
        self.var_dir = tk.StringVar()
        self.ent_dir = ttk.Entry(row, textvariable=self.var_dir, font=font)
        self.ent_dir.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(row, text="浏览…", command=self._choose_dir).pack(side="left")
        ttk.Button(row, text="用上次目录", command=self._use_last_dir).pack(side="left", padx=(6, 0))

        # 选项
        f3 = ttk.LabelFrame(outer, text=" ③ 搜索选项 ", padding=6)
        f3.pack(fill="x", **pad)
        self.var_recursive = tk.BooleanVar(value=True)
        self.var_ci = tk.BooleanVar(value=True)
        self.var_filename = tk.BooleanVar(value=False)
        self.var_hidden = tk.BooleanVar(value=False)
        self.var_ocr = tk.BooleanVar(value=True)
        ttk.Checkbutton(f3, text="包含子文件夹", variable=self.var_recursive).grid(row=0, column=0, sticky="w", padx=(0, 18))
        ttk.Checkbutton(f3, text="忽略大小写（英文）", variable=self.var_ci).grid(row=0, column=1, sticky="w", padx=(0, 18))
        ttk.Checkbutton(f3, text="包含文件名", variable=self.var_filename).grid(row=0, column=2, sticky="w", padx=(0, 18))
        ttk.Checkbutton(f3, text="包含隐藏文件/目录", variable=self.var_hidden).grid(row=0, column=3, sticky="w")
        ttk.Checkbutton(f3, text="扫描版PDF用OCR识别（无文字层也能搜，较慢）", variable=self.var_ocr).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(f3, text="只搜索类型(空=全部, 如 .docx,.txt,.pdf)：").grid(row=1, column=0, sticky="e", pady=(6, 0))
        self.var_ext = tk.StringVar(value="")
        ttk.Entry(f3, textvariable=self.var_ext, width=28).grid(row=1, column=1, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(f3, text="单个文件上限(MB, 0=不限)：").grid(row=1, column=3, sticky="e", pady=(6, 0))
        self.var_maxmb = tk.StringVar(value="200")
        ttk.Spinbox(f3, from_=0, to=99999, textvariable=self.var_maxmb, width=8).grid(row=1, column=4, sticky="w", pady=(6, 0))
        f3.columnconfigure(4, weight=1)

        # 按钮
        f4 = ttk.Frame(outer)
        f4.pack(fill="x", **pad)
        self.btn_search_open = ttk.Button(f4, text="🔍 搜索并打开全部", command=self._on_search_open)
        self.btn_search_open.pack(side="left")
        self.btn_search = ttk.Button(f4, text="仅搜索（不打开）", command=self._on_search_only)
        self.btn_search.pack(side="left", padx=(8, 0))
        self.btn_stop = ttk.Button(f4, text="停止", command=self._on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(8, 0))
        ttk.Button(f4, text="打开选中的文件", command=self._open_selected).pack(side="left", padx=(8, 0))
        ttk.Button(f4, text="复制选中路径", command=self._copy_selected).pack(side="left", padx=(8, 0))
        ttk.Button(f4, text="清空结果", command=self._clear_results).pack(side="left", padx=(8, 0))

        # 结果
        f5 = ttk.LabelFrame(outer, text=" 搜索结果 ", padding=6)
        f5.pack(fill="both", expand=True, **pad)
        cols = ("name", "path")
        self.tree = ttk.Treeview(f5, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("name", text="文件名")
        self.tree.heading("path", text="完整路径")
        self.tree.column("name", width=260, anchor="w")
        self.tree.column("path", width=520, anchor="w")
        vsb = ttk.Scrollbar(f5, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self._open_selected())
        self.tree.bind("<Return>", lambda e: self._open_selected())

        # 状态栏
        self.status = tk.StringVar(value="就绪。")
        bar = ttk.Label(outer, textvariable=self.status, anchor="w", relief="sunken")
        bar.pack(fill="x", **pad)

    # ---------------- 状态持久化 ----------------

    def _load_ui_state(self):
        if self.cfg.get("dir"):
            self.var_dir.set(self.cfg["dir"])
        if self.cfg.get("keyword"):
            self.txt_keyword.insert("1.0", self.cfg["keyword"])
        for var, key in ((self.var_recursive, "recursive"), (self.var_ci, "ci"),
                         (self.var_filename, "filename"), (self.var_hidden, "hidden"),
                         (self.var_ocr, "ocr_pdf")):
            if key in self.cfg:
                var.set(bool(self.cfg[key]))
        if self.cfg.get("ext"):
            self.var_ext.set(self.cfg["ext"])
        if self.cfg.get("maxmb"):
            self.var_maxmb.set(str(self.cfg["maxmb"]))

    def _save_state(self):
        self.cfg.update({
            "dir": self.var_dir.get().strip(),
            "keyword": self.txt_keyword.get("1.0", "end").strip(),
            "recursive": bool(self.var_recursive.get()),
            "ci": bool(self.var_ci.get()),
            "filename": bool(self.var_filename.get()),
            "hidden": bool(self.var_hidden.get()),
            "ocr_pdf": bool(self.var_ocr.get()),
            "ext": self.var_ext.get().strip(),
            "maxmb": self.var_maxmb.get().strip(),
        })
        save_config(self.cfg)

    # ---------------- 事件 ----------------

    def _choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.var_dir.get() or APP_DIR,
                                    title="选择要搜索的文件夹")
        if d:
            self.var_dir.set(d)

    def _use_last_dir(self):
        if self.cfg.get("dir"):
            self.var_dir.set(self.cfg["dir"])
        else:
            messagebox.showinfo(APP_NAME, "还没有记录过上次使用的目录。")

    def _on_search_open(self):
        self._start_search(open_after=True)

    def _on_search_only(self):
        self._start_search(open_after=False)

    def _collect_options(self):
        folder = self.var_dir.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning(APP_NAME, "请先选择一个有效的文件夹。")
            return None
        try:
            maxmb = float(self.var_maxmb.get().strip() or "0")
        except ValueError:
            maxmb = 0.0
        return {
            "folder": folder,
            "keyword": self.txt_keyword.get("1.0", "end").strip(),
            "recursive": bool(self.var_recursive.get()),
            "case_sensitive": not bool(self.var_ci.get()),
            "include_hidden": bool(self.var_hidden.get()),
            "extensions": self.var_ext.get().strip(),
            "max_file_size_mb": maxmb,
            "match_filename": bool(self.var_filename.get()),
            "ocr_pdf": bool(self.var_ocr.get()),
        }

    def _start_search(self, open_after: bool):
        if self.search_thread and self.search_thread.is_alive():
            messagebox.showinfo(APP_NAME, "搜索正在进行中，请先停止或等待完成。")
            return
        opts = self._collect_options()
        if opts is None:
            return
        if not opts["keyword"]:
            messagebox.showwarning(APP_NAME, "请先输入要查找的内容。")
            return

        self._save_state()
        self._clear_results()
        self.stop_event = threading.Event()
        self.btn_search_open.config(state="disabled")
        self.btn_search.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status.set("正在搜索…")
        q: queue.Queue = queue.Queue()
        self.search_thread = threading.Thread(
            target=self._worker, args=(opts, open_after, q), daemon=True)
        self.search_thread.start()
        self.root.after(100, lambda: self._pump(q, open_after))

    def _worker(self, opts, open_after: bool, q: queue.Queue):
        last = [0, 0, ""]

        def progress(count, hits, path):
            # 节流：避免高频刷新卡 UI
            if count - last[0] >= 5 or hits != last[1] or path != last[2]:
                last[0], last[1], last[2] = count, hits, path
                q.put(("progress", count, hits, path))

        stopped = False
        try:
            hits = search_folder(
                folder=opts["folder"],
                keyword=opts["keyword"],
                recursive=opts["recursive"],
                case_sensitive=opts["case_sensitive"],
                include_hidden=opts["include_hidden"],
                extensions=opts["extensions"],
                max_file_size_mb=opts["max_file_size_mb"],
                match_filename=opts["match_filename"],
                ocr_pdf=opts.get("ocr_pdf", False),
                on_progress=progress,
                stop_event=self.stop_event,
            )
            stopped = self.stop_event.is_set()
        except Exception as e:  # noqa
            q.put(("error", str(e)))
            return
        # 用户手动停止时不再自动打开已找到的部分文件
        q.put(("done", hits, open_after and not stopped, stopped))

    def _pump(self, q: queue.Queue, open_after: bool):
        stopped = False
        try:
            while True:
                msg = q.get_nowait()
                if msg[0] == "progress":
                    _, count, hits, path = msg
                    self.status.set(f"已扫描 {count} 个文件，命中 {hits} 个… 正在检查：{os.path.basename(path)}")
                elif msg[0] == "done":
                    _, hits, _open, _stopped = msg
                    self._finish_search(hits, _open, _stopped)
                    stopped = True
                    break
                elif msg[0] == "error":
                    self.status.set("搜索出错。")
                    messagebox.showerror(APP_NAME, f"搜索出错：\n{msg[1]}")
                    stopped = True
                    break
        except queue.Empty:
            pass
        if not stopped:
            if self.stop_event.is_set():
                self.status.set("已停止。")
            self.root.after(100, lambda: self._pump(q, open_after))

    def _finish_search(self, hits: list[str], open_after: bool, stopped: bool = False):
        self.btn_search_open.config(state="normal")
        self.btn_search.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.search_thread = None
        self.result_paths = hits
        for p in hits:
            self.tree.insert("", "end", values=(os.path.basename(p), p))
        if stopped:
            self.status.set(f"已停止：已扫描到 {len(hits)} 个命中文件（未自动打开）。")
            return
        if not hits:
            self.status.set("搜索完成：没有找到包含该内容的文件。")
            messagebox.showinfo(APP_NAME, "没有找到内容包含该文字的文件。")
            return
        self.status.set(f"搜索完成：共命中 {len(hits)} 个文件。")
        if open_after:
            if messagebox.askyesno(
                    APP_NAME,
                    f"共找到 {len(hits)} 个文件：\n\n"
                    + "\n".join(os.path.basename(p) for p in hits[:15])
                    + ("\n…" if len(hits) > 15 else "")
                    + f"\n\n是否用系统默认程序全部打开这 {len(hits)} 个文件？"):
                self._open_paths(hits)

    def _open_paths(self, paths: list[str]):
        ok, total = open_paths(paths)
        if ok < total:
            messagebox.showwarning(APP_NAME, f"成功打开 {ok}/{total} 个文件，部分文件打开失败。")
        else:
            self.status.set(f"已打开全部 {total} 个文件。")

    def _open_selected(self):
        sel = self._selected_paths()
        if sel:
            self._open_paths(sel)
        else:
            messagebox.showinfo(APP_NAME, "请先在结果列表中选中文件（可按住 Ctrl 多选）。")

    def _selected_paths(self) -> list[str]:
        sel = set(self.tree.selection())
        return [self.result_paths[self.tree.index(i)] for i in sel
                if self.tree.index(i) < len(self.result_paths)]

    def _copy_selected(self):
        sel = self._selected_paths()
        if not sel:
            messagebox.showinfo(APP_NAME, "请先选中要复制路径的文件。")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(sel))
        self.status.set(f"已复制 {len(sel)} 条路径到剪贴板。")

    def _clear_results(self):
        self.tree.delete(*self.tree.get_children())
        self.result_paths = []
        self.status.set("结果已清空。")

    def _on_stop(self):
        self.stop_event.set()
        self.status.set("正在停止…")
        self.btn_stop.config(state="disabled")


# ---------------------------------------------------------------------------
# 命令行模式（自测/批量使用）
# ---------------------------------------------------------------------------

def run_cli(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=APP_NAME + "（命令行模式）")
    ap.add_argument("--dir", required=True, help="要搜索的文件夹")
    ap.add_argument("--text", required=True, help="要查找的内容")
    ap.add_argument("--no-recursive", action="store_true")
    ap.add_argument("--case-sensitive", action="store_true")
    ap.add_argument("--filename", action="store_true", help="文件名包含关键词也算命中")
    ap.add_argument("--no-ocr", action="store_true", help="不识别扫描版PDF")
    ap.add_argument("--extensions", default="")
    ap.add_argument("--max-size-mb", type=float, default=200.0)
    ap.add_argument("--open", action="store_true", help="搜索后打开全部命中文件")
    args = ap.parse_args(argv)

    hits = search_folder(
        folder=args.dir,
        keyword=args.text,
        recursive=not args.no_recursive,
        case_sensitive=args.case_sensitive,
        include_hidden=False,
        extensions=args.extensions,
        max_file_size_mb=args.max_size_mb,
        match_filename=args.filename,
        ocr_pdf=not args.no_ocr,
    )
    for h in hits:
        print(h)
    print(f"\n共命中 {len(hits)} 个文件")
    if args.open and hits:
        ok, total = open_paths(hits)
        print(f"已打开 {ok}/{total} 个文件")
    return 0


def main() -> int:
    if "--cli" in sys.argv[1:]:
        rest = [a for a in sys.argv[1:] if a != "--cli"]
        return run_cli(rest)

    # Windows 高 DPI 适配
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore
        except Exception:
            pass

    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
