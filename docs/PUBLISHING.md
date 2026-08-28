# 第一次发布到 GitHub

这份清单面向 iCloud Live Photo Picker 的首次公开发布。本项目采用“GitHub 开源代码 + 百度网盘发布 Windows 文件”的方式：GitHub 只保存源码、文档、Issue、版本标签和版本说明，不上传 EXE 或便携版 ZIP。

## 1. 发布前检查

在项目根目录运行：

```powershell
python -m unittest discover -s tests -v
.\build_installer.bat
git status --short
```

确认：

- 自动化测试全部通过。
- 本地 `dist/` 中能生成安装版、便携版和源码包。
- 新 Windows 用户环境下可以安装、启动和卸载。
- README 截图不包含私人照片、Apple 账号或本机敏感路径。
- 没有提交 `.venv/`、`dist/`、`build/`、`settings.json` 或 `.icloudpd-picker/`。

## 2. 创建 GitHub 仓库

在 GitHub 新建一个空的 Public repository：

- Repository name：`iCloudLivePhotoPicker`
- Description：`A privacy-conscious Windows desktop picker for iCloud Photos and Live Photo pairs.`
- 不勾选 Add a README、`.gitignore` 或 License；项目中已经包含这些文件。

建议添加 Topics：

```text
icloud  live-photo  icloud-photos  photo-downloader  pyqt6  python  windows
```

仓库社交预览图可以先使用 `docs/images/application.png`；后续再制作 1280 × 640 的专用横幅。

## 3. 初始化并推送源码

如果本地目录还不是 Git 仓库：

```powershell
git init
git branch -M main
git add .
git status
git grep --cached -n -I -E "(password|verification.?code|session_token|cookie)"
git commit -m "Initial open-source release"
git remote add origin https://github.com/<你的GitHub用户名>/iCloudLivePhotoPicker.git
git push -u origin main
```

在执行 `git commit` 前认真检查 `git status` 和秘密信息搜索结果。代码中的字段名不等于已经泄露秘密，需要人工判断；尖括号中的用户名需要替换成自己的 GitHub 用户名。

如果 Git 尚未设置提交身份：

```powershell
git config --global user.name "你的公开显示名"
git config --global user.email "你的 GitHub noreply 邮箱"
```

GitHub noreply 邮箱可以减少真实邮箱暴露；它位于 GitHub 的 Email settings 页面。

## 4. 检查仓库首页

推送后检查以下内容：

- README 的全部截图、目录链接和徽章能正常显示。
- Actions 中的 `CI` 在 Python 3.10、3.12、3.13 上通过。
- About 区显示 Description、Topics 和 GPL-3.0 license。
- Issues 中能看到错误报告与功能建议模板。
- Settings → Security 中启用 Private vulnerability reporting（如果当前账户与仓库支持）。

## 5. 准备百度网盘发布目录

网盘共享目录中放置：

- `iCloudLivePhotoPicker-v0.5.3-Setup.exe`
- `iCloudLivePhotoPicker-v0.5.3-windows-x64.zip`
- `iCloudLivePhotoPicker-v0.5.3-source.zip`

确认共享地址是：

```text
https://pan.baidu.com/s/13qvegP94vbW2sPKHhcliOg?pwd=r8na
提取码：r8na
```

每次替换网盘文件后，重新下载并核对文件名、大小和 SHA-256。

## 6. 创建仅源码的 v0.5.3 Release

进入 Releases → Draft a new release：

- Choose a tag：`v0.5.3`
- Target：`main`
- Release title：`iCloud Live Photo Picker v0.5.3`
- 内容：复制 [`docs/releases/v0.5.3.md`](releases/v0.5.3.md)
- 不上传 EXE、便携 ZIP 或其他 Windows 二进制附件。

发布后 GitHub 会自动提供该标签对应的 Source code ZIP/TAR，这是 GitHub 上唯一需要保留的下载内容。Windows 安装包、便携版和整理好的源码包继续从百度网盘下载。

不要勾选 Set as a pre-release；当前版本虽然是 Beta，但首页已明确标注项目状态，普通 Release 更便于用户找到“Latest”。

## 7. 公布 SHA-256

在 PowerShell 中计算：

```powershell
Get-FileHash .\dist\iCloudLivePhotoPicker-v0.5.3-Setup.exe -Algorithm SHA256
Get-FileHash .\dist\iCloudLivePhotoPicker-v0.5.3-windows-x64.zip -Algorithm SHA256
Get-FileHash .\dist\iCloudLivePhotoPicker-v0.5.3-source.zip -Algorithm SHA256
```

把结果粘贴到 Release notes 的校验区。虽然二进制在网盘中，GitHub 上的版本说明仍是公开且可追踪的校验来源。哈希只能确认文件与发布时一致，不能替代代码签名。

## 8. 发布后验证

从百度网盘共享链接重新下载，而不是直接使用本机 `dist/` 中的文件，然后完成一次：

1. 下载并核对 SHA-256。
2. 安装、启动、登录和加载少量缩略图。
3. 下载一组 Live Photo，并确认照片/MOV 与方向处理符合设置。
4. 使用“打开下载目录”。
5. 卸载并确认应用文件被移除，用户设置和会话仍按文档保留。

## 后续版本的固定流程

1. 更新 `pyproject.toml`、构建脚本、安装器脚本和应用常量中的版本号。
2. 更新 `CHANGELOG.md` 与 README 中的下载文件名。
3. 运行测试并构建安装版、便携版和源码包。
4. 提交源码并推送 `main`。
5. 更新百度网盘文件及共享链接。
6. 创建 `vX.Y.Z` tag 与仅源码 Release，写入网盘地址和三个文件的哈希。
7. 从网盘重新下载安装，完成发布后冒烟测试。

正式拥有代码签名证书后，再把签名和签名验证加入此流程。
