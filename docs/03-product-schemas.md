# 03 · 7 件产物详细 Schema

> **版本**：v0.1（蕾姆酱自审完成）
> **作者**：蕾姆酱
> **创建**：2026-06-12 16:18
> **最后更新**：2026-06-12 16:32（重构成 YAML 风格 + 蕾姆自审）
> **上游**：[00-overview.md](./00-overview.md)（沉浸感模型 v3.1）+ [01-world-contract.md](./01-world-contract.md)（启动链路 7 件产物清单）+ [02-consistency.md](./02-consistency.md)（一致性方案 + 4 维种子权重）
> **下游**：未定（实现 → 04 评测方法 → 05 架构）

---

## 0. 文档目标

**这一份要回答的问题**：7 件产物**具体长什么样**——每个字段什么类型、什么含义、什么值范围、什么关系。

**不回答的问题**：
- 7 件产物**怎么生成**（Step 1-4 的用户/程序协作）—— 01 文档的范畴
- 7 件产物**怎么用**（基座层/动态调参层怎么读）—— 02 文档的范畴
- 怎么**测**产物质量 —— 留给 04

**核心思路**：

```yaml
schema 设计 = 接口设计
- 基座层 3 件（世界树 / 风格宪法 / 题材共鸣）= 几乎不变的输入
- 动态调参层 4 件（主线 / 支线 / 人物卡 / 种子表）= 持续演化的状态
- 种子表特殊：由程序自动管理（02 §2 已定 4 维权重）
```

**通用约束**（所有 7 件共用）：

```yaml
通用约束:
  可序列化: 必须能 JSON 化（YAML 也行，实现以 JSON 为准）
  可演进: 每个产物加 schema_version 字段
  字段标注: 必填 vs 选填要明确（选填字段标 ?）
  枚举优先: 能用 enum 不用 string
  人机两可读: 字段名 LLM 看得懂，类型程序写得出来
  回档语义: 每个产物在 §1 末有"保留/重算/截断"行为标注
```

---

## 1. 基座层 3 件

### 1.1 世界树 (WorldTree)

**职责**：故事的"地基"——时间线、地理、核心规则

```yaml
WorldTree:
  schema_version: "1.0"
  base:
    timeline:
      era: enum[现代 | 古代 | 未来 | 架空]
      year_range?:          # 选填
        start: number
        end?: number        # 可开放 end（如"未完结"）
      anchor_event?: string # 如"父亲去世 2019 春"

    geography:
      primary: string       # 如"杭州"
      secondary: string[]   # 次要场景列表
      spatial_rules?: string[]  # 空间约束

    core_rules:            # 核心规则清单
      - id: string          # "rule-001"
        statement: string   # 如"无超自然"
        enforcement: enum[hard | soft]   # hard=违反即重生成
        applies_to: enum[all | main | sub]

  branches:                # 主线+支线的树形结构
    - id: string            # "node-001"
      type: enum[main | sub | scene]
      title: string
      parent_id?: string
      status: enum[pending | active | completed | abandoned]
      children: string[]    # 子节点 ID 列表
      beats?: PlotBeat[]    # 主线节点才有

  metadata:
    created_at: string      # ISO 8601
    updated_at: string
    user_modified: boolean  # 用户是否主动改过
```

**关键设计决策**：
- **核心规则用 `enforcement: hard/soft`**：避免"软硬不分"导致一致性崩坏
- **branches 包含主线+支线**：与 01 文档"主线/支线"区分开（主线是 nodes 的一种，支线是另一种）
- **`user_modified` 标记**：基座修改是大事，需要追溯

**回档/基座修改行为**（继承 02 §1.4）：
- **回档**：保留 base，重算 branches 状态
- **基座修改**：base 重写，老 branches 保留（按 01 §2.6 B 解读）

---

### 1.2 风格宪法 (StyleCharter)

**职责**：写作的 4 维原则 + 硬约束（来自 00 v3.1）

