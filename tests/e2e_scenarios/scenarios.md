# 业务场景长链路用例（v0.7.1）— 2026-07-01 蕾姆

> **目标**：覆盖 3 个 agent + 全部 11+4+7 = 22 个工具 + 14 个 HTTP 端点，验证实际实现
> **方式**：用 HTTP 客户端 + 直接调工具层，模拟真实用户路径
> **重点验证**：
>   1. agent 路由是否正确（管家→管家工具 / 管家→委托 WTM / 管家→委托 文笔家）
>   2. 世界树基座数据是否正确生成落库（9 张表）
>   3. prompt/context 加载数据是否正确，相关 agent 是否有依赖工具

---

## 场景 1：新用户从零开始，写一个完整故事（最完整路径）

**用户故事**：
> 张三第一次打开应用，想写个"程序员穿越古代修真界"的奇幻小说

**完整路径**：
1. `POST /projects` 创建项目
   - 触发：管家 LLM 调 `create_project(name="穿越修真", palette="#3a5f8f", exploration_level="standard", style_pack_id="xianxia_ranhu")`
   - 落库：projects / project_state
2. 管家 LLM 调 `list_style_packs` 验证笔风（虽然 create 已传 style_pack_id）
3. 管家 LLM 调 `adjust_style` 二次确认笔风
4. 多轮对话：用户描述故事核心、角色、世界观、笔风
5. 管家 LLM 调 `verify_world_tree_baseline(project_id)` 校验 6 项
6. 管家 LLM 调 `delegate_to_agent(agent="world_tree_manager", mode="full_baseline", payload=...)` 委托 WTM
   - WTM 落库：world_tree / characters / main_plot / sub_plot / volumes / world_entries / timeline_events / geography_locations + core_rules
   - 自动触发 `onboarding.step4_confirmed` 事件 → 后台生成项目名 + 封面
7. `POST /projects/{id}/chapters` 生成第 1 章
   - 触发：管家调 `delegate_to_agent(agent="novel_writer", task="第 1 章")`
   - 落库：chapters
8. `GET /projects/{id}/chapters` 列出所有章节
9. `GET /projects/{id}/chapters/1` 读第 1 章内容

**验证点**：
- ✅ 9 张表全有数据
- ✅ projects.deleted_at IS NULL
- ✅ project_state.current_chapter = 1
- ✅ chapter.content 已生成
- ✅ 封面图 URL 已写入
- ✅ 项目名已生成

**潜在 Gap 检查**：
- ❓ 管家 LLM 调 `list_style_packs` 时——WTM agent 不在白名单，会不会绕过 LLM 调工具？
- ❓ 第 7 步 `delegate_to_agent(agent="novel_writer")` 是不是真触发了 novel_writer ReAct loop（不是直接调 generate_chapter）？
- ❓ 第 1 章生成时，context 是否注入了完整世界树（9 张表）？

---

## 场景 2：用户读到一半想改剧情（章节调整路径）

**用户故事**：
> 张三读到第 3 章，发现主角性格太弱了，想加一个"师父指点"的情节

**完整路径**：
1. `POST /projects/{id}/interventions` 提交干预
   - 触发：管家 LLM 调 `delegate_to_agent(agent="world_tree_manager", task="主角下一章需要师父指点")`（mode 默认 analyze）
   - WTM.analyze_intervention 评估：risk / consistency / requires_confirm
   - 落库：chapters.intervention = "主角下一章需要师父指点"
2. `POST /projects/{id}/chapters` 生成第 4 章
   - 触发：管家 LLM 调 `delegate_to_agent(agent="novel_writer", task="按 intervention 写第 4 章")`
   - novel_writer 自动读 chapters.intervention，注入 prompt
   - 落库：chapters
3. `GET /projects/{id}/chapters/4` 验证第 4 章内容

**验证点**：
- ✅ chapters[3].intervention = "主角下一章需要师父指点"
- ✅ chapters[4] 实际内容反映了"师父指点"
- ✅ analyze_intervention 的 risk_level 是 low/medium（不是 high 触发二次确认）

