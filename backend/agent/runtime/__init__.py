"""runtime — Agent 运行时基础设施（v0.6.2 重塑）

- executor: ReAct loop 引擎（max_iterations=7）

v0.6.2 删除:
- intent_recognizer.py: 管家 ReAct 化后不再预分类 intent
- state.py: Intent 枚举 + AgentState 数据类（v0.4 旧 schema, 已废弃）
"""