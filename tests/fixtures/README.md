# 测试 Fixtures

e2e 测试需 `paths.test_source`（默认 `storage/test/original/`）下：

- normal.mov
- jitter.mov
- black.mov
- image.jpg

可放置极小测试视频（几秒、几 MB）用于 CI。Path decoupling：路径从 config 读取，可覆盖。
