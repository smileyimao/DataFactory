# tests/unit/test_system_probe.py
"""utils.system_probe 单元测试。

auto_configure() 是纯字典逻辑，完全可测。
detect_capabilities() 调真实硬件，只验 keys 和类型，不断言具体值。
"""
import pytest

pytestmark = pytest.mark.unit


# ─────────────────────────── auto_configure() ──────────────────────────────

class TestAutoConfigure:
    def _cfg(self, **kwargs):
        """构造 caps 字典，defaults = cpu only / 8 GB RAM。"""
        base = {
            "device": "cpu",
            "ram_gb": 8.0,
            "vram_gb": 0.0,
            "is_apple_silicon": False,
            "is_jetson": False,
        }
        base.update(kwargs)
        return base

    def _call(self, **kwargs):
        from utils.system_probe import auto_configure
        return auto_configure(self._cfg(**kwargs))

    # ── Apple Silicon（MPS + arm64）────────────────────────────────────────
    def test_mps_apple_silicon_uses_vit_l(self):
        result = self._call(device="mps", is_apple_silicon=True)
        assert result["sam_model_type"] == "vit_l"
        assert result["yolo_model"] == "yolov8m"
        assert result["clip_enabled"] is True

    # ── Intel Mac：mps 可能为 True，但 NOT arm64 → 走 CPU 路径 ────────────
    def test_mps_intel_mac_falls_to_cpu_path(self):
        result = self._call(device="mps", is_apple_silicon=False, ram_gb=16.0)
        assert result["yolo_model"] == "yolov8s"  # CPU + 高 RAM → vit_b
        assert result["sam_model_type"] == "vit_b"

    # ── CUDA 各档 ────────────────────────────────────────────────────────
    def test_cuda_32gb_uses_vit_h(self):
        result = self._call(device="cuda", vram_gb=32.0)
        assert result["sam_model_type"] == "vit_h"
        assert result["yolo_model"] == "yolov8x"

    def test_cuda_32gb_exact_boundary(self):
        result = self._call(device="cuda", vram_gb=32.0)
        assert result["sam_model_type"] == "vit_h"

    def test_cuda_16gb_uses_vit_l(self):
        result = self._call(device="cuda", vram_gb=16.0)
        assert result["sam_model_type"] == "vit_l"
        assert result["yolo_model"] == "yolov8m"

    def test_cuda_8gb_uses_vit_b(self):
        result = self._call(device="cuda", vram_gb=8.0)
        assert result["sam_model_type"] == "vit_b"
        assert result["yolo_model"] == "yolov8s"

    def test_cuda_below_16gb_uses_vit_b(self):
        result = self._call(device="cuda", vram_gb=10.0)
        assert result["sam_model_type"] == "vit_b"

    # ── CPU only ─────────────────────────────────────────────────────────
    def test_cpu_high_ram_enables_clip_sam(self):
        result = self._call(device="cpu", ram_gb=16.0)
        assert result["clip_enabled"] is True
        assert result["sam_enabled"] is True
        assert result["sam_model_type"] == "vit_b"
        assert result["yolo_model"] == "yolov8s"

    def test_cpu_exactly_8gb_ram_enables(self):
        result = self._call(device="cpu", ram_gb=8.0)
        assert result["clip_enabled"] is True

    def test_cpu_low_ram_disables_foundation_models(self):
        result = self._call(device="cpu", ram_gb=4.0)
        assert result["clip_enabled"] is False
        assert result["sam_enabled"] is False
        assert result["yolo_model"] == "yolov8n"

    def test_cpu_zero_ram_disables(self):
        result = self._call(device="cpu", ram_gb=0.0)
        assert result["clip_enabled"] is False

    # ── 返回结构完整 ──────────────────────────────────────────────────────
    def test_result_has_required_keys(self):
        result = self._call()
        for key in ("clip_enabled", "sam_enabled", "sam_model_type", "yolo_model"):
            assert key in result, f"缺少 key: {key}"


# ─────────────────────────── detect_capabilities() ─────────────────────────

class TestDetectCapabilities:
    def test_returns_dict_with_required_keys(self):
        from utils.system_probe import detect_capabilities
        caps = detect_capabilities()
        for key in ("cpu", "ram_gb", "has_gpu", "vram_gb", "device", "is_jetson", "is_apple_silicon"):
            assert key in caps, f"缺少 key: {key}"

    def test_device_is_valid_string(self):
        from utils.system_probe import detect_capabilities
        caps = detect_capabilities()
        assert caps["device"] in ("cuda", "mps", "cpu")

    def test_ram_gb_is_positive(self):
        from utils.system_probe import detect_capabilities
        caps = detect_capabilities()
        assert caps["ram_gb"] >= 0.0  # psutil 可能未安装 → 0.0

    def test_is_apple_silicon_is_bool(self):
        from utils.system_probe import detect_capabilities
        caps = detect_capabilities()
        assert isinstance(caps["is_apple_silicon"], bool)

    def test_is_jetson_is_bool(self):
        from utils.system_probe import detect_capabilities
        caps = detect_capabilities()
        assert isinstance(caps["is_jetson"], bool)


# ─────────────────────────── print_system_info() ───────────────────────────

class TestPrintSystemInfo:
    def test_does_not_crash(self, capsys):
        from utils.system_probe import auto_configure, detect_capabilities, print_system_info
        caps = detect_capabilities()
        config = auto_configure(caps)
        print_system_info(caps, config)
        out = capsys.readouterr().out
        assert "Device" in out
        assert "CLIP" in out
        assert "SAM" in out
