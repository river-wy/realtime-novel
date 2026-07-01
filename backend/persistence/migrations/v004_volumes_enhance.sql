-- v004_volumes_enhance.sql
-- 欧尼酱 20:16 拍板：volumes 表加 status + summary 字段
-- 背景：之前 _load_project_data 没读 volumes，_format_chapter_summaries_by_volume
--       实际拿到的是空 list，所有章节都降级到 "__no_volume__" 分组 = 无卷模式
-- 修复：
--   1. status    TEXT DEFAULT 'in_progress' (in_progress / completed)
--   2. summary   TEXT (整卷 1000 字总结，卷完结时由 generate_volume_summary 写入)

-- 状态枚举约束（轻量 CHECK，SQLite < 3.37 不强制但保留语义）
-- v004 注意：不加 CHECK 约束（SQLite 兼容性），应用层 enum 保证

ALTER TABLE volumes ADD COLUMN status TEXT NOT NULL DEFAULT 'in_progress';
ALTER TABLE volumes ADD COLUMN summary TEXT;

-- 加索引：按 status 过滤（找当前活跃卷时常用）
CREATE INDEX IF NOT EXISTS idx_volumes_status ON volumes(project_id, status);
