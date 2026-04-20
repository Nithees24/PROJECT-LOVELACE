# 🧠 Project Lovelace — Agentic AI Research Assistant


## ⚡ An intelligent Agentic AI system that can chat, think, and perform deep research autonomously.

### ✨ Overview

Lovelace is an AI-powered workspace that combines:
- 🧠 LLM reasoning  
- 🔍 Tool usage (search, scraping, research papers)  
- ⚙️ Autonomous multi-step pipelines  

It automatically decides:

- 💬 Chat Mode → instant answers
- 🔬 Deep Research Mode → structured research
- 🖼️ UI Preview

<img width="1918" height="912" alt="version 0 0 1" src="https://github.com/user-attachments/assets/25cc5ada-d9ba-4bfe-a89e-a1f1b74f0066" />


💬 Chat Mode

🔬 Deep Research Mode

- 🧠 How It Works
- ⚙️ Features
- 🧠 Intelligent Planner-based routing
- 🔄 Dual-mode system (Chat + Deep Research)
- 🌐 Web search + scraping
- 📄 Research paper integration
- 📊 Ranking & summarization pipeline
- 🎨 Clean Lovelace UI
- ⚡ Modular architecture
- 🏗️ Project Structure
```
project-root/
│
├── agents/
│   ├── general_chat_agent.py
│   ├── deep_research_agent.py
│
├── pipeline/
│   ├── planner.py
│   ├── ranker.py
│   ├── synthesizer.py
│   ├── aggregator.py
│
├── tools/
│   ├── scrapper.py
│   ├── web_search.py
│   ├── paper_fetch.py
│   ├── pdf_parser.py
│
├── llm/
│   ├── llm_client.py
│
├── utils/
│   ├── prompt_builder.py
│
├── frontend/
│   ├── lovelace.html
│   ├── script.js
│   ├── styles.css
│
├── config.py
├── main.py
└── README.md
```

🚀 Getting Started
- 1️⃣ Clone the repo
- git clone https://github.com/your-username/project-lovelace.git
- cd project-lovelace
- 2️⃣ Install dependencies
- pip install -r requirements.txt
- 3️⃣ Setup environment variables

- Create .env:

- YOUR_LLM_SERVICE_API=your_api_key_here
- 4️⃣ Run backend
- python main.py
- 5️⃣ Run frontend

- Open:

- frontend/lovelace.html

- Make sure backend endpoint is:

- /api/chat
- 🔧 Configuration
- LLM_MODEL = "gemini-3.1-flash-lite-preview"
- TEMPERATURE = 0.2
- 🧩 Core Components
- 🧠 Planner
- Decides execution mode
- Outputs structured JSON plan
- 💬 General Chat Agent
- Handles simple queries
- 🔬 Deep Research Agent

- Pipeline:

- Plan → Search → Scrape → Papers → Parse → Rank → Summarize → Aggregate

- ⚠️ Limitations
- Some tools may not be fully implemented
- No persistent memory yet
- Needs proper backend API integration
- Error handling can be improved
  
### 🔮 Roadmap
-  Vector DB (RAG)
-  Streaming responses
-  Memory system
-  Multi-agent collaboration
-  Better ranking (embeddings)
-  Production API (FastAPI)

### 🤝 Contributing
- fork → clone → create branch → commit → PR 🚀
  
 ### 📜 License

- This project is licensed under the MIT License.

### 👨‍💻 Author

### Nithees Kanna

### ⭐ Support

- If you like this project:

- ⭐ Star the repo
- 🍴 Fork it
- 🚀 Build something amazing
- 🔥 Next Upgrade (Highly Recommended)
