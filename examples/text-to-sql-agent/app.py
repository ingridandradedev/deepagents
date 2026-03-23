"""Streamlit interface for the text-to-SQL Deep Agent."""

import asyncio
import glob
import os
import uuid

import nest_asyncio
import streamlit as st

# Allow nested asyncio.run() calls inside Streamlit's event loop
nest_asyncio.apply()
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent import BASE_DIR, _create_agent, _get_store

load_dotenv()

CHECKPOINTER_PATH = os.getenv("CHECKPOINTER_DB", os.path.join(BASE_DIR, "checkpoints.db"))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# --- Page config ---
st.set_page_config(
    page_title="Text-to-SQL Deep Agent",
    page_icon="🗄️",
    layout="wide",
)

# --- Session state init ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_name" not in st.session_state:
    st.session_state.session_name = "default"
if "processing" not in st.session_state:
    st.session_state.processing = False


def get_thread_id(session_name: str) -> tuple[str, bool]:
    """Get or create a thread_id for the given session name."""
    thread_file = os.path.join(BASE_DIR, f".session_{session_name}.thread")
    try:
        with open(thread_file, "r") as f:
            tid = f.read().strip()
            if tid:
                return tid, False
    except FileNotFoundError:
        pass
    tid = str(uuid.uuid4())
    with open(thread_file, "w") as f:
        f.write(tid)
    return tid, True


def list_sessions() -> list[str]:
    """List existing session names from .session_*.thread files."""
    pattern = os.path.join(BASE_DIR, ".session_*.thread")
    files = glob.glob(pattern)
    names = []
    for f in files:
        basename = os.path.basename(f)
        # .session_NAME.thread -> NAME
        name = basename.replace(".session_", "").replace(".thread", "")
        names.append(name)
    return sorted(names)


def find_new_files(before: set[str]) -> list[str]:
    """Find files created in OUTPUT_DIR since `before` snapshot."""
    if not os.path.exists(OUTPUT_DIR):
        return []
    current = set(glob.glob(os.path.join(OUTPUT_DIR, "*")))
    return sorted(current - before)


async def run_agent(question: str, thread_id: str):
    """Run the agent and stream results back.

    Returns (answer_text, tool_calls_info, new_files).
    """
    store = _get_store()
    config = {"configurable": {"thread_id": thread_id}}

    # Snapshot output dir before
    existing_files = set(glob.glob(os.path.join(OUTPUT_DIR, "*"))) if os.path.exists(OUTPUT_DIR) else set()

    async with AsyncSqliteSaver.from_conn_string(CHECKPOINTER_PATH) as checkpointer:
        agent = _create_agent(checkpointer, store)

        answer_text = ""
        tool_calls = []

        async for event in agent.astream(
            {"messages": [{"role": "user", "content": question}]},
            config=config,
            stream_mode="values",
        ):
            messages = event.get("messages", [])
            if not messages:
                continue
            last = messages[-1]

            # Collect tool messages
            if isinstance(last, ToolMessage):
                tool_calls.append({
                    "name": last.name,
                    "content": str(last.content)[:500],
                })

            # Final AI answer
            if isinstance(last, AIMessage) and last.content and not last.tool_calls:
                answer_text = last.content

    new_files = find_new_files(existing_files)
    return answer_text, tool_calls, new_files


# --- Sidebar ---
with st.sidebar:
    st.title("🗄️ Text-to-SQL Agent")
    st.caption("Chinook Music Store Database")

    st.divider()

    # Session management
    st.subheader("Sessions")
    existing = list_sessions()

    new_session = st.text_input(
        "New session name",
        placeholder="e.g. sales_analysis",
        key="new_session_input",
    )
    if st.button("Create session", use_container_width=True) and new_session.strip():
        st.session_state.session_name = new_session.strip()
        st.session_state.messages = []
        st.rerun()

    if existing:
        selected = st.selectbox(
            "Or resume existing",
            options=existing,
            index=existing.index(st.session_state.session_name) if st.session_state.session_name in existing else 0,
        )
        if selected != st.session_state.session_name:
            if st.button("Switch session", use_container_width=True):
                st.session_state.session_name = selected
                st.session_state.messages = []
                st.rerun()

    st.divider()
    st.caption(f"Active: **{st.session_state.session_name}**")

    # Show generated files
    if os.path.exists(OUTPUT_DIR):
        files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*")))
        if files:
            st.divider()
            st.subheader("Generated Files")
            for fpath in files[-10:]:  # Show last 10
                fname = os.path.basename(fpath)
                with open(fpath, "rb") as f:
                    st.download_button(
                        f"📥 {fname}",
                        data=f.read(),
                        file_name=fname,
                        use_container_width=True,
                    )


# --- Main chat area ---
st.header(f"Session: {st.session_state.session_name}")

# Render chat history
for msg in st.session_state.messages:
    role = msg["role"]
    with st.chat_message(role):
        st.markdown(msg["content"])
        # Show inline images if any
        if "files" in msg:
            for fpath in msg["files"]:
                if fpath.lower().endswith(".png"):
                    st.image(fpath, use_container_width=True)

# Chat input
if prompt := st.chat_input("Ask about the Chinook database..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process with agent
    with st.chat_message("assistant"):
        thread_id, is_new = get_thread_id(st.session_state.session_name)

        if is_new:
            st.caption(f"🆕 New session (thread {thread_id[:8]}...)")
        else:
            st.caption(f"🔄 Resuming (thread {thread_id[:8]}...)")

        with st.status("🤖 Agent working...", expanded=True) as status:
            st.write("Querying database and analyzing...")

            try:
                answer, tool_calls, new_files = asyncio.run(
                    run_agent(prompt, thread_id)
                )

                # Show tool calls
                if tool_calls:
                    for tc in tool_calls:
                        st.write(f"🔧 **{tc['name']}**")
                        if tc["content"]:
                            st.code(tc["content"], language="text")

                status.update(label="✅ Done", state="complete", expanded=False)

            except Exception as e:
                status.update(label="❌ Error", state="error")
                st.error(f"Agent error: {e}")
                answer = f"Error: {e}"
                new_files = []
                tool_calls = []

        # Display answer
        if answer:
            st.markdown(answer)

        # Display generated charts inline
        png_files = [f for f in new_files if f.lower().endswith(".png")]
        for fpath in png_files:
            st.image(fpath, use_container_width=True)

        # Download buttons for PDFs
        pdf_files = [f for f in new_files if f.lower().endswith(".pdf")]
        for fpath in pdf_files:
            fname = os.path.basename(fpath)
            with open(fpath, "rb") as f:
                st.download_button(
                    f"📄 Download {fname}",
                    data=f.read(),
                    file_name=fname,
                )

        # Save to history
        st.session_state.messages.append({
            "role": "assistant",
            "content": answer or "No response.",
            "files": png_files,
        })
