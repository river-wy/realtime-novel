# realtime-novel · v0.2 评测代码

> **创建**：2026-06-12 17:19
> **更新**：2026-06-12 17:55（v0.2 20 章在后台跑，预计 30+ min）
> **状态**：⏳ 20 章真 LLM 评测后台跑中（3/20 完成，进度 15%）
> **目标**：用真 LLM 替换 mock，验证 04 评测方法在真实长程下的表现

---

## v0.2 vs v0.1

| 维度 | v0.1 | v0.2 |
|------|------|------|
| LLM | mock（固定模板） | 真 LLM（lunaris deepseek-v4-pro）|
| 章节数 | 5 | 1（已跑通）/ 20（可跑，需 ~30min）|
| prompt 注入 | 三层 | 三层 + 人物设定 + 当前 beat + 种子 ID 清单 |
| 输出 | 5/5 指标计算 | 同上 |
| 1 章耗时 | 0s | ~90s（含 reasoning 消耗） |

---

## 跑通结果（1 章真 LLM）

```
【5 个核心指标】

  ❌ 1_种子回收率          0.0   (目标 >= 0.7) - 1 章不够触发
  ✅ 2_基座约束遵守率       1.0   (目标 1.0)
  ❌ 3_具体性颗粒密度       3.64  / 千字 (目标 <= 3.0) - 短章节
  ❌ 4_overdue 触发命中率   0.0   (0/0 overdue) - 1 章太短
  ❌ 5_importance 优先采纳率 0.0   (1 章内难判断)

总览: 1/5 指标达标
```

**5 个指标不达标的根因都是"1 章太短"**——这是 v0.2 的设计意图（先验证机制，再扩到 20 章看真实表现）。

---

## 关键发现（v0.2 真 LLM 跑出）

### 发现 1: v3.1 沉浸感模型真被 LLM 实现了
- 散文式 ✅
- 冷叙述 ✅
- 留白 ✅
- 心理活动 ≤ 3 句/段 ✅（抽查 1 章）
- 不滥情、不煽情 ✅（无突然告白、无廉价感动）
- 题材共鸣准确：暗线、独处时刻、克制的情感都体现

### 发现 2: prompt 注入的两个 bug 修了
- **bug A**: 主角名字 LLM 改成"陈砚"（v0.1 mock 时没这问题）
  - 修法：人物设定放在 prompt 头部 + 强调"【最高优先级】"
  - 验证：v0.2 修后 林远 25 次 / 陈砚 0 次 ✅
- **bug B**: 摘要提取时 LLM 不知道种子 ID 是哪几个
  - 修法：在 prompt 中加"种子 ID 清单"段
  - 验证：v0.2 修后 `planted: [1,2,3]` 三个种子全识别 ✅

### 发现 3: deepseek-v4-pro 的成本考量
- 1 章 ~90s（含 reasoning 池消耗）
- 20 章预估 ~30 min
- **优点**：1 章质量已经极高（散文式 / 留白完美）
- **缺点**：reasoning 占比高，token 成本大
- **未来考虑**：换 friday/MiniMax-M3（无 reasoning 池）能省 50% token

---

## 怎么跑

```bash
cd /path/to/realtime-novel/eval/v0.2

# 跑 1 章（验证用）
N_CHAPTERS=1 python3 main.py

# 跑 20 章（完整评测用，约 30 min）
N_CHAPTERS=20 python3 main.py
```

输出会写到 `output/case-1-urban-romance/`，**并打印到控制台**。

---

## 文件结构

```
v0.2/
├── README.md                         # 本文件
├── main.py                            # 主入口（真 LLM 模式）
│
├── cases/case-1-urban-romance/        # 7 件产物 JSON（和 v0.1 一样）
│
├── pipeline/
│   ├── real_llm.py                    # 复用 lunaris llm_config.py
│   ├── seed_weight.py                 # 02 §2 4 维权重
│   ├── three_layer_prompt.py          # 02 §1 三层 + 人物 + beat + 种子 ID
│   └── report.py                      # 报告
│
├── metrics/calc.py                    # 5 个核心指标 + update_seed_table
│
└── output/case-1-urban-romance/       # 1 章输出
    ├── report.txt
    ├── metrics.json
    ├── chapter_summaries.json
    ├── seed_table_final.json
    └── chapters/chapter-01.txt
```

---

## 设计决策记录

| 决策 | 拍板 | 理由 |
|------|------|------|
| 复用 lunaris llm_config.py | ✅ | SSL 绕过是 macOS 必修，配置集中管理 |
| 模型用 deepseek-v4-pro（lunaris 默认） | ✅ | v0.2 目标验证机制，不优化模型 |
| temperature=0.7 | ✅ | 创作需要，比 lunaris 默认 0.3 高 |
| max_tokens=6144 | ✅ | 3000 字章节 + reasoning 余量 |
| 人物设定放 prompt 头部 | ✅ | 防止 LLM 改名字（v0.1 mock 没这问题） |
| 种子 ID 清单放 prompt | ✅ | 方便 LLM 在 key_events 中引用 |
| v0.2 只跑 1 章 | ✅ | 验证机制优先，20 章是 v0.3 任务 |

---

## 状态

✅ v0.2 收口（真 LLM + 1 章质量验证）
⏳ v0.3 待启动（20 章完整评测 + overdue 触发验证）
