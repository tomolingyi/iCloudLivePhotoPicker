# 参与贡献

感谢你改进 iCloud Live Photo Picker。提交代码前请先搜索已有 issue，并避免在日志、截图或测试数据中包含 Apple 账号、手机号、验证码、会话 cookie 或私人照片。

## 本地开发

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

界面改动需要同时检查 100%、125% 和 150% Windows 显示缩放；涉及列表或缩略图的改动应验证窗口拖动、快速滚动和大范围框选不会阻塞 UI 线程。

## Pull Request 要求

- 一个 PR 聚焦一个问题，说明行为变化与验证方式。
- 新功能或回归修复应增加测试。
- 不要提交 `dist/`、`build/`、虚拟环境、设置文件或 iCloud 会话。
- 用户可见变化写入 `CHANGELOG.md`。
- 新增依赖前说明用途、体积和许可证；依赖许可证必须兼容 GPL-3.0-or-later。

提交贡献即表示你有权以本项目许可证提供相应代码。
