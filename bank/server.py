import os, json, threading, asyncio, io
from datetime import datetime
from pathlib import Path
from flask import Flask, request, Response, jsonify, stream_with_context, send_file
from flask_cors import CORS
from dotenv import load_dotenv
import requests as req
import edge_tts

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("MOONSHOT_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL") or os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
MODEL = os.getenv("MODEL", "kimi-k2-thinking")
PORT = int(os.getenv("PORT", 5000))

KB_FILE = Path("knowledge_base.json")
STATS_FILE = Path("stats.json")
QA_FILE = Path("qa_history.json")

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

SYSTEM_PROMPT = """你是一个专为有需要的朋友服务的智能助手，拥有以下领域的专业知识：

1. 出行与无障碍设施：景区、商场、交通工具的无障碍设施信息，轮椅友好路线
2. 辅助工具与 DIY 改造：低成本辅助器具推荐，3D 打印方案，智能家居改造
3. 政策与补贴：各地残疾人补贴政策解读，申请流程，所需材料清单
4. 就业与技能：适合有需要的朋友的远程工作机会，无障碍职业技能学习资源
5. 日常生活攻略：视障、肢残、听障等不同群体的实用生活技巧

回答原则：
- 信息具体、实用，优先提供可操作的步骤或清单
- 用户若已提供摘要或建议，不要重复，直接在此基础上补充更深入的内容
- 如涉及地区性政策，提醒用户核实当地最新规定
- 语气温和、尊重，不使用歧视性表达
- 不确定的信息明确说明，建议通过官方渠道核实
- 回答结构清晰，适当使用编号或分段，方便阅读"""


# ── 知识库 ────────────────────────────────────────────────────────

def load_kb():
    if KB_FILE.exists():
        return json.loads(KB_FILE.read_text(encoding="utf-8"))
    return []

def save_kb(kb):
    KB_FILE.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")

def load_kb_context():
    kb = load_kb()
    if not kb:
        return ""
    lines = ["\n\n以下是知识库中的相关信息，请优先参考："]
    for i, item in enumerate(kb[:30], 1):
        lines.append(f"\n[{i}] {item.get('title','')}（{item.get('category','')}）")
        lines.append(f"    {item.get('summary','')}")
        tips = item.get("tips", [])
        if tips:
            lines.append(f"    建议：{'；'.join(tips[:2])}")
    return "\n".join(lines)

def is_duplicate(kb, title, category=""):
    return any(e.get("title") == title and (not category or e.get("category") == category) for e in kb)


# ── SSE 流式调用 ──────────────────────────────────────────────────

def stream_chat(messages):
    """向 AI 发请求，返回 SSE 生成器"""
    resp = req.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": messages, "temperature": 0.7, "max_tokens": 1000, "stream": True},
        stream=True, timeout=60
    )
    resp.raise_for_status()
    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                content = chunk["choices"][0]["delta"].get("content")
                if content:
                    yield content
            except Exception:
                pass

def call_chat(prompt, max_tokens=600, temperature=0.3):
    """单次非流式调用，返回完整字符串"""
    resp = req.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
              "temperature": temperature, "max_tokens": max_tokens, "stream": True},
        stream=True, timeout=60
    )
    out = ""
    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                out += json.loads(data)["choices"][0]["delta"].get("content") or ""
            except Exception:
                pass
    return out.strip()


# ── 问答自动入库 ──────────────────────────────────────────────────

