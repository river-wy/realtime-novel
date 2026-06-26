"""writing_laws — 写作法则库 + 红线清单（hard code 预设选项）

法则分两类：
- global_mandatory（全局必备）：无论选什么笔风都生效，共 17 条
- style_linked（定向关联）：随笔风开启，共 4 条

另有 8 条红线禁令（red_lines），单独成块，所有笔风恒定生效。

来源：18 份终极写作指令 + 文风5-9 的结构化抽取。

查询方法：
- list_laws(scope=None): 返回法则列表（可按 scope 过滤）
- get_global_laws(): 返回所有全局必备法则
- get_laws_for_style(pack_id): 返回该笔风生效的全局法则 + 定向法则
- get_red_lines(): 返回红线清单
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ============ 法则库 ============

WRITING_LAWS: Dict[str, Dict[str, Any]] = {

    # ── 人物与互动 ──────────────────────────────────────

    "character_consistency": {
        "id": "character_consistency",
        "name": "人物一致性",
        "category": "character",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "人物性格、说话方式、行为逻辑必须前后一致，严禁 OOC（Out of Character）",
            "性格转变需要铺垫和动机，不能凭空突变",
            "每个人物有独特的语言习惯：用词偏好、句式长短、口头禅，读者能凭对话认出是谁在说",
            "人物的反应必须符合其身份、经历和当下情绪状态，不能为了剧情需要强行扭曲",
        ],
        "avoid_list": [
            "为了推动剧情让人物做出不符合性格的事",
            "所有角色说话方式雷同，换个名字分不出谁是谁",
            "人物性格前后矛盾，上一章勇敢下一章怯懦且无交代",
        ],
    },

    "healthy_personality": {
        "id": "healthy_personality",
        "name": "健全人格",
        "category": "character",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "拒绝脸谱化：反派不纯恶，配角不纯工具，每个角色都有自己的动机和立场",
            "配角也要有独立人格，不是主角的附属品或背景板",
            "人物的善恶有层次：好人有缺点，坏人有软肋，灰色地带最动人",
            "群像中每个出场角色都应有可辨识的记忆点",
        ],
        "avoid_list": [
            "反派为恶而恶，没有任何合理动机",
            "配角只在主角需要时出现，没有自己的生活轨迹",
            "所有正面角色完美无缺，所有反面角色十恶不赦",
        ],
    },

    "micro_carving": {
        "id": "micro_carving",
        "name": "微雕描写",
        "category": "detail",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "用具体细节代替抽象形容：不说「很美」，写具体的视觉特征（睫毛的弧度、锁骨的阴影）",
            "一个精准的细节胜过十句空泛赞美",
            "五感细节轮换：视觉、听觉、嗅觉、触觉、味觉，不要只靠视觉撑场",
            "细节要服务于人物和情绪，不是为了细节而细节",
        ],
        "avoid_list": [
            "用「美丽」「英俊」「可怕」等抽象词一笔带过",
            "堆砌形容词而不给具体画面",
            "细节与当前情绪无关，纯凑字数",
        ],
    },

    "dialogue_full": {
        "id": "dialogue_full",
        "name": "对话丰满",
        "category": "character",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "对话要有潜台词：角色嘴上说的和心里想的可以不一样，读者能品出弦外之音",
            "对话配合动作、神态、环境描写，不能只有干巴巴的台词",
            "对话要有信息密度：每句对话要么推进剧情、要么刻画人物、要么埋伏笔，不能全是废话",
            "对话节奏要有起伏：有短促交锋，也有长段独白，不能从头到尾一个节奏",
        ],
        "avoid_list": [
            "纯台词对话（只有说话内容，没有任何动作神态描写）",
            "对话沦为信息转述工具，角色像在念说明书",
            "所有对话都直白表达角色想法，没有潜台词",
        ],
    },

    # ── 动作与场景 ──────────────────────────────────────

    "action_continuity": {
        "id": "action_continuity",
        "name": "动作连贯性",
        "category": "scene",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "动作有因果链：前一个动作是后一个动作的因，不能跳跃",
            "一个动作完成才能接下一个，不能同时做互相矛盾的事",
            "动作描写融入情绪和意图，不是机械记录肢体运动",
            "关键动作放慢写清楚，过渡动作一笔带过，节奏要有轻重",
        ],
        "avoid_list": [
            "一句话一动作的机械流水账（他走过去。他坐下。他拿起杯子。）",
            "连续用「他/她」做主语开头，句式单调",
            "动作之间缺乏逻辑过渡，像跳帧",
        ],
    },

    "scene_immersion": {
        "id": "scene_immersion",
        "name": "场景沉浸感",
        "category": "scene",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "场景要有五感细节，让读者身临其境",
            "环境描写与人物情绪呼应：开心时阳光明媚，压抑时阴雨连绵（但不要每章都这么直白）",
            "场景转换要自然：用时间过渡、空间移动、情绪转折来衔接，不能硬切",
            "场景信息分散在叙事中自然带出，不要一上来就大段环境说明",
        ],
        "avoid_list": [
            "场景描写与人物情绪完全脱节",
            "场景转换生硬，上一段在A地下一段突然在B地",
            "开头大段环境铺垫才进入人物和情节",
        ],
    },

    # ── 语言与句式 ──────────────────────────────────────

    "anti_ai_cliche": {
        "id": "anti_ai_cliche",
        "name": "去 AI 口癖",
        "category": "language",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "禁用否定对比句式：「没有…没有…」「不是…而是…」「并非…而是…」",
            "禁用弱转折句式：「虽然…但是…」「尽管…却…」",
            "禁用空泛抒情词：「仿佛」「似乎」「一般而言」「不可思议」「不言而喻」",
            "禁用 AI 常用总结句：「这一切」「在那个瞬间」「时间仿佛静止」「空气中弥漫着」「不禁」「油然而生」",
            "用具体的、有画面感的表达替代上述套路",
        ],
        "avoid_list": [
            "「不是A，而是B」句式（AI 最爱用的伪深刻）",
            "「没有…没有…也没有…」三连否定排比",
            "「仿佛」「似乎」开头的比喻滥用",
            "段落结尾用「这一切…」「那一刻…」收束",
        ],
    },

    "sentence_variety": {
        "id": "sentence_variety",
        "name": "句式多样性",
        "category": "language",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "长短句交替：短句制造紧张节奏，长句铺展氛围，两者穿插",
            "避免连续三句以上同结构对称句式（A是…B是…C是…）",
            "动作描写用短句，环境描写用长句，情绪爆发用短句",
            "句首主语要变化，不能连续用「他」「她」开头",
        ],
        "avoid_list": [
            "连续三句以上同结构的对称排比",
            "所有句子长度相近，读起来没有节奏起伏",
            "连续用同一主语开头",
        ],
    },

    "pure_text_format": {
        "id": "pure_text_format",
        "name": "纯文本格式",
        "category": "language",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "正文用纯文本，不用小标题、不用括号补充说明、不用 markdown 标记",
            "对话用中文引号「」包裹，自然融入段落",
            "段落自然分段，一个段落聚焦一个场景或一个动作单元",
            "不写「（注：…）」「【旁白】」等元叙述标记",
        ],
        "avoid_list": [
            "用小标题分割正文（如「一、相遇」「二、冲突」）",
            "用括号做补充说明（破坏沉浸感）",
            "用 markdown 加粗、列表等格式标记",
        ],
    },

    # ── 叙事与情节 ──────────────────────────────────────

    "pov_discipline": {
        "id": "pov_discipline",
        "name": "视角纪律",
        "category": "narrative",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "一章内锁定一个主视角（POV），整章围绕这个人物的感知展开",
            "严禁段落内跳视角：A 的内心刚写完，下一段就写 B 的内心想法",
            "视角人物无法感知的信息（他人内心、远处发生的事）不得直接描写，只能通过外部观察推测",
            "第三人称限知视角：只写视角人物能看到、听到、想到的",
            "需要切换视角时，用明确的场景分隔（空行或时间跳转），且一章不超过两个视角",
        ],
        "avoid_list": [
            "同一段落内在两个人物内心之间跳转",
            "全知视角旁白介入（「他不知道的是，此时…」）",
            "视角人物描写自己看不到的表情（「她眼中闪过一丝狡黠」——除非她在照镜子）",
        ],
    },

    "plot_progression": {
        "id": "plot_progression",
        "name": "情节推进",
        "category": "plot",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "每章必须有信息增量或情感增量，不能原地踏步",
            "推进可以通过对话、行动、事件、发现，不只是内心独白",
            "情节要有因果逻辑：因为A所以B，不是随机事件堆砌",
            "高潮要有铺垫：先蓄势再爆发，不能突然高潮",
        ],
        "avoid_list": [
            "整章都在环境和内心描写，情节没有推进",
            "情节靠巧合和意外推进（天降神兵/巧合救场）",
            "没有铺垫直接进入高潮，读者来不及共情",
        ],
    },

    "no_preaching": {
        "id": "no_preaching",
        "name": "拒绝说教",
        "category": "narrative",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "主题通过故事自然展现，不通过旁白说教",
            "严禁大段哲理感悟和人生总结",
            "人物的感悟要符合其认知水平，不能让小学生说出哲学家的台词",
            "道理要让读者自己悟出来，而不是作者替读者总结",
        ],
        "avoid_list": [
            "章末大段「人生就是…」「原来…」的哲理总结",
            "旁白直接点明主题和道德寓意",
            "人物突然发表与情境不符的深刻感悟",
        ],
    },

    "detail_consistency": {
        "id": "detail_consistency",
        "name": "细节一致性",
        "category": "detail",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "前后细节不能矛盾：上一章说左撇子，这章不能变右撇子",
            "时间线要自洽：季节、年龄、事件先后顺序不能错乱",
            "空间逻辑要合理：从A地到B地需要的时间、路线要一致",
            "物品、能力设定要前后一致，不能忽强忽弱",
        ],
        "avoid_list": [
            "人物外貌特征前后矛盾（发色、身高、疤痕位置）",
            "时间线错乱（春天发生的事到秋天还在讲，却又提到夏天）",
            "能力设定前后不一致（上章还不会飞，这章突然会了且无交代）",
        ],
    },

    # ── 伏笔与校验 ──────────────────────────────────────

    "hook_ending": {
        "id": "hook_ending",
        "name": "钩子结尾",
        "category": "plot",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "每章结尾留悬念或情绪余韵，让读者想继续往下看",
            "钩子类型：悬念（未解之谜）、转折（意外发展）、情感爆发（情绪高点）、伏笔暗示（暗线推进）",
            "钩子要自然，不能为了悬念而强行制造突兀转折",
            "结尾要有力度，最后一句要能留在读者脑海里",
        ],
        "avoid_list": [
            "平淡收尾，没有留任何想看下一章的欲望",
            "为了悬念强行制造不合理转折",
            "结尾拖沓，高潮过后还在絮絮叨叨收尾",
        ],
    },

    "opening_impact": {
        "id": "opening_impact",
        "name": "开篇冲击",
        "category": "plot",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "开篇第一段要抓住注意力，可以：动作开场、对话开场、冲突开场、悬念开场",
            "快速进入场景和人物，不要大段环境铺垫",
            "开篇信息量适中：给足进入场景的锚点，但留有悬念",
            "第一句话要有张力或画面感，不能平庸",
        ],
        "avoid_list": [
            "缓慢的环境铺垫开场（「这是一个阳光明媚的早晨…」）",
            "开篇大段背景介绍和设定说明",
            "第一句话平淡无奇，没有吸引人的元素",
        ],
    },

    "foreshadow_registration": {
        "id": "foreshadow_registration",
        "name": "伏笔登记",
        "category": "plot",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "埋下的伏笔要在后续章节回收，不能埋了就忘",
            "伏笔要自然融入叙事，不能太刻意（「他注意到墙上的画，但没在意」太刻意）",
            "重要伏笔要有铺垫层次：先暗示、再强化、最后揭晓",
            "揭晓伏笔时要有满足感，让读者恍然大悟又能回溯线索",
        ],
        "avoid_list": [
            "埋了伏笔但从不回收",
            "伏笔太刻意，读者一看就知道后面要用",
            "伏笔揭晓太突兀，之前没有任何铺垫",
        ],
    },

    "self_check": {
        "id": "self_check",
        "name": "写完自校",
        "category": "plot",
        "scope": "global_mandatory",
        "linked_styles": [],
        "rules": [
            "成稿后逐项自检：人物是否 OOC、视角是否跳转、有没有 AI 口癖、细节是否矛盾",
            "自检句式：是否连续三句同结构、是否连续用同一主语、是否用了禁用句式",
            "自检情节：本章是否有推进、伏笔是否登记、结尾是否有钩子",
            "发现问题立即修正，不留到下一章",
        ],
        "avoid_list": [
            "写完不复检直接提交",
            "自检流于形式，不逐项对照",
        ],
    },

    # ── 定向关联（随笔风开启）──────────────────────────────

    "longline_narrative": {
        "id": "longline_narrative",
        "name": "长线叙事驱动",
        "category": "plot",
        "scope": "style_linked",
        "linked_styles": ["yanhuo_shiyi", "huangjin_shidai"],
        "rules": [
            "注重长线伏笔和暗线交织，不追求单章爽感",
            "人物弧光跨多章展开，转变需要足够铺垫",
            "群像戏要有主次，但每条线都在推进",
            "允许慢热，但慢热期间也要有小钩子维持阅读动力",
        ],
        "avoid_list": [
            "只顾单章爽感，牺牲长线逻辑",
            "人物转变过快，缺乏铺垫",
            "群像戏平均用力，没有主次",
        ],
    },

    "human_warmth": {
        "id": "human_warmth",
        "name": "人文底色温润",
        "category": "character",
        "scope": "style_linked",
        "linked_styles": ["yanhuo_shiyi"],
        "rules": [
            "在苦难中保留温度：不回避痛苦，但也不沉溺于黑暗",
            "小人物的尊严和挣扎要写得有分量",
            "情感表达克制而深沉，不煽情但有后劲",
            "在平凡日常中提炼诗意，不靠奇观取胜",
        ],
        "avoid_list": [
            "为虐而虐，堆砌苦难",
            "情感表达过于直白煽情",
            "小人物沦为背景板，没有自己的故事",
        ],
    },

    "localization_zh": {
        "id": "localization_zh",
        "name": "现代中式本土化",
        "category": "language",
        "scope": "style_linked",
        "linked_styles": ["yanhuo_shiyi", "souffle_fairy"],
        "rules": [
            "用词和意象本土化：便利店、菜市场、公交卡、共享单车，而不是7-11、farmer's market",
            "社会细节真实：社保、租房、通勤、外卖，符合当代中国生活质感",
            "人名、地名、俚语有中国味道，不生搬日式或欧美表达",
            "节日和季节感贴合中国农历和城市生活",
        ],
        "avoid_list": [
            "生搬日式表达（「果然」「大丈夫」混入中文叙述）",
            "社会细节悬浮，不像中国当代生活",
            "人名地名没有中国味道",
        ],
    },

    "combat_layered": {
        "id": "combat_layered",
        "name": "战斗三层描写",
        "category": "scene",
        "scope": "style_linked",
        "linked_styles": ["huangjin_shidai"],
        "rules": [
            "战斗分三层：战术层（招式策略）、感官层（画面冲击）、情感层（角色心理）",
            "招式有因果：为什么出这招、对手怎么应对，不能瞎打",
            "战斗节奏张弛有度：高强度交锋穿插短暂喘息",
            "战斗结果有代价：赢了也有伤，输了也有收获",
        ],
        "avoid_list": [
            "战斗沦为招式名称堆砌",
            "战斗没有策略逻辑，纯靠数值碾压",
            "战斗无代价，主角毫发无损",
        ],
    },
}


# ============ 红线清单（8 条，终极硬性禁令，恒定生效）============

RED_LINES: List[Dict[str, Any]] = [
    {
        "id": "red_01",
        "title": "禁用否定对比句式",
        "desc": "「没有…没有…」「不是…而是…」「并非…而是…」——AI 伪深刻的标志，一律禁止",
    },
    {
        "id": "red_02",
        "title": "禁用弱转折句式",
        "desc": "「虽然…但是…」「尽管…却…」——削弱叙事力度的口水句，用行动展示转折而非句式",
    },
    {
        "id": "red_03",
        "title": "禁用机械流水账",
        "desc": "一句一动作、连续主语「他/她」、机械记录肢体运动——动作要有因果链和情绪意图",
    },
    {
        "id": "red_04",
        "title": "禁用纯台词/上帝视角/AI口癖/格式标记",
        "desc": "纯台词对话（无动作神态）、上帝视角旁白、AI 口癖词（仿佛/似乎/不可思议）、小标题与括号补充——一律禁止",
    },
    {
        "id": "red_05",
        "title": "禁用同质化句式与硬切",
        "desc": "连续三句以上同结构对称句式、视角随意跳转、场景转换生硬、行为逻辑断层——破坏沉浸感的硬伤",
    },
    {
        "id": "red_06",
        "title": "禁用脸谱化与模板化",
        "desc": "脸谱化人物、同质化台词、模板化情节、通用化场景、空洞化心理——没有辨识度的写作",
    },
    {
        "id": "red_07",
        "title": "禁用冗余与矛盾",
        "desc": "副词泛滥、无效修辞、语句啰嗦、细节矛盾、逻辑 bug——拖累节奏和可信度",
    },
    {
        "id": "red_08",
        "title": "禁用无根写作",
        "desc": "无动机行为、无理由情绪、无铺垫转变、无回收伏笔——一切行为和转变都要有根有据",
    },
]


# ============ 查询方法 ============

def list_laws(scope: Optional[str] = None) -> List[Dict[str, Any]]:
    """返回法则列表，可按 scope 过滤（global_mandatory / style_linked）"""
    if scope:
        return [law for law in WRITING_LAWS.values() if law["scope"] == scope]
    return list(WRITING_LAWS.values())


def get_global_laws() -> List[Dict[str, Any]]:
    """返回所有全局必备法则（17 条）"""
    return [law for law in WRITING_LAWS.values() if law["scope"] == "global_mandatory"]


def get_laws_for_style(pack_id: str) -> List[Dict[str, Any]]:
    """返回该笔风生效的法则 = 全局必备 + 定向关联该笔风的法则"""
    result = get_global_laws()
    linked = [
        law for law in WRITING_LAWS.values()
        if law["scope"] == "style_linked" and pack_id in law.get("linked_styles", [])
    ]
    return result + linked


def get_red_lines() -> List[Dict[str, Any]]:
    """返回红线清单（8 条，恒定生效）"""
    return RED_LINES

