-- realtime_novel v0.9: 世界封面图
-- 生成日期: 2026-06-24 蕾姆酱
-- 背景: onboarding Step 4 完成后，Gemini 并发生成世界主图（1:1），URL 持久化到 projects 表
-- 图片文件存放到 data/projects/{project_id}/cover.png，cover_image_url 存相对路径

ALTER TABLE projects ADD COLUMN cover_image_url TEXT;
-- 示例值: /static/projects/world-3f7a8b2c/cover.png
-- null 表示尚未生成（旧项目 / 生成失败）

