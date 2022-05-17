import pytest

from dvc.fs import Path


@pytest.mark.parametrize("prefix", ["", "/"])
@pytest.mark.parametrize("postfix", ["", "/"])
@pytest.mark.parametrize(
    "path,expected",
    [
        ("path", ("path",)),
        ("some/path", ("some", "path")),
    ],
)
def test_parts_posix(prefix, postfix, path, expected):
    assert Path("/").parts(prefix + path + postfix) == tuple(prefix) + expected


@pytest.mark.parametrize("postfix", ["", "\\"])
@pytest.mark.parametrize(
    "path,expected",
    [
        ("path", ("path",)),
        ("c:\\path", ("c:", "\\", "path")),
        ("some\\path", ("some", "path")),
    ],
)
def test_parts_nt(postfix, path, expected):
    assert Path("\\").parts(path + postfix) == expected


@pytest.mark.parametrize("postfix", ["", "/"])
@pytest.mark.parametrize(
    "path,expected",
    [
        ("", ""),
        ("/file", "file"),
        ("/path/to/file", "file"),
        (".", "."),
        ("..", ".."),
    ],
)
def test_name(postfix, path, expected):
    assert Path("/").name(path + postfix) == expected


@pytest.mark.parametrize("postfix", ["", "\\"])
@pytest.mark.parametrize(
    "path,expected",
    [
        ("", ""),
        ("path", "path"),
        ("c:\\file", "file"),
        ("c:\\path\\to\\file", "file"),
        ("some\\path", "path"),
    ],
)
def test_name_nt(postfix, path, expected):
    assert Path("\\").name(path + postfix) == expected
