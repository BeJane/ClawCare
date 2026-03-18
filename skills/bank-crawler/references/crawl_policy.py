#!/usr/bin/env python3
"""
bank-crawler: 政策网站爬取 + AI 提炼 + 知识库入库
用法: python3 crawl_policy.py
"""
import urllib.request, re, html, json, os, time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import requests as req

load_dotenv('/root/bank/.env')
API_KEY = os.getenv('OPENAI_API_KEY')
BASE_URL = os.getenv('OPENAI_BASE_URL')
MODEL = os.getenv('MODEL', 'kimi-k2-thinking')
KB_FILE = Path('/root/bank/knowledge_base.json')

# ── 爬取目标列表（按需增减）──────────────────────────────────────
LINKS = [
    ('国务院促进残疾人就业三年行动方案2025-2027', 'https://www.gov.cn/zhengce/content/202506/content_7030053.htm'),
    ('国务院加强重度残疾人托养照护意见', 'https://www.gov.cn/zhengce/content/202507/content_7034631.htm'),
    ('江西省促进残疾人就业三年行动方案', 'http://www.jiangxi.gov.cn/jxsrmzf/szfbg100/pc/content/content_2007653864991363072.html'),
    ('河南省促进残疾人就业三年行动方案', 'https://www.henan.gov.cn/2022/11-30/2648811.html'),
    ('福建省促进残疾人就业三年行动方案', 'http://www.fujian.gov.cn/zwgk/ztzl/zswzjjylzzccs/sj/202510/t20251011_7019955.htm'),
    ('上海市促进残疾人就业三年行动方案', 'https://www.shanghai.gov.cn/nw12344/20220601/5e0e0e0e0e0e0e0e0e0e0e0e.html'),
    ('精准施策破解残疾人就业难题', 'https://topics.gmw.cn/2022-10/27/content_36119631.htm'),
    ('安徽启动促进残疾人就业行动', 'https://www.ahdpf.org.cn/ztzl/jyxcn/150424631.html'),
]
# ─────────────────────────────────────────────────────────────────

PROMPT_TPL = """你是无障碍知识库整理助手。
从以下政策文章中提炼对有需要的人士有实用价值的知识条目。
严格输出JSON，不要输出其他内容：
{{"title":"15字以内标题","category":"政策/就业/出行/辅具/生活技巧/健康","summary":"100字以内核心摘要","tips":["可操作建议1","建议2","建议3"],"target_group":"肢残/视障/听障/通用"}}
如无价值输出：{{"skip":true}}

文章内容：
{text}"""


def load_kb():
    return json.loads(KB_FILE.read_text(encoding='utf-8')) if KB_FILE.exists() else []

def save_kb(kb):
    KB_FILE.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding='utf-8')

def is_dup(kb, title, url=''):
    return any(e.get('title') == title or (url and e.get('source_url') == url) for e in kb)

def fetch(url):
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; research-bot/1.0)'}
    r = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=12)
    raw = r.read()
    for enc in ['utf-8', 'gbk', 'gb2312']:
        try: return raw.decode(enc)
        except: pass
    return raw.decode('utf-8', errors='ignore')

def extract_text(html_str):
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_str, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()[:3000]

def chat(prompt):
    resp = req.post(f'{BASE_URL}/chat/completions',
        headers={'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'},
        json={'model': MODEL, 'messages': [{'role': 'user', 'content': prompt}],
              'temperature': 0.2, 'max_tokens': 600, 'stream': True},
        stream=True, timeout=60)
    out = ''
    for line in resp.iter_lines():
        if not line: continue
        line = line.decode('utf-8')
        if line.startswith('data: '):
            data = line[6:]
            if data == '[DONE]': break
            try: out += json.loads(data)['choices'][0]['delta'].get('content') or ''
            except: pass
    return out.strip()

def parse_json(raw):
    if '```' in raw:
        raw = raw.split('```')[1].lstrip('json').strip()
    s, e = raw.find('{'), raw.rfind('}') + 1
    if s == -1: return None
    return json.loads(raw[s:e])


def get_external_links(index_url, exclude_domain='cdpf.org.cn'):
    """从子栏目页面提取外链"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    page = urllib.request.urlopen(
        urllib.request.Request(index_url, headers=headers), timeout=10
    ).read().decode('utf-8', errors='ignore')
    links = []
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, re.DOTALL):
        href = m.group(1)
        text = html.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip()
        if href.startswith('http') and exclude_domain not in href and len(text) > 5:
            links.append((text[:40], href))
    return links


def crawl_links(links):
    kb = load_kb()
    added = 0
    for i, (title, url) in enumerate(links, 1):
        print(f'[{i}/{len(links)}] {title[:30]}...', flush=True)
        try:
            if is_dup(kb, '', url):
                print('  ⏭ URL已存在'); continue
            page = fetch(url)
            text = extract_text(page)
            if len(text) < 100:
                print('  ⏭ 内容太短'); continue
            result = parse_json(chat(PROMPT_TPL.format(text=text)))
            if not result or result.get('skip'):
                print('  ⏭ 无价值'); continue
            if is_dup(kb, result['title']):
                print(f'  ⏭ 重复: {result["title"]}'); continue
            entry = {**result, 'source_url': url, 'source_name': title,
                     'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M')}
            kb.append(entry)
            save_kb(kb)
            added += 1
            print(f'  ✅ [{result["category"]}] {result["title"]}')
        except Exception as ex:
            print(f'  ❌ {ex}')
        time.sleep(0.5)
    print(f'\n完成！新增 {added} 条，知识库总计 {len(kb)} 条')


if __name__ == '__main__':
    crawl_links(LINKS)
