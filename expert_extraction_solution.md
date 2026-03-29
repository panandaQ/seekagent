# 基于 Browser-Use 的专家信息自动化采集系统——技术方案与提示词指南（v2.0）

---

## 一、项目概述

### 1.1 目标

从给定的 Excel 专家名单中读取姓名，利用 `browser-use` 库控制浏览器在公开网页上搜索每位专家（计算机/信息科学领域），从高可信度网站中提取专家简介与联系方式，并将结果写回 Excel。

### 1.2 技术选型

| 组件         | 技术                          | 说明                          |
| ------------ | ----------------------------- | ----------------------------- |
| 浏览器自动化 | `browser-use`               | 基于 LLM 驱动的浏览器操作框架 |
| LLM 后端     | Claude / GPT-4o / DeepSeek 等 | 作为 browser-use 的决策大脑   |
| Excel 读写   | `openpyxl`                  | 读取名单、写回结果            |
| 数据模型     | `pydantic`                  | 结构化提取结果校验            |
| 并发控制     | `asyncio` + 信号量          | 控制并行浏览器数量            |

### 1.3 输入/输出规范

**输入 Excel 格式（最低要求）：**

| 列        | 含义          |
| --------- | ------------- |
| A         | 专家姓名      |
| B（可选） | 已知单位/机构 |

**输出 Excel 格式（在原表追加列）：**

| 新增列      | 含义                      |
| ----------- | ------------------------- |
| 简介        | 专家个人简介（200-500字） |
| 研究方向    | 主要研究领域和方向        |
| 职称/职务   | 当前职称、行政职务        |
| 单位        | 所属机构全称              |
| 邮箱        | 电子邮箱地址              |
| 电话        | 联系电话（如公开）        |
| 个人主页    | 个人学术主页 URL          |
| 信息来源URL | 提取信息的网页地址        |
| 提取状态    | 成功/部分成功/失败        |
| 备注        | 额外信息或失败原因        |

---

## 二、browser-use 执行机制深度分析

### 2.1 browser-use 的 step-by-step 本质

browser-use 的 Agent 运行模型是一个**循环决策过程**：

```
while not done and step_count < max_steps:
    1. LLM 观察当前页面状态（DOM 摘要 / 截图）
    2. LLM 根据 task + 当前状态 决定下一个 action
    3. 执行 action（点击/输入/滚动/导航等）
    4. 等待页面响应
    5. 判断任务是否完成
```

**关键认知：** 提示词（task）不是"一次性指令"，而是在每一步都被 LLM 重新阅读的"持久目标"。这意味着：

- 提示词必须同时服务于"首步执行"和"中间步骤的决策判断"。
- 提示词中需要包含"状态识别规则"——让 Agent 判断自己当前处于流程的哪个阶段。
- 提示词需要包含"完成条件"——让 Agent 知道何时停止。

### 2.2 真实导航路径分析

对于计算机/信息科学领域专家的搜索，典型的导航路径远比"搜索→点击→提取"复杂：

**路径模式A：院校官网路径（最常见，3-6步）**

```
百度搜索 → 搜索结果页 → 院校官网首页/院系首页
→ 导航菜单"师资队伍"/"人才团队" → 教师列表页
→ 目标教师的详情页 → [可能还有子标签页：简介/研究/成果]
```

**路径模式B：百度百科路径（2-3步）**

```
百度搜索 → 搜索结果页 → 百度百科词条页
→ [可能需要点击"展开全部"查看完整内容]
```

**路径模式C：学术平台路径（2-4步）**

```
百度搜索 → DBLP/Google Scholar 主页
→ 作者页面 → [可能需要点击个人主页链接跳转到官网]
```

**路径模式D：间接发现路径（4-7步）**

```
百度搜索 → 新闻/报道页面（提到专家所在单位）
→ 根据发现的单位信息，构建新搜索
→ 直接搜索"单位名 + 姓名"
→ 进入院校官网教师页
```

### 2.3 多步执行中的核心挑战

