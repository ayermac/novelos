#!/usr/bin/env python3
"""
章节检查工具 - check_chapter.py
用于检查章节的常见问题，不依赖 LLM 的理解能力

注意：此文件导入共享的 db_common 模块
数据库位置：shared/data/novel_factory.db
"""

import json
import re
from pathlib import Path
import os
import sys

# 添加共享工具目录到路径
_shared_tools = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if _shared_tools not in sys.path:
    sys.path.insert(0, _shared_tools)

from db_common import DB_PATH, get_connection

def check_chapter(project_id, chapter_num):
    """
    检查章节的常见问题
    
    Args:
        project_id: 项目ID
        chapter_num: 章节号
    
    Returns:
        {
            "issues": [...],     # 必须修改的问题
            "warnings": [...],   # 建议修改的问题
            "passed": True/False
        }
    """
    issues = []
    warnings = []
    
    conn = get_connection()
    
    try:
        # 1. 获取章节内容
        cursor = conn.execute(
            "SELECT content, word_count FROM chapters WHERE project_id=? AND chapter_number=?",
            (project_id, chapter_num)
        )
        chapter = cursor.fetchone()
        if not chapter:
            return {"issues": ["章节不存在"], "warnings": [], "passed": False}
        
        content = chapter['content'] or ""
        actual_word_count = len(content)
        db_word_count = chapter['word_count']
        
        # 2. 获取指令
        cursor = conn.execute(
            "SELECT objective, key_events, word_target, plots_to_resolve FROM instructions WHERE project_id=? AND chapter_number=?",
            (project_id, chapter_num)
        )
        instruction = cursor.fetchone()
        if not instruction:
            return {"issues": ["指令不存在"], "warnings": [], "passed": False}
        
        word_target = instruction['word_target'] or 2500
        key_events = instruction['key_events'] or ""
        plots_to_resolve = json.loads(instruction['plots_to_resolve']) if instruction['plots_to_resolve'] else []
        
        # 3. 获取上一章状态卡
        cursor = conn.execute(
            "SELECT state_data FROM chapter_state WHERE project_id=? AND chapter_number=?",
            (project_id, chapter_num - 1)
        )
        state_card = cursor.fetchone()
        state_data = json.loads(state_card['state_data']) if state_card and state_card['state_data'] else None
        
        # ===== 开始检查 =====
        
        # 1. 字数检查
        word_deviation = (actual_word_count - word_target) / word_target
        if word_deviation > 0.5:
            issues.append(f"字数超标：实际 {actual_word_count} 字，目标 {word_target} 字，超标 {word_deviation*100:.0f}%")
        elif word_deviation > 0.3:
            warnings.append(f"字数偏多：实际 {actual_word_count} 字，目标 {word_target} 字，偏差 {word_deviation*100:.0f}%")
        elif word_deviation < -0.3:
            warnings.append(f"字数偏少：实际 {actual_word_count} 字，目标 {word_target} 字，偏差 {word_deviation*100:.0f}%")
        
        # 2. 数据库字数统计检查
        if abs(actual_word_count - db_word_count) > actual_word_count * 0.1:
            warnings.append(f"数据库字数统计不准确：数据库 {db_word_count}，实际 {actual_word_count}")
        
        # 3. 状态卡对比
        if state_data:
            # 检查"短期不会有大动作"矛盾
            state_str = json.dumps(state_data, ensure_ascii=False)
            if "短期不会有大动作" in state_str or "短期无大动作" in state_str:
                # 检查内容中是否有立即行动
                if "明天" in content and ("反击" in content or "打脸" in content or "动手" in content):
                    issues.append("状态卡矛盾：状态卡说'短期不会有大动作'，但内容有'明天反击'")
                
                if "立即" in content and ("行动" in content or "任务" in content):
                    warnings.append("状态卡可能矛盾：状态卡说'短期不会有大动作'，但内容有'立即行动'")
            
            # 检查林默状态
            if "林默" in state_str:
                if "伪装buff失效" in state_str and "伪装" not in content:
                    warnings.append("状态卡提及'伪装buff失效'，但内容未提及")
        
        # 4. 指令对齐检查
        if key_events:
            events = key_events.split('；') if '；' in key_events else key_events.split(';')
            for i, event in enumerate(events[:3], 1):  # 只检查前3个关键事件
                event = event.strip()
                if len(event) > 10:  # 只检查有意义的事件
                    # 检查关键词是否出现
                    keywords = extract_keywords(event)
                    if keywords:
                        found = all(kw in content for kw in keywords[:2])  # 至少匹配前2个关键词
                        if not found:
                            warnings.append(f"关键事件可能缺失：{event[:50]}...")
        
        # 5. 伏笔触发对象检查
        for plot_code in plots_to_resolve:
            cursor = conn.execute(
                "SELECT title, description FROM plot_holes WHERE project_id=? AND code=?",
                (project_id, plot_code.split(':')[0])
            )
            plot = cursor.fetchone()
            if plot:
                # 提取触发对象
                trigger_object = extract_trigger_object(plot['description'])
                if trigger_object:
                    # 检查是否直接涉及
                    if not is_directly_involved(content, trigger_object):
                        issues.append(f"伏笔{plot_code}触发对象可能错误：'{trigger_object}'未被直接涉及")
        
        # 6. 基础检查
        if len(content) < 100:
            issues.append("章节内容过短（少于100字）")
        
        if "第" in content and "章" in content and content.index("第") < 50:
            # 检查章节标题
            pass
        else:
            warnings.append("章节可能缺少标题")
        
        # 7. 格式检查
        # 7.1 检查【】标记
        bracket_marks = re.findall(r'【[^】]*】', content)
        if bracket_marks:
            issues.append(f"正文中有未清理的【】标记: {len(bracket_marks)}处")
        
        # 7.2 检查「」引号
        chinese_quotes = re.findall(r'「[^」]*」', content)
        if chinese_quotes:
            issues.append(f"使用「」引号而非双引号: {len(chinese_quotes)}处")
        
        # 7.3 检查章节标题编号格式
        first_line = content.split('\n')[0] if content else ""
        cn_nums = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
        if first_line.startswith('第'):
            after_di = first_line[1:]
            if after_di and after_di[0].isdigit():
                warnings.append(f"章节编号应使用中文数字: '第{after_di[0]}章' → '第{cn_nums[int(after_di[0])-1]}章'")
        
        # 7.4 检查对话引号（强制级别）
        double_quotes = len(re.findall(r'"[^"]*"', content))
        chinese_quotes = len(re.findall(r'「[^」]*」', content))
        single_quote_dialogs = len(re.findall(r"'[^']{10,}'", content))  # 10字符以上可能是对话
        
        # 如果章节有说话动词但对话很少，可能缺失引号
        say_count = len(re.findall(r'(说|道|问|喊|低声|声音|传来|传出|回答)[，:：]', content))
        
        # 强制检查：有说话动词必须有引号
        if say_count >= 3 and double_quotes < say_count:
            issues.append(f"对话缺失引号: 发现{say_count}处说话动词但只有{double_quotes}处双引号")
        
        # 检查单引号对话
        if single_quote_dialogs > 0:
            # 排除文档条款（以"一、"、"二、"开头）
            real_dialogs = 0
            for sq in re.findall(r"'[^']{10,}'", content):
                inner = sq.strip("'")
                if not inner.startswith(('一、', '二、', '三、', '四、', '五、')):
                    if any(x in inner for x in ['我是', '你是', '说', '道', '问', '记住', '请求']):
                        real_dialogs += 1
            if real_dialogs > 0:
                issues.append(f"使用单引号而非双引号: {real_dialogs}处对话")
        
        # 7.5 检查死刑红线词汇
        forbidden_words = [
            '冷笑', '嘴角微扬', '嘴角勾起', '倒吸一口凉气', '倒吸凉气',
            '眼中闪过', '眼中闪现', '眼中精光', '眼中寒芒',
            '心中暗想', '心道', '夜色笼罩', '夜幕降临'
        ]
        found_forbidden = []
        for word in forbidden_words:
            if word in content:
                count = len(re.findall(word, content))
                found_forbidden.append(f'{word}({count}处)')
        if found_forbidden:
            issues.append(f"发现死刑红线词汇: {', '.join(found_forbidden)}")
        
        return {
            "issues": issues,
            "warnings": warnings,
            "passed": len(issues) == 0
        }
        
    finally:
        conn.close()


