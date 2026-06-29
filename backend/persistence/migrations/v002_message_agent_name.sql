-- v002: messages 表新增 agent_name 字段
-- 标记当前消息是哪个 agent 接收/处理的
-- novel_steward / novel_writer / world_tree_manager
-- user 消息的 agent_name 标记为接收该消息的 agent（通常是 novel_steward）
ALTER TABLE messages ADD COLUMN agent_name TEXT;
CREATE INDEX IF NOT EXISTS idx_msg_agent ON messages(agent_name, created_at DESC);