| 挑战                 | 具体场景                     | 应对策略                      |
| -------------------- | ---------------------------- | ----------------------------- |
| 页面类型识别         | 当前页是列表页还是详情页？   | 提示词中提供判断规则          |
| 导航菜单发现         | 不同院校官网菜单文案不同     | 给出常见菜单文案列表          |
| 信息分散在多个标签页 | 简介在A标签、联系方式在B标签 | 指示 Agent 检查并切换标签     |
| 死胡同回退           | 点进无关页面                 | 明确回退指令（后退/重新搜索） |
| 弹窗/Cookie提示      | 阻挡内容区域                 | 指示关闭弹窗                  |
| 动态加载内容         | 需要滚动或点击展开           | 指示滚动和点击展开按钮        |
| 同名不同人           | 搜索结果中有多个同名者       | 通过单位/领域交叉验证         |

---

## 三、系统架构

### 3.1 改进后的整体流程

```
Excel读取 → 构建搜索策略 → Browser-Use多步搜索与导航
    → 页面类型识别 → 深度导航至详情页 → 信息提取
    → [如信息不完整] → 切换来源/补充搜索
    → 结果结构化与合并 → 写回Excel
```

### 3.2 核心模块划分

```
project/
├── main.py                  # 主入口，编排整体流程
├── config.py                # 配置（LLM Key、路径、并发数、max_steps等）
├── excel_handler.py         # Excel 读写模块
├── search_strategy.py       # 搜索关键词策略生成
├── browser_agent.py         # browser-use Agent 封装（核心）
├── url_ranker.py            # URL 可信度评分与排序
├── models.py                # Pydantic 数据模型定义
├── utils.py                 # 工具函数（日志、重试、清洗）
└── prompts/
    ├── task_prompt.py       # Agent task 提示词模板（核心）
    └── merge_prompt.py      # 多源合并提示词
```

---

## 四、各模块实现方案

### 4.1 Excel 读写模块 (`excel_handler.py`)

**职责：** 读取专家名单，写回提取结果。

**关键实现要点：**

- 使用 `openpyxl` 库，`load_workbook()` 加载，遍历指定列读取姓名。
- 写回时在原表头部追加新列（简介、研究方向、职称/职务、单位、邮箱、电话、个人主页、信息来源URL、提取状态、备注）。
- 支持断点续采：检查"提取状态"列，跳过已成功采集的行。
- 每采集完一位专家立即保存文件，防止中断丢失数据。

**接口定义：**

```python
class ExcelHandler:
    def __init__(self, filepath: str):
        """加载 Excel 文件"""
  
    def read_expert_names(self, name_col: str = "A", start_row: int = 2) -> list[dict]:
        """
        读取专家名单
        返回: [{"row": 2, "name": "张三", "affiliation": "清华大学"}, ...]
        """
  
    def write_result(self, row: int, result: ExpertInfo):
        """将单条提取结果写入指定行"""
  
    def save(self):
        """保存文件"""
```

### 4.2 搜索策略模块 (`search_strategy.py`)

**职责：** 为每位专家生成多轮搜索关键词。

**策略设计（分层递进）：**

- **L1 精确定位：** `"姓名" "单位" 教授`（已知单位时） 或 `"姓名" 计算机 教授`
- **L2 官网定位：** `姓名 单位 个人主页` 或 `site:edu.cn 姓名`
- **L3 百科兜底：** `姓名 百度百科 计算机`
- **L4 广泛搜索：** `姓名 计算机科学 学者`

```python
def generate_queries(name: str, affiliation: str = "") -> list[str]:
    """生成搜索关键词列表（按优先级排序），返回 4-6 个候选查询"""
```

### 4.3 URL 优先级筛选模块 (`url_ranker.py`)

**职责：** 对搜索结果中的 URL 进行可信度评分。

**可信度分级体系：**

