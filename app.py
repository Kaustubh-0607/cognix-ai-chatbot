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
import csv
import io
import time
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
        except sqlite3.OperationalError: pass
        
        try:
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN admin_rating INTEGER")
        except sqlite3.OperationalError: pass
        
        try:
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN true_intent_label TEXT")
        except sqlite3.OperationalError: pass
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT,
                name TEXT,
                last_login DATETIME
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS message_logs (
                log_id      TEXT PRIMARY KEY,
                session_id  TEXT,
                user_id     TEXT,
                user_message TEXT,
                detected_intent TEXT,
                response_type   TEXT,
                timestamp   DATETIME
            )
        ''')
        conn.commit()

def save_user(user_id, email, name):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            INSERT INTO users (user_id, email, name, last_login)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                email = excluded.email,
                name = excluded.name,
                last_login = excluded.last_login
        ''', (user_id, email, name, datetime.now().isoformat()))
        conn.commit()

def save_admin_rating(session_id, rating, label):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('UPDATE chat_sessions SET admin_rating = ?, true_intent_label = ? WHERE session_id = ?', 
                     (rating, label, session_id))
        conn.commit()

def get_all_sessions_for_admin():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.session_id, c.title, c.messages, c.updated_at, c.admin_rating, c.true_intent_label, 
                   u.name, u.email 
            FROM chat_sessions c
            LEFT JOIN users u ON c.user_id = u.user_id
            ORDER BY c.updated_at DESC
        ''')
        return cursor.fetchall()

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
# Message Logging & Analytics DB Helpers
# ──────────────────────────────────────────────
def log_message(session_id, user_id, user_message, detected_intent, response_type):
    """Log each user message with intent + response type for analytics."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            INSERT INTO message_logs (log_id, session_id, user_id, user_message, detected_intent, response_type, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (str(uuid.uuid4()), session_id, user_id, user_message,
              detected_intent, response_type, datetime.now().isoformat()))
        conn.commit()

def get_analytics_summary():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute('SELECT COUNT(DISTINCT user_id) as n FROM users')
        total_users = cur.fetchone()['n']
        cur.execute('SELECT COUNT(*) as n FROM message_logs')
        total_msgs = cur.fetchone()['n']
        cur.execute("SELECT COUNT(*) as n FROM message_logs WHERE response_type = 'fallback'")
        fallbacks = cur.fetchone()['n']
        cur.execute('SELECT AVG(c) as a FROM (SELECT COUNT(*) as c FROM message_logs GROUP BY session_id)')
        avg_len = cur.fetchone()['a'] or 0
        return {'total_users': total_users, 'total_messages': total_msgs,
                'fallback_rate': round(fallbacks / max(total_msgs, 1) * 100, 1),
                'avg_session_length': round(avg_len, 1)}

def get_intent_distribution():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT detected_intent, COUNT(*) as cnt FROM message_logs
            WHERE detected_intent IS NOT NULL
            GROUP BY detected_intent ORDER BY cnt DESC LIMIT 10
        ''')
        return cur.fetchall()

def get_response_type_distribution():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute('SELECT response_type, COUNT(*) as cnt FROM message_logs GROUP BY response_type')
        return cur.fetchall()

def get_daily_activity(days=14):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT DATE(timestamp) as day, COUNT(*) as cnt FROM message_logs
            WHERE timestamp >= DATE('now', ?)
            GROUP BY DATE(timestamp) ORDER BY day
        ''', (f'-{days} days',))
        return cur.fetchall()

def get_hourly_activity():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT CAST(strftime('%H', timestamp) AS INTEGER) as hr, COUNT(*) as cnt
            FROM message_logs GROUP BY hr ORDER BY hr
        ''')
        return cur.fetchall()

