"""
无障碍知识库 · 网页爬取+AI提炼流水线

流程：
  1. 从 SOURCES 列表抓取网页原文
  2. AI 提炼成结构化条目（不凭空生成）
  3. 追加写入 knowledge_base.json（自动去重）
  4. 每条条目保留 source_url 供溯源
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("MODEL", "kimi-k2-thinking")
KB_FILE = Path("knowledge_base.json")

SOURCES = [
    {
        "url": "https://www.who.int/zh/news-room/fact-sheets/detail/disability-and-health",
        "tag": "健康",
        "desc": "WHO · 残疾与健康",
    },
    {
        "url": "https://baike.baidu.com/item/%E6%AE%8B%E7%96%BE%E4%BA%BA%E4%BF%9D%E9%9A%9C%E6%B3%95",
        "tag": "政策",
        "desc": "百度百科 · 残疾人保障法",
    },
    {
        "url": "https://baike.baidu.com/item/%E6%AE%8B%E7%96%BE%E4%BA%BA%E5%B0%B1%E4%B8%9A%E4%BF%83%E8%BF%9B%E6%9D%A1%E4%BE%8B",
        "tag": "就业",
        "desc": "百度百科 · 残疾人就业促进条例",
    },
    {
        "url": "https://baike.baidu.com/item/%E6%97%A0%E9%9A%9C%E7%A2%8D%E7%8E%AF%E5%A2%83%E5%BB%BA%E8%AE%BE%E6%B3%95",
        "tag": "出行",
        "desc": "百度百科 · 无障碍环境建设法",
    },
    {
        "url": "https://baike.baidu.com/item/%E6%AE%8B%E7%96%BE%E4%BA%BA%E8%AF%81",
        "tag": "政策",
        "desc": "百度百科 · 残疾人证",
    },
    {
        "url": "https://baike.baidu.com/item/%E8%BE%85%E5%8A%A9%E5%99%A8%E5%85%B7",
        "tag": "辅具",
        "desc": "百度百科 · 辅助器具",
    },
    {
        "url": "https://baike.baidu.com/item/%E6%AE%8B%E7%96%BE%E4%BA%BA%E6%95%99%E8%82%B2",
        "tag": "教育",
        "desc": "百度百科 · 残疾人教育",
    },
    {
        "url": "https://baike.baidu.com/item/%E7%B2%BE%E7%A5%9E%E6%AE%8B%E7%96%BE",
        "tag": "健康",
        "desc": "百度百科 · 精神残疾",
    },
    {
        "url": "https://baike.baidu.com/item/%E8%82%A2%E4%BD%93%E6%AE%8B%E7%96%BE",
        "tag": "健康",
        "desc": "百度百科 · 肢体残疾",
    },
    {
        "url": "https://baike.baidu.com/item/%E8%A7%86%E5%8A%9B%E6%AE%8B%E7%96%BE",
        "tag": "健康",
        "desc": "百度百科 · 视力残疾",
    },
    {
        "url": "https://baike.baidu.com/item/%E5%90%AC%E5%8A%9B%E6%AE%8B%E7%96%BE",
        "tag": "健康",
        "desc": "百度百科 · 听力残疾",
    },
    {
        "url": "https://baike.baidu.com/item/%E6%AE%8B%E7%96%BE%E4%BA%BA%E4%B8%A4%E9%A1%B9%E8%A1%A5%E8%B4%B4",
        "tag": "政策",
        "desc": "百度百科 · 残疾人两项补贴",
    },
    {
        "url": "https://www.gov.cn/zhengce/content/2015-08/17/content_10097.htm",
        "tag": "就业",
        "desc": "国务院 · 残疾人就业条例",
    },
]


def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 未设置，请检查 .env 文件")
    return OpenAI(api_key=api_key, base_url=base_url)


def fetch_page(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return text[:6000]


def ai_extract(client: OpenAI, raw_text: str, source_tag: str) -> dict | None:
    """从真实网页文本中提炼结构化条目，不凭空生成内容"""
    prompt = f"""你是无障碍知识库的内容编辑。

下面是从网页抓取的原始文本（来源分类：{source_tag}）：

---
{raw_text}
---

任务：
1. 判断这段内容是否包含对有需要的人有实用价值的信息（出行、辅具、政策、就业、生活技巧、健康等）。
2. 如果有价值，将其中的真实信息整理为 JSON；如果没有实质内容，只输出 null。

重要：只提炼原文中存在的信息，不要补充或推断原文没有的内容。

JSON 格式（只输出 JSON 或 null，不要其他文字）：
{{"title":"标题（15字以内）","category":"分类（出行/辅具/政策/就业/生活技巧/健康 之一）","summary":"基于原文的摘要（100字以内）","tips":["原文中的具体信息1","信息2","信息3"],"target_group":"适用人群（肢残/视障/听障/通用）"}}"""

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.1,
        stream=False,
    )
    content = resp.choices[0].message.content
    if not content:
        return None
    content = content.strip()
    if not content or content.lower() == "null":
        return None
    # 提取 JSON 块
    if "```" in content:
        parts = content.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                content = part
                break
    start = content.find("{")
    end = content.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    return json.loads(content[start:end])


def load_kb() -> list:
    if KB_FILE.exists():
        try:
            return json.loads(KB_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_kb(entries: list):
    KB_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_duplicate(kb: list, entry: dict) -> bool:
    for e in kb:
        if e.get("source_url") and e["source_url"] == entry.get("source_url"):
            return True
        if e.get("title") == entry.get("title") and e.get("category") == entry.get("category"):
            return True
    return False


def run():
    client = get_client()
    # 保留所有现有条目，不过滤
    kb = load_kb()
    print(f"知识库现有条目：{len(kb)} 条\n")

    existing_urls = {e.get("source_url", "") for e in kb}
    success, failed = 0, 0

    for source in SOURCES:
        url = source["url"]
        if url in existing_urls:
            print(f"[跳过] 已收录：{source['desc']}")
            continue

        print(f"[抓取] {source['desc']} ...")
        try:
            raw = fetch_page(url)
        except Exception as e:
            print(f"  [失败] 抓取失败：{e}")
            failed += 1
            continue

        print("  AI 提炼中...")
        try:
            entry = ai_extract(client, raw, source["tag"])
        except Exception as e:
            print(f"  [失败] AI 处理失败：{e}")
            failed += 1
            continue

        if entry is None:
            print("  内容不相关，跳过")
            continue

        entry["source_url"] = url
        entry["source_name"] = source["desc"]
        entry["collected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        if is_duplicate(kb, entry):
            print(f"  重复条目，跳过：{entry['title']}")
            continue

        kb.append(entry)
        save_kb(kb)
        success += 1
        print(f"  [OK] 已收录：{entry['title']} [{entry['category']}]")
        time.sleep(1)

    print(f"\n完成：新增 {success} 条，失败 {failed} 条，知识库共 {len(kb)} 条。")
    if failed > 0:
        print("提示：部分 URL 无法访问，可在 SOURCES 列表中替换为可用链接。")


if __name__ == "__main__":
    run()