| 优先级     | 来源类型           | 域名特征                                                   | 分值 |
| ---------- | ------------------ | ---------------------------------------------------------- | ---- |
| P0（最高） | 院校官网教师主页   | `.edu.cn`、各高校域名                                    | 100  |
| P1         | 中科院/研究所官网  | `.cas.cn`、`.ac.cn`                                    | 95   |
| P2         | 百度百科/搜狗百科  | `baike.baidu.com` 等                                     | 85   |
| P3         | 知名企业官网人员页 | 企业官方域名 `/about`、`/team` 路径                    | 80   |
| P4         | 学术平台           | `scholar.google.com`、`dblp.org`、`researchgate.net` | 75   |
| P5         | 政府/基金委        | `.gov.cn`                                                | 70   |
| P6         | 权威媒体报道       | `xinhuanet.com`、`people.com.cn`                       | 60   |
| P7（最低） | 其他来源           | 论坛、博客、自媒体                                         | 20   |

**排除规则：** 纯搜索中间页、社交媒体动态、招聘网站、纯论文列表、需登录页面。

```python
class URLRanker:
    def score_url(self, url: str) -> int: ...
    def rank_urls(self, urls: list[str]) -> list[str]: ...
    def is_blocked(self, url: str) -> bool: ...
```

### 4.4 Browser-Use Agent 封装 (`browser_agent.py`)——核心改进

**关键架构决策：使用单 Agent 多步完成，而非拆分为多个 Agent。**

原因：

- browser-use 的 Agent 本身就是多步循环执行的，天然支持 step-by-step。
- 拆分为多个 Agent 会丢失浏览器上下文（页面状态、Cookie、历史记录）。
- 单 Agent 可以根据中间发现动态调整策略（如发现单位信息后改进搜索）。

**核心配置：**

```python
from browser_use import Agent, Browser, BrowserConfig
from browser_use.controller.service import Controller

# 关键：给足 steps 预算，因为多步跳转需要更多步
AGENT_CONFIG = {
    "max_steps": 40,               # 从20提升到40，适应深度导航
    "max_actions_per_step": 5,     # 每步最多5个原子操作
    "use_vision": True,            # 开启视觉模式，处理图片化内容
    "generate_gif": False,         # 生产环境关闭，调试时开启
    "save_conversation_path": "./logs/",  # 保存对话用于调试
}

browser_config = BrowserConfig(
    headless=True,
    disable_security=False,
    extra_chromium_args=[
        "--disable-blink-features=AutomationControlled",  # 减少被检测概率
    ],
)
```

**结构化输出集成——通过 Controller 自定义 action：**

```python
from pydantic import BaseModel
from typing import Optional

class ExpertInfoResult(BaseModel):
    """定义为 browser-use 的自定义 action 返回类型"""
    name: str
    biography: Optional[str] = None
    research_areas: Optional[str] = None
    title: Optional[str] = None
    affiliation: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    homepage: Optional[str] = None
    source_urls: list[str] = []
    status: str = "成功"
    notes: Optional[str] = None

controller = Controller()

@controller.action(
    "当你收集到足够的专家信息后，调用此 action 提交最终结果",
    param_model=ExpertInfoResult,
)
async def submit_expert_info(params: ExpertInfoResult):
    """将提取结果结构化返回给主程序"""
    return params.model_dump_json()
```

**Agent 创建与调用：**

```python
async def process_expert(name: str, affiliation: str = "") -> ExpertInfoResult:
    task = build_task_prompt(name, affiliation)  # 见第五节
  
    browser = Browser(config=browser_config)
  
    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        controller=controller,    # 注册自定义 action
        max_steps=40,
        use_vision=True,
    )
  
    try:
        result = await agent.run()
        # 解析 agent 最终输出
        return parse_agent_result(result)
    except Exception as e:
        return ExpertInfoResult(
            name=name, 
            status="失败", 
            notes=str(e)
        )
    finally:
        await browser.close()
```

### 4.5 数据模型 (`models.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional

class ExpertInfo(BaseModel):
    name: str = Field(description="专家姓名")
    biography: Optional[str] = Field(default=None, description="个人简介, 200-500字")
    research_areas: Optional[str] = Field(default=None, description="研究方向")
    title: Optional[str] = Field(default=None, description="职称/职务")
    affiliation: Optional[str] = Field(default=None, description="所属单位")
    email: Optional[str] = Field(default=None, description="电子邮箱")
    phone: Optional[str] = Field(default=None, description="联系电话")
    homepage: Optional[str] = Field(default=None, description="个人主页URL")
    source_url: str = Field(description="信息来源网址")
    status: str = Field(default="成功", description="提取状态")
    notes: Optional[str] = Field(default=None, description="备注")
```

---

## 五、提示词设计（核心——v2 多步感知版）

### 5.1 设计原则

针对 browser-use 的 step-by-step 执行机制，提示词需满足以下原则：

1. **阶段感知（Phase-Aware）：** Agent 每一步都会重新阅读 task，提示词必须让 Agent 能判断"我现在处于哪个阶段"。
2. **条件分支（Conditional Branching）：** 不同页面类型需要不同操作，提示词中必须显式列出判断条件和对应动作。
3. **目标锚定（Goal Anchoring）：** 多步执行中 Agent 容易"迷路"，需要反复强调最终目标和完成条件。
4. **回退机制（Fallback）：** 明确死胡同的识别条件和回退操作。
5. **信息累积（Incremental Collection）：** 指示 Agent 在多个页面/标签页逐步积累信息，而非期望一页获取全部。

### 5.2 主任务提示词（Task Prompt）——多步感知版

这是传给 `Agent(task=...)` 的完整提示词模板。这是本方案最核心的交付物。

```
## 你的身份
你是一个专业的学术专家信息检索Agent。你将在浏览器中通过多步操作，查找计算机/信息科学领域专家的公开信息。

## 目标专家
- 姓名：{expert_name}
- 已知单位：{affiliation}（如为空则表示未知，需要你在搜索过程中确认）

## 最终目标
找到并提取该专家的以下信息：简介、研究方向、职称/职务、所属单位、邮箱、电话、个人主页。
当你收集到足够信息后（至少获得3个以上字段），调用 submit_expert_info action 提交结果。

## ===== 执行流程（逐步跟随） =====

### 阶段1：搜索
1. 打开 https://www.baidu.com
2. 使用以下搜索词（按顺序尝试，第一个有效即可）：
   - 第1优先：{query_1}
   - 第2优先：{query_2}
   - 第3优先：{query_3}
3. 如果页面有弹窗或Cookie提示，先关闭它

### 阶段2：搜索结果筛选
在搜索结果页面中，你需要判断并选择最佳的链接来点击。

**优先点击（按优先级排序）：**
- .edu.cn 域名的链接（大学官网）→ 这是最优来源
- .ac.cn 或 .cas.cn 域名的链接（中科院/研究所）
- baike.baidu.com 的链接（百度百科）
- 知名企业官网中明确包含专家名字的链接

**不要点击：**
- 招聘网站（boss直聘、猎聘、智联等）
- 微博、知乎问答页、微信公众号
- 纯论文数据库（知网论文列表页、万方）
- 视频网站（B站、优酷）

**关键判断：** 如果搜索结果中已经有 .edu.cn 域名的教师个人页链接，直接点击它。如果只有院校首页或院系首页的链接，也要点击——你可以在进入后继续导航到教师页面。

### 阶段3：页面深度导航（关键！）

点击搜索结果后，你到达的页面可能是以下几种类型。根据页面类型执行不同操作：

**情况A：你到达了专家的个人详情页**
特征：页面上有该专家的姓名、照片、简介、研究方向等详细信息。
→ 直接进入阶段4（提取信息）。

**情况B：你到达了院校/院系的首页或导航页**
特征：页面是某大学或某学院的主页，没有具体教师信息。
→ 寻找并点击以下菜单项（不同网站文案不同，按可能性排列）：
  - "师资队伍" / "师资力量" / "教师名录" / "Faculty"
  - "人才团队" / "科研团队" / "研究人员"
  - "教授" / "教师" / "People" / "Members"
  - 如果有搜索框，直接在站内搜索专家姓名