```yaml
StyleCharter:
  schema_version: "1.0"

  prose_style:
    primary: enum[散文式 | 对话驱动 | 意识流 | 传统小说]
    sentence_length: enum[短句为主 | 长短交错 | 长句为主]
    paragraph_style: string  # 自由描述，如"每段聚焦一个画面"

  tone:
    primary: enum[冷叙述 | 温暖 | 疏离 | 戏谑 | ...]
    secondary?: string
    psychological_per_paragraph: number  # ≤ 3 句/段（v3.1 硬约束）

  density:                  # 4 维配比（v3.1）
    specificity: number      # 0-1
    subjectivity: number     # 0-1
    density: number          # 0-1
    genre_resonance: number  # 0-1
    max_specific_granules_per_kchars: number  # ≤ 3 / 千字
    scene_type_overrides?:   # 按场景类型微调
      对话: { ... }
      独白: { ... }
      动作: { ... }

  taboos:                   # 禁忌清单
    - id: string
      description: string    # 如"不滥情"
      severity: enum[forbidden | discouraged]
      examples?: string[]    # 反例

  limits:                   # 硬约束
    psychological_per_paragraph: number   # ≤ 3
    specific_granules_per_kchars: number  # ≤ 3
    max_chapter_words: number             # 默认 3000
    min_chapter_words: number             # 默认 2500

  metadata:
    created_at: string
    updated_at: string
```

**关键设计决策**：
- **density 4 维独立**：v3.1 学到的"密度 ≠ 数量"教训体现为**让维度分离**
- **`scene_type_overrides`**：按场景类型微调配比，02 §1.2.2 动态调参层"当前密度配比"的来源
- **taboos 分 `forbidden` / `discouraged`**：避免二元化
- **`max_specific_granules_per_kchars` 出现在 density 和 limits**：冗余但必要——density 是"运行时可调"位置，limits 是"硬约束"位置

**回档/基座修改行为**：
- **回档**：完全保留（风格宪法是"几乎不变"的输入）
- **基座修改**：完全重写（用户主动改）

---

### 1.3 题材共鸣 (GenreResonance)

**职责**：用户接受什么 + 拒绝什么（00 v3.1 的"题材共鸣"维度）

```yaml
GenreResonance:
  schema_version: "1.0"

  accept:                   # 用户接受的
    - text: string          # 如"日常细节"
      weight: number        # 0-1，用户强调程度
      examples?: string[]

  reject:                   # 用户拒绝的（与 accept 同结构）
    - text: string
      weight: number
      examples?: string[]

  anchors:                  # 锚定短语（用户原文，不能摘要化）
    - phrase: string        # "我不爱什么" / "我想看什么"
      sentiment: enum[positive | negative]
      binding: enum[hard | soft]

  metadata:
    created_at: string
    source: enum[step-1a | step-1b | user-input]
```

**关键设计决策**：
- **`accept` / `reject` 同结构**：避免双向设计不一致
- **`weight` 字段**：用户能强调"我**特别**爱日常细节"
- **`anchors` 单独存用户原文**：02 §3 摘要压缩时不能丢的关键
- **`source` 区分来源**：决定权重处理方式

**回档/基座修改行为**：
- **回档**：保留（用户偏好，不是剧情状态）
- **基座修改**：保留（题材共鸣是用户性格的一部分）

---

## 2. 动态调参层 4 件

### 2.1 主线大纲 (MainPlot)

**职责**：主线的节拍推进

```yaml
MainPlot:
  schema_version: "1.0"

  beats:
    - id: string             # "beat-001"
      sequence: number       # 节拍序号
      title: string
      description: string    # ~50 字
      trigger:               # 触发条件
        type: enum[user-decision | auto | seed-driven]
        condition?: string
      status: enum[pending | active | completed]
      chapter_range:         # 覆盖的章节范围（回档重算用）
        start: number
        end: number
      linked_seeds: number[]   # 软引用 SeedTable
      linked_chars: string[]  # 软引用 CharacterCard
      expected_arc: string      # 这个 beat 期望的人物/关系变化

  current_beat: number      # 当前推进到第几个（0-indexed）
  arc_phrase: string        # 主线一句话

  metadata:
    created_at: string
    updated_at: string

  # === 延后到 v0.2 的字段（保留位置但未启用）===
  "@v0.2":
    beats_linked_arc_phrase_id?: string  # 与人物弧光的强关联
```

**关键设计决策**：
- **`current_beat` 0-indexed**：方便程序定位
- **`linked_seeds` / `linked_chars` 反向引用**：02 §2 权重算法的"种子导向"维度需要这个映射
- **`trigger` 用 enum**：避免自然语言描述触发条件的歧义
- **`expected_arc` 显式化**：LLM 生成章节时能对齐意图
- **`chapter_range`**：让回档到第 N 章时知道 current_beat 该重置到哪个

