# 专家信息采集系统

基于浏览器自动化和大语言模型的专家信息智能采集工具。系统通过百度搜索自动查找专家的公开信息，并提取简介、工作单位、邮箱、电话等字段。

## 功能特点

- **自动化采集**：使用 browser-use 库实现浏览器自动化，模拟人工搜索和浏览
- **智能提取**：利用 LLM（大语言模型）从网页中智能提取结构化信息
- **断点续采**：支持从中断处继续采集，避免重复工作
- **动态字段**：通过配置文件自定义需要提取的字段
- **并发处理**：支持多专家并发采集，提高效率
- **视觉自适应**：自动调整截图尺寸以适应不同 LLM 的限制

## 目录结构

```
Seekagent/
├── main.py              # 主入口文件
├── browser_agent.py     # 浏览器自动化 Agent
├── config.py            # 配置管理模块
├── config.yaml          # 配置文件
├── models.py            # 数据模型定义
├── excel_handler.py     # Excel 读写处理
├── search_strategy.py   # 搜索策略生成
├── utils.py             # 工具函数
├── prompts/             # 提示词模板
│   ├── __init__.py
│   └── task_prompt.py
├── logs/                # 日志目录
├── .venv/               # Python 虚拟环境
├── .env                 # 环境变量配置
├── requirements.txt     # 依赖列表
└── 专家名单-small.xlsx  # 输入文件示例
```

## 环境要求

- Python 3.10+
- Chrome/Chromium 浏览器

## 快速开始 (Windows)

打开命令提示符 (CMD) 或 PowerShell，依次执行：

```cmd
REM 1. 进入项目目录
cd C:\path\to\Seekagent

REM 2. 创建虚拟环境
python -m venv .venv

REM 3. 激活虚拟环境 (CMD)
.venv\Scripts\activate.bat

REM 3. 激活虚拟环境 (PowerShell)
.\.venv\Scripts\Activate.ps1

REM 4. 安装依赖
pip install -r requirements.txt

REM 5. 配置 .env 文件中的 API Key

REM 6. 运行采集
python main.py
```

## 安装步骤

### 1. 克隆项目

```bash
git clone <repository-url>
cd Seekagent
```

### 2. 创建虚拟环境

```bash
# Windows (CMD)
python -m venv .venv
.venv\Scripts\activate.bat

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
```

> **Windows PowerShell 执行策略**：如果 PowerShell 报错无法运行脚本，请先执行：
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### 3. 安装依赖

```bash
# Windows / Linux / macOS
pip install -r requirements.txt

# 如果 pip 版本过低，先升级
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 配置环境变量

复制 `.env.example`（如有）或直接编辑 `.env` 文件：

```env
# LLM API 配置
OPENAI_API_KEY=your-api-key-here
LLM_MODEL=qwen3.5-flash
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 可选：其他 LLM 提供商
# ANTHROPIC_API_KEY=
# GOOGLE_API_KEY=
# BROWSER_USE_API_KEY=
```

### 5. 配置 config.yaml

编辑 `config.yaml` 文件，配置采集参数：

```yaml
# 提取字段配置
fields:
  - name: biography
    label: 简介
    description: 教育背景、工作经历、主要成就（200-500字）
    priority: high
  - name: affiliation
    label: 工作单位
    description: 院校级单位名称
    priority: high
  - name: email
    label: 邮箱
    description: 公开邮箱
    priority: high
  - name: phone
    label: 电话
    description: 公开办公电话
    priority: medium

# 文件路径
paths:
  excel_path: "专家名单-small.xlsx"
  log_dir: "logs"

# LLM 配置
llm:
  model: "qwen3.5-flash"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 浏览器配置
browser:
  headless: true    # 无头模式
  use_vision: true  # 使用视觉能力

# Agent 配置
agent:
  max_steps: 20
  max_actions_per_step: 5

# 并发配置
execution:
  concurrency: 1
  request_interval_seconds: 5.0
```

## 使用方法

### 准备输入文件

准备一个 Excel 文件（如 `专家名单-small.xlsx`），第一列为专家姓名，可选包含"单位"列。

### 运行采集

#### Windows (CMD)

```cmd
REM 基本运行（使用默认配置）
python main.py

REM 指定 Excel 文件
python main.py --excel-path 专家名单.xlsx

REM 显示浏览器窗口（调试用）
python main.py --headed

REM 设置并发数
python main.py --concurrency 2

REM 仅统计不执行
python main.py --dry-run
```

#### Windows (PowerShell)

```powershell
# 基本运行（使用默认配置）
python main.py

# 指定 Excel 文件
python main.py --excel-path "专家名单.xlsx"

# 显示浏览器窗口（调试用）
python main.py --headed