→ 进入教师列表后，找到并点击目标专家姓名的链接。

**情况C：你到达了教师列表页**
特征：页面显示多位教师的姓名（可能带照片和简短头衔）。
→ 在列表中找到目标专家「{expert_name}」，点击其姓名或"详情"链接。
→ 如果当前页面没有该专家，检查是否有分页，翻到下一页继续查找。
→ 如果整个列表都没有，回退到搜索（浏览器后退或重新打开百度）。

**情况D：你到达了百度百科页面**
特征：URL 包含 baike.baidu.com，页面有词条结构。
→ 首先确认该词条确实是目标专家（检查姓名和领域）。
→ 如果页面有"展开全部"或"查看更多"按钮，点击展开。
→ 提取信息（进入阶段4）。

**情况E：你到达了无关页面或错误页面**
特征：页面内容与目标专家无关、404错误、需要登录。
→ 立即回退：点击浏览器后退按钮。
→ 如果回退后仍在无关页面，直接在地址栏重新打开百度搜索，换用下一个搜索关键词。

**情况F：你到达了有专家信息但不够完整的页面**
特征：页面有部分信息（如只有姓名和职称，没有邮箱和简介）。
→ 先提取当前页面上所有可用信息（记在心里）。
→ 检查页面上是否有其他标签页/选项卡：如"个人简介"、"科研成果"、"联系方式"等，逐一点击查看。
→ 如果页面有"个人主页"的外部链接，点击跳转获取更多信息。
→ 如果仍不完整，回退到搜索结果页尝试下一个链接。

### 阶段4：信息提取

当你到达包含专家详细信息的页面时，提取以下字段：

1. **个人简介**：教育背景、工作经历、主要成就（200-500字）。保留关键年份和学术头衔（如IEEE Fellow）。
2. **研究方向**：所有提及的研究领域，用逗号分隔。
3. **职称/职务**：当前最高职称 + 行政职务，用"/"分隔。
4. **所属单位**：完整机构名称，如"清华大学计算机科学与技术系"。
5. **邮箱**：公开的电子邮箱。注意 [at] 或 # 替代 @ 的情况，请还原为标准格式。
6. **电话**：公开的办公电话。
7. **个人主页**：学术主页URL。

### 阶段5：补充（如信息不完整）

如果从第一个来源获取的信息不够完整（缺少3个以上字段），请：
1. 回退到百度搜索结果页，点击下一个优先级的链接。
2. 或者发起新的搜索："{expert_name} 邮箱 联系方式"。
3. 从新页面中补充缺失的字段。
4. 最多额外访问2个来源。

### 阶段6：提交结果

当你满足以下任一条件时，调用 submit_expert_info 提交结果：
- 已获取5个以上字段的信息（提交：status=成功）
- 已获取3-4个字段的信息（提交：status=部分成功）
- 已尝试3个以上来源仍未获取有效信息（提交：status=失败，notes中说明原因）
- 已执行超过30步操作（提交当前已有信息，避免超时）

## ===== 关键规则 =====

1. **只提取页面上明确存在的信息，绝对不要猜测或编造任何内容**。找不到的字段填 null。
2. **确认身份一致性**：每次提取前，确认页面上的人就是目标专家「{expert_name}」。如果有同名不同人的情况，通过单位、研究领域交叉验证。
3. **高效导航**：不要在同一页面反复操作。如果一个页面3步内找不到有用信息，立即离开。
4. **记住来源**：记录每个提取到信息的页面URL，最终在 source_urls 中列出。
5. **处理弹窗**：遇到任何弹窗（Cookie提示、广告弹窗、订阅提示），先关闭再继续。
6. **滚动查看**：如果页面很长，向下滚动查看更多内容，不要只看首屏。
```

### 5.3 提示词模板的代码实现

```python
# prompts/task_prompt.py

