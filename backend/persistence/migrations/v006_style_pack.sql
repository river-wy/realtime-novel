-- v006: 新增 style_pack_id 字段到 projects 表
--
-- style_pack 作为第 7 件基座，替代废弃的 style_charter。
-- style_charter 表暂保留（代码层面已废弃），后续清理迁移再删。
--
-- style_pack_id 存储笔风库中的笔风 id（如 yanhuo_shiyi / shuise_qiangwei 等），
-- 为空时组装模块使用默认笔风（yanhuo_shiyi）。

ALTER TABLE projects ADD COLUMN style_pack_id TEXT;

