"""v6.6.16: Real project burn-in fixture — 异常修正员.

Not a generic placeholder. Concretely depicts:
- Modern urban supernatural organization + system + real-world conflict
- World settings, characters (with specific traits), factions, outlines, 
  plot holes, chapter instructions for 3 chapters
- Enough specificity to pass genesis/context gates
"""

from __future__ import annotations

from pathlib import Path

BURNIN_PROJECT_ID = "burnin_anomaly_corrector"
PROJECT_NAME = "异常修正员"
PROJECT_GENRE = "urban_supernatural"
PROJECT_DESC = (
    "2029年，深市。全球地下存在一个秘密机构'异常修正局'(ACB)，"
    "专门处理因人类集体意识波动引发的'现实异常'——记忆被篡改的街区、"
    "物理规则短暂失效的建筑、以及从平行现实渗入的'异相实体'。"
    "修正员郑行舟在一次行动中发现自己能感知异常的'源头意志'，"
    "这一能力让他从普通工具人变成各方势力争夺的关键。"
    "更危险的是，异常正在加速蔓延，背后似乎有组织在刻意引发。"
)
TARGET_WORDS = 180000
TOTAL_CHAPTERS_PLANNED = 90


def seed_burnin_project(repo, project_id: str = BURNIN_PROJECT_ID) -> None:
    """Seed a real-feeling project into the given Repository.

    Covers world_settings, characters, factions, outlines, plot_holes, and
    chapter instructions for chapters 1-3.
    """

    conn = repo._conn()
    try:
        # ── Project (must come first — genesis_runs has FK to projects) ──
        conn.execute(
            "INSERT OR IGNORE INTO projects (project_id, name, genre, is_current, "
            "description, target_words, total_chapters_planned) VALUES (?, ?, ?, 1, ?, ?, ?)",
            (project_id, PROJECT_NAME, PROJECT_GENRE,
             PROJECT_DESC, TARGET_WORDS, TOTAL_CHAPTERS_PLANNED),
        )

        # ── Genesis run (approved) — required to pass context readiness gate ──
        genesis_id = f"genesis_{project_id}_approved"
        conn.execute(
            "INSERT OR IGNORE INTO genesis_runs (id, project_id, status, created_at) "
            "VALUES (?, ?, 'approved', datetime('now'))",
            (genesis_id, project_id),
        )

        # ── Chapters 1-3 (all planned) ──
        for ch in range(1, 4):
            titles = {1: "第一章：下水道的眼睛",
                      2: "第二章：血液里的频率",
                      3: "第三章：第三修正厅"}
            conn.execute(
                "INSERT OR IGNORE INTO chapters (project_id, chapter_number, title, status) "
                "VALUES (?, ?, ?, 'planned')",
                (project_id, ch, titles.get(ch, f"第{ch}章")),
            )

        # ── World Settings ──
        world_settings = [
            ("异常体系", "异常等级分类",
             "ACB 将异常分为五级：Alpha 级（局部感官偏差，如集体幻听）、Beta 级（物理规则微扰，"
             "如重力方向偏移 5 度）、Gamma 级（空间拓扑扭曲，如无限回廊）、Delta 级（时间感知异常，"
             "如局部区域时间流速不同）、Omega 级（现实层崩解，记录中仅两次，均以大规模人员撤离告终）。"
             "每次修正需要消耗修正员的'锚点能量'，能量从修正员自身精神力中提取，过度使用会导致'锚点衰减'。"),
            ("机构设定", "修正员编制与等级",
             "修正员分为 D/C/B/A/S 五个等级。D 级为实习修正员，C 级可独立执行 Alpha/Beta 任务，B 级可带组，"
             "A 级为厅级主管，S 级仅设三人，直接对局长负责。等级晋升高依赖于修正成功率、异常强度记录和同僚评审。"
             "郑行舟在故事开始时为 C 级修正员，编号 ACB-C-0741。"),
            ("世界观", "平行现实与异相实体",
             "人类集体意识如同巨大的量子场，在特定条件下会产生'意识湍流'。湍流足够强时会撕开现实裂缝，"
             "让平行现实中的异相实体渗入。这些实体并非有意识的入侵者，多数是被'推'过来的被动幸存者。"
             "但也存在主动渗透的高级实体，它们能伪装成普通异常等待时机。"),
            ("技术设定", "靶向稳定器(TS-7)",
             "修正员的标准装备，形如手电筒。通过释放编码锚点波修正局部现实参数。TS-7 型号可覆盖半径 50 米，"
             "充满电可持续工作约 6 小时。核心部件为锚点晶体，每颗晶体的合成成本约为 12 万元人民币。"
             "郑行舟的 TS-7 在故事初期因异常过载损坏，成为他使用自身感知能力的契机。"),
        ]
        for category, title, content in world_settings:
            conn.execute(
                "INSERT OR IGNORE INTO world_settings (project_id, category, title, content) "
                "VALUES (?, ?, ?, ?)",
                (project_id, category, title, content),
            )

        # ── Characters ──
        characters = [
            ("郑行舟", "protagonist",
             "26 岁，深市本地人。C 级修正员，编号 ACB-C-0741。理工科出身，曾在深市大学读应用物理学，"
             "大三时意外卷入一次 Gamma 级异常事件，被 ACB 招募。性格沉默寡言但观察力极强，"
             "执行任务时冷静到近乎冷酷。在'春熙路事件'后获得感知异常源头意志的能力，"
             "这种能力让他能'听到'异常核心的频率——但也让他开始听到不该听到的东西。"
             "有一个在深市医院做护士的妹妹郑行雨，是他的情感软肋。",
             '["沉默寡言", "观察力极强", "冷静", "保护欲强", "自责倾向"]'),
            ("李墨言", "major_ally",
             "31 岁，B 级修正员，郑行舟的小组长。曾是深市警局刑侦队长，在一次连环失踪案中接触 ACB。"
             "性格谨慎但果断，对下属保护意识强，对上级不卑不亢。左手在一次修正任务中被异相实体腐蚀，"
             "平时戴着黑色手套掩盖疤痕。坚信'异常修正局不是屠刀，是盾牌'。",
             '["谨慎果断", "保护下属", "正直", "经验丰富", "左手残疾"]'),
            ("宋晚晴", "major_ally",
             "28 岁，ACB 异常研究员，负责异常信号监测和风险评估。曾是神经科学博士，论文方向为集体意识的神经关联，"
             "后被 ACB 以'国家安全项目'名义招入。性格直率，有时过于理性让人感觉冷漠，但对数据从不妥协。"
             "在故事中逐渐发现 ACB 内部有人在系统性隐瞒重要数据。",
             '["理性直率", "数据驱动", "求知欲强", "不善社交"]'),
            ("魏延昭", "antagonist",
             "45 岁，ACB 第三修正厅厅长，A 级修正员。表面上是深受尊敬的前辈，行事稳重，从不越权。"
             "实际上暗中推动'主动异常诱导计划'——通过人为制造意识湍流来'预演'大规模异常应对方案。"
             "认为牺牲少数人来拯救多数人是必要的。与外部势力'白塔组织'有秘密联系。",
             '["表面稳重", "城府极深", "能力超群", "不择手段", "伪善"]'),
            ("郑行雨", "supporting",
             "23 岁，深市中心医院 ICU 护士。郑行舟的妹妹，不知道哥哥的真实身份，只以为他在'应急管理部门'工作。"
             "性格活泼开朗，与哥哥的沉默形成鲜明对比。故事中期被卷入一起异常事件，成为郑行舟的最大动机。",
             '["活泼开朗", "善良", "勇敢", "关心家人"]'),
            ("许正阳", "supporting",
             "52 岁，ACB 深市分局局长，S 级修正员。曾参与 2008 年汶川 Omega 级预警行动，"
             "是现存修正员中资历最深的一个。对郑行舟的能力非常关注，态度暧昧——既像导师又像棋手。"
             "知道魏延昭有问题但选择按兵不动，原因不明。",
             '["深不可测", "经验老到", "大局观", "手段灵活"]'),
        ]
        for name, role, desc, traits in characters:
            conn.execute(
                "INSERT OR IGNORE INTO characters (project_id, name, role, description, traits, status) "
                "VALUES (?, ?, ?, ?, ?, 'active')",
                (project_id, name, role, desc, traits),
            )

        # ── Factions ──
        factions = [
            ("异常修正局(ACB)深市分局", "official_org",
             "直属于国家安全委员会，对外以'应急管理部特别事务处'名义运作。"
             "深市分局下设三个修正厅：第一修正厅（日常巡逻与 Alpha/Beta 响应）、"
             "第二修正厅（研究与技术支持）、第三修正厅（特殊任务与危机干预，魏延昭主管）。",
             "郑行舟及其直接上级所属机构，当前故事主要舞台"),
            ("白塔组织", "shadow_faction",
             "国际性秘密组织，渗透各国异常管理机构。理念是'人类需要突破现实限制'，"
             "认为异常不是灾难而是进化机会。已在 ACB 内部发展多名成员，魏延昭是其中之一。"
             "拥有远超 ACB 的异常控制技术，能人工触发定向异常。",
             "主要敌对势力，通过魏延昭在 ACB 内部运作"),
        ]
        for name, ftype, desc, rel in factions:
            conn.execute(
                "INSERT OR IGNORE INTO factions (project_id, name, type, description, "
                "relationship_with_protagonist) VALUES (?, ?, ?, ?, ?)",
                (project_id, name, ftype, desc, rel),
            )

        # ── Outlines ──
        outlines = [
            ("chapter", 1, "第一章：下水道的眼睛",
             "深市地铁三号线连续收到乘客报告，称晚班列车经过春熙路站时看到隧道墙壁上有眼睛在眨动。"
             "ACB 派遣郑行舟与李墨言前往调查。在隧道深处，郑行舟发现不是眼睛，而是 Gamma 级异常——"
             "一截不存在于任何建筑图纸中的废弃站台，上面停留着 1987 年深市图书馆的残影。"
             "修正过程中郑行舟的 TS-7 因能量过载损坏，他在紧急状态下第一次激活了感知异常源头能力——"
             "他听到了异常核心发出的'请求'：有东西在推它进来。"
             "修正成功后，他在废弃站台发现一枚不属于任何已知机构的金属徽章。",
             "1"),
            ("chapter", 2, "第二章：血液里的频率",
             "春熙路事件后，郑行舟的能力引起注意。宋晚晴对他的神经特征进行测试，发现他的锚点频率"
             "与普通人不同——能接收到异常核心发出的'源频信号'。与此同时，第二修正厅的监测系统检测到"
             "深市第三人民医院附近出现异常波动模式。郑行舟和李墨言赶到现场，发现 ICU 区域的时间流速"
             "正在减慢——病人生命体征稳定但外部时间快速流逝。异常核心是郑行舟的妹妹郑行雨所在的 ICU。"
             "修正成功后，宋晚晴在数据回溯中发现第三修正厅的系统记录中有一段被删除的异常预警日志，"
             "正是郑行雨的 ICU 区域——但删除操作发生在异常爆发之前。",
             "2"),
            ("chapter", 3, "第三章：第三修正厅",
             "郑行舟直接闯入第三修正厅要求魏延昭解释被删除的预警日志。魏延昭以'系统维护误操作'为由搪塞，"
             "但宋晚晴通过离线备份恢复的数据显示：删除操作使用的权限码属于魏延昭本人，且删除对象"
             "包括过去六个月共 17 条异常预警。许正阳召见郑行舟，暗示'有些事现在不是揭盖子的时候'，"
             "同时将他晋升为 B 级，实则是想用更高的权限让他接触到更多信息。"
             "郑行舟在第三修正厅的档案室发现一份标记为'废弃'的行动计划，代号'引火'——"
             "计划内容是通过人为诱导异常来测试修正员的极限应对能力。",
             "3"),
        ]
        for level, seq, title, content, ch_range in outlines:
            conn.execute(
                "INSERT OR IGNORE INTO outlines (project_id, level, sequence, title, content, "
                "chapters_range) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, level, seq, title, content, ch_range),
            )

        # ── Plot Holes ──
        plot_holes = [
            ("PH-Omega-01", "Omega 级异常历史",
             "2008 年汶川 Omega 级事件记录被加密，只有 S 级人员可查阅。到底发生了什么？"
             "为什么只有许正阳愿意讨论这件事？", "planted", 1, 15),
            ("PH-ACB-01", "删除预警的幕后",
             "魏延昭为什么要删除异常预警？他是为了隐藏引火计划的实验痕迹，"
             "还是另有目的？白塔组织在其中扮演什么角色？", "planted", 2, 8),
            ("PH-Mark-01", "金属徽章",
             "春熙路废弃站台发现的金属徽章来自哪里？不匹配任何已知机构。"
             "徽章的材质检测结果异常——含有地球上不存在的元素同位素比例。", "planted", 1, 12),
            ("PH-Freq-01", "源频信号的秘密",
             "郑行舟能感知异常源频——这种能力是先天还是后天？为什么其他人没有？"
             "他的神经特征与 2008 年 Omega 事件是否有联系？", "planted", 1, 20),
        ]
        for code, title, desc, status, planted, planned in plot_holes:
            conn.execute(
                "INSERT OR IGNORE INTO plot_holes (project_id, code, title, description, "
                "status, planted_chapter, planned_resolve_chapter) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (project_id, code, title, desc, status, planted, planned),
            )

        # ── Instructions for chapters 1-3 ──
        instructions = [
            (1, "建立世界观：异常修正局的设定、异常等级、修正员编制。"
                "主角郑行舟首次出场，展示沉默寡言的性格和扎实的专业能力。"
                "通过地铁异常事件展示异常修正的实际操作流程。"
                "在关键时刻让郑行舟的 TS-7 损坏，迫使他在极端情况下激活隐藏能力——"
                "感知异常源头意志。发现神秘金属徽章作为悬念钩子。",
             '["调查地铁异常报告", "进入废弃站台", "TS-7 能量过载", "首次感知异常源频", "修正异常", "发现金属徽章", "回局汇报"]',
             '["金属徽章来源", "异常背后的推力"]',
             '["无——第一章主要是建立"]',
             "金属徽章的主人是谁？谁在推异常进来？"),
            (2, "发展能力线：郑行舟接受神经特征测试，揭示他能'听到'异常源的独特性。"
                "发展个人线：妹妹郑行雨卷入异常事件，考验郑行舟在职责与亲情之间的抉择。"
                "发展悬疑线：宋晚晴发现被删除的预警日志，暗示 ACB 内部有问题。"
                "展示李墨言对郑行舟的保护态度和自身的自责任倾向。"
                "结尾揭示魏延昭删除预警的行为——但不是直接冲突，而是让读者先发现矛盾。",
             '["宋晚晴做神经测试", "三院 ICU 异常预警", "发现时间异常", "修正 ICU 异常", "郑行雨获救", "宋晚晴发现预警被删", "魏延昭登场"]',
             '["第三修正厅在隐瞒什么", "白塔组织的存在暗示"]',
             '["金属徽章检测结果"]',
             "谁删除了预警？出于什么目的？"),
            (3, "冲突升级：郑行舟直面魏延昭，但被有力反驳——建立魏延昭的复杂形象。"
                "体制博弈：许正阳的态度模糊，让郑行舟意识到这事不是简单的'抓到坏人'。"
                "发现引火计划：档案室找到的计划文件直接指向系统性人为诱导异常的实验——"
                "魏延昭不仅仅是删除预警这么简单。"
                "郑行舟被晋升为 B 级，但这让他感到更像是一种'收编'而非奖励。"
                "结尾：郑行舟决定私下调查引火计划，同时开始研究金属徽章。",
             '["闯第三修正厅质问", "与魏延昭对峙", "许正阳召见暗示", "宋晚晴恢复离线数据", "发现引火计划档案", "晋升 B 级", "决定私下调查"]',
             '["引火计划的具体细节", "白塔组织在 ACB 的渗透程度"]',
             '["金属徽章的分析需要时间"]',
             "引火计划是谁批准的？有多少人知道？"),
        ]
        for ch_num, obj, events, plant, resolve, hook in instructions:
            conn.execute(
                "INSERT OR IGNORE INTO instructions (project_id, chapter_number, objective, "
                "key_events, plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 3500, 'active')",
                (project_id, ch_num, obj, events, plant, resolve, hook),
            )

        conn.commit()
    finally:
        conn.close()
