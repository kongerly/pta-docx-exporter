# PTA 作业导出器

一个面向 Windows 的桌面工具：登录 PTA（Pintia）后，加载题目集或题型，并导出为结构化的 `.docx` 文档，方便教学整理、打印和归档。

当前版本：`0.2.0`

## 项目特点

- `Python + Tkinter` 桌面界面，适合教师或学生直接使用
- `Node + Playwright` 浏览器桥，复用真实登录态，减少页面兼容问题
- 支持导出整套题目集，也支持按题型单独导出
- 支持保留题面图片，并在图片下载失败时给出完整性警告
- 对判断题、单选题、多选题、填空题等页面结构做了专门解析
- 导出结果会显示摘要：导出项数量、题目成功数、缺失数、警告数

## 运行环境

- Windows 10/11
- Python `3.12+`
- Microsoft Edge 或 Google Chrome
- Node 运行时和 `playwright` Node 依赖

说明：

- 开发态运行时，程序会优先尝试使用以下 Node 运行时来源：
  - 环境变量 `PTA_NODE_EXE` / `PTA_NODE_MODULES`
  - 打包产物中的 `runtime/node`
  - Codex 自带 Node 依赖目录
- 发布态建议始终把 `runtime/node` 一起打包进去，这样最终用户不需要手动配置运行时。

## 安装依赖

```powershell
python -m pip install -r requirements.txt
```

## 启动方式

```powershell
python main.py
```

如果你在 Codex 自带 Python 环境中运行，也可以：

```powershell
& 'C:\Users\6\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\main.py
```

## 使用流程

1. 点击 `1. 打开登录页`
2. 在弹出的浏览器中完成 PTA 登录
3. 点击 `3. 确认账号`
4. 点击 `4. 加载题目集`
5. 在左侧树中选择题目集或题型，加入右侧导出队列
6. 选择导出方式：
   - 合并为一个 Word
   - 每个导出项单独生成 Word
7. 点击 `5. 导出 Word`
8. 导出完成后查看摘要、警告，并按需打开输出目录

## 稳定配置项

当前稳定配置由 [config.py](/D:/CodeBase/ptadocx/config.py) 中的 `AppConfig` 定义：

- `start_url`：默认入口 URL
- `output_dir`：导出目录
- `session_profile_dir`：浏览器登录会话目录
- `temp_dir`：临时文件目录
- `embed_images`：是否下载并嵌入图片

## 打包发布

推荐直接运行：

```powershell
pwsh .\build\build.ps1 -PythonExe python
```

脚本会优先自动寻找可用的 Node 运行时并复制到 `runtime/node`。如果你要显式指定运行时路径：

```powershell
pwsh .\build\build.ps1 `
  -PythonExe python `
  -NodeExe "C:\path\to\node.exe" `
  -NodeModulesDir "C:\path\to\node_modules"
```

如果只想在 CI 中验证 PyInstaller 打包是否成功，不拷贝运行时：

```powershell
pwsh .\build\build.ps1 -PythonExe python -SkipRuntimeCopy
```

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 已知限制

- 目前只面向 Windows 设计和验证
- 依赖 PTA 当前页面结构，若 Pintia 前端大改，解析规则可能需要更新
- 登录态依赖本地浏览器环境，无法脱离浏览器完成抓取
- 若图片资源受限、超时或失效，文档仍会导出，但会附带完整性警告

## 常见问题

### 1. 提示找不到 `node.exe`

优先使用打包产物，或设置：

```powershell
$env:PTA_NODE_EXE="C:\path\to\node.exe"
$env:PTA_NODE_MODULES="C:\path\to\node_modules"
python main.py
```

### 2. 提示找不到 Edge 或 Chrome

请先安装 Microsoft Edge 或 Google Chrome，并确保安装在默认路径，或通过 `PTA_BROWSER_EXECUTABLE` 指定路径。

### 3. 导出完成但有警告

这通常意味着：

- 个别题目页面抓取失败
- 题面图片下载失败
- 页面返回的题目总数和实际抓到的题目数不一致

程序会继续导出成功抓取到的内容，并在结果摘要和警告中标明问题。

## 隐私与账号风险提示

- 本工具不会尝试破解登录，仅复用你在本机浏览器中完成的真实登录状态
- 会话信息会保存在本地应用数据目录，用于后续抓取复用
- 请只在你有权限访问的课程、题目集和账号环境中使用
- 如果用于教学资料整理，请自行确认平台使用规范与课程要求

## 变更记录

见 [CHANGELOG.md](/D:/CodeBase/ptadocx/CHANGELOG.md)。