**潜在 Gap 检查**：
- ❓ novel_writer 调 `read_chapter` 时——它能读前面 3 章吗？
- ❓ WTM.analyze_intervention 返回的 requires_double_confirm 触发逻辑是什么？（管家看到要重新问用户？）
- ❓ consistency_checker.check_hard_rules 是否被调？

---

## 场景 3：用户改世界树（手动编辑基座）

**用户故事**：
> 张三在管家对话里说"主角有个妹妹叫林雪"，管家直接改基座

**完整路径**：
1. 管家 LLM 调 `edit_artifact(target="character", operation="add", data={name: "林雪", role: "sister"})`
   - 落库：characters 表
2. 管家 LLM 调 `verify_world_tree_baseline(project_id)` 校验
3. 管家 LLM 调 `PATCH /projects/{id}/base` 直接改基座字段（如 world_tree.story_core）
   - 触发：`update_base` 工具？还是直接 API？

**验证点**：
- ✅ characters 表新增"林雪"
- ✅ world_tree.story_core 已更新
- ✅ consistency_checker 校验通过（如果触发）

**潜在 Gap 检查**：
- ❓ 管家有 `edit_artifact` 但**没有** `update_base`——`update_base` 是 WTM 独有。如果用户说"改基座元数据"，管家要委托 WTM 吗？还是用 `edit_artifact` 凑合？
- ❓ `PATCH /base` 直接调 API 时——它走 `update_base` 还是 `edit_artifact`？

---

## 场景 4：Onboarding 失败回退（spec §5.8.4 失败路径）

**用户故事**：
> 张三信息没收集全就触发委托，WTM 校验失败

**完整路径**：
1. 管家 LLM 没调 `verify_world_tree_baseline` 就直接 `delegate_to_agent(mode="full_baseline")`
2. onboarding_artifacts.delegate_to_wtm 内部：
   - set_info_state("wtm_pending")
   - 调 generate_full_world_tree_baseline
   - 失败（LLM 异常 / 缺字段）
   - set_info_state("collecting")  ← 失败回退
   - 返回 error
3. 管家 LLM 收到 error，看到 onboarding_state 还是 collecting，继续对话

**验证点**：
- ✅ onboarding_state.info_state 流经 collecting → wtm_pending → collecting
- ✅ 没有任何基座数据落库（事务回滚或 WTM 失败前没 commit）

**潜在 Gap 检查**：
- ❓ WTM 失败时，`add_*` 系列方法落库的数据是否真回滚？（没有事务包裹？）
- ❓ 事件 `step4_confirmed` 不会 emit（成功路径才 emit），但失败时没日志？

---

## 场景 5：用户调整探索度（exploration_level）

**用户故事**：
> 张三觉得 AI 太保守了，要求更大胆

**完整路径**：
1. `PATCH /projects/{id}/exploration-level` body: {level: "wild"}
   - 触发：管家 LLM 调 `update_exploration_level(level="wild")`
   - 落库：project_state.exploration_level
2. 管家 LLM 调 `update_exploration_level(level="wild")` 确认（前端 UI 也可直调）
3. 生成下一章，novel_writer prompt 注入新的 exploration_level

**验证点**：
- ✅ project_state.exploration_level = "wild"
- ✅ 第 4 章内容比第 1 章更"野"

**潜在 Gap 检查**：
- ❓ `update_exploration_level` 是单项目还是全局？管家工具 description 写"调整项目/全局探索度"——全局怎么调？
- ❓ novel_writer prompt 实际能感知 exploration_level 吗？

---

## 场景 6：用户改笔风（中途换风格）

**用户故事**：
> 张三写到第 5 章觉得太严肃，想换轻松笔风

**完整路径**：
1. 管家 LLM 调 `list_style_packs` 拉所有可用笔风
2. 管家 LLM 调 `adjust_style(style_pack_id="qingkuai_danmei")` 切到新笔风
   - 落库：projects.style_pack_id
3. 生成第 6 章，novel_writer prompt 注入新笔风

**验证点**：
- ✅ projects.style_pack_id 已更新
- ✅ 第 6 章内容反映新笔风

