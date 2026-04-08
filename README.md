# Run : .venv\Scripts\python.exe -m streamlit run codebot.py

# 🤖 Cognix — AI Internship Assistant Chatbot

An intelligent, AI-powered chatbot built with **Streamlit** and **Google Gemini AI** that helps students explore and apply for internship programs.

Cognix uses a **hybrid approach**: rule-based matching for instant answers on known topics, and **Google Gemini AI** for dynamic, conversational responses to complex queries.

---

## ✨ Features

- 🔍 **Fuzzy Intent Matching** — Handles typos, natural language, and partial phrases using [thefuzz](https://github.com/seatgeek/thefuzz)
- 🧠 **AI-Powered Responses** — Google Gemini AI handles complex queries like comparisons, recommendations, and career advice
- 🗂️ **15+ Internship Programs** — Web Dev, Full Stack, ML, Data Science, Gen AI, Cyber Security, and more
- 💬 **Conversational Personality** — Tells jokes, gives career guidance, and has fun while staying helpful
- ⚙️ **Easy Configuration** — All intents, responses, and AI settings live in a single `intents.json` file
- 📊 **Sidebar Status** — Shows whether AI Mode is ON/OFF and which model is active
- 🔒 **Secure** — API keys stored in `.env`, protected by `.gitignore`

---

## 🛠️ Tech Stack

| Technology | Purpose |
|---|---|
| [Streamlit](https://streamlit.io/) | Chat UI framework |
| [Google Gemini AI](https://ai.google.dev/) | Generative AI for dynamic responses |
| [thefuzz](https://github.com/seatgeek/thefuzz) | Fuzzy string matching for intent detection |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | Environment variable management |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- A free [Google Gemini API key](https://aistudio.google.com/apikey)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Kaustubh-0607/cognix-ai-chatbot.git
   cd cognix-ai-chatbot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up your API key**
   
   Create a `.env` file in the project root:
   ```env
   GEMINI_API_KEY=your_api_key_here
   ```

4. **Run the chatbot**
   ```bash
   python -m streamlit run codebot.py
   ```

5. Open your browser at `http://localhost:8501` 🎉

---

## ☁️ Deploy on Replit (Complete Setup)

This project is now pre-configured for Replit with:
- `.replit` for run/deployment commands
- `.streamlit/config.toml` for Replit-safe host/port settings

### 1. Import the project

1. Open Replit and click **Create Repl**.
2. Choose **Import from GitHub** and paste your repository URL.
3. Wait for the workspace to load.

### 2. Add your secret API key

1. Open **Tools → Secrets** in Replit.
2. Add a new secret:
   - Key: `GEMINI_API_KEY`
   - Value: your Gemini API key

Do not hardcode the key in source files.

### 3. Run the app in Replit

Use the Replit **Run** button. The app starts with:

```bash
pip install -r requirements.txt && streamlit run codebot.py --server.address 0.0.0.0 --server.port ${PORT:-3000} --server.headless true
```

### 4. Deploy publicly

1. Click **Deploy** in Replit.
2. Choose **Autoscale Deployment**.
3. Confirm deploy.

Replit will use the deployment run command from `.replit` and expose your app on a public URL.

### 5. Verify after deploy

- Open the deployed URL.
- Send a basic message like `python internship`.
- Enable AI mode and test a complex prompt like `Compare Python vs Java internships`.

If AI mode fails, re-check the `GEMINI_API_KEY` secret.

---

## 📁 Project Structure

```
cognix-ai-chatbot/
├── codebot.py          # Main application (Streamlit UI + AI logic)
├── intents.json        # All config: intents, keywords, responses, AI settings
├── requirements.txt    # Python dependencies
├── .env                # API key (not committed)
├── .gitignore          # Protects secrets
└── README.md           # You are here!
```

---

## 🧪 How It Works

```
User Message
     │
     ▼
┌─────────────────┐
│  Smart Router    │
│  (detects query  │
│   complexity)    │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
 Simple    Complex
 keyword   (compare, joke,
    │       recommend...)
    ▼         ▼
 Rule-     Gemini
 Based     AI 🧠
 ⚡ instant  dynamic
```

**Examples:**
| User Input | Routed To | Why |
|---|---|---|
| `"python"` | Rule-based ⚡ | Direct keyword match |
| `"intrenship"` | Rule-based ⚡ | Fuzzy match catches the typo |
| `"Compare Python vs Java"` | Gemini AI 🧠 | Detected "compare" + "vs" |
| `"Tell me a joke"` | Gemini AI 🧠 | Detected "joke" |
| `"Which internship for beginners?"` | Gemini AI 🧠 | Detected "which" + "beginner" |

---

## ⚙️ Configuration

All settings live in `intents.json`:

| Setting | What it does |
|---|---|
| `enable_ai` | Toggle AI on/off (`true` / `false`) |
| `model_name` | Gemini model (e.g. `gemini-2.5-flash`) |
| `system_prompt` | AI personality and knowledge base |
| `fuzzy_threshold` | How strict the fuzzy matching is (0-100) |

### Adding a new intent (no code changes needed!)

```json
"new_topic": {
  "keywords": ["keyword1", "keyword2", "phrase"],
  "response": "**Cognix:** Your response here..."
}
```

---

## 📸 Screenshots

| Welcome Page | AI Response |
|---|---|
| ![Welcome](screenshots/welcome.png) | ![AI](screenshots/ai-response.png) |

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

## 🙋 Author

Built with ❤️ as an AI/ML internship project.

---

> **Tip:** Type `main menu` anytime in the chat to return to the start!
