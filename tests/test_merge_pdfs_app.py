import unittest
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from pypdf import PdfReader, PdfWriter

from merge_pdfs_app import (
    build_output_filename,
    find_pdf_files,
    run_merge_tasks,
    scan_merge_tasks,
)


TEMP_ROOT = Path(__file__).resolve().parents[1] / ".test_tmp"


@contextmanager
def temp_directory() -> Iterator[str]:
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT / f"case_{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


def create_pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as output:
        writer.write(output)


class PdfMergeAppTests(unittest.TestCase):
    def test_output_filename_includes_root_and_relative_folder(self) -> None:
        with temp_directory() as tmp:
            root = Path(tmp) / "A"
            folder = root / "B" / "C"
            folder.mkdir(parents=True)

            self.assertEqual(build_output_filename(root, folder), "A_B_C_merged.pdf")

    def test_scan_finds_each_pdf_folder_and_excludes_generated_pdfs(self) -> None:
        with temp_directory() as tmp:
            root = Path(tmp) / "Root"
            target = root / "Topic" / "Level"
            target.mkdir(parents=True)
            create_pdf(target / "002.pdf", 1)
            create_pdf(target / "001.pdf", 1)
            create_pdf(target / "Root_Topic_Level_merged.pdf", 5)

            tasks = scan_merge_tasks(root)

            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].output_path.name, "Root_Topic_Level_merged.pdf")
            self.assertEqual([path.name for path in tasks[0].input_pdfs], ["001.pdf", "002.pdf"])

    def test_merge_creates_output_with_expected_page_count(self) -> None:
        with temp_directory() as tmp:
            root = Path(tmp) / "Root"
            target = root / "Topic"
            target.mkdir(parents=True)
            create_pdf(target / "a.pdf", 2)
            create_pdf(target / "b.pdf", 3)

            tasks = scan_merge_tasks(root)
            logs: list[str] = []
            summary = run_merge_tasks(tasks, overwrite=False, log=logs.append)

            self.assertEqual(summary.succeeded, 1)
            self.assertEqual(summary.skipped, 0)
            self.assertEqual(summary.failed, 0)
            output = target / "Root_Topic_merged.pdf"
            self.assertTrue(output.exists())
            self.assertEqual(len(PdfReader(str(output)).pages), 5)

    def test_existing_output_is_skipped_without_overwrite(self) -> None:
        with temp_directory() as tmp:
            root = Path(tmp) / "Root"
            root.mkdir()
            create_pdf(root / "a.pdf", 1)
            create_pdf(root / "Root_merged.pdf", 1)

            tasks = scan_merge_tasks(root)
            logs: list[str] = []
            summary = run_merge_tasks(tasks, overwrite=False, log=logs.append)

            self.assertEqual(summary.succeeded, 0)
            self.assertEqual(summary.skipped, 1)
            self.assertEqual(summary.failed, 0)

    def test_generated_pdfs_are_not_inputs(self) -> None:
        with temp_directory() as tmp:
            folder = Path(tmp)
            create_pdf(folder / "source.pdf", 1)
            create_pdf(folder / "Folder_merged.pdf", 1)

            pdfs = find_pdf_files(folder)

            self.assertEqual([path.name for path in pdfs], ["source.pdf"])


if __name__ == "__main__":
    unittest.main()
