import json
import os
from pathlib import Path

from openai import OpenAI

KB_FILE = Path("knowledge_base.json")


def load_kb_context() -> str:
    """把知识库内容拼成字符串注入系统提示词"""
    if not KB_FILE.exists():
        return ""
    entries = json.loads(KB_FILE.read_text(encoding="utf-8"))
    if not entries:
        return ""
    lines = ["以下是知识库中已收录的攻略，回答时优先参考：\n"]
    for e in entries:
        lines.append(f"【{e['category']}】{e['title']}")
        lines.append(f"摘要：{e['summary']}")
        if e.get("tips"):
            lines.append("要点：" + "；".join(e["tips"]))
        lines.append("")
    return "\n".join(lines)


SYSTEM_PROMPT = """你是一个专为有需要的朋友服务的智能助手，拥有以下领域的专业知识：

1. **出行与无障碍设施**：景区、商场、交通工具的无障碍设施信息，轮椅友好路线，无障碍电梯状态
2. **辅助工具与 DIY 改造**：低成本辅助器具推荐，3D 打印方案，智能家居改造技巧
3. **政策与补贴**：各地残疾人补贴政策解读，申请流程，所需材料清单
4. **就业与技能**：适合有需要的朋友的远程工作机会，无障碍职业技能学习资源
5. **日常生活攻略**：视障、肢残、听障等不同群体的实用生活技巧

回答原则：
- 信息具体、实用，避免空话
- 优先提供可操作的步骤或清单
- 如果涉及地区性政策，提醒用户核实当地最新规定
- 语气温和、尊重，不使用歧视性表达
- 如果不确定某条信息，明确说明并建议用户通过官方渠道核实"""

MODEL = "kimi-k2-thinking"


def chat():
    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("OPENAI_BASE_URL"),
    )

    kb_context = load_kb_context()
    system = SYSTEM_PROMPT + ("\n\n" + kb_context if kb_context else "")
    messages = [{"role": "system", "content": system}]

    print("=" * 50)
    print("  无障碍知识库 · AI 智能问答")
    print("=" * 50)
    print("输入你的问题，输入 'quit' 退出\n")

    while True:
        user_input = input("你: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "退出"):
            print("再见！")
            break

        messages.append({"role": "user", "content": user_input})

        print("\nAI: ", end="", flush=True)

        stream = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=2048,
            stream=True,
        )

        full_response = ""
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                print(delta, end="", flush=True)
                full_response += delta

        print("\n")
        messages.append({"role": "assistant", "content": full_response})


if __name__ == "__main__":
    chat()
