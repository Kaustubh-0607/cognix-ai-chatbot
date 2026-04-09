"""
Cognix — AI Internship Assistant (Streamlit).

Hybrid chatbot: rule-based matching for known intents (instant),
Google Gemini AI for complex / unknown queries (smart).

All intent data and AI settings are loaded from `intents.json`.
API key is loaded from `.env`.
"""

import json
import os
import re
from pathlib import Path
import sqlite3
import uuid
import urllib.parse
import requests
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from thefuzz import fuzz, process

# ──────────────────────────────────────────────
# Database Setup
# ──────────────────────────────────────────────
DB_PATH = Path(__file__).parent / "chatbot.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT,
                messages TEXT,
                updated_at DATETIME
            )
        ''')
        try:
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN user_id TEXT DEFAULT 'anonymous'")
        except sqlite3.OperationalError:
            pass
        conn.commit()

init_db()

def get_recent_sessions(user_id, limit=5):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT session_id, title, updated_at 
            FROM chat_sessions 
            WHERE user_id = ?
            ORDER BY updated_at DESC LIMIT ?
        ''', (user_id, limit))
        return cursor.fetchall()

def load_session(user_id, session_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT messages FROM chat_sessions WHERE session_id = ? AND user_id = ?', (session_id, user_id))
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None

def save_session(user_id, session_id, title, messages):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            INSERT INTO chat_sessions (session_id, user_id, title, messages, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET 
                title = excluded.title,
                messages = excluded.messages,
                updated_at = excluded.updated_at
        ''', (session_id, user_id, title, json.dumps(messages), datetime.now().isoformat()))
        conn.commit()

def delete_session(user_id, session_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('DELETE FROM chat_sessions WHERE session_id = ? AND user_id = ?', (session_id, user_id))
        conn.commit()

def clear_all_sessions(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('DELETE FROM chat_sessions WHERE user_id = ?', (user_id,))
        conn.commit()

# ──────────────────────────────────────────────
# Load environment variables and configuration
# ──────────────────────────────────────────────
load_dotenv(Path(__file__).parent / ".env")

CONFIG_PATH = Path(__file__).parent / "intents.json"


def load_config(path: str) -> dict:
    """Read and parse the intents JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


config = load_config(str(CONFIG_PATH))
settings = config["settings"]
ai_settings = config.get("ai_settings", {})
INTENTS = config["intents"]

FUZZY_THRESHOLD = settings.get("fuzzy_threshold", 60)
MIN_TOKEN_LEN = settings.get("min_token_length", 3)
WELCOME_MSG = settings["welcome_message"]
FALLBACK_MSG = settings["fallback_response"]
BOT_NAME = settings["bot_name"]

# ──────────────────────────────────────────────
# Gemini AI setup
# ──────────────────────────────────────────────
AI_ENABLED = ai_settings.get("enable_ai", False)
GEMINI_MODEL = ai_settings.get("model_name", "gemini-2.0-flash")
SYSTEM_PROMPT = ai_settings.get("system_prompt", "")

gemini_model = None  # Will be initialized if AI is enabled

if AI_ENABLED:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if api_key and api_key != "PASTE_YOUR_API_KEY_HERE":
        try:
            from google import genai
            gemini_client = genai.Client(api_key=api_key)
            AI_READY = True
        except Exception as e:
            AI_READY = False
            st.sidebar.warning(f"⚠️ Gemini AI failed to initialize: {e}")
    else:
        AI_READY = False
else:
    AI_READY = False


def ask_gemini(user_msg: str, chat_history: list) -> str:
    """
    Send the user's message + conversation history to Gemini
    and return the AI-generated response.
    """
    if not AI_READY:
        return FALLBACK_MSG

    try:
        from google.genai import types
        # Build conversation context from chat history
        history = []
        for msg in chat_history[-10:]:  # Last 10 messages for context
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [{"text": msg["content"]}]})

        # Start a chat session with history for follow-up support
        chat = gemini_client.chats.create(
            model=GEMINI_MODEL, 
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            history=history
        )
        response = chat.send_message(user_msg)
        return response.text

    except Exception as e:
        return (
            f"**{BOT_NAME}:** I'm having trouble connecting to my AI brain right now. 😅\n\n"
            f"Error: `{e}`\n\n"
            "In the meantime, try asking about specific topics like:\n"
            "- Internship Opportunities\n"
            "- Project Guidelines\n"
            "- How to Apply\n\n"
            "Type **'main menu'** to see all options."
        )


# ──────────────────────────────────────────────
# Google OAuth setup
# ──────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8501/")

def get_login_url():
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent"
    }
    return f"{auth_url}?{urllib.parse.urlencode(params)}"

def authenticate_user():
    if "user" in st.session_state:
        return True
        
    query_params = st.query_params
    if "code" in query_params:
        code = query_params["code"]
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        res = requests.post(token_url, data=payload)
        st.query_params.clear()
        
        if res.status_code == 200:
            access_token = res.json().get("access_token")
            user_res = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"})
            if user_res.status_code == 200:
                st.session_state.user = user_res.json()
                st.rerun()
                return True
    return False

# ──────────────────────────────────────────────
# Streamlit page setup
# ──────────────────────────────────────────────
st.set_page_config(page_title=settings["page_title"], page_icon="🤖", layout="wide")

# Load and inject custom CSS
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

try:
    load_css(Path(__file__).parent / "style.css")
except FileNotFoundError:
    pass

st.markdown(f"<h1>🤖 {BOT_NAME} - {settings['page_title']}</h1>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align: center; color: rgba(255,255,255,0.7); margin-bottom: 2rem;'>{settings['subtitle']}</p>", unsafe_allow_html=True)

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    st.error("Google OAuth is not configured in .env. Please configure your Client ID and Secret.")
    st.stop()

is_authenticated = authenticate_user()
if not is_authenticated:
    st.info("🔒 Please log in with Google to securely access your chat history.")
    st.markdown(f'<a href="{get_login_url()}" target="_self"><button style="width:100%; padding:0.8rem; background:#4285F4; color:white; border:none; border-radius:8px; font-weight:bold; cursor:pointer;">Sign in with Google</button></a>', unsafe_allow_html=True)
    st.stop()

current_user_id = st.session_state.user.get("id", "anonymous")

# Sidebar: Database & AI status
with st.sidebar:
    st.markdown(f"### 👋 Welcome, {st.session_state.user.get('given_name', 'User')}!")
    if st.button("Logout", help="Sign out of your account"):
        del st.session_state["user"]
        st.rerun()
    st.divider()

    if st.button("➕ New Chat", type="primary", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.chat_title = "New Chat"
        st.session_state.messages = [
            {"role": "assistant", "content": WELCOME_MSG, "avatar": "🤖"}
        ]
        save_session(current_user_id, st.session_state.session_id, st.session_state.chat_title, st.session_state.messages)
        st.rerun()

    st.markdown("### 🕒 Recent Chats")
    recent_sessions = get_recent_sessions(current_user_id, 5)
    if not recent_sessions:
        st.caption("No recent chats found.")
    else:
        for sess in recent_sessions:
            col1, col2 = st.columns([0.85, 0.15])
            with col1:
                if st.button(f"💬 {sess['title']}", key=f"sess_{sess['session_id']}", use_container_width=True):
                    st.session_state.session_id = sess['session_id']
                    st.session_state.chat_title = sess['title']
                    msgs = load_session(current_user_id, sess['session_id'])
                    if msgs:
                        st.session_state.messages = msgs
                    st.rerun()
            with col2:
                if st.button("🗑️", key=f"del_{sess['session_id']}", help="Delete chat", use_container_width=True):
                    delete_session(current_user_id, sess['session_id'])
                    if st.session_state.session_id == sess['session_id']:
                        st.session_state.session_id = str(uuid.uuid4())
                        st.session_state.chat_title = "New Chat"
                        st.session_state.messages = [{"role": "assistant", "content": WELCOME_MSG, "avatar": "🤖"}]
                        save_session(current_user_id, st.session_state.session_id, st.session_state.chat_title, st.session_state.messages)
                    st.rerun()
                    
        if st.button("🚨 Clear All History", key="clear_all", help="Delete all chat history"):
            clear_all_sessions(current_user_id)
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.chat_title = "New Chat"
            st.session_state.messages = [{"role": "assistant", "content": WELCOME_MSG, "avatar": "🤖"}]
            save_session(current_user_id, st.session_state.session_id, st.session_state.chat_title, st.session_state.messages)
            st.rerun()
                
    st.divider()

    st.markdown("### ⚙️ Bot Settings")
    if AI_READY:
        use_ai_toggle = st.toggle("Enable AI Mode", value=False)
        st.caption("**Note:** Use AI mode only when necessary.  \n🌱 Save digital environment.")
        if use_ai_toggle:
            st.success(f"🧠 AI Mode: **ON** ({GEMINI_MODEL})")
            st.caption("Complex questions are answered by Google Gemini AI.")
        else:
            st.info("📋 AI Mode: **OFF** (Tokens saved!)")
            st.caption("The bot uses rule-based keyword matching only.")
    else:
        use_ai_toggle = False
        st.info("📋 AI Mode: **OFF** (Rule-based only)")
        if AI_ENABLED and not AI_READY:
            st.warning("Check your API key in `.env`")
        st.caption("The bot uses keyword matching for known topics.")
    st.divider()
    st.markdown(
        "**Tip:** Type `main menu` anytime to go back to the start."
    )


# ──────────────────────────────────────────────
# Intent matching engine (rule-based)
# ──────────────────────────────────────────────
def match_intent(user_msg: str) -> str | None:
    """
    Match user input to the best intent using a three-pass strategy:

    1. Whole-word substring match — covers obvious, exact cases
    2. Token overlap match       — catches keyword hits (tokens ≥ MIN_TOKEN_LEN chars)
    3. Fuzzy match (thefuzz)     — handles typos and partial phrases

    Returns the intent key, or None if no match meets the threshold.
    """
    msg = user_msg.lower().strip()

    best_intent = None
    best_score = 0

    for intent_key, intent_data in INTENTS.items():
        keywords = intent_data["keywords"]

        # ── Pass 1: whole-word substring match ──
        for kw in keywords:
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, msg):
                score = 100 + len(kw)
                if score > best_score:
                    best_score = score
                    best_intent = intent_key

        # ── Pass 2: token overlap (tokens ≥ MIN_TOKEN_LEN chars) ──
        msg_tokens = {t for t in msg.split() if len(t) >= MIN_TOKEN_LEN}
        for kw in keywords:
            kw_tokens = {t for t in kw.split() if len(t) >= MIN_TOKEN_LEN}
            if not kw_tokens:
                continue
            overlap = msg_tokens & kw_tokens
            if overlap:
                score = int((len(overlap) / len(kw_tokens)) * 90)
                if score > best_score:
                    best_score = score
                    best_intent = intent_key

        # ── Pass 3: fuzzy match ──
        best_kw, fuzzy_score = process.extractOne(
            msg, keywords, scorer=fuzz.token_sort_ratio
        )
        if fuzzy_score > best_score and fuzzy_score >= FUZZY_THRESHOLD:
            best_score = fuzzy_score
            best_intent = intent_key

    # ── Special handling for very short inputs (≤ 3 chars) ──
    if len(msg) <= 3 and best_score < 100:
        for intent_key, intent_data in INTENTS.items():
            if msg in intent_data["keywords"]:
                return intent_key
        return None

    return best_intent


# ──────────────────────────────────────────────
# Smart routing patterns (send these to AI, not rules)
# ──────────────────────────────────────────────
AI_ROUTE_PATTERNS = [
    # Comparisons & decisions
    r"\bcompare\b", r"\bvs\.?\b", r"\bversus\b",
    r"\bdifference\s+between\b", r"\bwhich\s+is\s+better\b",
    r"\bwhich\s+one\b", r"\bwhich\s+should\b",
    r"\brecommend\b", r"\bsuggest\b", r"\bbest\s+for\b",
    r"\bshould\s+i\b", r"\bpros\s+and\s+cons\b",
    r"\badvise\b", r"\bguidance\b", r"\bpath\b",
    r"\bcareer\b", r"\bbeginner\b", r"\bno\s+experience\b",
    r"\bwhat\s+should\b", r"\bhelp\s+me\s+choose\b",
    # Conversational / fun
    r"\bjoke\b", r"\bfunny\b", r"\btell\s+me\b",
    r"\bwhat\s+is\b", r"\bhow\s+does\b", r"\bwhy\s+is\b",
    r"\bexplain\b", r"\bwhat\s+are\b", r"\bfun\s+fact\b",
    r"\bwho\s+are\s+you\b", r"\bwhat\s+can\s+you\s+do\b",
    r"\bthanks?\b", r"\bthank\s+you\b",
]


def is_complex_query(msg: str) -> bool:
    """Check if the message is a complex question that the AI should handle."""
    lower = msg.lower()
    return any(re.search(p, lower) for p in AI_ROUTE_PATTERNS)


# ──────────────────────────────────────────────
# Chatbot reply (hybrid: rule-based → AI fallback)
# ──────────────────────────────────────────────
def chatbot_reply(user_msg: str, use_ai: bool = False) -> str:
    """
    Return the bot response for a given user message.

    Strategy:
    1. Check for "main menu" → reset chat (always rule-based)
    2. If AI is ready AND query looks complex → route to Gemini
    3. Otherwise → try rule-based matching
    4. If no rule match → fall back to Gemini AI (if enabled)
    5. If AI is off → return static fallback message
    """
    msg_lower = user_msg.lower().strip()

    # Always handle main menu via rules
    if "main menu" in msg_lower or msg_lower == "menu":
        intent_data = INTENTS.get("main_menu", {})
        if intent_data.get("reset_chat"):
            st.session_state.messages = [
                {"role": BOT_NAME, "content": WELCOME_MSG}
            ]
        return intent_data.get("response", WELCOME_MSG)

    # Route complex questions to AI (comparisons, recommendations, etc.)
    if use_ai and AI_READY and is_complex_query(user_msg):
        return ask_gemini(user_msg, st.session_state.get("messages", []))

    # Try rule-based matching
    intent = match_intent(user_msg)

    if intent is not None:
        intent_data = INTENTS[intent]

        if intent_data.get("reset_chat"):
            st.session_state.messages = [
                {"role": BOT_NAME, "content": WELCOME_MSG}
            ]

        return intent_data["response"]

    # No rule-based match → try AI
    if use_ai and AI_READY:
        return ask_gemini(user_msg, st.session_state.get("messages", []))

    return FALLBACK_MSG


# ──────────────────────────────────────────────
# Streamlit chat UI
# ──────────────────────────────────────────────

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.chat_title = "New Chat"

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": WELCOME_MSG, "avatar": "🤖"}
    ]
    # Save the initial welcome message immediately
    save_session(current_user_id, st.session_state.session_id, st.session_state.chat_title, st.session_state.messages)

# Display chat history
for msg in st.session_state.messages:
    avatar = msg.get("avatar") or ("🤖" if msg["role"] == "assistant" else "🧑‍💻")
    with st.chat_message(msg["role"], avatar=avatar):
        # Clean up any legacy prefix for cleaner UI
        content = msg["content"].replace("**Cognix:** ", "")
        st.markdown(content)

# User input widget
user_input = st.chat_input("Type your question here...")

if "pill_input" not in st.session_state:
    st.session_state.pill_input = None

# Intercept pill selection and map it to user_input
if st.session_state.pill_input:
    user_input = st.session_state.pill_input
    st.session_state.pill_input = None

# Process new user input
if user_input:
    # Update title based on first query
    if st.session_state.chat_title == "New Chat":
        st.session_state.chat_title = user_input[:20] + "..." if len(user_input) > 20 else user_input

    st.session_state.messages.append({"role": "user", "content": user_input, "avatar": "🧑‍💻"})

    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(user_input)

    # Show a spinner while generating AI responses
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking..."):
            response = chatbot_reply(user_input, use_ai=use_ai_toggle)
            # Remove legacy prefix if present for cleaner bubble
            clean_response = response.replace("**Cognix:** ", "").strip()
        st.markdown(clean_response)

    st.session_state.messages.append({"role": "assistant", "content": clean_response, "avatar": "🤖"})

    # Save to database
    save_session(current_user_id, st.session_state.session_id, st.session_state.chat_title, st.session_state.messages)

# ──────────────────────────────────────────────
# Quick Options / Default Buttons (Rendered last to stay at bottom)
# ──────────────────────────────────────────────
def handle_pill():
    if st.session_state.quick_option:
        st.session_state.pill_input = st.session_state.quick_option
        st.session_state.quick_option = None

quick_options = [
    "💼 Internship Opportunities",
    "📂 Project Guidelines",
    "🎓 Certificates",
    "🪄 Application Process",
    "🛟 Support"
]

# Hidden marker to anchor the CSS tightly to the exact next element (the pills)
st.markdown('<div class="pill-marker"></div>', unsafe_allow_html=True)

st.pills(
    "Quick Options",
    quick_options,
    label_visibility="collapsed",
    key="quick_option",
    on_change=handle_pill
)
