"""pytest configuration and shared fixtures."""

import sys
from pathlib import Path

import pytest

# Ensure novel_factory is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


# v5.3.0: Shared long chapter content (>= 2700 chars) for StubLLM fixtures.
# Required because v5.3 quality gate enforces:
# - Author/Polisher: word_target * 0.85 threshold
# - Editor: word_target * 0.90 threshold
# Old tests with ~720-char stubs fail the gate.
LONG_CHAPTER_CONTENT = (
    "林默推开房门，屋内弥漫着淡淡的茶香。他缓步走到窗前，凝望着外面的雨幕。\n"
    "\"你来了。\"身后传来一个低沉的声音。林默转身，看到一个黑衣男子站在阴影中。\n"
    "\"你是谁？\"林默警觉地问道，手已经摸向腰间的短剑。\n"
    "\"我是谁不重要，\"黑衣男子缓缓走近，\"重要的是，你正在寻找的东西，也在寻找你。\"\n"
    "林默心中一凛。这件事他从未告诉过任何人，这个人是怎么知道的？\n"
    "\"别紧张，\"黑衣男子停下脚步，\"我是来帮你的。但你必须做出选择。\"\n"
    "\"什么选择？\"林默紧盯着对方，随时准备出手。\n"
    "\"是继续寻找真相，还是保全你现在的平静生活。\"黑衣男子的目光变得复杂。\n"
    "林默沉默了片刻。窗外的雨越下越大，雷声隐隐传来。\n"
    "\"我已经没有退路了，\"他终于说道，\"不管前面是什么，我都必须走下去。\"\n"
    "黑衣男子点了点头。\"很好。那么，从现在开始，你要小心身边的每一个人。\"\n"
    "说完，他的身影渐渐消失在阴影中，仿佛从未出现过。\n"
    "林默站在原地，心中涌起一股不安。窗外的雨声似乎变得更加急促，仿佛在预示着什么。\n"
    "他走到书桌前，翻开那本泛黄的笔记本。纸页上密密麻麻的字迹记录着这些年来的调查。\n"
    "他拿起笔，在空白处写下今天的日期，然后停住了。笔尖悬在纸面上，迟迟没有落下。\n"
    "最后，他只写了一句话：今天，一切都将改变。\n"
    "就在这时，门外传来急促的敲门声。林默迅速合上笔记本，藏好短剑，然后走去开门。\n"
    "门外站着一个陌生的年轻人，浑身湿透，目光中带着惊恐。\n"
    "\"救救我，\"年轻人喘着气说，\"他们……他们要杀我。\"\n"
    "林默还没来得及反应，远处就传来了脚步声。不止一个人，而且正在快速接近。\n"
    "他一把将年轻人拉进屋内，关上门，然后吹灭了桌上的蜡烛。\n"
    "黑暗中，他听到了自己的心跳声。这一刻，他知道，平静的日子已经结束了。\n"
    "年轻人蜷缩在角落里，浑身发抖。林默从窗缝中看到几个黑影从门前掠过。\n"
    "他们没有停留，脚步声渐渐远去。林默松了口气，但并未放松警惕。\n"
    "\"他们是谁？\"林默低声问道。\n"
    "\"我不知道……\"年轻人摇着头，\"我只知道，他们想要我手里的东西。\"\n"
    "林默注意到年轻人紧握着拳头。他伸出手：\"给我看看。\"\n"
    "年轻人犹豫了一下，慢慢张开手掌。一枚古旧的玉佩躺在掌心，泛着微弱的幽光。\n"
    "林默瞳孔一缩。这枚玉佩，和他父亲临终前交给他的那枚，竟然一模一样。\n"
    "\"这东西……你从哪里得到的？\"林默的声音有些发紧。\n"
    "\"是我爷爷留给我的遗物。\"年轻人说，\"他说，这东西关系到一个大秘密。\"\n"
    "林默沉默了。父亲当年也是这么说的。两枚玉佩，两个家族，这绝不是巧合。\n"
    "窗外的雨渐渐小了。林默站起身，走到窗前。天边露出了一丝鱼肚白。\n"
    "\"天快亮了。\"林默说，\"你先在这里休息。等安全了，我们再细说。\"\n"
    "年轻人点了点头，靠在墙角闭上眼睛。林默却没有睡意，他握着两枚玉佩，陷入沉思。\n"
    "父亲当年调查的真相，或许就藏在这两枚玉佩之中。而现在，这个真相正在慢慢浮出水面。\n"
    "他必须做好准备。不管前方有多少危险，他都不会退缩。这是他的选择，也是他的宿命。\n"
    "门外又传来了动静。林默警觉地抬起头，手再次摸向短剑。\n"
    "\"林兄，是我。\"一个熟悉的声音传来。林默松了口气，走过去开门。\n"
    "门外站着他的好友陆尘，面色凝重。\"出事了。你之前调查的那个案子，又有了新的线索。\"\n"
    "\"进来说。\"林默让开身子，同时注意着街道上的动静。\n"
    "陆尘进屋后迅速关门，压低声音说：\"有人发现了你父亲的日记。\"\n"
    "林默瞳孔一缩。\"在哪里？\"\n"
    "\"城东的老书店，老板是你们林家的旧识。\"陆尘说，\"但那里现在被人盯着。\"\n"
    "林默看向窗外的晨曦，心中已有了决断。\"我去一趟。\"\n"
    "\"太危险了。\"陆尘摇头，\"他们肯定在等你出现。\"\n"
    "\"正因为如此，我才要去。\"林默的目光坚定，\"这是我唯一的机会。\"\n"
    "年轻人这时睁开眼睛，\"我和你一起去。\"\n"
    "林默看着他，摇了摇头。\"你先留在这里。等你安全了，我们再一起调查。\"\n"
    "年轻人想说什么，但最终点了点头。他知道，以他现在的情况，只会是累赘。\n"
    "林默收拾好行装，对着陆尘说：\"照顾好他。等我回来。\"\n"
    "陆尘拍了拍他的肩膀，\"小心。\"\n"
    "林默推开房门，消失在晨曦中。这一天，注定不平凡。\n"
    "街道上行人稀少，晨雾笼罩着整座城市。林默贴着墙根行走，尽量避开开阔地带。\n"
    "他知道，从现在开始，每一个转角都可能藏着危险。\n"
    "城东的老书店距离这里不算太远，但以他现在的处境，每一步都要格外小心。\n"
    "穿过一条小巷后，林默停下了脚步。前方，书店的招牌已经隐约可见。\n"
    "但更让他警觉的是，书店对面停着一辆黑色的轿车，车窗紧闭，看不清里面的人。\n"
    "林默深吸一口气，压低帽檐，若无其事地向书店走去。\n"
    "就在他即将推门的瞬间，一个苍老的声音从身后传来：\"年轻人，买书吗？\"\n"
    "林默转身，看到一个衣着破旧的老者，手中捧着几本书籍。\n"
    "\"不买。\"林默简短地回答，正要推门，却听到老者低声说：\n"
    "\"你父亲的东西，藏在第三排书架的夹层里。记住，快进快出。\"\n"
    "林默心中一震，看向老者。但老者已经转身离去，消失在晨雾中。\n"
    "他推开门，走进书店。空气中弥漫着陈旧纸张的气息，一切都和他记忆中一样。\n"
    "老板坐在柜台后，抬头看了他一眼，没有说话。只是微微点了点头。\n"
    "林默快步走向第三排书架，手指在书脊上滑动，寻找着那个夹层。\n"
    "终于，他找到了。一本看似普通的线装书，封皮微微鼓起。\n"
    "他将书取下，翻开封皮，里面赫然是一叠泛黄的纸张。\n"
    "父亲的笔迹。林默的心跳加速，但他强迫自己冷静下来。\n"
    "他将纸张塞入怀中，正要离开，却听到门外传来汽车引擎熄灭的声音。\n"
    "他们来了。林默看向后门的方向，老板朝他使了个眼色。\n"
    "\"后门。\"老板低声说，\"快。\"\n"
    "林默没有犹豫，快步冲向后门。就在他推开门的瞬间，前门被猛然推开。\n"
    "几个黑衣人冲了进来，但林默已经消失在后巷的阴影中。\n"
    "他一路狂奔，穿过数条小巷，确信没有人跟上来后，才停下来喘息。\n"
    "怀里的纸张沉甸甸的，父亲留下的线索，终于到了他手中。\n"
    "真相的脚步声越来越近，而危险，也在黑暗中悄然逼近。\n"
    "他沿着后巷一路向东，来到一座废弃的仓库前。这里是他和陆尘的秘密据点。\n"
    "林默推开门，在角落的木箱上坐下，将父亲的日记摊开在膝上。\n"
    "第一页的字迹已经有些模糊，但林默依然能辨认出那熟悉的笔锋。\n"
    "林默合上日记，将两枚玉佩小心地收入怀中。窗外的晨光已经大亮。\n"
    "他站起身，深吸一口气，准备迎接新的挑战。不惧前方未知，他已做好一切准备。\n"
    "林默小心地将日记本收入怀中，走出据点，消失在城市的人群中。\n"
    "街道两旁的店铺陆续开门，早起的人们开始了新的一天。\n"
    "他融入人流之中，没有人知道这个看似普通的年轻人身上，藏着足以改变一切秘密。\n"
    "他知道，真正的较量才刚刚开始。所有的谜团，所有的危险，都将在不久后揭晓。\n"
    "林默回到临时住处，关好门窗，将两枚玉佩并排放在桌上。\n"
    "玉佩上的纹路在阳光下若隐若现，仿佛在诉说着某段被遗忘的往事。\n"
    "他拿起父亲的日记，翻到最后一页。上面只有一句话：\"当你读到这些字时，真相就在你手中。\"\n"
    "林默闭上眼，深吸一口气。两代人的追寻，无数个夜晚的孤独探索，终于在这一刻画上了句号。\n"
    "然而，故事并未结束。新的篇章，正在他脚下缓缓展开。"
)