def extract_keywords(text):
    """从文本中提取关键词"""
    # 简单的关键词提取：提取2-4字的中文词组
    keywords = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
    return keywords[:5]  # 只返回前5个


def extract_trigger_object(description):
    """从伏笔描述中提取触发对象
    
    示例：
    "当赵婉清被羞辱或威胁时" → "赵婉清"
    "林默对妻子赵婉清有保护欲" → "赵婉清"
    """
    # 提取"当X被..."中的X
    match = re.search(r'当([^\s]+?)被', description)
    if match:
        return match.group(1)
    
    # 提取"对X有..."中的X
    match = re.search(r'对([^\s]+?)有', description)
    if match:
        return match.group(1)
    
    # 提取人名
    names = re.findall(r'[赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许][\u4e00-\u9fa5]{1,2}', description)
    if names:
        return names[0]
    
    return None


def is_directly_involved(content, trigger_object):
    """检查触发对象是否被直接涉及
    
    示例：
    触发对象："赵婉清"
    内容："赵婉清的脸色变白" → True（直接涉及）
    内容："赵国栋羞辱林默，让赵婉清丢脸" → False（间接牵连）
    """
    if not trigger_object:
        return True
    
    # 检查触发对象是否在内容中
    if trigger_object not in content:
        return False
    
    # 检查是否被直接羞辱/威胁
    direct_keywords = [
        f"{trigger_object}被羞辱",
        f"{trigger_object}被威胁",
        f"羞辱{trigger_object}",
        f"威胁{trigger_object}",
        f"{trigger_object}就是废物",
        f"{trigger_object}你就是废物",
        f"对{trigger_object}说",
    ]
    
    for keyword in direct_keywords:
        if keyword in content:
            return True
    
    # 检查是否被间接牵连
    indirect_keywords = [
        f"让{trigger_object}丢脸",
        f"让{trigger_object}难堪",
        f"{trigger_object}以后怎么见人",
        f"{trigger_object}继承权",
    ]
    
    for keyword in indirect_keywords:
        if keyword in content:
            return False
    
    # 默认：如果在内容中出现，认为直接涉及
    return True


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python check_chapter.py <project> <chapter>")
        sys.exit(1)
    
    project_id = sys.argv[1]
    chapter_num = int(sys.argv[2])
    
    result = check_chapter(project_id, chapter_num)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    if not result['passed']:
        sys.exit(1)
