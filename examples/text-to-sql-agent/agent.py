import argparse
import asyncio
import os
import sys
import uuid

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.memory import InMemoryStore
from rich.console import Console
from rich.panel import Panel

# Load environment variables
load_dotenv()

console = Console()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_store():
    """Get the persistent store for long-term memory.

    Uses PostgresStore if POSTGRES_STORE_URL is set (production),
    otherwise falls back to InMemoryStore (development).
    """
    postgres_url = os.getenv("POSTGRES_STORE_URL")
    if postgres_url:
        from langgraph.store.postgres import PostgresStore

        store = PostgresStore.from_conn_string(postgres_url)
        store.__enter__()
        store.setup()
        return store
    return InMemoryStore()


def _create_agent(checkpointer, store):
    """Create a text-to-SQL Deep Agent with persistent memory."""
    db_path = os.path.join(BASE_DIR, "chinook.db")
    db = SQLDatabase.from_uri(f"sqlite:///{db_path}", sample_rows_in_table_info=3)

    model = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)

    toolkit = SQLDatabaseToolkit(db=db, llm=model)
    sql_tools = toolkit.get_tools()

    def make_backend(rt):
        return CompositeBackend(
            default=StateBackend(rt),
            routes={"/memories/": StoreBackend(rt)},
        )

    return create_deep_agent(
        model=model,
        memory=["./AGENTS.md"],
        skills=["./skills/"],
        tools=sql_tools,
        subagents=[],
        backend=make_backend,
        store=store,
        checkpointer=checkpointer,
    )


def _get_thread_id(session_name):
    """Get or create a thread_id for the given session name."""
    thread_file = os.path.join(BASE_DIR, f".session_{session_name}.thread")
    try:
        with open(thread_file, "r") as f:
            thread_id = f.read().strip()
            if thread_id:
                return thread_id, False
    except FileNotFoundError:
        pass

    thread_id = str(uuid.uuid4())
    with open(thread_file, "w") as f:
        f.write(thread_id)
    return thread_id, True


async def main():
    """Main entry point for the SQL Deep Agent CLI."""
    parser = argparse.ArgumentParser(
        description="Text-to-SQL Deep Agent with persistent memory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python agent.py "What are the top 5 best-selling artists?"
  python agent.py "And their albums?" --session analysis
  python agent.py "How many customers are from Canada?" --session canada
        """,
    )
    parser.add_argument(
        "question",
        type=str,
        help="Natural language question to answer using the Chinook database",
    )
    parser.add_argument(
        "--session",
        type=str,
        default="default",
        help="Session name to resume a conversation (default: 'default')",
    )

    args = parser.parse_args()

    console.print(
        Panel(f"[bold cyan]Question:[/bold cyan] {args.question}", border_style="cyan")
    )
    console.print()

    # Thread management
    thread_id, is_new = _get_thread_id(args.session)
    if is_new:
        console.print(f"[blue]New session:[/blue] {args.session} (thread {thread_id[:8]}...)")
    else:
        console.print(f"[green]Resuming session:[/green] {args.session} (thread {thread_id[:8]}...)")

    # Persistence: AsyncSqliteSaver for checkpointing threads to disk
    checkpointer_path = os.getenv("CHECKPOINTER_DB", os.path.join(BASE_DIR, "checkpoints.db"))
    store = _get_store()

    async with AsyncSqliteSaver.from_conn_string(checkpointer_path) as checkpointer:
        console.print("[dim]Creating SQL Deep Agent...[/dim]")
        agent = _create_agent(checkpointer, store)

        console.print("[dim]Processing query...[/dim]\n")

        config = {"configurable": {"thread_id": thread_id}}

        try:
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": args.question}]},
                config=config,
            )

            final_message = result["messages"][-1]
            answer = (
                final_message.content
                if hasattr(final_message, "content")
                else str(final_message)
            )

            console.print(
                Panel(f"[bold green]Answer:[/bold green]\n\n{answer}", border_style="green")
            )
            console.print(
                f"\n[dim]Use --session {args.session} to continue this conversation.[/dim]"
            )

        except Exception as e:
            console.print(
                Panel(f"[bold red]Error:[/bold red]\n\n{str(e)}", border_style="red")
            )
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
