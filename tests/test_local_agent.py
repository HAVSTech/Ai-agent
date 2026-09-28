from pathlib import Path

from local_agent.services.file_manager import FileManager
from local_agent.services.queue_manager import JobStatus, PrintItem, PrintQueue


def test_file_manager_sorts_and_filters(tmp_path: Path):
    (tmp_path / "b.pdf").write_text("b")
    (tmp_path / "a.pdf").write_text("a")
    (tmp_path / "draft.pdf").write_text("draft")
    (tmp_path / "notes.txt").write_text("notes")

    manager = FileManager([str(tmp_path)], max_files_per_job=10)
    files = manager.list_files(str(tmp_path), {".pdf"}, ["draft"])

    assert [p.name for p in files] == ["a.pdf", "b.pdf"]


def test_file_manager_blocks_outside_root(tmp_path: Path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()

    manager = FileManager([str(allowed)])
    try:
        manager.list_files(str(outside), {".pdf"})
    except PermissionError:
        pass
    else:
        raise AssertionError("Expected outside-root access to be rejected")


def test_queue_stops_after_failure(tmp_path: Path):
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.pdf"
    first.write_text("a")
    second.write_text("b")

    queue = PrintQueue([PrintItem(first, {}), PrintItem(second, {})])
    calls = []

    def printer(item):
        calls.append(item.path.name)
        if item.path.name == "a.pdf":
            raise RuntimeError("printer error")
        return 1

    queue.run(printer)

    assert calls == ["a.pdf"]
    assert queue.items[0].status == JobStatus.FAILED
    assert queue.items[1].status == JobStatus.QUEUED
