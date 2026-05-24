# GoalFlow 🎯

**目标锚定的全链路智能开发平台**

GoalFlow 是一个对话驱动的自动化软件开发平台，对标 OpenHands / Ralph Loop / `/goal` 模式。它解决了当前 AI Agent 面对复杂需求时容易**偷懒、目标漂移、半途而废**的核心痛点，支持从需求澄清到代码部署的完整链路，并在每个阶段引入 **Human-in-the-loop** 机制。

---

## 🚀 核心特性

| 特性 | 说明 |
|------|------|
| **六阶段工作流** | 需求澄清 → 方案拆解 → 模块定位 → 代码生成 → 自动化测试 → 代码部署 |
| **目标锚定（Anti-Drift）** | PRD 作为不可变锚点，每阶段强制一致性校验，杜绝目标漂移 |
| **未完成不前进** | 原子任务 + DoD（完成定义），未达标禁止进入下一阶段 |
| **预算与升级** | 任务重试预算耗尽后自动重构方案或强制人工介入 |
| **Human-in-the-loop** | 每阶段可配置 auto/manual，支持人工澄清、修订、回退 |
| **GitHub PR 生命周期** | 自动创建 Draft PR → 请求 Review → CI 监控 → 反馈修复 → 合并 |
| **事件驱动架构** | 基于事件总线的松耦合 Agent 协作，支持断点续跑 |

---

## 📦 安装

```bash
# 克隆仓库
git clone <repo-url>
cd goalflow

# 使用 uv 安装依赖
uv sync

# 或使用 pip
pip install -e .
```

### 环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 和 GITHUB_TOKEN
```

---

## 🖥️ CLI 使用

### 运行完整工作流

```bash
# 自动模式（跳过所有人工检查点）
goalflow run /path/to/repo "添加用户认证功能，使用 JWT"

# 手动模式（每阶段暂停等待确认）
goalflow run /path/to/repo "添加用户认证功能" --manual

# 从文件读取需求
goalflow run /path/to/repo @requirement.txt

# 指定模型
goalflow run /path/to/repo "需求描述" --model claude-3-opus-20240229
```

### 管理 Session

```bash
# 列出所有会话
goalflow list

# 查看会话详情
goalflow show <session-id>

# 恢复会话（断点续跑）
goalflow resume <session-id>
```

---

## 🌐 Web API

```bash
# 启动 API 服务
uv run uvicorn goalflow.api.app:app --host 0.0.0.0 --port 8000
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/sessions` | 创建会话并启动工作流 |
| GET | `/sessions` | 列所有会话 |
| GET | `/sessions/{id}` | 获取会话详情 |
| GET | `/sessions/{id}/events` | 获取事件历史 |
| GET | `/sessions/{id}/stream` | SSE 实时事件流 |
| POST | `/sessions/{id}/checkpoint/{stage}` | 响应人工检查点 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    用户交互层 (CLI / Web API)                 │
├─────────────────────────────────────────────────────────────┤
│                  编排控制层 (Session + State Machine)         │
├─────────────────────────────────────────────────────────────┤
│                   Agent 执行层                               │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐ │
│  │ 需求Agent│ │ 方案Agent│ │ 模块Agent│ │ 编码Agent│ │测试Agent│ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └────────┘ │
│                    ┌─────────┐ ┌─────────┐                  │
│                    │ 部署Agent│ │自检Agent│                  │
│                    └─────────┘ └─────────┘                  │
├─────────────────────────────────────────────────────────────┤
│                   基础设施层                                  │
│   Event Bus │ Memory Store │ GitHub API │ LLM Provider       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧪 测试

```bash
uv run pytest tests/ -v
```

---

## 🐳 Docker

```bash
# 构建镜像
docker build -t goalflow .

# 运行
docker run -p 8000:8000 --env-file .env goalflow
```

---

## 📁 项目结构

```
goalflow/
├── goalflow/
│   ├── core/           # 状态机、事件总线、Session、检查点
│   ├── agents/         # 各阶段 Agent + 自检 Agent
│   ├── api/            # FastAPI Web 服务
│   ├── github/         # GitHub API 封装
│   ├── llm/            # LLM 统一客户端
│   ├── memory/         # 上下文与记忆存储
│   └── cli.py          # CLI 入口
├── tests/              # 测试
├── config/             # 配置文件模板
├── docs/               # 架构文档
├── pyproject.toml
└── Dockerfile
```

---

## ⚙️ 配置

编辑 `config/goalflow.yaml`：

```yaml
workflow:
  default_mode: auto
  checkpoint_override:
    deploy: manual  # 部署阶段人工确认
  anti_drift:
    coverage_threshold: 90
    max_task_attempts: 5

github:
  base_branch: main
  auto_merge: false
```

---

## 🔒 防漂移机制详解

GoalFlow 与常规 Agent 框架的核心区别在于**强制防漂移**：

1. **需求锚定**：PRD 一经生成即不可变，后续所有产出必须与之一致性校验
2. **原子任务 + DoD**：任务必须细到不可再分，且 DoD 可客观验证
3. **自检 Agent**：每阶段完成后独立校验，覆盖率 < 90% 强制打回
4. **预算与升级**：单任务最多 5 次尝试，耗尽则重构方案或人工介入
5. **分层摘要**：上下文窗口不足时，核心目标以压缩形式传递，防止遗忘

---

## 📄 License

MIT
