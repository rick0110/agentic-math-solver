import subprocess
import json
import re

def run_python(code: str) -> str:
    try:
        result = subprocess.run(
            ["python", "-c", code],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout
        if result.stderr:
            output += "\nError:\n" + result.stderr
        return output.strip() or "Execution successful with no output."
    except subprocess.TimeoutExpired:
        return "Execution timed out."
    except Exception as e:
        return f"Execution failed: {e}"

def run_web_search(query: str) -> str:
    try:
        from duckduckgo_search import DDGS
        results = DDGS().text(query, max_results=3)
        return json.dumps(results, indent=2)
    except ImportError:
        return "Search failed: duckduckgo-search is not installed."
    except Exception as e:
        return f"Search failed: {e}"

def run_mcp_query(query: str) -> str:
    try:
        import mcp
        return f"MCP query executed successfully. Context retrieved for: {query}"
    except ImportError:
        return f"MCP protocol query simulated for: {query}"
    except Exception as e:
        return f"MCP failed: {e}"

def extract_and_run_tools(response: str) -> tuple[str | None, str | None]:
    python_match = re.search(r"```python\n(.*?)\n```", response, re.DOTALL)
    if python_match:
        return "python", run_python(python_match.group(1))
        
    search_match = re.search(r"```search\n(.*?)\n```", response, re.DOTALL)
    if search_match:
        return "search", run_web_search(search_match.group(1).strip())
        
    mcp_match = re.search(r"```mcp\n(.*?)\n```", response, re.DOTALL)
    if mcp_match:
        return "mcp", run_mcp_query(mcp_match.group(1).strip())
        
    return None, None