TASK_PROMPT_TEMPLATE = """
## 你的身份
你是一个专业的学术专家信息检索Agent...
（完整内容同上 5.2）
"""

def build_task_prompt(
    expert_name: str, 
    affiliation: str = "",
    queries: list[str] = None
) -> str:
    """
    构建完整的 Agent task 提示词
  
    Args:
        expert_name: 专家姓名
        affiliation: 已知单位（可选）
        queries: 预生成的搜索关键词列表
  
    Returns:
        格式化后的 task 字符串
    """
    if queries is None:
        queries = generate_queries(expert_name, affiliation)
  
    # 确保至少有3个查询词
    while len(queries) < 3:
        queries.append(f"{expert_name} 计算机科学 学者")
  
    return TASK_PROMPT_TEMPLATE.format(
        expert_name=expert_name,
        affiliation=affiliation if affiliation else "未知",
        query_1=queries[0],
        query_2=queries[1],
        query_3=queries[2],
    )
```

### 5.4 多源合并提示词（当使用多 Agent 或外部 LLM 合并时）

```
你是一个数据合并助手。以下是从多个网页分别提取到的关于专家「{expert_name}」的信息。
请将这些信息合并为一条最终记录。

【多源数据】
来源1（类型：{source1_type}，URL：{source1_url}）：
{source1_data}

来源2（类型：{source2_type}，URL：{source2_url}）：
{source2_data}

【合并规则】
1. 优先级：院校官网 > 百度百科 > 企业官网 > 学术平台 > 其他来源
2. 同一字段有冲突时，取优先级最高的来源
3. 简介：取最完整版本；不同来源有互补信息时整合为一段流畅文字
4. 研究方向：合并所有不重复的方向
5. 联系方式：优先使用院校官网数据
6. source_url 选择提供信息最多的那个来源
7. 在 notes 中记录任何信息矛盾

【输出格式】返回合并后的单一 JSON 对象。
```

---

## 六、与 v1 方案的关键差异对比

| 维度         | v1 方案                             | v2 方案（本版）                               |
| ------------ | ----------------------------------- | --------------------------------------------- |
| Agent 架构   | 双阶段分离（搜索Agent + 提取Agent） | 单 Agent 多步完成，保持浏览器上下文连续       |
| 提示词结构   | 线性指令列表                        | 阶段感知 + 条件分支，适配 step-by-step 循环   |
| 导航深度     | 假设搜索→点击→提取（2步）         | 覆盖3-7步深度导航，含列表页→详情页跳转       |
| 页面类型处理 | 未区分                              | 明确6种页面类型（A-F）及各自操作指令          |
| 错误恢复     | 简单跳过                            | 显式回退策略（后退按钮/重新搜索）             |
| max_steps    | 20-30                               | 40（适应深度导航）                            |
| 信息累积     | 期望单页提取全部                    | 支持多页面/多标签逐步积累，显式补充阶段       |
| 完成判断     | 依赖 Agent 自行判断                 | 明确量化条件（5字段=成功，3-4字段=部分成功）  |
| 结构化输出   | 依赖 LLM 文本解析                   | 通过 Controller 自定义 action + Pydantic 模型 |
| 动态内容处理 | 未涉及                              | 指示滚动、展开、切换标签页                    |
| 弹窗处理     | 未涉及                              | 显式"关闭弹窗"指令                            |

---

## 七、运行流程与并发控制

### 7.1 主流程 (`main.py`)

```python
import asyncio
from browser_use import Agent, Browser, BrowserConfig
from browser_use.controller.service import Controller

