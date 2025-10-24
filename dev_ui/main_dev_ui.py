import asyncio
import sys
from pathlib import Path
from agent_framework.devui import serve
from dotenv import load_dotenv


async def create_workflow():
    """Create and return the workflow instance."""
    # Ensure the project root is on sys.path so we can import agent_workflow when running this
    # script directly (avoids "attempted relative import with no known parent package").
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   

    from agent_workflow import QuantInvestWorkflow

    load_dotenv()

    _workflow = QuantInvestWorkflow()
    workflow = await _workflow.create_workflow()
    return workflow


def main():
    """Launch DevUI server with the workflow."""
    # NOTE: serve() internally calls uvicorn.run() which uses asyncio.run().
    # To avoid "RuntimeError: asyncio.run() cannot be called from a running event loop",
    # we must NOT be inside an async context when calling serve().
    # Solution: Create workflow in its own temporary event loop first, then pass to serve().
    workflow = asyncio.run(create_workflow())
    
    serve(entities=[workflow], port=8090, auto_open=False)


if __name__ == "__main__":
    main()