def get_fallback_queries(limit=20):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT user_message, COUNT(*) as cnt FROM message_logs
            WHERE response_type = 'fallback'
            GROUP BY LOWER(user_message) ORDER BY cnt DESC LIMIT ?
        ''', (limit,))
        return cur.fetchall()

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
        
        # Exponential backoff retry logic for 503 (Unavailable) and 429 (Too Many Requests)
        max_retries = 3
        base_delay = 2 # seconds
        
        for attempt in range(max_retries):
            try:
                response = chat.send_message(user_msg)
                return response.text
            except Exception as api_error:
                error_str = str(api_error)
                # Check if it's a rate limit or server unavailable error
                if ("503" in error_str or "429" in error_str or "UNAVAILABLE" in error_str) and attempt < max_retries - 1:
                    time.sleep(base_delay * (2 ** attempt)) # Waits 2s, then 4s, etc.
                    continue
                else:
                    # If it's a different error or we are out of retries, throw it to the outer except block
                    raise api_error

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
ADMIN_EMAILS = [email.strip() for email in os.getenv("ADMIN_EMAILS", "").split(",") if email.strip()]

def get_redirect_uri():
    """Auto-detect the correct redirect URI from the current request host.
    Works on localhost (any port) and production (Replit, etc.) automatically.
    """
    try:
        host = st.context.headers.get("Host", "")
        if host:
            # Use HTTPS for known production domains, HTTP for localhost
            is_secure = not host.startswith("localhost") and not host.startswith("127.0.0.1")
            scheme = "https" if is_secure else "http"
            return f"{scheme}://{host}/"
    except Exception:
        pass
    # Fallback to .env value if header detection fails
    return os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:3000/")

def get_login_url():
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": get_redirect_uri(),
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
            "redirect_uri": get_redirect_uri(),
            "grant_type": "authorization_code"
        }
        res = requests.post(token_url, data=payload)
        st.query_params.clear()
        
        if res.status_code == 200:
            access_token = res.json().get("access_token")
            user_res = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"})
            if user_res.status_code == 200:
                user_data = user_res.json()
                st.session_state.user = user_data
                save_user(user_data.get("id"), user_data.get("email"), user_data.get("name"))
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
current_user_email = st.session_state.user.get("email", "")
is_admin = current_user_email in ADMIN_EMAILS

if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"

# Sidebar: Database & AI status
with st.sidebar:
    st.markdown(f"### 👋 Welcome, {st.session_state.user.get('given_name', 'User')}!")
    if st.button("Logout", help="Sign out of your account"):
        del st.session_state["user"]
        st.rerun()
    st.divider()

    if is_admin:
        if st.button("🛠️ Admin Dashboard", type="secondary" if st.session_state.current_page == "chat" else "primary", use_container_width=True):
            st.session_state.current_page = "admin" if st.session_state.current_page == "chat" else "chat"
            st.rerun()
        st.divider()

    if st.button("➕ New Chat", type="primary", use_container_width=True):
        st.session_state.current_page = "chat"
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
            st.info("⚡ AI Mode: **OFF**")
            st.caption("Operating in fast rule-based mode only.")
    else:
        st.warning("⚠️ AI Mode unavailable (Check API Key).")
        st.caption("Operating in rule-based mode.")
        use_ai_toggle = False
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


def match_intent_with_scores(user_msg: str) -> dict:
    """Return a confidence score (0.0–1.0) for EVERY intent.
    Used as probability estimates for ROC/AUC computation.
    """
    msg = user_msg.lower().strip()
    scores = {key: 0.0 for key in INTENTS}

    for intent_key, intent_data in INTENTS.items():
        keywords = intent_data["keywords"]
        best = 0

        for kw in keywords:
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, msg):
                best = max(best, 100 + len(kw))

        msg_tokens = {t for t in msg.split() if len(t) >= MIN_TOKEN_LEN}
        for kw in keywords:
            kw_tokens = {t for t in kw.split() if len(t) >= MIN_TOKEN_LEN}
            if kw_tokens:
                overlap = msg_tokens & kw_tokens
                if overlap:
                    best = max(best, int((len(overlap) / len(kw_tokens)) * 90))

        _, fscore = process.extractOne(msg, keywords, scorer=fuzz.token_sort_ratio)
        best = max(best, fscore)
        scores[intent_key] = min(best / 120.0, 1.0)  # normalise to [0, 1]

    return scores


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
# Admin Portal — 4-Tab Analytics Dashboard
# ──────────────────────────────────────────────
if st.session_state.current_page == "admin" and is_admin:
    st.markdown("## 🛠️ Admin Analytics Dashboard")

    try:
        import plotly.express as px
        import plotly.graph_objects as go
        import pandas as pd
        import numpy as np
        from sklearn.preprocessing import label_binarize
        from sklearn.metrics import (
            roc_curve, auc, accuracy_score,
            precision_score, recall_score, f1_score, confusion_matrix
        )
        ANALYTICS_READY = True
    except ImportError:
        ANALYTICS_READY = False
        st.warning("⚠️ Run: `pip install plotly scikit-learn numpy pandas` to enable analytics charts.")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📈 Live Analytics", "🎯 Live Evaluation", "🔬 Benchmark + ROC/AUC", "🗂️ Sessions"]
    )

    # ════════════════════════════════════════════════════
    # TAB 1 — LIVE ANALYTICS
    # ════════════════════════════════════════════════════
    with tab1:
        stats = get_analytics_summary()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("👥 Total Users",       stats['total_users'])
        c2.metric("💬 Total Messages",    stats['total_messages'])
        c3.metric("❌ Fallback Rate",      f"{stats['fallback_rate']}%")
        c4.metric("📊 Avg Session Length", f"{stats['avg_session_length']} msgs")
        st.divider()

        if not ANALYTICS_READY:
            st.info("Install analytics packages to view charts.")
        elif stats['total_messages'] == 0:
            st.info("No messages logged yet. Start chatting to populate analytics!")
        else:
            col_a, col_b = st.columns(2)
            with col_a:
                rt = get_response_type_distribution()
                if rt:
                    df_rt = pd.DataFrame(rt, columns=['Type', 'Count'])
                    cmap = {'rule': '#4CAF50', 'ai': '#2196F3', 'fallback': '#FF5722'}
                    fig = px.pie(df_rt, values='Count', names='Type',
                                 title='🔄 Response Type Distribution',
                                 color='Type', color_discrete_map=cmap, hole=0.4)
                    fig.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig, use_container_width=True)
            with col_b:
                idata = get_intent_distribution()
                if idata:
                    df_i = pd.DataFrame(idata, columns=['Intent', 'Count'])
                    fig = px.bar(df_i, x='Count', y='Intent', orientation='h',
                                 title='🏆 Top 10 Detected Intents',
                                 color='Count', color_continuous_scale='Viridis')
                    fig.update_layout(yaxis={'categoryorder': 'total ascending'})
                    st.plotly_chart(fig, use_container_width=True)

            col_c, col_d = st.columns(2)
            with col_c:
                daily = get_daily_activity()
                if daily:
                    df_d = pd.DataFrame(daily, columns=['Date', 'Messages'])
                    fig = px.line(df_d, x='Date', y='Messages',
                                  title='📅 Daily Message Volume (Last 14 Days)',
                                  markers=True, color_discrete_sequence=['#7C3AED'])
                    fig.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)
            with col_d:
                hourly = get_hourly_activity()
                if hourly:
                    df_h = pd.DataFrame(hourly, columns=['Hour', 'Count'])
                    all_h = pd.DataFrame({'Hour': range(24)})
                    df_h = all_h.merge(df_h, on='Hour', how='left').fillna(0)
                    fig = px.bar(df_h, x='Hour', y='Count',
                                 title='🕐 Activity by Hour of Day',
                                 color='Count', color_continuous_scale='Sunset')
                    fig.update_layout(xaxis_tickmode='linear')
                    st.plotly_chart(fig, use_container_width=True)

            st.markdown("### ❓ Unrecognised Queries — Help Improve Intents")
            fq = get_fallback_queries()
            if fq:
                st.dataframe(pd.DataFrame(fq, columns=['User Query', 'Frequency']),
                             use_container_width=True, hide_index=True)
            else:
                st.success("🎉 No fallback queries yet!")

    # ════════════════════════════════════════════════════
    # TAB 2 — LIVE EVALUATION (from predefined benchmark queries)
    # ════════════════════════════════════════════════════
    with tab2:
        st.markdown("### 🎯 Live Evaluation — Predefined Benchmark Queries")
        st.caption("Evaluates the rule-based engine against **benchmark_queries.json** in real-time.")

        BENCH_PATH_T2 = Path(__file__).parent / "evaluation" / "benchmark_queries.json"
        if not BENCH_PATH_T2.exists():
            st.error("benchmark_queries.json not found in evaluation/")
        elif not ANALYTICS_READY:
            st.info("Install analytics packages to view charts.")
        else:
            bench_data = json.loads(BENCH_PATH_T2.read_text(encoding='utf-8'))
            bm_queries = [d['query'] for d in bench_data]
            bm_gold    = [d['label']  for d in bench_data]
            bm_types   = [d.get('type', 'unknown') for d in bench_data]
            bm_labels  = sorted(set(bm_gold))

            # Rule-only predictions on benchmark
            bm_preds = [match_intent(q) or '__fallback__' for q in bm_queries]

            acc  = accuracy_score(bm_gold, bm_preds)
            prec = precision_score(bm_gold, bm_preds, average='macro', zero_division=0, labels=bm_labels)
            rec  = recall_score(bm_gold, bm_preds,    average='macro', zero_division=0, labels=bm_labels)
            f1v  = f1_score(bm_gold, bm_preds,        average='macro', zero_division=0, labels=bm_labels)

            st.info(f"**{len(bench_data)}** benchmark queries  |  **{len(bm_labels)}** intent classes")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("✅ Accuracy",  f"{acc*100:.1f}%")
            m2.metric("🎯 Precision", f"{prec*100:.1f}%")
            m3.metric("📡 Recall",    f"{rec*100:.1f}%")
            m4.metric("⚖️ F1 Score",  f"{f1v*100:.1f}%")
            st.divider()

            # ── Per-type accuracy breakdown ──
            st.markdown("#### 📋 Accuracy by Query Type")
            type_rows = []
            for qtype in sorted(set(bm_types)):
                idxs = [i for i, t in enumerate(bm_types) if t == qtype]
                t_gold = [bm_gold[i] for i in idxs]
                t_pred = [bm_preds[i] for i in idxs]
                t_acc = accuracy_score(t_gold, t_pred)
                type_rows.append({'Type': qtype.title(), 'Queries': len(idxs), 'Accuracy': f"{t_acc*100:.1f}%"})
            st.dataframe(pd.DataFrame(type_rows), use_container_width=True, hide_index=True)
            st.divider()

            # ── F1 per intent ──
            f1_per = f1_score(bm_gold, bm_preds, average=None, zero_division=0, labels=bm_labels)
            df_f1 = pd.DataFrame({'Intent': bm_labels, 'F1 Score': f1_per})
            fig = px.bar(df_f1, x='Intent', y='F1 Score',
                         title='F1 Score per Intent (Benchmark — Rule Engine)',
                         color='F1 Score', color_continuous_scale='RdYlGn', range_color=[0, 1])
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

            # ── Confusion matrix ──
            cm = confusion_matrix(bm_gold, bm_preds, labels=bm_labels)
            fig_cm = px.imshow(cm, x=bm_labels, y=bm_labels,
                               title='Confusion Matrix (Benchmark — Rule Engine)',
                               labels=dict(x='Predicted', y='True', color='Count'),
                               color_continuous_scale='Blues', text_auto=True)
            fig_cm.update_layout(height=600, xaxis_tickangle=-45)
            st.plotly_chart(fig_cm, use_container_width=True)

            # ── Misclassified queries table ──
            st.markdown("#### ❌ Misclassified Queries")
            misses = [{'Query': bm_queries[i], 'True': bm_gold[i], 'Predicted': bm_preds[i], 'Type': bm_types[i]}
                      for i in range(len(bm_queries)) if bm_gold[i] != bm_preds[i]]
            if misses:
                st.dataframe(pd.DataFrame(misses), use_container_width=True, hide_index=True)
            else:
                st.success("🎉 All benchmark queries classified correctly!")

    # ════════════════════════════════════════════════════
    # TAB 3 — BENCHMARK EVALUATION + ROC/AUC
    # ════════════════════════════════════════════════════
    with tab3:
        st.markdown("### 🔬 Benchmark Evaluation on Known Queries")

        BENCHMARK_PATH = Path(__file__).parent / "evaluation" / "benchmark_queries.json"
        RESULTS_PATH   = Path(__file__).parent / "evaluation" / "latest_results.json"

        # ── Inner helpers (defined once per render) ──────────
        def _build_rule_score_matrix(queries, classes):
            import numpy as _np
            matrix = []
            for q in queries:
                sc = match_intent_with_scores(q)
                matrix.append([sc.get(c, 0.0) for c in classes])
            return _np.array(matrix)

        def _one_hot(preds, classes):
            import numpy as _np
            m = []
            for p in preds:
                m.append([1.0 if c == p else 0.0 for c in classes])
            return _np.array(m)

        def _compute_roc(y_bin, prob_matrix, classes):
            import numpy as _np
            curves, aucs = {}, {}
            for i, cls in enumerate(classes):
                if y_bin[:, i].sum() == 0:
                    continue
                fpr, tpr, _ = roc_curve(y_bin[:, i], prob_matrix[:, i])
                curves[cls] = (fpr.tolist(), tpr.tolist())
                aucs[cls]   = round(float(auc(fpr, tpr)), 4)
            # macro-average ROC
            all_fpr  = _np.unique(_np.concatenate([curves[c][0] for c in curves]))
            mean_tpr = _np.zeros_like(all_fpr)
            for cls in curves:
                mean_tpr += _np.interp(all_fpr, curves[cls][0], curves[cls][1])
            mean_tpr /= len(curves)
            macro_auc = round(float(_np.mean(list(aucs.values()))), 4) if aucs else 0.0
            return curves, aucs, macro_auc, all_fpr.tolist(), mean_tpr.tolist()

        def _plot_roc(curves, aucs, macro_auc, macro_fpr, macro_tpr, title):
            colors = (px.colors.qualitative.Plotly +
                      px.colors.qualitative.D3 +
                      px.colors.qualitative.Safe)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[0,1], y=[0,1], mode='lines',
                                     line=dict(dash='dash', color='gray', width=1),
                                     name='Random (AUC=0.50)'))
            for idx, (cls, (fpr, tpr)) in enumerate(curves.items()):
                fig.add_trace(go.Scatter(x=fpr, y=tpr, mode='lines',
                                         name=f'{cls} (AUC={aucs[cls]:.2f})',
                                         line=dict(color=colors[idx % len(colors)], width=1.5),
                                         opacity=0.75))
            fig.add_trace(go.Scatter(x=macro_fpr, y=macro_tpr, mode='lines',
                                     name=f'Macro Avg (AUC={macro_auc:.3f})',
                                     line=dict(color='black', width=3, dash='dot')))
            fig.update_layout(
                title=title,
                xaxis_title='False Positive Rate', yaxis_title='True Positive Rate',
                height=580, xaxis=dict(range=[0,1]), yaxis=dict(range=[0,1]),
                legend=dict(font=dict(size=9), x=1.0, y=0)
            )
            return fig

        # ── Load saved results ────────────────────────────────
        saved = None
        if RESULTS_PATH.exists():
            saved = json.loads(RESULTS_PATH.read_text(encoding='utf-8'))

        btn_col, info_col = st.columns([1, 3])
        with btn_col:
            run_btn = st.button("▶ Run Benchmark Evaluation", type="primary", use_container_width=True)
        with info_col:
            if saved and 'timestamp' in saved:
                st.info(f"Last run: **{saved['timestamp'][:19]}**  |  "
                        f"{saved.get('n_samples','?')} samples, {saved.get('n_labels','?')} classes")
            else:
                st.info("No results yet. Click **▶ Run Benchmark Evaluation** to start.")

        if run_btn:
            if not ANALYTICS_READY:
                st.error("Install `plotly scikit-learn numpy pandas` first!")
            elif not BENCHMARK_PATH.exists():
                st.error("benchmark_queries.json not found in evaluation/")
            else:
                with st.spinner("Running… (may take 30–60 s if AI mode is enabled)"):
                    dataset = json.loads(BENCHMARK_PATH.read_text(encoding='utf-8'))
                    queries = [d['query'] for d in dataset]
                    gold    = [d['label']  for d in dataset]
                    qtypes  = [d.get('type', 'unknown') for d in dataset]
                    classes = sorted(set(gold))
                    y_bin   = label_binarize(gold, classes=classes)

                    # Rule-only
                    rule_preds    = [match_intent(q) or '__fallback__' for q in queries]
                    rule_acc      = accuracy_score(gold, rule_preds)
                    rule_prec     = precision_score(gold, rule_preds, average='macro', zero_division=0, labels=classes)
                    rule_rec      = recall_score(   gold, rule_preds, average='macro', zero_division=0, labels=classes)
                    rule_f1       = f1_score(       gold, rule_preds, average='macro', zero_division=0, labels=classes)
                    rule_smat     = _build_rule_score_matrix(queries, classes)
                    rc, ra, rmauc, rmfpr, rmtpr = _compute_roc(y_bin, rule_smat, classes)

                    new_saved = {
                        'timestamp': datetime.now().isoformat(),
                        'n_samples': len(dataset), 'n_labels': len(classes),
                        'classes': classes, 'gold': gold, 'query_types': qtypes,
                        'rule_only': {
                            'accuracy': round(rule_acc*100, 2),
                            'precision': round(rule_prec*100, 2),
                            'recall': round(rule_rec*100, 2),
                            'f1': round(rule_f1*100, 2),
                            'predictions': rule_preds, 'macro_auc': rmauc,
                            'roc_curves': rc, 'auc_scores': ra,
                            'macro_fpr': rmfpr, 'macro_tpr': rmtpr,
                        }
                    }

                    # LLM + Hybrid (only if AI is ready)
                    if AI_READY:
                        try:
                            from google.genai import types as _gt
                            import re as _re
                            intent_desc = "\n".join(
                                [f"- {k}: {', '.join(INTENTS[k]['keywords'][:5])}" for k in classes]
                            )
                            qblock = "\n".join([f"{i+1}. {q}" for i, q in enumerate(queries)])
                            prompt = (
                                "Classify each query into exactly one intent key from this list.\n"
                                'Return STRICT JSON only: {"predictions": [{"id": 1, "intent": "..."}, ...]}\n\n'
                                f"Valid intents:\n{intent_desc}\n\nQueries:\n{qblock}"
                            )
                            resp = gemini_client.models.generate_content(
                                model=GEMINI_MODEL,
                                config=_gt.GenerateContentConfig(temperature=0),
                                contents=prompt
                            )
                            m = _re.search(r'\{[\s\S]*\}', resp.text or '')
                            obj = json.loads(m.group(0))
                            pm = {int(x['id']): x['intent'] for x in obj.get('predictions', [])}
                            llm_preds = [pm.get(i+1, '__fallback__') for i in range(len(queries))]

                            hybrid_preds = [
                                lp if is_complex_query(q)
                                else (rp if rp != '__fallback__' else lp)
                                for q, rp, lp in zip(queries, rule_preds, llm_preds)
                            ]

                            for mode_name, preds in [('llm_only', llm_preds), ('hybrid', hybrid_preds)]:
                                acc  = accuracy_score( gold, preds)
                                prec = precision_score(gold, preds, average='macro', zero_division=0, labels=classes)
                                rec  = recall_score(   gold, preds, average='macro', zero_division=0, labels=classes)
                                f1v  = f1_score(       gold, preds, average='macro', zero_division=0, labels=classes)
                                pm2  = _one_hot(preds, classes)
                                c2, a2, mauc2, mfpr2, mtpr2 = _compute_roc(y_bin, pm2, classes)
                                new_saved[mode_name] = {
                                    'accuracy': round(acc*100, 2),
                                    'precision': round(prec*100, 2),
                                    'recall': round(rec*100, 2),
                                    'f1': round(f1v*100, 2),
                                    'predictions': preds, 'macro_auc': mauc2,
                                    'roc_curves': c2, 'auc_scores': a2,
                                    'macro_fpr': mfpr2, 'macro_tpr': mtpr2,
                                }
                        except Exception as llm_err:
                            st.warning(f"LLM evaluation skipped: {llm_err}")

                    RESULTS_PATH.write_text(json.dumps(new_saved, indent=2), encoding='utf-8')
                    saved = new_saved
                st.success("✅ Benchmark evaluation complete!")
                st.rerun()

        # ── Display results ───────────────────────────────────
        if saved and ANALYTICS_READY:
            st.divider()
            modes_avail   = [m for m in ['rule_only', 'llm_only', 'hybrid'] if m in saved]
            mode_labels_m = {'rule_only': '⚡ Rule-only', 'llm_only': '🧠 LLM-only', 'hybrid': '🔀 Hybrid'}

            # Metric cards
            st.markdown("#### 📊 Performance Metrics")
            mcols = st.columns(len(modes_avail))
            for col, mode in zip(mcols, modes_avail):
                d = saved[mode]
                with col:
                    st.markdown(f"**{mode_labels_m[mode]}**")
                    st.metric("Accuracy",   f"{d.get('accuracy','?')}%")
                    st.metric("Precision",  f"{d.get('precision','?')}%")
                    st.metric("Recall",     f"{d.get('recall','?')}%")
                    st.metric("F1 Score",   f"{d.get('f1','?')}%")
                    if 'macro_auc' in d:
                        st.metric("Macro AUC", f"{d['macro_auc']:.3f}")

            # Per-type accuracy breakdown
            qtypes_saved = saved.get('query_types')
            if qtypes_saved:
                st.divider()
                st.markdown("#### 📋 Accuracy by Query Type")
                type_table_rows = []
                for qtype in sorted(set(qtypes_saved)):
                    idxs = [i for i, t in enumerate(qtypes_saved) if t == qtype]
                    row = {'Type': qtype.title(), 'Queries': len(idxs)}
                    for mode in modes_avail:
                        mp = saved[mode].get('predictions', [])
                        if mp:
                            g = [saved['gold'][i] for i in idxs]
                            p = [mp[i] for i in idxs]
                            row[mode_labels_m[mode]] = f"{accuracy_score(g, p)*100:.1f}%"
                    type_table_rows.append(row)
                st.dataframe(pd.DataFrame(type_table_rows), use_container_width=True, hide_index=True)

            # Grouped bar chart
            st.divider()
            st.markdown("#### 📈 Metric Comparison Chart")
            bar_rows = []
            for mode in modes_avail:
                d = saved[mode]
                for metric in ['accuracy', 'precision', 'recall', 'f1']:
                    bar_rows.append({'Mode': mode_labels_m[mode], 'Metric': metric.title(), 'Score': d.get(metric, 0)})
            fig_bar = px.bar(
                pd.DataFrame(bar_rows), x='Metric', y='Score', color='Mode', barmode='group',
                title='Accuracy / Precision / Recall / F1 — All Modes',
                color_discrete_sequence=['#4CAF50', '#2196F3', '#FF9800'],
                range_y=[0, 100]
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            # Macro AUC comparison
            auc_rows = [{'Mode': mode_labels_m[m], 'Macro AUC': saved[m]['macro_auc']}
                        for m in modes_avail if 'macro_auc' in saved[m]]
            if len(auc_rows) > 1:
                st.divider()
                st.markdown("#### 🏆 Macro AUC Comparison")
                df_auc = pd.DataFrame(auc_rows)
                fig_auc = px.bar(df_auc, x='Mode', y='Macro AUC',
                                 title='Macro-Averaged AUC — Rule / LLM / Hybrid',
                                 color='Mode',
                                 color_discrete_sequence=['#4CAF50', '#2196F3', '#FF9800'],
                                 range_y=[0.5, 1.0], text='Macro AUC')
                fig_auc.update_traces(texttemplate='%{text:.3f}', textposition='outside')
                st.plotly_chart(fig_auc, use_container_width=True)

            # ROC Curves
            st.divider()
            st.markdown("#### 📉 ROC Curves (One-vs-Rest, per Intent Class)")
            roc_mode_opts = [m for m in modes_avail if 'roc_curves' in saved.get(m, {})]
            if roc_mode_opts:
                sel_mode = st.selectbox(
                    "Select mode to view ROC curves:",
                    options=roc_mode_opts,
                    format_func=lambda x: mode_labels_m[x]
                )
                md = saved[sel_mode]
                fig_roc = _plot_roc(
                    md['roc_curves'], md['auc_scores'], md['macro_auc'],
                    md['macro_fpr'], md['macro_tpr'],
                    f"ROC Curves — {mode_labels_m[sel_mode]}"
                )
                st.plotly_chart(fig_roc, use_container_width=True)

                st.markdown("#### 🏅 AUC Per Intent Class")
                df_auc_tbl = pd.DataFrame(
                    [{'Intent': k, 'AUC': v} for k, v in md['auc_scores'].items()]
                ).sort_values('AUC', ascending=False)
                st.dataframe(df_auc_tbl, use_container_width=True, hide_index=True)

    # ════════════════════════════════════════════════════
    # TAB 4 — SESSION INSPECTOR
    # ════════════════════════════════════════════════════
    with tab4:
        st.markdown("### 🗂️ Session Inspector & Manual Labeling")
        raw_sessions = get_all_sessions_for_admin()
        if not raw_sessions:
            st.info("No chat sessions found.")
        else:
            csv_buffer = io.StringIO()
            csv_writer = csv.writer(csv_buffer)
            csv_writer.writerow(["Session ID", "User Email", "User Name", "Title",
                                  "Updated At", "Admin Rating", "True Intent Label", "Messages (JSON)"])
            for s in raw_sessions:
                csv_writer.writerow([s['session_id'], s['email'], s['name'], s['title'],
                                     s['updated_at'], s['admin_rating'], s['true_intent_label'], s['messages']])
            st.download_button(
                "📊 Download Dataset (CSV)", data=csv_buffer.getvalue(),
                file_name=f"chatbot_analytics_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv", type="primary"
            )
            st.divider()

            session_opts = {
                s['session_id']: f"{s['updated_at'][:16]} | {s['email']} — {s['title'][:30]}"
                for s in raw_sessions
            }
            selected_sid = st.selectbox(
                "Select a session to review:",
                options=list(session_opts.keys()),
                format_func=lambda x: session_opts[x]
            )
            if selected_sid:
                sel = next(s for s in raw_sessions if s['session_id'] == selected_sid)
                with st.expander("🔍 Chat Transcript", expanded=True):
                    for m in json.loads(sel['messages']):
                        st.markdown(f"**{m['role'].title()}:** {m['content']}")
                st.markdown("#### ✍️ Evaluate This Session")
                with st.form("evaluation_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        rating = st.slider("Rating (1=Poor → 5=Excellent)", 1, 5, sel['admin_rating'] or 3)
                    with col2:
                        base_opts = ["None (Unlabeled)", "General Inquiry", "AI Handled"]
                        intent_opts = sorted(INTENTS.keys())
                        label_options = list(dict.fromkeys(base_opts + intent_opts))
                        cur_label = sel['true_intent_label'] if sel['true_intent_label'] in label_options else "None (Unlabeled)"
                        label = st.selectbox("True Intent (Ground Truth)", label_options,
                                             index=label_options.index(cur_label))
                    if st.form_submit_button("💾 Save Evaluation"):
                        save_admin_rating(selected_sid, rating, label)
                        st.success("Evaluation saved!")
                        st.rerun()

    st.stop()  # Prevent chat UI from rendering


# ──────────────────────────────────────────────
# Chatbot reply (hybrid: rule-based → AI fallback)
# ──────────────────────────────────────────────
def chatbot_reply(user_msg: str, use_ai: bool = False):
    """
    Return (response_text, detected_intent, response_type).
    response_type: 'rule' | 'ai' | 'fallback'
    """
    msg_lower = user_msg.lower().strip()

    if "main menu" in msg_lower or msg_lower == "menu":
        intent_data = INTENTS.get("main_menu", {})
        if intent_data.get("reset_chat"):
            st.session_state.messages = [{"role": BOT_NAME, "content": WELCOME_MSG}]
        return intent_data.get("response", WELCOME_MSG), "main_menu", "rule"

    if use_ai and AI_READY and is_complex_query(user_msg):
        return ask_gemini(user_msg, st.session_state.get("messages", [])), None, "ai"

    intent = match_intent(user_msg)
    if intent is not None:
        intent_data = INTENTS[intent]
        if intent_data.get("reset_chat"):
            st.session_state.messages = [{"role": BOT_NAME, "content": WELCOME_MSG}]
        return intent_data["response"], intent, "rule"

    if use_ai and AI_READY:
        return ask_gemini(user_msg, st.session_state.get("messages", [])), None, "ai"

    return FALLBACK_MSG, None, "fallback"


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
            response, detected_intent, response_type = chatbot_reply(user_input, use_ai=use_ai_toggle)
            clean_response = response.replace("**Cognix:** ", "").strip()
        st.markdown(clean_response)

    # Log message for analytics
    log_message(st.session_state.session_id, current_user_id, user_input, detected_intent, response_type)

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
