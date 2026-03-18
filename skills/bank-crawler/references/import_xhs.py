#!/usr/bin/env python3
"""
将小红书爬取数据提炼为知识库条目并写入 knowledge_base.json
"""
import json
import os
import time
import requests
from datetime import datetime

# 配置
from dotenv import load_dotenv
load_dotenv('/root/bank/.env')

API_KEY = os.getenv('OPENAI_API_KEY')
BASE_URL = os.getenv('OPENAI_BASE_URL', '').rstrip('/')
MODEL = os.getenv('MODEL', 'kimi-k2-thinking')


def chat(messages, temperature=0.3, max_tokens=600):
    """调用API，处理流式响应"""
    resp = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": messages, "temperature": temperature,
              "max_tokens": max_tokens, "stream": True},
        stream=True, timeout=60
    )
    resp.raise_for_status()
    content = ""
    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode('utf-8')
        if line.startswith('data: '):
            data = line[6:]
            if data == '[DONE]':
                break
            try:
                chunk = json.loads(data)
                delta = chunk['choices'][0]['delta']
                content += delta.get('content') or ''
            except Exception:
                pass
    return content.strip()

KB_PATH = '/root/bank/knowledge_base.json'
XHS_PATH = '/root/xhs_data/xhs/json/search_contents_2026-03-18.json'

SYSTEM_PROMPT = """你是一个专业的无障碍信息整理助手。
请将小红书笔记内容提炼为结构化知识条目，严格按照以下JSON格式输出（不要有任何其他文字）：

{
  "title": "15字以内的精炼标题",
  "category": "分类（只能是：政策/就业/出行/辅具/生活技巧/健康）",
  "summary": "100字以内的核心摘要，提炼最有价值的信息",
  "tips": ["具体可操作的建议1", "具体可操作的建议2", "具体可操作的建议3"],
  "target_group": "适用人群（只能是：肢残/视障/听障/通用）"
}

要求：
- 只提炼有实质性信息价值的内容（政策、流程、技巧等）
- 如果内容太空洞或无实质信息，返回 {"skip": true}
- tips至少3条，每条20字以内，具体可操作
- 不要包含广告、情绪化内容"""


def load_kb():
    if os.path.exists(KB_PATH):
        return json.load(open(KB_PATH, encoding='utf-8'))
    return []


def save_kb(data):
    with open(KB_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_duplicate(kb, title, category):
    for item in kb:
        if item.get('title') == title and item.get('category') == category:
            return True
    return False


def process_note(note):
    title = note.get('title', '').strip()
    desc = note.get('desc', '').strip()
    # 合并标题和正文，去重
    content = title if title == desc else f"{title}\n{desc}"
    content = content[:1000]  # 限制长度

    try:
        raw = chat([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请提炼以下小红书笔记：\n\n{content}"}
        ])
        # 提取JSON
        if '```' in raw:
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        result = json.loads(raw)
        return result
    except Exception as e:
        print(f"  ❌ AI处理失败: {e}")
        return None


def main():
    xhs_data = json.load(open(XHS_PATH, encoding='utf-8'))
    kb = load_kb()
    existing_urls = {item.get('source_url') for item in kb}

    print(f"知识库现有条目: {len(kb)}")
    print(f"小红书数据条数: {len(xhs_data)}")
    print("=" * 50)

    added = 0
    skipped = 0

    for i, note in enumerate(xhs_data):
        note_url = note.get('note_url', '')
        title_preview = note.get('title', '')[:30]
        print(f"[{i+1}/{len(xhs_data)}] 处理: {title_preview}...")

        # URL去重
        if note_url and note_url in existing_urls:
            print(f"  ⏭ 已存在，跳过")
            skipped += 1
            continue

        result = process_note(note)
        if not result:
            skipped += 1
            continue

        if result.get('skip'):
            print(f"  ⏭ 内容无价值，跳过")
            skipped += 1
            continue

        # 标题+分类去重
        if is_duplicate(kb, result.get('title', ''), result.get('category', '')):
            print(f"  ⏭ 标题重复，跳过")
            skipped += 1
            continue

        entry = {
            "title": result.get('title', ''),
            "category": result.get('category', '政策'),
            "summary": result.get('summary', ''),
            "tips": result.get('tips', []),
            "target_group": result.get('target_group', '通用'),
            "source_url": note_url or f"https://www.xiaohongshu.com/explore/{note.get('note_id','')}",
            "collected_at": datetime.now().strftime('%Y-%m-%d %H:%M'),
            "source": "小红书"
        }

        kb.append(entry)
        existing_urls.add(note_url)
        added += 1
        print(f"  ✅ 已入库: [{entry['category']}] {entry['title']}")

        # 每5条保存一次
        if added % 5 == 0:
            save_kb(kb)
            print(f"  💾 已保存 ({len(kb)} 条)")

        time.sleep(0.5)  # 避免请求过快

    save_kb(kb)
    print("=" * 50)
    print(f"完成！新增: {added} 条，跳过: {skipped} 条，知识库总计: {len(kb)} 条")


if __name__ == '__main__':
    main()
