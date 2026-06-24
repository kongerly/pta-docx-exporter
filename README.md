# PTA Word 导出工具

一个面向 Windows 的桌面工具，用于将 PTA（Pintia）题目集导出为结构化的 Word（`.docx`）文档。

适合用于题目整理、离线查阅、打印复习和资料归档等场景。

当前版本：`v0.3.0`

## 功能特点

- 基于 `Python + Tkinter` 的桌面图形界面
- 通过 `Node + Playwright` 复用本机浏览器中的真实登录状态
- 支持导出：
  - 整个题目集
  - 题目集中的单个题型
- 按钮会根据登录状态、题目集加载状态和导出项选择状态自动启用或禁用，减少误操作
- 生成结构化的 `.docx` 文档，便于阅读和打印
- 支持下载并嵌入题面图片
- 当部分题目或图片抓取失败时，会保留完整告警信息，并按漏题、页面异常、图片异常、乱码修复提示分类汇总
- 当 PTA 页面结构变化导致题目集或题型无法识别时，会给出中文排查提示，提醒先确认页面已正常打开，再检查解析规则
- 导出文件名会自动规避 Windows 非法字符、保留名、尾部空格/句点和过长名称，减少保存失败
- 导出前会显示更完整的确认摘要，包含当前账号、入口 URL、导出方式、图片策略、输出位置和导出项预览
- 导出完成但存在问题时，会优先展示告警分类汇总，再附代表性示例，避免把大量重复日志直接抛给普通用户
- 主界面中的导出摘要会同时显示成功题数、缺失题数和关键告警分类，便于快速判断结果是否完整
- 如果当前登录账号与目标账号不一致，程序会明确提示先点击“重新登录”，再重新确认账号继续操作

## 当前支持的内容

目前已针对 PTA 中常见的题目页面做了解析支持，包括：

- 判断题
- 单选题
- 多选题
- 填空题

## 运行环境

- Windows 10/11
- Python `3.12+`
- Microsoft Edge 或 Google Chrome
- Node 运行时及 Playwright 相关依赖

## 安装依赖

```powershell
python -m pip install -r requirements.txt
```

## 启动方式

```powershell
python main.py
```

## 使用流程

1. 在程序中打开 PTA 登录页。
2. 在浏览器窗口中完成登录。
3. 回到程序中确认当前账号。
4. 加载可用题目集。
5. 选择需要导出的题目集或题型。
6. 选择合并导出或分别导出模式。
7. 导出为 `.docx` 文档。

## 打包构建

本阶段正式交付物仅为 Windows 便携版，不提供安装包。

构建带运行时的完整便携版：

```powershell
powershell -ExecutionPolicy Bypass -File .\build\build.ps1 -PythonExe python
```

如需手动指定 Node 运行时：

```powershell
powershell -ExecutionPolicy Bypass -File .\build\build.ps1 `
  -PythonExe python `
  -NodeExe "C:\path\to\node.exe" `
  -NodeModulesDir "C:\path\to\node_modules"
```

如果只想在 CI 中验证是否能成功打包，可使用最小打包模式：

```powershell
powershell -ExecutionPolicy Bypass -File .\build\build.ps1 -PythonExe python -SkipRuntimeCopy
```

构建脚本会用中文提示当前构建版本，并在缺少 `node.exe`、`node_modules` 或 Playwright 依赖时给出区分说明。
构建完成后，脚本还会自动校验 `dist/` 中的关键产物是否存在，减少“看起来成功、实际缺文件”的情况。
应用标识、窗口标题、版本号和打包产物名称都统一来源于 `app_meta.py`，避免发布时多处漂移。
当前版本已在本地完成完整便携版构建验证，并确认产物可最小启动。

## 隐私说明

- 本项目不会绕过 PTA 登录，只会复用你在本机浏览器中完成的真实登录状态。
- 浏览器配置目录与会话数据应仅保留在本地，不能提交到版本库。
- 直接从 PTA 页面保存的原始 HTML 可能包含真实姓名、课程名称、题目集编号等敏感信息，建议只保存在本地忽略目录 `1234html/` 中。
- 本地协作文件、原始页面样本和浏览器会话数据都不应进入公开仓库。
- 请仅在你有权限访问的课程、题目集和账号环境中使用本工具。

## 已知限制

- 当前仅面向 Windows 开发与测试
- 依赖 PTA 当前页面结构
- 若 Pintia 前端页面结构发生较大变化，解析逻辑可能需要调整
- 图片下载可能因网络限制、超时或源站问题失败，但导出流程会继续并给出告警

## 更新记录

详见 [CHANGELOG.md](CHANGELOG.md)。
