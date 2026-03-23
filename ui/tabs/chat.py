import streamlit as st
from core import rag_engine
from utils import history_manager

def render():
    """Renders the Chat tab."""
    st.markdown("## 💬 Ask About Your Project")
    st.caption(
        "Ask any question — RAG retrieves the most relevant code chunks "
        "and DeepSeek Coder answers based on your actual codebase."
    )

    # Project-specific Chat history in session state
    active_proj = st.session_state.get("active_project")
    if "chat_history" not in st.session_state or st.session_state.get("chat_active_project") != active_proj:
        st.session_state.chat_history = history_manager.load_chat_history(active_proj)
        st.session_state.chat_active_project = active_proj

    # Display history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input
    user_q = st.chat_input("Ask a question about your project…")
    if user_q:
        st.session_state.chat_history.append(
            {"role": "user", "content": user_q}
        )
        history_manager.save_chat_history(active_proj, st.session_state.chat_history)
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
