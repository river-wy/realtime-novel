"""backend.tests 包入口

v0.4 测试层：
- conftest.py: fixtures (temp_db / test_app / mock_llm)
- test_persistence.py: SQLite 5 张表 + Repository
- test_tools.py: 13 个工具
- test_state_graph.py: 6 节点 LangGraph
- test_http_routes.py: 12 个 RESTful 端点
- test_ws_channel.py: WS /api/chat
- test_e2e.py: 端到端
"""