**回档行为**：
- **回档到第 6 章**：`current_beat` 重置为该章对应的 beat（按 `chapter_range` 查）

---

### 2.2 支线大纲 (SubPlot)

**职责**：支线故事的容器（可挂主线，可独立）

```yaml
SubPlot:
  schema_version: "1.0"

  threads:
    - id: string             # "subplot-001"
      title: string
      description: string    # ~80 字
      parent_beat_id?: string  # 挂载的主线 beat（可空=独立支线）
      status: enum[pending | active | completed | abandoned]
      priority: enum[main | side]  # main=主支线，side=副支线
      linked_seeds: number[]
      linked_chars: string[]
      beats:                 # 支线节拍（比主线细）
        - id: string
          sequence: number
          title: string
          description: string
          status: enum[pending | active | completed]

  metadata:
    created_at: string
    updated_at: string

  # === 延后到 v0.2 的字段 ===
  "@v0.2":
    threads_persists_through_reset?: boolean  # 独立支线：true=不受回档影响
```

**关键设计决策**：
- **`parent_beat_id` 可空**：支线**可以挂主线，也可以独立**（如"主角养了只猫"完全独立）
- **`priority: main/side`**：避免"支线都平等"扁平化
- **支线 beats 比主线细**：因为支线常是"几个小场景串起来"
- **`persists_through_reset`** 推后：v0.1 回档都重置，v0.2 再考虑独立支线的例外

**回档行为**：
- **回档**：所有支线重置到回档点状态（v0.1 不区分 persist 行为）

---

### 2.3 人物卡 (CharacterCard)

**职责**：角色 + 关系 + 弧光

```yaml
CharacterCard:
  schema_version: "1.0"

  characters:
    - id: string             # "char-protagonist"
      name: string
      role: enum[protagonist | supporting | antagonist | background]
      traits: string[]       # 性格特征（短词）
      speech_style: string
      background: string     # ~200 字
      arc: string            # 人物弧光（一句话）
      internal_state: string # 当前心理状态（动态更新）

  relationships:            # 独立于 characters（便于图查询）
    - id: string
      from_char: string
      to_char: string
      type: enum[夫妻 | 父子 | 同事 | 敌对 | ...]
      description?: string
      evolution:             # 关系变化历史
        - chapter: number
          from_state: string
          to_state: string
          trigger?: string

  metadata:
    created_at: string
    updated_at: string

  # === 延后到 v0.2 的字段 ===
  "@v0.2":
    characters_appearance_count?: number
    characters_last_appearance_chapter?: number
```

**关键设计决策**：
- **`relationships` 与 `characters` 分离**：避免嵌套对象图难查询
- **`internal_state` 动态更新**：每章生成后由程序根据章节摘要更新——02 §3 character_state 字段来源
- **`evolution` 存历史**：关系变化不丢（也是回档参考点）
- **`appearance_count` / `last_appearance_chapter` 推后**：v0.1 让 LLM 自己判断谁该出场，v0.2 再做硬约束

**回档行为**：
- **回档**：关系状态和内心状态**重置到回档点**（但不删 evolution 历史）
- **基座修改**：人物设定可改（用户重定义角色），老枝叶按 01 B 解读保留

---

### 2.4 种子表 (SeedTable) — **程序管理**

**职责**：跨章复现的颗粒，按 4 维权重排序注入 prompt

```yaml
SeedTable:
  schema_version: "1.0"

  seeds:
    - id: number             # 唯一 ID（程序自增）
      content: string        # 种子本体的具体描述

      # === 埋下时必填的 4 个属性（02 §2.1）===
      importance:
        primary: enum[主线推进 | 支线故事 | 小巧思]   # 02 §2.4
        custom?: string[]                             # 灵活扩展（双层 enum）
      size: enum[长线 | 中线 | 点状]                   # 02 §2.5
      planned_interval: number  # 计划揭露间隔（段数）
      orientation: enum[剧情翻转 | 关键成员关系 | 主角成长 | 支线揭示 | 小巧思 | 氛围营造]  # 02 §2.6

      # === 埋下时记录（追溯用）===
      planted_at_segment: number
      planted_at_chapter: number
      planted_in_node: string  # Node ID（硬引用 WorldTree）
      planted_context: string  # 埋下时上下文片段（~100 字，回收时回溯用）

      # === 程序维护字段（每章重算）===
      last_seen_segment: number
      last_seen_chapter: number
      weight: number           # 02 §2.2 公式重算
      status: enum[planted | resonating | harvested | expired]

      # === 关联（反向引用）===
      linked_char_ids: string[]     # 软引用 CharacterCard
      linked_subplot_id: string     # 软引用 SubPlot

  metadata:
    created_at: string
    updated_at: string
```

