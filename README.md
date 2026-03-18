# ClawCare · 无障碍生活助手

> 基于 OpenClaw 的自进化 AI 无障碍信息服务平台  
> An AI-powered, self-evolving accessibility information platform built on OpenClaw

[中文](#中文) | [English](#english)

---

## 中文

### 项目简介

**ClawCare（无障碍生活助手）** 是一个面向残障人士及其家属的 AI 问答平台，帮助用户快速获取残障权益、补贴政策、无障碍出行等实用信息。

项目以 **OpenClaw** 作为智能运营核心，实现知识库的持续更新、网站内容的自动优化，以及用户问答的智能沉淀——让平台在无人值守的情况下持续生长。

### 核心功能

- **AI 问答**：检索本地知识库后调用大模型生成回答，支持 SSE 流式输出
- **知识库浏览**：可搜索、按分类筛选全部知识条目（政策 / 就业 / 出行 / 辅具 / 生活技巧 / 健康）
- **问答自动沉淀**：每次对话后自动判断是否有新知识价值并写入知识库，越用越聪明
- **知识库自生长**：OpenClaw 定期爬取政策网站 + AI 提炼，无需人工维护

### OpenClaw 的角色

| 职责 | 说明 |
|------|------|
| 🔄 持续更新知识库 | 定期爬取中国残联、国务院、各省市政府网站，AI 提炼为结构化条目 |
| 🛠 优化网站内容 | 前端迭代、后端优化、数据脚本维护、日志分析 |
| 💬 运营平台 | 撰写宣传文案、问答质量监控、数据统计播报 |

### 技术架构

```
用户浏览器
    │
    ▼
Flask 后端 (bank/server.py)
    ├── /api/chat        SSE 流式问答
    ├── /api/kb          知识库 CRUD
    ├── /api/kb/search   全文搜索
    └── /api/stats       访问统计
    │
    ├── knowledge_base.json   本地知识库
    ├── qa_history.json       问答历史
    └── stats.json            访问统计

OpenClaw（后台运营引擎）
    ├── bank-crawler skill    爬取 + AI提炼 + 入库
    ├── import_xhs.py         小红书数据导入
    └── 对话驱动              前端优化 / 文案撰写 / 数据分析
```

**技术栈**：Python · Flask · SSE · JSON · OpenAI 兼容 API

### 目录结构

```
ClawCare/
├── bank/                   # 核心应用
│   ├── server.py           # Flask 后端
│   ├── chatbot.py          # AI 问答逻辑
│   ├── collector.py        # 数据采集
│   ├── import_xhs.py       # 小红书数据导入
│   ├── knowledge_base.json # 知识库数据
│   ├── index.html          # 前端页面
│   └── .env.example        # 环境变量模板
├── logo-demo/              # Logo 设计展示
│   └── index.html
├── skills/                 # OpenClaw Skills
│   └── github/
└── README.md
```

### 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/BeJane/ClawCare.git
cd ClawCare

# 2. 配置环境变量
cp bank/.env.example bank/.env
# 编辑 .env，填入你的 API Key

# 3. 安装依赖
pip install flask openai

# 4. 启动服务
cd bank && python3 server.py
```

访问 `http://localhost:5000`

### 数据来源

- 中国残联官网（cdpf.org.cn）
- 国务院政策文件（gov.cn）
- 各省市人民政府官网
- 小红书用户真实经验（MediaCrawler 爬取）

---

## English

### Overview

**ClawCare** is an AI-powered Q&A platform for people with disabilities and their families, providing quick access to disability benefits, subsidy policies, and accessible transportation information.

Built on **OpenClaw**, the platform continuously evolves — automatically updating its knowledge base, optimizing content, and learning from user interactions — all without manual intervention.

### Key Features

- **AI Q&A**: Retrieves from local knowledge base and generates answers via LLM with SSE streaming
- **Knowledge Browser**: Search and filter entries by category (Policy / Employment / Transportation / Assistive Devices / Life Tips / Health)
- **Auto Knowledge Accumulation**: After each conversation, valuable answers are automatically distilled into the knowledge base
- **Self-growing Knowledge Base**: OpenClaw periodically crawls policy websites and uses AI to extract structured entries

### OpenClaw's Role

| Role | Description |
|------|-------------|
| 🔄 Knowledge Updates | Periodically crawls CDPF, State Council, and provincial government sites; AI extracts structured entries |
| 🛠 Site Optimization | Frontend iteration, backend tuning, data script maintenance, log analysis |
| 💬 Platform Operations | Copywriting, Q&A quality monitoring, traffic analytics |

### Tech Stack

```
Browser
    │
    ▼
Flask Backend (bank/server.py)
    ├── /api/chat        SSE streaming Q&A
    ├── /api/kb          Knowledge base CRUD
    ├── /api/kb/search   Full-text search
    └── /api/stats       Access statistics
    │
    ├── knowledge_base.json
    ├── qa_history.json
    └── stats.json

OpenClaw (background engine)
    ├── bank-crawler skill    Crawl + AI extract + ingest
    ├── import_xhs.py         Xiaohongshu data import
    └── Conversational ops    Frontend / copywriting / analytics
```

**Stack**: Python · Flask · SSE · JSON · OpenAI-compatible API

### Project Structure

```
ClawCare/
├── bank/                   # Core application
│   ├── server.py           # Flask backend
│   ├── chatbot.py          # AI Q&A logic
│   ├── collector.py        # Data collection
│   ├── import_xhs.py       # Xiaohongshu importer
│   ├── knowledge_base.json # Knowledge base data
│   ├── index.html          # Frontend
│   └── .env.example        # Environment template
├── logo-demo/              # Logo design showcase
│   └── index.html
├── skills/                 # OpenClaw Skills
│   └── github/
└── README.md
```

### Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/BeJane/ClawCare.git
cd ClawCare

# 2. Set up environment
cp bank/.env.example bank/.env
# Edit .env with your API keys

# 3. Install dependencies
pip install flask openai

# 4. Start the server
cd bank && python3 server.py
```

Visit `http://localhost:5000`

### Data Sources

- China Disabled Persons' Federation (cdpf.org.cn)
- State Council policy documents (gov.cn)
- Provincial and municipal government websites
- Real user experiences from Xiaohongshu (via MediaCrawler)

---

## License

MIT
