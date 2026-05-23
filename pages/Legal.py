"""
Cognix — Legal Information Page
Publicly accessible; no authentication required.
Route: /Legal  (Streamlit multi-page routing)
"""

import os
from pathlib import Path
import streamlit as st

st.set_page_config(
    page_title="Cognix Legal Information",
    page_icon="⚖️",
    layout="wide",
)

# ── Load shared CSS ──────────────────────────────────────────────────────
_css_path = Path(__file__).parent.parent / "style.css"
try:
    with open(_css_path) as _f:
        st.markdown(f"<style>{_f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    pass

# ── Matching sidebar ─────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-icon">🤖</div>
            <div class="sidebar-brand-text">
                <div class="sidebar-brand-title">Cognix</div>
                <div class="sidebar-brand-sub">AI Internship Assistant</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div class='sidebar-hr'></div>", unsafe_allow_html=True)

    # APP section
    st.markdown("<div class='sidebar-section-label'>APP</div>", unsafe_allow_html=True)
    st.markdown(
        '<a href="/" target="_self" class="sidebar-nav-item" style="text-decoration:none;">💬 Chat</a>',
        unsafe_allow_html=True,
    )

    st.markdown("<div class='sidebar-hr'></div>", unsafe_allow_html=True)

    # LEGAL section — highlighted as active on this page
    st.markdown("<div class='sidebar-section-label'>LEGAL</div>", unsafe_allow_html=True)
    st.markdown(
        '<a href="./Legal" target="_self" class="sidebar-nav-item sidebar-nav-active" style="text-decoration:none;">⚖️ Legal</a>',
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div class='sidebar-footer'>© 2026 Cognix AI Intelligence</div>",
        unsafe_allow_html=True,
    )

# SEO meta tags
st.markdown(
    """
    <head>
        <meta name="description" content="Terms &amp; Conditions, Privacy Policy, and Disclaimer for Cognix." />
        <meta name="robots" content="index, follow" />
    </head>
    """,
    unsafe_allow_html=True,
)


LEGAL_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cognix Legal Information</title>
    <style>
        /* Reset any Streamlit container padding that bleeds in */
        .legal-wrap * { box-sizing: border-box; }

        .legal-wrap {
            font-family: Arial, sans-serif;
            background-color: #0f172a;
            color: #e2e8f0;
            line-height: 1.8;
            padding: 0;
            margin: 0;
        }

        .legal-container {
            max-width: 900px;
            margin: auto;
            padding: 40px 20px;
        }

        .legal-wrap h1 {
            text-align: center;
            color: #38bdf8;
            font-size: 2rem;
            margin-bottom: 0.4rem;
        }

        .legal-wrap .subtitle {
            text-align: center;
            margin-bottom: 30px;
            color: #94a3b8;
        }

        .legal-wrap .section {
            background: #1e293b;
            padding: 30px;
            margin-bottom: 25px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        }

        .legal-wrap h2 {
            color: #38bdf8;
            margin-bottom: 15px;
        }

        .legal-wrap p {
            margin-bottom: 15px;
        }

        .legal-wrap a {
            color: #38bdf8;
            text-decoration: none;
        }

        .legal-wrap a:hover {
            text-decoration: underline;
        }

        .legal-wrap footer {
            text-align: center;
            margin-top: 40px;
            color: #94a3b8;
        }

        .legal-wrap .highlight {
            color: #facc15;
        }

        /* ── Responsive ── */
        @media (max-width: 768px) {
            .legal-container { padding: 24px 14px; }
            .legal-wrap h1   { font-size: 1.5rem; }
            .legal-wrap .section { padding: 20px 16px; }
        }

        @media (max-width: 480px) {
            .legal-wrap h1 { font-size: 1.25rem; }
            .legal-wrap .section { padding: 16px 12px; border-radius: 8px; }
        }
    </style>
</head>
<body>
<div class="legal-wrap">
<div class="legal-container">

    <h1>Cognix Legal Information</h1>
    <p class="subtitle">Terms &amp; Conditions &bull; Privacy Policy &bull; Disclaimer</p>

    <!-- TERMS & CONDITIONS -->
    <div class="section">
        <h2>Terms &amp; Conditions</h2>

        <p><strong>Last Updated:</strong> April 2026</p>

        <p>Welcome to <span class="highlight">Cognix: A Hybrid AI-Powered Internship Assistant for Fresh
        Undergraduates</span>. By accessing or using this application, you agree to comply with and be bound
        by these Terms and Conditions. If you do not agree with any part of these terms, you must discontinue
        use of the platform immediately.</p>

        <p>Cognix is intended solely for students, particularly fresh undergraduates. By using this platform,
        you confirm that you are legally eligible to enter into this agreement under the laws of India.</p>

        <p>The platform provides AI-powered internship recommendations, career guidance, and conversational
        assistance. While we aim to offer useful and relevant suggestions, Cognix functions as an assistive
        tool and should not be relied upon as the sole basis for decision-making.</p>

        <p>User authentication is handled through Google OAuth. We only access basic profile information such
        as your email address and do not store or have access to your passwords. You are responsible for
        maintaining the confidentiality of your account and any activity that occurs under it.</p>

        <p>You agree not to misuse the platform, attempt unauthorized access, disrupt system functionality,
        or input harmful or illegal content. Any violation of these terms may result in suspension or
        termination of your access without prior notice.</p>

        <p>All content, design, and functionality of Cognix are the intellectual property of the developer
        and may not be copied, reproduced, or distributed without permission. These terms are governed by
        the laws of India.</p>
    </div>

    <!-- PRIVACY POLICY -->
    <div class="section">
        <h2>Privacy Policy</h2>

        <p>Cognix collects limited user information to provide and improve its services. This includes your
        email address (via Google login) and chat interactions with the AI system. This data is used to
        enhance user experience, improve recommendation quality, and analyze system performance.</p>

        <p>The platform integrates third-party services such as Google OAuth for authentication and Google
        Gemini API for AI-generated responses. As a result, your inputs may be processed by these external
        services. We do not control how these third parties handle data, and users are advised not to share
        sensitive or confidential information.</p>

        <p>We do not sell, rent, or trade your personal data. Information is only shared when necessary for
        core functionality or if required by law. We implement reasonable security measures to protect your
        data; however, no method of transmission over the internet is completely secure.</p>

        <p>User data may be retained for a limited period to improve system performance and user experience.
        You have the right to request access to your data or request its deletion by contacting us.</p>

        <p>Cognix is not intended for children under the age of 13, and we do not knowingly collect personal
        data from minors.</p>
    </div>

    <!-- DISCLAIMER -->
    <div class="section">
        <h2>Disclaimer</h2>

        <p>Cognix provides general guidance and AI-generated responses for informational purposes only.
        The platform does not offer professional, legal, or career counseling services. Users should
        independently verify any information before making decisions.</p>

        <p>We do not guarantee internship placements, interview calls, or job offers. All recommendations
        provided by the system are suggestions based on available data and algorithms.</p>

        <p>Due to the nature of artificial intelligence, responses may sometimes be inaccurate, incomplete,
        or outdated. Cognix shall not be held responsible for any decisions, actions, or outcomes resulting
        from the use of the platform.</p>

        <p>By using this application, you acknowledge and accept that you are using the service at your
        own risk.</p>

        <p><strong>Contact:</strong>
        <a href="mailto:kaustubh.tech06@gmail.com">kaustubh.tech06@gmail.com</a></p>
    </div>

    <footer>
        &copy; 2026 Cognix &bull; All Rights Reserved
    </footer>

</div>
</div>
</body>
</html>
"""

st.components.v1.html(LEGAL_HTML, height=1800, scrolling=True)
