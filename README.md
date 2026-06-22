# RecorderAnalyzer

**手工测试流量智能分析工具** — 录制浏览器操作，自动分析 HTTP 请求，生成可执行的 Postman 集合。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Flet](https://img.shields.io/badge/UI-Flet-0268d1)
![Playwright](https://img.shields.io/badge/Engine-Playwright-45ba4b)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 目录

- [功能概述](#功能概述)
- [应用截图](#应用截图)
- [快速开始](#快速开始)
- [详细使用指南](#详细使用指南)
  - [录制](#1-录制)
  - [分析](#2-分析)
  - [执行重放](#3-执行重放)
  - [导出](#4-导出)
  - [变量提取与依赖图谱](#5-变量提取与依赖图谱)
  - [保存/加载会话](#6-保存加载会话)
- [界面说明](#界面说明)
- [配置项](#配置项)
- [构建打包](#构建打包)
- [项目结构](#项目结构)
- [常见问题](#常见问题)
- [许可](#许可)

---

## 功能概述

RecorderAnalyzer 是一个桌面 GUI 工具，解决**从浏览器操作到 API 测试用例**的工作流断层：

| 步骤 | 功能 | 技术 |
|---|---|---|
| **录制** | 启动 Chromium 浏览器，录制用户的所有操作和网络请求 | Playwright Trace |
| **分析** | 自动关联操作与请求，提取动态变量（token、id、session 等） | 时间窗口关联 + JSON Path 挖掘 |
| **执行** | 按依赖拓扑顺序重放请求，自动替换变量 | httpx + 拓扑排序 |
| **导出** | 生成 Postman v2.1 Collection，可直接导入 Postman | 自定义生成器 |

### 核心特性

- **一键录制** — 输入 URL 自动打开浏览器，追踪所有点击、输入、导航
- **智能关联** — 基于时间窗口将请求自动匹配到触发它的用户操作
- **自动变量挖掘** — 从 JSON 响应中识别 token、id、session 等动态值
- **依赖拓扑排序** — 自动推导请求间的变量依赖关系，按正确顺序执行
- **流式执行** — 逐条执行并回显进度，支持失败重试（指数退避）
- **可视化** — 操作时间线、请求瀑布流、依赖图谱、报文详情
- **搜索过滤** — 按 URL/方法/状态码实时过滤请求
- **保存会话** — 分析结果可保存为 JSON 文件，随时加载恢复
- **Postman 导出** — 生成标准 v2.1.0 Collection 文件

---

## 快速开始

### 环境要求

- Python 3.10+
- 操作系统：Windows / Linux（麒麟/统信/UOS/Deepin/Ubuntu） / macOS

### 安装

```bash
# 1. 克隆或下载项目
git clone <repo-url>
cd RecorderAnalyzer

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装 Playwright 浏览器（用于录制）
playwright install chromium

# 4. 启动
python main.py
```

### 快速使用流程

1. 在顶部输入框输入目标 URL（如 `https://example.com`）
2. 点击 **开始录制**，在打开的浏览器中执行操作
3. 点击 **停止录制**，等待分析完成
4. 在 **操作时间线** 选择操作，**请求瀑布流** 高亮关联请求
5. 点击 **执行** 重放请求，点击 **导出 Postman** 生成集合

---

## 详细使用指南

### 1. 录制

点击"开始录制"后，程序会：

- 启动 Chromium 浏览器（非无头模式）
- 自动导航到输入的 URL
- 启用 Playwright Tracing（含截图 + DOM 快照）

录制期间顶部工具栏会实时显示**已捕获的请求数**。

> 提示：录制过程中可以在浏览器中正常操作——点击按钮、填写表单、翻页等。所有操作和网络请求都会被记录。

完成操作后点击 **停止录制**，浏览器自动关闭，进入分析阶段。

### 2. 分析

分析阶段自动完成：

1. **Trace 解析** — 解包 Playwright trace.zip，提取操作事件和网络请求事件
2. **操作-请求关联** — 基于时间窗口（默认 5000ms），将请求匹配到其触发操作
3. **变量提取** — 遍历 JSON 响应体，自动识别 token、id、session 等动态变量
4. **依赖验证** — 验证变量是否在其他请求中被引用，构建依赖图

分析完成后，界面自动加载数据：

- 左侧：操作时间线
- 中间：请求瀑布流（支持搜索过滤）
- 底部标签页：报文详情、关联变量、依赖图谱

### 3. 执行重放

点击 **执行**，程序会：

1. 对请求进行**拓扑排序**（变量生产者在前，消费者在后）
2. 依次发送 HTTP 请求，自动替换 `{{变量名}}` 占位符
3. 从响应中提取新值更新变量存储
4. 失败时自动重试（默认 2 次，指数退避）

执行结果在底部"执行结果"标签页**逐条实时显示**，每个请求展示状态码、耗时和错误信息。

### 4. 导出

支持导出为 **Postman v2.1 Collection**（JSON 文件），包含：

- 按域名分组的请求文件夹
- 自动填充的 Method、URL、Headers、Body
- 变量占位符替换（`{{variable_name}}`）
- 全局变量列表

导出的文件可直接导入 Postman：

```
Postman → Import → 选择 collection.postman_collection.json
```

### 5. 变量提取与依赖图谱

程序会自动从 JSON 响应中挖掘变量，匹配以下 key 模式（不区分大小写）：

```
id, token, code, key, uid, sid, session, auth, order, trade, sn, uuid
```

在 **关联变量** 标签页可查看所有提取的变量及其值、来源请求、引用次数。点击变量卡片可高亮瀑布流中引用该变量的请求。

**依赖图谱** 标签页以树形结构展示：

```
[req_3] /api/login
  └ 提取 token = abc123
     → [req_5] /api/orders
     → [req_7] /api/profile
```

### 6. 保存/加载会话

分析完成后：

- **保存** — 将完整的分析结果（操作、请求、关联、变量）保存为 JSON 文件
- **加载** — 从保存的 JSON 文件恢复会话，无需重新录制和分析

---

## 界面说明

```
┌─────────────────────────────────────────────────────────────┐
│ [URL输入框] [开始] [停止] [执行] [导出] [保存] [加载]      │   ← 工具栏
│ 窗口:[5000ms]  ● 空闲中                                     │
├────────────────────────────────┬────────────────────────────┤
│ 操作时间线                      │ 请求瀑布流                  │
│                                │ [搜索 URL...]              │
│ ● Click 点击登录按钮            │ GET  /api/login        200 │
│ ◉ Input 输入用户名              │ POST /api/auth         200 │
│ ● Navigation 跳转首页           │ GET  /api/orders       200 │
│ ● Click 点击订单                │ GET  /api/profile      200 │
│                                │                            │
├────────────────────────────────┴────────────────────────────┤
│ [报文详情] [关联变量] [依赖图谱] [执行结果]                   │
│ URL: https://api.example.com/login                          │
│ Method: POST  Status: 200                                   │
│ 请求头: {...}  请求体: {...}  响应体: {...}                  │
└─────────────────────────────────────────────────────────────┘
```

### 各面板说明

| 面板 | 功能 |
|---|---|
| **工具栏** | URL 输入、录制控制、执行/导出/保存/加载按钮、关联时间窗口、状态指示 |
| **操作时间线** | 按时间顺序列出所有用户操作（点击/输入/导航/滚动），点击选中高亮关联请求 |
| **请求瀑布流** | 列出所有 HTTP 请求，支持实时搜索过滤，高亮与当前操作关联的请求 |
| **报文详情** | 展示选中请求的完整 URL、Method、Headers、Body、Response |
| **关联变量** | 列出自动提取的动态变量，点击可查看引用该变量的请求 |
| **依赖图谱** | 以树形图展示变量从生产到消费的完整链路 |
| **执行结果** | 逐条显示重放请求的执行状态、耗时、错误信息 |

---

## 配置项

### 关联时间窗口

工具栏的 **窗口** 输入框控制操作→请求关联的时间范围（单位：ms，默认 5000）。

- 值过小：部分请求可能匹配不到操作（成为孤儿请求）
- 值过大：请求可能错误关联到无关操作

同一操作关联的多个请求中，选择时间差最小的作为匹配。

### 执行重试

执行器默认最多重试 2 次（共 3 次尝试），间隔 0.5s → 1s → 2s 指数退避。

---

## 构建打包

### Linux（含麒麟/统信/UOS/Deepin）

```bash
# 完整构建（安装依赖 → 构建 → .deb → 桌面快捷方式）
sudo ./build.sh all

# 分步执行
./build.sh deps       # 安装系统依赖 + Python 依赖
./build.sh build      # 构建单文件二进制
./build.sh deb        # 打包 .deb 安装包
./build.sh desktop    # 安装桌面快捷方式
./build.sh clean      # 清理构建产物
```

产物位于 `dist/` 目录：

```
dist/
├── RecorderAnalyzer              # 单文件可执行 (58MB)
└── RecorderAnalyzer_1.0.0_amd64.deb  # .deb 安装包
```

### Windows

```batch
# 双击运行，或命令行执行：
build.bat
```

产物：`dist\RecorderAnalyzer.exe`

### 跨平台 Python 脚本

```bash
python build.py          # 构建当前平台
python build.py clean    # 清理构建产物
python build.py --onedir # 目录模式（调试用）
```

### GitHub Actions CI/CD

推送代码到 GitHub 后自动在 Windows/Linux/macOS 三个平台构建。打 tag `v*` 时自动发布 Release。

---

## 项目结构

```
RecorderAnalyzer/
├── main.py                    # 入口文件
├── requirements.txt           # Python 依赖
├── build.sh                   # Linux 构建脚本（支持麒麟）
├── build.bat                  # Windows 构建脚本
├── build.py                   # 跨平台构建脚本
├── README.md                  # 本文档
├── .gitignore
├── .github/workflows/build.yml  # GitHub Actions CI/CD
├── core/
│   ├── __init__.py
│   ├── models.py              # 数据模型（RequestEvent, ActionEvent 等）
│   ├── analyzer.py            # Trace 解析、关联算法、变量提取
│   ├── generator.py           # Postman Collection 生成器
│   ├── executor.py            # HTTP 执行器（拓扑排序 + 重试）
│   └── recorder.py            # Playwright 浏览器录制
├── ui/
│   ├── __init__.py
│   ├── app.py                 # 主应用控制器
│   └── panels.py              # UI 组件（工具栏、时间线、瀑布流、详情面板）
└── packaging/                 # 构建时生成的桌面文件
    └── RecorderAnalyzer.desktop
```

### 核心模块说明

| 模块 | 职责 |
|---|---|
| `core/models.py` | 定义 `ActionEvent`、`RequestEvent`、`CorrelationMap`、`VariableDep`、`AnalysisResult` 五个数据类 |
| `core/analyzer.py` | `TraceParser` 解析 Playwright trace.zip；`Correlator` 时间窗口关联；`VariableExtractor` JSON 变量挖掘 |
| `core/generator.py` | `PostmanGenerator` 将分析结果转为 Postman v2.1.0 Collection JSON |
| `core/executor.py` | `Executor` 拓扑排序 + 变量替换 + HTTP 执行 + 响应变量提取 + 自动重试 |
| `core/recorder.py` | `Recorder` 封装 Playwright，管理浏览器生命周期和 Tracing |
| `ui/app.py` | `RecorderApp` 主控制器，协调各模块与 Flet UI 的交互 |
| `ui/panels.py` | `ToolBar`、`ActionTimeline`、`RequestWaterfall`、`DetailPanel` 四个 UI 组件 |

---

## 常见问题

### Q: 启动后浏览器没有打开？

确保已安装 Playwright 浏览器：

```bash
playwright install chromium
```

### Q: 麒麟/UOS 上按钮显示异常？

安装 GTK 依赖：

```bash
sudo apt install libgtk-3-0 libxcb-cursor0 libxkbcommon-x11-0
# 或使用 build.sh 自动安装：
sudo ./build.sh deps
```

### Q: 无桌面环境如何运行？

使用 `xvfb` 虚拟显示器：

```bash
sudo apt install xvfb
xvfb-run python main.py
# 或
xvfb-run dist/RecorderAnalyzer
```

### Q: 关联不准确（请求匹配到错误操作）？

调整工具栏的 **窗口** 参数。减小窗口值（如 2000ms）使关联更精确。

### Q: 某些变量未被提取？

- 检查 JSON 响应中的字段名是否匹配内置模式：`id, token, code, key, uid, sid, session, auth, order, trade, sn, uuid`
- 确认该变量的值确实在其他请求中被引用（URL 或请求体中出现）

### Q: 执行时出现变量替换失败？

确保变量名在 `{{变量名}}` 格式中与变量列表中的名称一致。执行过程中新提取的变量会自动更新。

### Q: 如何获取更多调试信息？

程序通过 Flet SnackBar 显示错误信息。如果遇到未捕获的异常，可在终端看到完整的 Python traceback。

---

## 许可

[MIT License](LICENSE)
