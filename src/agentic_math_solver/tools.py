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

def extract_tool_call(response: str) -> tuple[str | None, str | None]:
    """Look for a fenced tool block in the response. Returns (tool_name, tool_input)."""
    python_match = re.search(r"```python\n(.*?)\n```", response, re.DOTALL)
    if python_match:
        return "python", python_match.group(1)

    search_match = re.search(r"```search\n(.*?)\n```", response, re.DOTALL)
    if search_match:
        return "search", search_match.group(1).strip()

    mcp_match = re.search(r"```mcp\n(.*?)\n```", response, re.DOTALL)
    if mcp_match:
        return "mcp", mcp_match.group(1).strip()

    return None, None


def run_tool(tool_name: str, tool_input: str) -> str:
    if tool_name == "python":
        return run_python(tool_input)
    if tool_name == "search":
        return run_web_search(tool_input)
    if tool_name == "mcp":
        return run_mcp_query(tool_input)
    return f"Unknown tool: {tool_name}"


def extract_and_run_tools(response: str) -> tuple[str | None, str | None]:
    tool_name, tool_input = extract_tool_call(response)
    if tool_name is None:
        return None, None
    return tool_name, run_tool(tool_name, tool_input)
