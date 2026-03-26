import streamlit as st
from core import rag_engine
from utils import history_manager

# Inject CSS once to make the chat container fill available viewport height
_CHAT_CSS = """
<style>
/* Target the scrollable div Streamlit creates for st.container(height=...) */
[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stVerticalBlock"] {
    /* fallback if selector misses */
}

/* The actual scroll container Streamlit wraps around a fixed-height container */
div[data-testid="stVerticalBlockBorderWrapper"]:has(div.chat-scroll-anchor) {
    height: calc(100vh - 260px) !important;
    max-height: calc(100vh - 260px) !important;
    overflow-y: auto !important;
}
</style>
"""

def render():
    """Renders the Chat tab with ChatGPT-style layout — dynamic height."""
    st.markdown(
        '<div class="section-header">'
        '<span class="icon">💬</span>'
        '<span class="title">Ask About Your Project</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Ask any question — the AI retrieves the most relevant code chunks "
        "and answers based on your actual codebase."
    )

    # Inject dynamic-height CSS for the chat container
    st.markdown(_CHAT_CSS, unsafe_allow_html=True)

    # Project-specific Chat history in session state
    active_proj = st.session_state.get("active_project")
    if "chat_history" not in st.session_state or st.session_state.get("chat_active_project") != active_proj:
        st.session_state.chat_history = history_manager.load_chat_history(active_proj)
        st.session_state.chat_active_project = active_proj

    # ── Scrollable message area ──
    # height=600 is the Streamlit fallback; CSS above overrides it to fill the screen
    chat_container = st.container(height=600)

    with chat_container:
        # Anchor div so CSS :has() selector can target this container
        st.markdown('<div class="chat-scroll-anchor"></div>', unsafe_allow_html=True)

        if not st.session_state.chat_history:
            st.markdown(
                '<div style="display:flex;align-items:center;justify-content:center;'
                'padding-top:80px;opacity:0.4;font-size:1.1rem;color:#64748B;">'
                '💬 Start a conversation by typing below…'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

    # ── Input (sits below the scrollable container) ──
    user_q = st.chat_input("Ask a question about your project…")
    if user_q:
        st.session_state.chat_history.append(
            {"role": "user", "content": user_q}
        )
        history_manager.save_chat_history(active_proj, st.session_state.chat_history)

        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_q)

            with st.chat_message("assistant"):
                response_area = st.empty()
                full_response = ""
                for token in rag_engine.query_stream(user_q):
                    full_response += token
                    response_area.markdown(full_response + "▌")
                response_area.markdown(full_response)

        st.session_state.chat_history.append(
            {"role": "assistant", "content": full_response}
        )
        history_manager.save_chat_history(active_proj, st.session_state.chat_history)