def try_save_to_kb(user_question, ai_answer):
    """后台线程：判断对话是否有知识价值，有则提炼入库"""
    try:
        prompt = f"""判断以下问答是否包含对残障人士有长期参考价值的知识。
如有价值，提炼为JSON（严格输出JSON，不要其他内容）：
{{"title":"15字以内标题","category":"政策/就业/出行/辅具/生活技巧/健康","summary":"100字以内摘要","tips":["建议1","建议2"],"target_group":"肢残/视障/听障/通用"}}
如无价值输出：{{"skip":true}}

用户问题：{user_question[:200]}
AI回答：{ai_answer[:2000]}"""

        result_raw = call_chat(prompt, max_tokens=500, temperature=0.1)
        if "```" in result_raw:
            result_raw = result_raw.split("```")[1].lstrip("json").strip()
        s, e = result_raw.find("{"), result_raw.rfind("}") + 1
        if s == -1:
            return
        result = json.loads(result_raw[s:e])
        if result.get("skip"):
            return

        kb = load_kb()
        if is_duplicate(kb, result["title"], result.get("category", "")):
            return

        entry = {
            **result,
            "source_url": "",
            "source_name": "用户问答沉淀",
            "source_question": user_question[:100],
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        kb.append(entry)
        save_kb(kb)
    except Exception:
        pass


# ── 问答历史 ─────────────────────────────────────────────────────

def append_qa_history(user_question, ai_answer, hit_kb=False):
    """追加一条问答记录到 qa_history.json"""
    try:
        history = []
        if QA_FILE.exists():
            history = json.loads(QA_FILE.read_text(encoding="utf-8"))
        history.append({
            "q": user_question[:300],
            "a": ai_answer[:1000],
            "hit_kb": hit_kb,
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        # 只保留最近 500 条
        if len(history) > 500:
            history = history[-500:]
        QA_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── 统计 ──────────────────────────────────────────────────────────

def load_stats():
    if STATS_FILE.exists():
        return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    return {"pv": 0, "today": "", "today_pv": 0}

def record_visit():
    stats = load_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    stats["pv"] = stats.get("pv", 0) + 1
    if stats.get("today") != today:
        stats["today"] = today
        stats["today_pv"] = 0
    stats["today_pv"] = stats.get("today_pv", 0) + 1
    STATS_FILE.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")


# ── 路由 ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    record_visit()
    return app.send_static_file("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)

    # 兼容两种格式：{ message: "..." } 或 { messages: [...] }
    if "messages" in data:
        history = data["messages"]
        user_msg = next((m["content"] for m in reversed(history) if m["role"] == "user"), "").strip()
    else:
        user_msg = data.get("message", "").strip()
        history = [{"role": "user", "content": user_msg}]

    if not user_msg:
        return jsonify({"error": "message is required"}), 400

    kb_context = load_kb_context()
    system = SYSTEM_PROMPT + kb_context
    messages = [{"role": "system", "content": system}] + history

    full_answer = []

    def generate():
        for chunk in stream_chat(messages):
            full_answer.append(chunk)
            # 同时输出 content 和 token 字段，兼容不同前端
            yield f"data: {json.dumps({'content': chunk, 'token': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        # 后台入库 + 记录问答历史
        answer = "".join(full_answer)
        kb_hit = bool(kb_context)
        threading.Thread(target=try_save_to_kb, args=(user_msg, answer), daemon=True).start()
        threading.Thread(target=append_qa_history, args=(user_msg, answer, kb_hit), daemon=True).start()

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/kb", methods=["GET"])
def kb_list():
    kb = load_kb()
    category = request.args.get("category")
    if category:
        kb = [e for e in kb if e.get("category") == category]
    return jsonify(kb)

@app.route("/api/kb", methods=["POST"])
def kb_add():
    data = request.get_json(force=True)
    for field in ("title", "category", "summary"):
        if not data.get(field):
            return jsonify({"error": f"missing field: {field}"}), 400
    kb = load_kb()
    if is_duplicate(kb, data["title"], data["category"]):
        return jsonify({"error": "duplicate entry"}), 409
    entry = {
        "title": data["title"],
        "category": data["category"],
        "summary": data["summary"],
        "tips": data.get("tips", []),
        "target_group": data.get("target_group", "通用"),
        "source_url": data.get("source_url", ""),
        "source_name": data.get("source_name", ""),
        "collected_at": data.get("collected_at", datetime.now().strftime("%Y-%m-%d %H:%M")),
    }
    kb.append(entry)
    save_kb(kb)
    return jsonify(entry), 201

@app.route("/api/kb/<int:idx>", methods=["DELETE"])
def kb_delete(idx):
    kb = load_kb()
    if idx < 0 or idx >= len(kb):
        return jsonify({"error": "index out of range"}), 404
    removed = kb.pop(idx)
    save_kb(kb)
    return jsonify(removed)

@app.route("/api/kb/search", methods=["GET"])
def kb_search():
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify([])
    kb = load_kb()
    results = []
    for item in kb:
        text = " ".join([
            item.get("title", ""), item.get("summary", ""),
            " ".join(item.get("tips", [])), item.get("category", "")
        ]).lower()
        if q in text:
            results.append(item)
    return jsonify(results)

@app.route("/api/stats", methods=["GET"])
def stats():
    return jsonify(load_stats())


@app.route("/api/gaps", methods=["GET"])
def gaps():
    """分析 qa_history.json，识别高频痛点和知识盲区"""
    if not QA_FILE.exists():
        return jsonify({"gaps": [], "total": 0, "message": "暂无问答历史"})

    history = json.loads(QA_FILE.read_text(encoding="utf-8"))
    if not history:
        return jsonify({"gaps": [], "total": 0, "message": "暂无问答历史"})

    # 只分析未命中知识库的问题（hit_kb=False），最多取最近 100 条
    missed = [h for h in history if not h.get("hit_kb", True)][-100:]
    total = len(history)

    if not missed:
        return jsonify({"gaps": [], "total": total, "message": "所有问题均已被知识库覆盖"})

    questions_text = "\n".join(f"- {h['q']}" for h in missed[:50])
    prompt = f"""以下是用户提出但知识库未能覆盖的问题列表（共{len(missed)}条）：

{questions_text}

请分析这些问题，识别出：
1. 高频痛点主题（出现3次以上或语义相近的问题归为一类）
2. 每个主题的代表性问题
3. 建议补充的知识方向

严格输出JSON数组，每项格式：
{{"theme":"主题名","count":出现次数,"example":"代表性问题","suggestion":"建议补充的内容方向"}}

只输出JSON数组，不要其他内容。"""

    try:
        result_raw = call_chat(prompt, max_tokens=800, temperature=0.2)
        s, e = result_raw.find("["), result_raw.rfind("]") + 1
        if s == -1:
            return jsonify({"gaps": [], "total": total, "raw": result_raw})
        gaps_list = json.loads(result_raw[s:e])
        return jsonify({"gaps": gaps_list, "total": total, "missed_count": len(missed)})
    except Exception as ex:
        return jsonify({"error": str(ex), "total": total}), 500


@app.route("/api/tts", methods=["POST"])
def tts():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    if len(text) > 3000:
        text = text[:3000]
    voice = data.get("voice", "zh-CN-XiaoxiaoNeural")

    async def _gen():
        buf = io.BytesIO()
        communicate = edge_tts.Communicate(text, voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        buf.seek(0)
        return buf

    try:
        buf = asyncio.run(_gen())
        return send_file(buf, mimetype="audio/mpeg", as_attachment=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
