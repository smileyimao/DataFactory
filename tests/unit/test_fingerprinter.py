# tests/unit/test_fingerprinter.py — fingerprinter.compute() 单元测试
"""验证指纹计算的一致性、去重语义和错误处理。"""
import os
import pytest

pytestmark = pytest.mark.unit


def test_same_file_same_hash(tmp_path):
    """同一文件两次计算结果相同。"""
    from utils import fingerprinter

    f = tmp_path / "a.bin"
    f.write_bytes(b"hello world")
    assert fingerprinter.compute(str(f)) == fingerprinter.compute(str(f))


def test_different_content_different_hash(tmp_path):
    """内容不同的文件指纹不同。"""
    from utils import fingerprinter

    f1 = tmp_path / "a.bin"
    f2 = tmp_path / "b.bin"
    f1.write_bytes(b"content-a")
    f2.write_bytes(b"content-b")
    assert fingerprinter.compute(str(f1)) != fingerprinter.compute(str(f2))


def test_identical_content_same_hash(tmp_path):
    """内容完全相同的两个不同文件，指纹应相同（去重依据）。"""
    from utils import fingerprinter

    data = b"duplicate content"
    f1 = tmp_path / "copy1.bin"
    f2 = tmp_path / "copy2.bin"
    f1.write_bytes(data)
    f2.write_bytes(data)
    assert fingerprinter.compute(str(f1)) == fingerprinter.compute(str(f2))


def test_nonexistent_file_returns_empty():
    """文件不存在时返回空字符串，不抛异常。"""
    from utils import fingerprinter

    result = fingerprinter.compute("/nonexistent/path/file.mp4")
    assert result == ""


def test_empty_file(tmp_path):
    """空文件也能正常计算（返回非空 hash）。"""
    from utils import fingerprinter

    f = tmp_path / "empty.bin"
    f.write_bytes(b"")
    result = fingerprinter.compute(str(f))
    assert isinstance(result, str)
    assert len(result) == 32  # MD5 十六进制长度


def test_large_file_uses_sampling(tmp_path):
    """超过 2MB 的文件走头尾采样，结果仍为合法 MD5。"""
    from utils import fingerprinter

    f = tmp_path / "large.bin"
    f.write_bytes(b"X" * (3 * 1024 * 1024))  # 3 MB
    result = fingerprinter.compute(str(f))
    assert len(result) == 32


def test_large_file_sampling_differs_from_small(tmp_path):
    """头尾内容不同的两个大文件，指纹应不同。"""
    from utils import fingerprinter

    f1 = tmp_path / "large1.bin"
    f2 = tmp_path / "large2.bin"
    # 3MB，但头部内容不同
    f1.write_bytes(b"A" * (3 * 1024 * 1024))
    f2.write_bytes(b"B" + b"A" * (3 * 1024 * 1024 - 1))
    assert fingerprinter.compute(str(f1)) != fingerprinter.compute(str(f2))
