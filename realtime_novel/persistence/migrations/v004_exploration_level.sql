-- realtime_novel v0.8: 探索度旋钮 (conservative/standard/wild)
-- 生成日期: 2026-06-22 蕾姆酱
-- 背景: 用户希望同一题材反复创作时能探索不同方向, 探索度旋钮控制 LLM Temperature/补充范围/篇幅
-- 取值: conservative | standard(默认) | wild
-- standard 是为了与 v0.7 默认行为保持一致, 旧项目自动升级为 standard

ALTER TABLE projects ADD COLUMN exploration_level TEXT NOT NULL DEFAULT 'standard';

-- CHECK 约束 (SQLite 3.3+ 支持, 注意: ALTER TABLE 加 CHECK 不会应用到已存在的数据, 后续 INSERT 会校验)
-- 不在这里加 CHECK, 避免 SQLite 老版本不兼容, 由 Pydantic schema 校验

-- 索引 (按 exploration_level 过滤项目列表, 暂时不加 — 探索度不是常用查询字段)
-- CREATE INDEX IF NOT EXISTS idx_projects_exploration ON projects(exploration_level);
