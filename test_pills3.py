import streamlit as st

def handle_pill():
    if st.session_state.quick_option:
        st.session_state.pill_input = st.session_state.quick_option
        st.session_state.quick_option = None

if "pill_input" not in st.session_state:
    st.session_state.pill_input = None

options = ["Option A", "Option B"]
st.pills("Options", options, key="quick_option", on_change=handle_pill)

user_input = st.chat_input("Type...")

if st.session_state.pill_input:
    user_input = st.session_state.pill_input
    st.session_state.pill_input = None

if user_input:
    st.write(f"Processed: {user_input}")
