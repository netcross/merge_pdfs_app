from __future__ import annotations

import queue
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pypdf import PdfReader, PdfWriter


APP_TITLE = "폴더별 PDF 통합"
MERGED_SUFFIX = "_merged.pdf"


@dataclass(frozen=True)
class MergeTask:
    folder: Path
    output_path: Path
    input_pdfs: tuple[Path, ...]


@dataclass
class MergeSummary:
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    scanned_folders: int = 0


def natural_sort_key(path: Path) -> list[object]:
    parts = re.split(r"(\d+)", path.name.casefold())
    return [int(part) if part.isdigit() else part for part in parts]


def sanitize_filename_part(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip()
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip(" ._") or "folder"


def build_output_filename(root: Path, folder: Path) -> str:
    root = root.resolve()
    folder = folder.resolve()
    if folder == root:
        parts = [root.name]
    else:
        parts = [root.name, *folder.relative_to(root).parts]
    safe_parts = [sanitize_filename_part(part) for part in parts]
    return f"{'_'.join(safe_parts)}{MERGED_SUFFIX}"


def is_generated_pdf(path: Path) -> bool:
    return path.name.casefold().endswith(MERGED_SUFFIX)


def find_pdf_files(folder: Path) -> tuple[Path, ...]:
    pdfs = [
        child
        for child in folder.iterdir()
        if child.is_file()
        and child.suffix.casefold() == ".pdf"
        and not is_generated_pdf(child)
    ]
    return tuple(sorted(pdfs, key=natural_sort_key))


def scan_merge_tasks(root: Path) -> tuple[MergeTask, ...]:
    root = root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"폴더가 존재하지 않습니다: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"폴더가 아닙니다: {root}")

    tasks: list[MergeTask] = []
    for folder in [root, *sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: str(p).casefold())]:
        input_pdfs = find_pdf_files(folder)
        if not input_pdfs:
            continue
        output_path = folder / build_output_filename(root, folder)
        tasks.append(MergeTask(folder=folder, output_path=output_path, input_pdfs=input_pdfs))
    return tuple(tasks)


def count_pages(pdf_path: Path) -> int:
    return len(PdfReader(str(pdf_path)).pages)


def merge_pdf_files(input_pdfs: Iterable[Path], output_path: Path) -> int:
    writer = PdfWriter()
    total_pages = 0
    for pdf_path in input_pdfs:
        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            writer.add_page(page)
            total_pages += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    with temp_path.open("wb") as output_file:
        writer.write(output_file)
    temp_path.replace(output_path)
    return total_pages


def run_merge_tasks(
    tasks: Iterable[MergeTask],
    overwrite: bool,
    log: Callable[[str], None],
) -> MergeSummary:
    summary = MergeSummary()
    task_list = list(tasks)
    summary.scanned_folders = len(task_list)

    for task in task_list:
        if task.output_path.exists() and not overwrite:
            summary.skipped += 1
            log(f"[건너뜀] 이미 존재: {task.output_path}")
            continue

        try:
            pages = merge_pdf_files(task.input_pdfs, task.output_path)
        except Exception as exc:  # pypdf raises several parser-specific exceptions.
            summary.failed += 1
            log(f"[실패] {task.folder}")
            log(f"       원인: {exc}")
            continue

        summary.succeeded += 1
        log(f"[성공] {task.output_path} ({len(task.input_pdfs)}개 파일, {pages}페이지)")

    return summary


class PdfMergeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("860x620")
        self.minsize(760, 520)

        self.root_path = tk.StringVar()
        self.overwrite = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="루트 폴더를 선택하세요.")
        self.tasks: tuple[MergeTask, ...] = ()
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        header = ttk.Frame(self, padding=(16, 16, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="루트 폴더").grid(row=0, column=0, sticky="w")
        ttk.Entry(header, textvariable=self.root_path).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(header, text="찾아보기", command=self.choose_folder).grid(row=0, column=2)

        rule = (
            "출력 파일명: 선택한 폴더명부터 PDF가 있는 폴더명까지 '_'로 연결하고 "
            "'_merged.pdf'를 붙입니다. 예: A/B/C -> A_B_C_merged.pdf"
        )
        ttk.Label(header, text=rule, foreground="#444").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(10, 0)
        )

        options = ttk.Frame(self, padding=(16, 4, 16, 8))
        options.grid(row=1, column=0, sticky="ew")
        ttk.Checkbutton(options, text="기존 통합 PDF 덮어쓰기", variable=self.overwrite).pack(side="left")

        actions = ttk.Frame(self, padding=(16, 4, 16, 8))
        actions.grid(row=2, column=0, sticky="ew")
        self.scan_button = ttk.Button(actions, text="미리보기/스캔", command=self.scan)
        self.scan_button.pack(side="left")
        self.merge_button = ttk.Button(actions, text="병합 실행", command=self.merge, state="disabled")
        self.merge_button.pack(side="left", padx=(8, 0))

        status_frame = ttk.Frame(self, padding=(16, 0, 16, 8))
        status_frame.grid(row=3, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        ttk.Label(status_frame, textvariable=self.status).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(status_frame, mode="indeterminate")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        log_frame = ttk.Frame(self, padding=(16, 0, 16, 16))
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", height=18)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="PDF를 검색할 루트 폴더 선택")
        if selected:
            self.root_path.set(selected)
            self.tasks = ()
            self.merge_button.configure(state="disabled")
            self.status.set("스캔을 실행하세요.")
            self.clear_log()

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")

    def selected_root(self) -> Path | None:
        value = self.root_path.get().strip()
        if not value:
            messagebox.showwarning(APP_TITLE, "먼저 루트 폴더를 선택하세요.")
            return None
        return Path(value)

    def scan(self) -> None:
        root = self.selected_root()
        if root is None:
            return

        try:
            self.tasks = scan_merge_tasks(root)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            self.status.set("스캔 실패")
            return

        self.clear_log()
        if not self.tasks:
            self.status.set("PDF 파일이 들어있는 폴더를 찾지 못했습니다.")
            self.merge_button.configure(state="disabled")
            self.log("[정보] 병합 대상이 없습니다.")
            return

        for task in self.tasks:
            self.log(f"[대상] {task.folder}")
            self.log(f"       출력: {task.output_path.name}")
            self.log(f"       입력: {len(task.input_pdfs)}개 PDF")

        self.status.set(f"병합 대상 폴더 {len(self.tasks)}개를 찾았습니다.")
        self.merge_button.configure(state="normal")

    def merge(self) -> None:
        if not self.tasks:
            self.scan()
            if not self.tasks:
                return

        self.scan_button.configure(state="disabled")
        self.merge_button.configure(state="disabled")
        self.progress.start(10)
        self.status.set("병합 중입니다...")
        self.log("")
        self.log("[시작] PDF 병합을 시작합니다.")

        self.worker_thread = threading.Thread(target=self._merge_worker, daemon=True)
        self.worker_thread.start()
        self.after(100, self._poll_worker)

    def _merge_worker(self) -> None:
        def queue_log(message: str) -> None:
            self.worker_queue.put(("log", message))

        summary = run_merge_tasks(self.tasks, self.overwrite.get(), queue_log)
        self.worker_queue.put(("done", summary))

    def _poll_worker(self) -> None:
        try:
            while True:
                event, payload = self.worker_queue.get_nowait()
                if event == "log":
                    self.log(str(payload))
                elif event == "done":
                    self._finish_merge(payload)  # type: ignore[arg-type]
                    return
        except queue.Empty:
            pass
        self.after(100, self._poll_worker)

    def _finish_merge(self, summary: MergeSummary) -> None:
        self.progress.stop()
        self.scan_button.configure(state="normal")
        self.merge_button.configure(state="normal" if self.tasks else "disabled")
        message = (
            f"완료: 성공 {summary.succeeded}개, 건너뜀 {summary.skipped}개, "
            f"실패 {summary.failed}개"
        )
        self.status.set(message)
        self.log(f"[완료] {message}")
        messagebox.showinfo(APP_TITLE, message)


def main() -> None:
    app = PdfMergeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