async def main(excel_path: str):
    # 1. 读取 Excel
    handler = ExcelHandler(excel_path)
    experts = handler.read_expert_names()
  
    # 2. 过滤已完成的（断点续采）
    pending = [e for e in experts if e.get("status") != "成功"]
  
    # 3. 并发控制（建议 2-3）
    semaphore = asyncio.Semaphore(2)
  
    async def process_one(expert: dict):
        async with semaphore:
            # 每个专家使用独立的 Browser 实例
            browser = Browser(config=browser_config)
            controller = create_controller()  # 包含 submit_expert_info action
          
            task = build_task_prompt(
                expert_name=expert["name"],
                affiliation=expert.get("affiliation", "")
            )
          
            agent = Agent(
                task=task,
                llm=llm,
                browser=browser,
                controller=controller,
                max_steps=40,
                use_vision=True,
            )
          
            try:
                result = await agent.run()
                expert_info = parse_agent_result(result)
                handler.write_result(expert["row"], expert_info)
                handler.save()
            except Exception as e:
                handler.write_result(expert["row"], ExpertInfo(
                    name=expert["name"],
                    status="失败",
                    notes=f"Agent异常: {str(e)}",
                    source_url=""
                ))
                handler.save()
            finally:
                await browser.close()
          
            # 请求间隔，避免触发反爬
            await asyncio.sleep(3)
  
    # 4. 批量执行
    tasks = [process_one(e) for e in pending]
    await asyncio.gather(*tasks, return_exceptions=True)
  
    # 5. 统计报告
    print_summary(handler)
```

### 7.2 日志与调试

- `save_conversation_path` 参数保存每个 Agent 的完整对话记录。
- 调试时开启 `generate_gif=True`，生成浏览器操作动图。
- 调试时使用 `headless=False`，可视化观察 Agent 行为。

---

## 八、关键注意事项

### 8.1 反爬与合规

- 每次请求间隔建议 3-5 秒，避免触发反爬机制。
- 仅采集公开可访问的信息，不尝试绕过登录或验证码。
- 遵守 robots.txt 协议。
- 采集到的个人信息应仅用于合法目的，注意数据保护合规。

### 8.2 成本与效率预估

| 指标                | 预估值          | 说明                           |
| ------------------- | --------------- | ------------------------------ |
| 每位专家 Token 消耗 | 10,000 - 30,000 | v2因多步执行比v1更高           |
| 每位专家平均耗时    | 1-3 分钟        | 取决于导航深度和页面加载速度   |
| 每位专家平均步数    | 10-25 步        | 简单案例约10步，复杂案例约25步 |
| 建议试运行规模      | 5-10 人         | 评估后再批量执行               |

### 8.3 常见问题应对表

| 问题                     | 应对策略                                                 |
| ------------------------ | -------------------------------------------------------- |
| Agent 在某个页面无限循环 | max_steps=40 强制终止；提示词中有"3步内找不到就离开"规则 |
| 同名不同人干扰           | 提示词要求交叉验证单位和领域                             |
| 院校官网结构差异大       | 提示词列举了多种菜单文案变体；开启 use_vision 辅助理解   |
| 页面反爬/验证码          | 记录失败，跳到下一个来源URL                              |
| 联系方式为图片           | use_vision=True 可识别图片中的文字                       |
| 动态加载内容             | 提示词指示滚动和点击展开                                 |
| 专家已退休/信息过时      | 在 notes 中标注信息时效性                                |

### 8.4 browser-use 版本注意

- 建议使用 `browser-use >= 0.1.40`。
- Controller 的自定义 action API 可能随版本变动，实施前需查阅最新文档。
- `use_vision` 依赖多模态 LLM（GPT-4o / Claude），纯文本模型不支持。

---

## 九、依赖安装

```bash
pip install browser-use openpyxl pydantic langchain-openai playwright
playwright install chromium
```

---

## 十、验收标准

| 指标                 | 目标值   |
| -------------------- | -------- |
| 姓名+单位 提取成功率 | ≥ 95%   |
| 简介 提取成功率      | ≥ 80%   |
| 邮箱 提取成功率      | ≥ 60%   |
| 单位专家平均耗时     | < 3 分钟 |
| 信息准确率（抽检）   | ≥ 90%   |
| Agent 无限循环率     | < 5%     |

---

*文档版本：v2.0 | 适用于 browser-use >= 0.1.40*
*主要改进：多步导航感知、条件分支提示词、深度页面处理、回退机制*
