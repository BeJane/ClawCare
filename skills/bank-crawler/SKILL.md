# bank-crawler skill

## 描述
爬取政策网站（中国残联官网等）和小红书数据，通过 AI 提炼后导入 `/root/bank/knowledge_base.json` 知识库。

## 触发条件
用户提到以下任意一项时激活：
- 爬取/抓取官网/政策网站数据
- 导入小红书数据到知识库
- 更新知识库
- 知识库入库

---

## 环境配置

所有配置从 `/root/bank/.env` 读取：

```
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.apimart.ai/v1
MODEL=kimi-k2-thinking
```

知识库路径：`/root/bank/knowledge_base.json`
小红书数据路径：`/root/xhs_data/xhs/json/`

---

## 任务一：小红书数据入库

直接运行现有脚本：

```bash
cd /root/bank && python3 import_xhs.py
```

脚本路径：`/root/bank/import_xhs.py`（见 `references/import_xhs.py`）

**注意**：数据文件名含日期，如有新文件需先修改脚本中的 `XHS_PATH`。

---

## 任务二：政策网站爬取入库

使用 `references/crawl_policy.py` 脚本。

### 用法

```bash
cd /root/bank && python3 /root/.openclaw/workspace/skills/bank-crawler/references/crawl_policy.py
```

### 流程

1. 从目标 URL 列表抓取页面（静态 HTML，`urllib`）
2. 提取正文文本（去除 script/style/标签）
3. 调用 AI 提炼为结构化知识条目（SSE 流式解析）
4. 去重后写入 `knowledge_base.json`

### 添加新爬取目标

编辑 `references/crawl_policy.py` 中的 `LINKS` 列表：

```python
LINKS = [
    ('文章标题', 'https://...'),
    ...
]
```

### 常见问题

| 错误 | 原因 | 处理 |
|------|------|------|
| HTTP 403 | 目标站反爬 | 跳过，换其他链接 |
| HTTP 404 | 链接失效 | 跳过 |
| Extra data (JSON) | AI 输出多余内容 | 脚本已做 `{...}` 提取，若仍失败检查 AI 输出 |
| TLS 错误 | 证书问题 | 加 `context = ssl.create_default_context(); context.check_hostname = False` |

---

## 任务三：从子栏目页面发现外链并批量入库

适用于中国残联官网等，文章链接指向省市政府网站。

### 步骤

1. 抓取子栏目页面，提取所有非 `cdpf.org.cn` 的外链
2. 过滤掉备案/导航链接（长度 < 6 字、含 `beian`/`gov.cn/home` 等）
3. 对每条外链执行任务二的流程

```python
import urllib.request, re, html

def get_external_links(index_url, exclude_domain='cdpf.org.cn'):
    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(index_url, headers=headers)
    page = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
    links = []
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, re.DOTALL):
        href = m.group(1)
        text = html.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip()
        if href.startswith('http') and exclude_domain not in href and len(text) > 5:
            links.append((text[:40], href))
    return links
```

---

## AI 提炼 Prompt

```
你是无障碍知识库整理助手。
从以下政策文章中提炼对有需要的人士有实用价值的知识条目。
严格输出JSON，不要输出其他内容：
{"title":"15字以内标题","category":"政策/就业/出行/辅具/生活技巧/健康","summary":"100字以内核心摘要","tips":["可操作建议1","建议2","建议3"],"target_group":"肢残/视障/听障/通用"}
如无价值输出：{"skip":true}

文章内容：
{text}
```

---

## 知识条目结构

```json
{
  "title": "15字以内标题",
  "category": "政策/就业/出行/辅具/生活技巧/健康",
  "summary": "核心摘要",
  "tips": ["建议1", "建议2", "建议3"],
  "target_group": "肢残/视障/听障/通用",
  "source_url": "https://...",
  "source_name": "来源名称",
  "collected_at": "2026-03-18 15:00"
}
```

## 去重策略

- URL 去重：`source_url` 已存在则跳过
- 标题去重：`title` 相同则跳过
- 双重保障，避免重复条目

## SSE 流式解析（核心函数）

API 返回 SSE 格式，需手动解析（不能用 `openai` 库直接调用）：

```python
import requests, json

def chat(prompt, api_key, base_url, model):
    resp = requests.post(f'{base_url}/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={'model': model, 'messages': [{'role': 'user', 'content': prompt}],
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
```