**潜在 Gap 检查**：
- ❓ `list_style_packs` 真的会返回所有笔风？还是只返回已注册的？
- ❓ `adjust_style` 改了 projects.style_pack_id，但 chapter_tools / context_builder 是否真读这个字段？

---

## 场景 7：删除项目（软删 + 恢复路径）

**用户故事**：
> 张三写了一半想删项目重写

**完整路径**：
1. `DELETE /projects/{id}` body: {confirm: true}
   - 触发：管家 LLM 调 `delete_project(project_id, confirm=true)`
   - 软删：projects.deleted_at = now()
2. 项目移到 .trash/ 目录
3. 列出项目时（`GET /projects`），删除项目**不**出现

**验证点**：
- ✅ projects.deleted_at 非空
- ✅ .trash/ 下有项目数据
- ✅ GET /projects 列表不包含

**潜在 Gap 检查**：
- ❓ 管家 description 说"⚠️ 危险，需用户二次确认"——`delete_project` 工具本身有 confirm 校验吗？还是依赖 HTTP 层？
- ❓ 软删后还能 `load_project(id)` 吗？（应该不能，但代码里是否校验？）

---

## 场景 8：图片生成（封面 + 插图）

**用户故事**：
> 张三想给第 1 章生成配图

**完整路径**：
1. `POST /projects/{id}/image` body: {prompt: "主角林渊站在山巅", chapter_num: 1}
   - 触发：管家 LLM 调 `generate_image(prompt=..., chapter_num=1)`
   - 落库：image_url 字段
2. 用户确认图片
3. `POST /projects/{id}/rollback` 回滚到第 1 章前（如果配图要改）

**验证点**：
- ✅ chapters[0].image_url 非空
- ✅ 触发 step4_confirmed 事件后，封面图也生成

**潜在 Gap 检查**：
- ❓ `generate_image` 工具的 chapter_num 参数是 optional 吗？API 必填时工具是否对齐？
- ❓ `rollback` 工具的边界——是回滚章节内容还是回滚世界树基座？

---

# Gap 验证清单（执行时逐项检查）

| 编号 | 场景 | 检查项 | 严重度 |
|------|------|--------|--------|
| 1.1 | 场景 1 | 管家能否真用 list_style_packs（不在 novel_writer 白名单）| 🟠 |
| 1.2 | 场景 1 | delegate_to_agent(agent=novel_writer) 是否真触发 ReAct loop | 🟠 |
| 1.3 | 场景 1 | 第 1 章 context 是否注入 9 张表 | 🔴 |
| 2.1 | 场景 2 | novel_writer 能 read 前面 3 章 | 🟡 |
| 2.2 | 场景 2 | analyze_intervention.requires_double_confirm 触发逻辑 | 🟡 |
| 2.3 | 场景 2 | consistency_checker.check_hard_rules 是否被调 | 🔴 |
| 3.1 | 场景 3 | 管家能否用 update_base（WTM 独有）| 🟠 |
| 3.2 | 场景 3 | PATCH /base 走哪个路径 | 🟡 |
| 4.1 | 场景 4 | WTM 失败时 add_* 落库数据是否回滚 | 🔴 |
| 4.2 | 场景 4 | 失败路径日志 | 🟢 |
| 5.1 | 场景 5 | update_exploration_level 全局 vs 项目 | 🟡 |
| 5.2 | 场景 5 | novel_writer prompt 能否感知 exploration_level | 🔴 |
| 6.1 | 场景 6 | list_style_packs 实际返回什么 | 🟢 |
| 6.2 | 场景 6 | context_builder 是否读 style_pack_id | 🟠 |
| 7.1 | 场景 7 | delete_project confirm 校验在哪一层 | 🟠 |
| 7.2 | 场景 7 | 软删后 load_project 行为 | 🟡 |
| 8.1 | 场景 8 | generate_image chapter_num optional 行为 | 🟢 |
| 8.2 | 场景 8 | rollback 工具边界 | 🟠 |

---

*蕾姆酱 | 2026-07-01 11:04*
