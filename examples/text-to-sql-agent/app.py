"""Gradio interface for the text-to-SQL Deep Agent."""

import asyncio
import glob
import os
import uuid

import gradio as gr
from dotenv import load_dotenv
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent import BASE_DIR, _create_agent, _get_store

load_dotenv()

CHECKPOINTER_PATH = os.getenv("CHECKPOINTER_DB", os.path.join(BASE_DIR, "checkpoints.db"))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


async def respond(message, history, session_name):
    """Process a user message and return the agent response + any generated charts."""
    if not message.strip():
        return "", history, []

    if not session_name.strip():
        session_name = "gradio_default"

    # Resolve thread_id for this session
    thread_file = os.path.join(BASE_DIR, f".session_{session_name}.thread")
    try:
        with open(thread_file, "r") as f:
            thread_id = f.read().strip()
    except FileNotFoundError:
        thread_id = str(uuid.uuid4())
        with open(thread_file, "w") as f:
            f.write(thread_id)

    store = _get_store()
    config = {"configurable": {"thread_id": thread_id}}

    # Track existing output files before invoke
    existing_files = set(glob.glob(os.path.join(OUTPUT_DIR, "*")))

    async with AsyncSqliteSaver.from_conn_string(CHECKPOINTER_PATH) as checkpointer:
        agent = _create_agent(checkpointer, store)
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
        )

    final_message = result["messages"][-1]
    answer = (
        final_message.content
        if hasattr(final_message, "content")
        else str(final_message)
    )

    # Find newly generated files (charts/PDFs)
    new_files = []
    if os.path.exists(OUTPUT_DIR):
        current_files = set(glob.glob(os.path.join(OUTPUT_DIR, "*")))
        new_files = sorted(current_files - existing_files)

    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ]

    return "", history, new_files


def build_app():
    """Build and return the Gradio app."""
    with gr.Blocks(title="Text-to-SQL Deep Agent") as app:
        gr.Markdown(
            "## Text-to-SQL Deep Agent\n"
            "Ask questions about the Chinook music store database. "
            "The agent can generate charts and PDF reports."
        )

        with gr.Row():
            session_input = gr.Textbox(
                value="gradio_default",
                label="Session",
                scale=1,
                info="Same session name = continued conversation",
            )

        chatbot = gr.Chatbot(label="Conversation", height=480)

        with gr.Row():
            msg_input = gr.Textbox(
                label="Your question",
                placeholder="Ex: Quais são os top 5 artistas por vendas?",
                scale=4,
                show_label=False,
            )
            send_btn = gr.Button("Send", variant="primary", scale=1)

        file_output = gr.File(
            label="Generated files (charts / PDFs)",
            file_count="multiple",
        )

        send_btn.click(
            fn=respond,
            inputs=[msg_input, chatbot, session_input],
            outputs=[msg_input, chatbot, file_output],
        )
        msg_input.submit(
            fn=respond,
            inputs=[msg_input, chatbot, session_input],
            outputs=[msg_input, chatbot, file_output],
        )

    return app


if __name__ == "__main__":
    app = build_app()
    app.launch(theme=gr.themes.Soft())
