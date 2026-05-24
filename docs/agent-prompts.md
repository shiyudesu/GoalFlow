# Agent Prompt 设计指南

## 设计原则

1. **输出结构化**：所有 Agent 必须输出 JSON，便于程序解析
2. **锚点前置**：每个 Agent 的 prompt 中必须包含 PRD 锚点
3. **自检要求**：Prompt 中明确要求 Agent 自我检查是否遗漏
4. **拒绝妥协**：明确告知 Agent 不允许简化、跳过或假设

## 各 Agent Prompt 要点

### RequirementAgent
- 要求覆盖所有用户提到的功能
- 消除歧义，基于最合理假设澄清
- 输出为结构化 PRD

### PlanningAgent
- 任务必须原子化（不可再分）
- 每个任务必须有可验证的 DoD
- 必须覆盖 PRD 所有功能点

### ModuleLocatorAgent
- 基于实际文件树分析
- 给出选择文件的理由
- 识别依赖影响和副作用

### CodingAgent
- modify 时必须提供精确 search_block
- 遵循项目现有编码风格
- 不省略任何实现细节

### TestingAgent
- 覆盖正常路径和边界情况
- 使用项目已有测试框架
- 测试代码必须可直接运行

### SelfCheckAgent
- 严格、诚实、不妥协
- coverage_score < 90 视为不合格
- 必须列出所有遗漏和偏差
