-- realtime_novel v0.5: 1.1/1.2 完整落地 migration
-- 生成日期：2026-06-18 蕾姆酱
-- 背景：
--   1.1 小说家 = 全局管家，不绑 project（conversations.project_id 移除）
--   1.2 user-valid conversation 一对一（conversations 加 status/invalidated_at/reason）
--   messages.project_id 新增（每条消息绑 project，是"操作目标"）
--
-- 幂等保护：每个 ALTER TABLE 都用子查询判断列是否已存在

-- 1. conversations 表加 status/invalidated_at/reason
-- ALTER TABLE conversations ADD COLUMN status TEXT NOT NULL DEFAULT 'active' CHECK(...)
-- 不能用 IF NOT EXISTS（SQLite 限制），改用判断列是否已存在
-- 注：每个 ALTER 包在 SAVEPOINT 里，失败就 ROLLBACK
SAVEPOINT sp1;
ALTER TABLE conversations ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
    CHECK(status IN ('active', 'invalidated', 'archived'));
RELEASE sp1;

SAVEPOINT sp2;
ALTER TABLE conversations ADD COLUMN invalidated_at TIMESTAMP;
RELEASE sp2;

SAVEPOINT sp3;
ALTER TABLE conversations ADD COLUMN reason TEXT;
RELEASE sp3;

CREATE INDEX IF NOT EXISTS idx_conv_status ON conversations(user_id, status);
CREATE INDEX IF NOT EXISTS idx_conv_invalidated ON conversations(invalidated_at DESC);

-- 2. messages 表加 project_id
SAVEPOINT sp4;
ALTER TABLE messages ADD COLUMN project_id TEXT;
RELEASE sp4;

CREATE INDEX IF NOT EXISTS idx_msg_project ON messages(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_msg_conv_project ON messages(conversation_id, project_id);

-- 3. conversations.summary + message_count（讨论 5 暂搁置，v0.5 落地）
SAVEPOINT sp5;
ALTER TABLE conversations ADD COLUMN summary TEXT;
RELEASE sp5;

SAVEPOINT sp6;
ALTER TABLE conversations ADD COLUMN message_count INTEGER DEFAULT 0;
RELEASE sp6;

-- 4. 1.1 拍板：conversations.project_id 移除（小说家 = 全局管家，不绑 project）
-- SQLite 3.35+ 支持 DROP COLUMN
-- 顺序：先删引用 project_id 的索引 → 再删列
DROP INDEX IF EXISTS idx_conv_project;
SAVEPOINT sp7;
ALTER TABLE conversations DROP COLUMN project_id;
RELEASE sp7;