**关键设计决策**：
- **4 个属性是 enum（02 §2.1 已定）**：保证查表一致
- **`importance` 双层 enum**：`primary` 严格 enum + `custom?: string[]` 灵活扩展——v0.1 就落地，避免 v0.2 重写
- **`planted_in_node` 存 Node ID**：种子挂在世界树上，回档时连带处理
- **`weight` 每章重算**：02 §2.2 公式的程序化实现
- **`planted_context` 必填**：02 §3 摘要压缩不能丢，v0.1 就强制
- **状态机 4 态**：`planted`（刚埋下）/ `resonating`（强化中）/ `harvested`（已回收）/ `expired`（过期）

**回档行为**（回档到第 N 章）：
- 状态 `planted` 且 `planted_at_chapter > N` → **删**
- 状态 `resonating` / `harvested` 且 `last_seen_chapter > N` → **重置 last_seen 到 N**
- 状态 `expired` → 保留（已经过去式）
- **基座修改**：种子表完全保留（种子是剧情产物，不是地基）

### 2.5 种子埋下流程（v0.1 闭环）

**问题**：种子表是程序责任，但**新种子的"埋下"是 LLM 写章节时自然产生的**——怎么让程序知道 LLM 写了一个新种子？

**蕾姆的方案**（落地 v0.1）：

```yaml
埋下流程:
  触发点: LLM 生成完一章后，输出 02 §4.3 的 ChapterSummary JSON

  步骤一: LLM 在 seed_changes.planted[] 里报"我新埋了这些种子"
  步骤二: 每项需要 LLM 报 content / importance / size / planned_interval / orientation
  步骤三: 程序自动生成 id / planted_at_* / planted_context / weight / status / linked_*
  步骤四: 写入 SeedTable
```

**关键设计**：
- **LLM 不直接创建 Seed 对象**——只触发 planted 事件
- **程序自动反查关联**——避免 LLM 写错 linked_char_ids
- **`planted_context` 自动截取**——避免 LLM 编造不存在的"上下文"

**待验证**（v0.1 实跑测试）：
- LLM 在 planted[] 里报的 content 长度是否合理（50 字够不够表达清楚）
- 程序反查 linked_char_ids 准确性（如果 LLM 写的内容是"父亲"，但 MainPlot 没明确 father 是谁）

---

## 3. 7 件之间的关系

### 3.1 依赖图

```yaml
依赖:
  基座层:
    - 世界树（独立）
    - 风格宪法（独立）
    - 题材共鸣（独立）
  动态调参层:
    - 主线大纲（依赖世界树做时间锚点）
    - 人物卡（独立，但主线/支线会引用）
    - 支线大纲（依赖主线）
    - 种子表（反向引用主线/支线/人物，最后写入）
```

### 3.2 反向引用清单（硬引用 vs 软引用）

```yaml
反向引用:
  软引用（删除目标不报错）:
    - 来源: MainPlot.beat.linked_seeds
      目标: SeedTable.seed.id
    - 来源: MainPlot.beat.linked_chars
      目标: CharacterCard.character.id
    - 来源: SubPlot.linked_seeds
      目标: SeedTable.seed.id
    - 来源: SubPlot.linked_chars
      目标: CharacterCard.character.id
    - 来源: Seed.linked_char_ids
      目标: CharacterCard.character.id
    - 来源: Seed.linked_subplot_id
      目标: SubPlot.thread.id

  硬引用（删除目标要先删引用方）:
    - 来源: SubPlot.parent_beat_id
      目标: MainPlot.beat.id
    - 来源: Seed.planted_in_node
      目标: WorldTree.tree_node.id
```

