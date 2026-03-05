# tests/unit/test_labeled_return.py — labeled_return 核心函数单元测试
"""
覆盖：
  - parse_yolo_txt     解析各种合法/非法格式
  - _box_iou_norm      IoU 精确计算（已知答案）
  - _match_pairs       贪心匹配计数
  - compare_one_image  一致率组合
"""
import os
import pytest

pytestmark = pytest.mark.unit


# ─── parse_yolo_txt ──────────────────────────────────────────────────────────

class TestParseYoloTxt:
    def test_standard_5col(self, tmp_path):
        """标准 5 列格式正常解析。"""
        from engines.labeled_return import parse_yolo_txt

        f = tmp_path / "a.txt"
        f.write_text("0 0.5 0.5 0.2 0.2\n1 0.1 0.1 0.05 0.05\n")
        result = parse_yolo_txt(str(f))
        assert result == [(0, 0.5, 0.5, 0.2, 0.2), (1, 0.1, 0.1, 0.05, 0.05)]

    def test_6col_conf_ignored(self, tmp_path):
        """6 列（含置信度）时第 6 列被忽略，不影响解析。"""
        from engines.labeled_return import parse_yolo_txt

        f = tmp_path / "b.txt"
        f.write_text("0 0.5 0.5 0.2 0.2 0.95\n")
        result = parse_yolo_txt(str(f))
        assert result == [(0, 0.5, 0.5, 0.2, 0.2)]

    def test_empty_file(self, tmp_path):
        """空文件返回空列表。"""
        from engines.labeled_return import parse_yolo_txt

        f = tmp_path / "empty.txt"
        f.write_text("")
        assert parse_yolo_txt(str(f)) == []

    def test_nonexistent_file(self):
        """文件不存在时返回空列表，不抛异常。"""
        from engines.labeled_return import parse_yolo_txt

        assert parse_yolo_txt("/nonexistent/file.txt") == []

    def test_malformed_lines_skipped(self, tmp_path):
        """格式错误的行跳过，合法行保留。"""
        from engines.labeled_return import parse_yolo_txt

        f = tmp_path / "mixed.txt"
        f.write_text("bad line\n0 0.5 0.5 0.2 0.2\nnot a number 1 2 3\n")
        result = parse_yolo_txt(str(f))
        assert result == [(0, 0.5, 0.5, 0.2, 0.2)]

    def test_blank_lines_ignored(self, tmp_path):
        """空行被忽略。"""
        from engines.labeled_return import parse_yolo_txt

        f = tmp_path / "blanks.txt"
        f.write_text("\n0 0.5 0.5 0.1 0.1\n\n")
        result = parse_yolo_txt(str(f))
        assert len(result) == 1


# ─── _box_iou_norm ───────────────────────────────────────────────────────────

class TestBoxIouNorm:
    def test_perfect_overlap(self):
        """完全重叠，IoU = 1.0。"""
        from engines.labeled_return import _box_iou_norm

        box = (0, 0.5, 0.5, 0.4, 0.4)
        assert _box_iou_norm(box, box) == pytest.approx(1.0)

    def test_no_overlap(self):
        """完全不重叠，IoU = 0.0。"""
        from engines.labeled_return import _box_iou_norm

        a = (0, 0.1, 0.1, 0.1, 0.1)
        b = (0, 0.9, 0.9, 0.1, 0.1)
        assert _box_iou_norm(a, b) == 0.0

    def test_different_class_zero_iou(self):
        """类别不同，IoU 强制为 0（不允许跨类匹配）。"""
        from engines.labeled_return import _box_iou_norm

        a = (0, 0.5, 0.5, 0.4, 0.4)
        b = (1, 0.5, 0.5, 0.4, 0.4)
        assert _box_iou_norm(a, b) == 0.0

    def test_partial_overlap(self):
        """部分重叠，IoU 在 (0, 1) 之间。"""
        from engines.labeled_return import _box_iou_norm

        # 两个同样大小的正方形，各占 50% 宽度重叠
        a = (0, 0.25, 0.5, 0.5, 0.5)   # x_center=0.25, covers 0.0~0.5
        b = (0, 0.75, 0.5, 0.5, 0.5)   # x_center=0.75, covers 0.5~1.0
        iou = _box_iou_norm(a, b)
        assert 0.0 <= iou <= 1.0

    def test_known_iou_value(self):
        """手工计算已知 IoU 验证精度。
        两框均为 0.4x0.4，中心偏移 0.2（半边长），交叉区为 0.2x0.4=0.08
        area_a = area_b = 0.16, union = 0.32 - 0.08 = 0.24, iou = 0.08/0.24 ≈ 0.333
        """
        from engines.labeled_return import _box_iou_norm

        a = (0, 0.3, 0.5, 0.4, 0.4)
        b = (0, 0.5, 0.5, 0.4, 0.4)
        iou = _box_iou_norm(a, b)
        assert iou == pytest.approx(1 / 3, abs=0.01)


