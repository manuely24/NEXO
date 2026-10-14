import pytest

from nexo.tools.fs_tools import FsListTool, FsReadTool, FsWriteTool


def test_write_read_and_list_are_scoped_to_workspace(tmp_path):
    write = FsWriteTool(tmp_path)
    read = FsReadTool(tmp_path)
    list_files = FsListTool(tmp_path)

    write.run({"path": "data/notes.txt", "content": "local note"})

    assert read.run({"path": "data/notes.txt"}) == "local note"
    assert "notes.txt" in list_files.run({"path": "data"})


def test_filesystem_tool_rejects_parent_traversal(tmp_path):
    tool = FsReadTool(tmp_path)

    with pytest.raises(PermissionError):
        tool.run({"path": "../outside.txt"})