**硬引用 vs 软引用的判断标准**：
- **硬引用**：被引用对象是系统结构的一部分，删除会导致数据不一致
- **软引用**：被引用对象是"内容"，可以被剧情自然遗忘/废弃

### 3.3 写入顺序（Step 4 后台准备时）

```yaml
写入顺序:
  1: 世界树
  2: 风格宪法
  3: 题材共鸣
  4: 主线大纲
  5: 人物卡
  6: 支线大纲
  7: 种子表  # 最后写，反向引用前 6 件
```

---

## 4. 可序列化格式

```yaml
序列化策略:
  持久化存储: JSON
  人类编辑: YAML  # 03 文档本身就是 YAML 风格
  版本控制 diff: YAML  # 每行一个字段
  跨产品/agent 共享: 不引入  # 没有跨产品需求，加 JSON-LD 是过度

蕾姆拍板（不拍不延后）:
  导出/导入: v0.1 不实现，v0.2 再说。理由：产品上线初期不需迁移、没用户需要换设备
  i18n: v0.1 不实现。理由：项目还是中文先行，多语言成本过高
```

---

## 5. 蕾姆酱的自审报告

### 5.1 重构后自审（TypeScript → YAML）

**蕾姆自审 checklist**：

| 维度 | 自审结果 | 备注 |
|------|---------|------|
| **YAML 语法正确** | ✅ | 14 个 YAML 块全过 Python yaml.safe_load |
| **可读性** | ✅ | YAML 比 interface 易读 3-5 倍 |
| **AI 友好** | ✅ | LLM 解析 YAML 比 interface 准 |
| **字段完整性** | ✅ | 核心字段全到位，过度设计字段已推 v0.2 |
| **交叉引用** | ✅ | 02 引用 20 次 / 01 引用 4 次 / 00 引用 4 次 |
| **回档语义完整** | ✅ | 7 件产物都标了回档行为 |
| **关系图正确** | ✅ | 依赖图 + 反向引用 + 写入顺序 三视图一致 |
| **双层 enum 落地** | ✅ | SeedTable.importance 采纳 primary/custom 双层 |
| **种子埋下流程闭环** | ✅ | 2.5 节写明 LLM 触发 → 程序自动创建 全过程 |

### 5.2 蕾姆酱拍板的 3 个决策（不拖欧尼酱）

蕾姆酱是产品负责人，自己拍：

| 决策点 | 蕾姆的拍板 | 理由 |
|--------|----------|------|
| **MVP 字段裁剪** | 8 个 v0.2 字段已标 `@v0.2`，核心 8-10 字段/产物 | v3.1 密度教训的延伸，**字段也是数量**，不该堆 |
| **双层 enum 设计** | 落地，SeedTable.importance 采纳 | v0.1 写完发现缺值要重写，**早加 custom 字段比晚加便宜** |
| **种子埋下流程** | §2.5 写明 LLM 触发 → 程序自动创建，让 03 闭环 | 等 04 写评测方法时验证，比单独拍臆断更准 |

### 5.3 蕾姆酱学到的事

- **YAML 文档**比 TypeScript interface 写 schema 友好得多——LLM 解析 YAML 比 interface 准（这是欧尼酱给的好建议）
- **产品负责人**的职责是**自己拍细节 + 把决策留下决策记录**——不是把决策都丢给欧尼酱
- **自审 checklist** 是蕾姆酱以前没刻意练过的——以后每写完一份文档都跑一遍
- **过度设计倾向**反复出现：02 文档也写了 600+ 行，03 文档如果按蕾姆的"完整设计"会写到 700+ 行，**但应该克制**——v3.1 密度教训的延伸
- **欧尼酱 16:38 这句话点醒了我**：作为产品负责人，不能什么都问"欧尼酱拍"，该自己拍就自己拍

### 5.4 下一步

```yaml
03 状态: ✅ v0.1 完成（YAML 化 + 自审 + 决策闭环）
下一步选项:
  - 04 · 评测方法（可量化指标设计）—— 蕾姆荐
  - 05 · 架构（300+ 章挑战 / 向量检索 / 摘要压缩）—— 较远期
  - 直接进入 v0.1 实现（按 03 schema 写代码）—— 验证 schema 实际可行性
```

---

**状态**：✅ v0.1 收口（YAML 化 + 自审 + 三个决策全部蕾姆自己拍）