# ─── _match_pairs ────────────────────────────────────────────────────────────

class TestMatchPairs:
    def test_perfect_match(self):
        """一一对应完全匹配。"""
        from engines.labeled_return import _match_pairs

        boxes = [(0, 0.5, 0.5, 0.2, 0.2)]
        assert _match_pairs(boxes, boxes, iou_thresh=0.5) == 1

    def test_no_match_different_class(self):
        """类别不同时，匹配数为 0。"""
        from engines.labeled_return import _match_pairs

        a = [(0, 0.5, 0.5, 0.2, 0.2)]
        b = [(1, 0.5, 0.5, 0.2, 0.2)]
        assert _match_pairs(a, b, iou_thresh=0.5) == 0

    def test_empty_inputs(self):
        """空输入，匹配数为 0。"""
        from engines.labeled_return import _match_pairs

        assert _match_pairs([], [], iou_thresh=0.5) == 0

    def test_multiple_boxes_partial_match(self):
        """2 个 returned，1 个匹配，1 个不匹配。"""
        from engines.labeled_return import _match_pairs

        returned = [
            (0, 0.5, 0.5, 0.2, 0.2),   # 能匹配
            (0, 0.9, 0.9, 0.05, 0.05),  # 位置远，IoU < 0.5
        ]
        pseudo = [(0, 0.5, 0.5, 0.2, 0.2)]
        assert _match_pairs(returned, pseudo, iou_thresh=0.5) == 1

    def test_one_pseudo_two_returned_match_only_one(self):
        """伪标签只有 1 个，即使 returned 有 2 个完全重叠，最多匹配 1 次。"""
        from engines.labeled_return import _match_pairs

        box = (0, 0.5, 0.5, 0.2, 0.2)
        returned = [box, box]
        pseudo = [box]
        assert _match_pairs(returned, pseudo, iou_thresh=0.5) == 1


# ─── compare_one_image ───────────────────────────────────────────────────────

class TestCompareOneImage:
    def test_perfect_consistency(self):
        """完全一致时，matched == returned == pseudo。"""
        from engines.labeled_return import compare_one_image

        box = (0, 0.5, 0.5, 0.2, 0.2)
        matched, n_ret, n_pseudo = compare_one_image([box], [box])
        assert matched == 1
        assert n_ret == 1
        assert n_pseudo == 1

    def test_empty_both(self):
        """双方都为空，结果全 0。"""
        from engines.labeled_return import compare_one_image

        matched, n_ret, n_pseudo = compare_one_image([], [])
        assert (matched, n_ret, n_pseudo) == (0, 0, 0)

    def test_pseudo_has_extra_boxes(self):
        """伪标签多出框（漏检），matched < n_pseudo。"""
        from engines.labeled_return import compare_one_image

        box = (0, 0.5, 0.5, 0.2, 0.2)
        extra = (0, 0.1, 0.1, 0.05, 0.05)
        matched, n_ret, n_pseudo = compare_one_image([box], [box, extra])
        assert matched == 1
        assert n_pseudo == 2
