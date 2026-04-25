#!/usr/bin/env python3
"""
章节格式检查工具
检查章节内容是否符合格式规范
"""

import sys
import re
import sqlite3
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 中文数字映射
CN_NUMS = {
    '1': '一', '2': '二', '3': '三', '4': '四', '5': '五',
    '6': '六', '7': '七', '8': '八', '9': '九', '10': '十',
    '11': '十一', '12': '十二', '13': '十三', '14': '十四', '15': '十五',
    '16': '十六', '17': '十七', '18': '十八', '19': '十九', '20': '二十'
}


def check_chapter_format(content: str, chapter_num: int) -> dict:
    """检查章节格式，返回问题列表"""
    issues = []
    
    # 1. 检查章节标题格式
    first_line = content.split('\n')[0] if content else ""
    title_match = re.match(r'^第(\d+|[一二三四五六七八九十]+)章\s+(.+)$', first_line)
    
    if not title_match:
        issues.append({
            'type': 'chapter_title',
            'severity': 'error',
            'message': f'章节标题格式错误: "{first_line[:30]}"',
            'expected': '第N章 标题（N为中文数字）'
        })
    else:
        num = title_match.group(1)
        if num.isdigit():
            issues.append({
                'type': 'chapter_title',
                'severity': 'warning',
                'message': f'章节编号应使用中文数字: "第{num}章" → "第{CN_NUMS.get(num, num)}章"',
                'expected': f'第{CN_NUMS.get(str(chapter_num), str(chapter_num))}章'
            })
    
    # 2. 检查对话引号格式
    chinese_quotes = re.findall(r'「[^」]*」', content)
    if chinese_quotes:
        issues.append({
            'type': 'dialogue_quotes',
            'severity': 'error',
            'message': f'使用「」引号而非双引号: {len(chinese_quotes)}处',
            'examples': chinese_quotes[:3]
        })
    
    # 2.5 检查单引号对话（应使用双引号）
    single_quote_dialogs = re.findall(r"'[^']{2,}'", content)  # 至少2个字符的对话
    if single_quote_dialogs:
        issues.append({
            'type': 'single_quote_dialogue',
            'severity': 'error',
            'message': f'使用单引号而非双引号: {len(single_quote_dialogs)}处',
            'examples': [d[:40] + '...' if len(d) > 40 else d for d in single_quote_dialogs[:3]]
        })
    
    # 3. 检查场景分隔符
    dash_separators = re.findall(r'^---+$', content, re.MULTILINE)
    emdash_separators = re.findall(r'^——+$', content, re.MULTILINE)
    
    if dash_separators:
        issues.append({
            'type': 'scene_separator',
            'severity': 'warning',
            'message': f'使用 --- 作为场景分隔符: {len(dash_separators)}处',
            'expected': '使用空行分隔场景'
        })
    
    if emdash_separators:
        issues.append({
            'type': 'scene_separator',
            'severity': 'warning',
            'message': f'使用 —— 作为场景分隔符: {len(emdash_separators)}处',
            'expected': '使用空行分隔场景'
        })
    
    # 4. 检查伏笔/系统标记
    bracket_marks = re.findall(r'【[^】]*】', content)
    if bracket_marks:
        issues.append({
            'type': 'bracket_marks',
            'severity': 'error',
            'message': f'正文中有未清理的【】标记: {len(bracket_marks)}处',
            'examples': [m[:50] + '...' if len(m) > 50 else m for m in bracket_marks[:3]]
        })
    
    # 5. 检查连续空行
    empty_lines = len(re.findall(r'\n{4,}', content))
    if empty_lines > 0:
        issues.append({
            'type': 'empty_lines',
            'severity': 'warning',
            'message': f'连续空行过多(>3个换行): {empty_lines}处',
            'expected': '段落间最多1个空行'
        })
    
    # 6. 检查死刑红线词汇
    forbidden_words = [
        '冷笑', '嘴角微扬', '嘴角勾起', '倒吸一口凉气', '倒吸凉气',
        '眼中闪过', '眼中闪现', '眼中精光', '眼中寒芒',
        '心中暗想', '心道', '不禁想', '不由得想',
        '夜色笼罩', '夜幕降临'
    ]
    
    found_forbidden = []
    for word in forbidden_words:
        if word in content:
            count = len(re.findall(word, content))
            found_forbidden.append(f'{word}({count}处)')
    
    if found_forbidden:
        issues.append({
            'type': 'forbidden_words',
            'severity': 'error',
            'message': f'发现死刑红线词汇: {", ".join(found_forbidden)}',
            'expected': '删除或替换这些词汇'
        })
    
    # 7. 检查缺失引号的对话
    # 模式：说/道/问/喊 + 内容（无引号包裹）
    missing_quotes = []
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        # 检查是否包含说话动词但无引号
        if re.search(r'(说|道|问|喊|低声|声音)[：:，,]', line):
            if '"' not in line and '「' not in line:
                # 排除间接引语（"他说他要去"）
                if not re.search(r'他说他|她说她|他们说', line):
                    missing_quotes.append((i, line.strip()[:60]))
    
    if missing_quotes:
        issues.append({
            'type': 'missing_quotes',
            'severity': 'warning',
            'message': f'可能缺失引号的对话: {len(missing_quotes)}处',
            'examples': [f"行{num}: {text}..." for num, text in missing_quotes[:3]]
        })
    
    return {
        'valid': len([i for i in issues if i['severity'] == 'error']) == 0,
        'issues': issues,
        'stats': {
            'total_issues': len(issues),
            'errors': len([i for i in issues if i['severity'] == 'error']),
            'warnings': len([i for i in issues if i['severity'] == 'warning'])
        }
    }


def main():
    if len(sys.argv) < 3:
        print("用法: python3 check_format.py <project_id> <chapter_number>")
        print("示例: python3 check_format.py novel_003 5")
        sys.exit(1)
    
    project_id = sys.argv[1]
    try:
        chapter_num = int(sys.argv[2])
    except ValueError:
        print(f"错误: 章节号必须是数字")
        sys.exit(1)
    
    # 连接数据库
    # 脚本在 author/workspace/skills/novel-writing/scripts/ 下
    # 数据库在 agents/shared/data/ 下，需要向上 6 级
    db_path = Path(__file__).parent.parent.parent.parent.parent.parent / 'shared' / 'data' / 'novel_factory.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取章节内容
    cursor.execute("""
        SELECT content, title 
        FROM chapters 
        WHERE project_id = ? AND chapter_number = ?
    """, (project_id, chapter_num))
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print(f"错误: 找不到项目 {project_id} 的第 {chapter_num} 章")
        sys.exit(1)
    
    content, title = result
    
    # 检查格式
    result = check_chapter_format(content, chapter_num)
    
    print(f"\n{'='*60}")
    print(f"第{chapter_num}章: {title}")
    print(f"{'='*60}")
    
    if result['valid']:
        print("✅ 格式检查通过")
    else:
        print("❌ 格式检查未通过")
    
    if result['issues']:
        print(f"\n问题统计: {result['stats']['errors']} 错误, {result['stats']['warnings']} 警告")
        print("-" * 60)
        
        for issue in result['issues']:
            severity = '❌' if issue['severity'] == 'error' else '⚠️'
            print(f"\n{severity} [{issue['type']}]")
            print(f"   {issue['message']}")
            if 'expected' in issue:
                print(f"   期望: {issue['expected']}")
            if 'examples' in issue:
                for ex in issue['examples']:
                    print(f"   示例: {ex}")
    else:
        print("\n未发现格式问题 ✨")
    
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    sys.exit(main())