def seed_context_for_chapter(db_path_or_repo, project_id: str = "测试项目", chapter_number: int = 1) -> None:
    """Seed all context required by the v5.3.0 Context Readiness Gate.

    This fixture ensures projects have complete context before chapter generation:
    1. project.description non-empty
    2. world_settings >= 1
    3. characters >= 1 protagonist
    4. outlines covering current chapter
    5. word_target defined

    Call this before any test that calls /api/run/chapter on a new project.

    Args:
        db_path_or_repo: Database path string or Repository instance.
        project_id: ID of the project to create/find (also used as name if new).
        chapter_number: Chapter number for outline coverage check.
    """
    # Import here to avoid circular imports at module level
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository

    if isinstance(db_path_or_repo, Repository):
        repo = db_path_or_repo
    else:
        db_path = db_path_or_repo
        init_db(db_path)
        repo = Repository(db_path)

    _description = "一段跨越两个家族的秘密往事，探寻真相的青年踏上了充满危险的道路。"

    # Ensure project exists with required description and word_target
    existing = repo.get_project(project_id)
    if existing is None:
        repo.create_project(
            project_id=project_id,
            name=project_id,
            genre="武侠",
            description=_description,
            total_chapters_planned=50,
            target_words=150000,
            current_chapter=chapter_number,
        )
    else:
        # Use a single connection to avoid the two-connection bug
        # (repo._conn() creates a new connection each time)
        conn = repo._conn()
        try:
            updates = []
            params = []
            if not existing.get("description"):
                updates.append("description=?")
                params.append(_description)
            if not existing.get("target_words"):
                updates.append("target_words=?")
                params.append(150000)
            if not existing.get("total_chapters_planned"):
                updates.append("total_chapters_planned=?")
                params.append(50)
            if updates:
                params.append(project_id)
                conn.execute(
                    f"UPDATE projects SET {', '.join(updates)} WHERE project_id=?",
                    tuple(params),
                )
                conn.commit()
        finally:
            conn.close()

    # Add world setting if none exist
    world_settings = repo.list_world_settings(project_id)
    if len(world_settings) < 1:
        repo.create_world_setting(
            project_id=project_id,
            category="力量体系",
            title="内功心法",
            content="以内功为主，外功为辅。内功深厚者可隔空伤人，外功精纯者可刀枪不入。",
        )

    # Add protagonist character if none exist
    characters = repo.list_characters(project_id)
    protagonists = [c for c in characters if c.get("role") == "protagonist"]
    if len(protagonists) < 1:
        repo.create_character(
            project_id=project_id,
            name="林默",
            role="protagonist",
            description="年轻武者，性格沉稳冷静，身负两代人的秘密与使命。",
            alias="默",
            traits="沉稳,冷静,果断",
            first_appearance=chapter_number,
        )

    # Add chapter-level outline covering the chapter
    outlines = repo.list_outlines(project_id)
    chapter_outlines = [
        o
        for o in outlines
        if o.get("level") == "chapter"
        and _covers_chapter(o.get("chapters_range", ""), chapter_number)
    ]
    if len(chapter_outlines) < 1:
        # Create a chapter outline for the specific chapter number
        repo.create_outline(
            project_id=project_id,
            level="chapter",
            sequence=chapter_number,
            title=f"第{chapter_number}章：命运的交汇",
            content="主要角色命运的交汇点，真相逐渐浮出水面。",
            chapters_range=str(chapter_number),
        )


def _covers_chapter(chapters_range: str, chapter_number: int) -> bool:
    """Check if an outline's chapters_range covers the given chapter number."""
    if not chapters_range:
        return False
    chapters_range = chapters_range.strip()
    if chapters_range.isdigit():
        return int(chapters_range) == chapter_number
    if "-" in chapters_range:
        parts = chapters_range.split("-")
        if len(parts) == 2:
            try:
                start = int(parts[0].strip())
                end = int(parts[1].strip())
                return start <= chapter_number <= end
            except ValueError:
                return False
    return False


@pytest.fixture(autouse=True)
def disable_dotenv_for_tests(monkeypatch):
    """Disable .env loading for all tests to prevent project root .env pollution.

    This ensures tests that verify "missing API key" behavior are not
    accidentally passing because of keys in the project's .env file.

    Individual tests that need .env can temporarily re-enable it by
    removing the env var with monkeypatch.delenv().
    """
    monkeypatch.setenv("NOVEL_FACTORY_DISABLE_DOTENV", "1")