# 设置并发数
python main.py --concurrency 2

# 仅统计不执行
python main.py --dry-run
```

#### Linux/macOS

```bash
# 基本运行（使用默认配置）
python main.py

# 指定 Excel 文件
python main.py --excel-path 专家名单.xlsx

# 显示浏览器窗口（调试用）
python main.py --headed

# 设置并发数
python main.py --concurrency 2

# 仅统计不执行
python main.py --dry-run
```

### 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--excel-path` | 输入 Excel 文件路径 | config.yaml 配置 |
| `--model` | LLM 模型名称 | config.yaml 配置 |
| `--concurrency` | 并发处理数量 | 1 |
| `--max-steps` | 每个 Agent 最大步骤数 | 20 |
| `--request-interval` | 每个专家处理后等待秒数 | 5.0 |
| `--dry-run` | 仅读取统计，不执行采集 | False |
| `--no-resume` | 不启用断点续采 | False |
| `--headed` | 显示浏览器窗口 | False |
| `--headless` | 强制无头模式 | True |

## 输出说明

采集结果将直接写入输入 Excel 文件的以下列：

| 列名 | 说明 |
|------|------|
| 姓名 | 专家姓名 |
| 工作单位 | 所属机构 |
| 简介 | 个人简介 |
| 邮箱 | 电子邮箱 |
| 电话 | 联系电话 |
| 信息来源URL | 数据来源网页 |
| 提取状态 | 成功/失败 |
| 备注 | 失败原因或其他说明 |

### 成功标准

一次采集被标记为"成功"需要满足：
1. 有工作单位信息
2. 有个人简介
3. 有邮箱或电话至少一个联系方式

## 日志

日志文件位于 `logs/` 目录：
- `expert_extraction.log` - 主日志文件
- `agent_conversations/` - Agent 对话记录（调试用）

## 支持的 LLM

系统支持多种 LLM 提供商：

| 提供商 | 模型前缀 | 环境变量 |
|--------|----------|----------|
| OpenAI | `openai_gpt_4o` | `OPENAI_API_KEY` |
| Browser Use Cloud | `bu_latest` | `BROWSER_USE_API_KEY` |
| 阿里云通义千问 | `qwen3.5-flash` | `OPENAI_API_KEY` + `LLM_BASE_URL` |
| Anthropic Claude | `claude-sonnet` | `ANTHROPIC_API_KEY` |
| Google Gemini | `gemini-pro` | `GOOGLE_API_KEY` |

## 常见问题

### Q: Windows 上虚拟环境激活失败 (PowerShell)

PowerShell 默认禁止运行脚本，需要先修改执行策略：

```powershell
# 以管理员身份运行 PowerShell，执行以下命令
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 然后重新激活虚拟环境
.\.venv\Scripts\Activate.ps1
```

### Q: Windows 上提示 "'python' 不是内部或外部命令"

需要将 Python 添加到系统环境变量 PATH 中：

1. 打开「系统属性」→「高级」→「环境变量」
2. 在「用户变量」或「系统变量」中找到 `Path`，点击编辑
3. 添加 Python 安装路径（如 `C:\Users\用户名\AppData\Local\Programs\Python\Python310\`）
4. 添加 Scripts 路径（如 `C:\Users\用户名\AppData\Local\Programs\Python\Python310\Scripts\`）
5. 重启命令行窗口

或者使用 `py` 命令替代 `python`：

```cmd
py -m venv .venv
.venv\Scripts\activate
py main.py
```

### Q: 浏览器启动失败

确保已安装 Chrome/Chromium 浏览器。在无头模式下运行时，确保系统有足够的资源。

**Windows 特别说明**：
- 确保 Chrome 安装在默认路径，或设置 `CHROME_PATH` 环境变量
- 常见 Chrome 路径：`C:\Program Files\Google\Chrome\Application\chrome.exe`
- 如果使用 Chromium，路径可能为：`C:\Users\用户名\AppData\Local\Chromium\Application\chrome.exe`

### Q: Windows 上出现 SSL 证书错误

```cmd
# 安装证书
python -m pip install certifi

# 或设置环境变量
set SSL_CERT_FILE=
set REQUESTS_CA_BUNDLE=
```

### Q: API 调用失败

检查 `.env` 文件中的 API Key 是否正确，以及网络连接是否正常。

### Q: 采集结果不准确

可以尝试：
1. 增加 `max_steps` 值
2. 使用更强大的 LLM 模型
3. 使用 `--headed` 模式观察 Agent 行为

## 注意事项

1. 请遵守目标网站的 robots.txt 和使用条款
2. 合理设置并发数和请求间隔，避免对目标网站造成压力
3. API Key 等敏感信息请勿提交到版本控制

## 许可证

MIT License
