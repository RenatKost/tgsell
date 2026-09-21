"""Interactive developer-agent chat.

Powers the "talk to the developer like a coworker" Telegram chat (see
bot/main.py, admin-only plain-text handler). Runs entirely on Railway via
direct calls to the Claude API — independent of any Claude Code session or
the owner's own machine, so it works 24/7 from a phone.

The agent reads/writes the repo purely through the GitHub REST API (no git
checkout inside this container — the running container only has the
backend source baked in at build time, not the frontend source or git
history, so GitHub is the only complete view of the repo). It never pushes
to `main` directly — `propose_changes` always opens a PR, and branch
protection makes a direct push physically impossible anyway.
"""
import base64
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"
MAX_TOOL_ITERATIONS = 12
GITHUB_API = "https://api.github.com"


def _charter() -> str:
    """Load the developer agent's charter (automation/agents/developer.md).

    Read at call time (not import time) so editing the charter takes effect
    on the next chat message without a redeploy. Checked against two bases
    because the on-disk layout differs between local dev and the Railway
    image: locally this file lives under repo_root/backend/app/services/,
    but Dockerfile.railway's `COPY backend/ .` flattens that one level, so
    in prod it's /app/app/services/ with automation/ copied to /app/automation.
    """
    here = Path(__file__).resolve()
    candidates = [here.parents[2] / "automation", here.parents[3] / "automation"] if len(here.parents) > 3 else [here.parents[2] / "automation"]
    for base in candidates:
        path = base / "agents" / "developer.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
    logger.warning(f"[DEV_AGENT] Could not find developer.md under any of: {candidates}")
    return "You are the tgsell developer agent. Investigate and fix real bugs, always via a PR."


def _gh_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _list_directory(client: httpx.AsyncClient, path: str) -> str:
    resp = await client.get(
        f"{GITHUB_API}/repos/{settings.github_repo}/contents/{path.lstrip('/')}",
        headers=_gh_headers(),
        params={"ref": "main"},
    )
    if resp.status_code == 404:
        return f"Path not found: {path}"
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        return f"{path} is a file, not a directory. Use read_file instead."
    lines = [f"{'📁' if e['type'] == 'dir' else '📄'} {e['path']}" for e in data]
    return "\n".join(lines) if lines else "(empty directory)"


async def _read_file(client: httpx.AsyncClient, path: str) -> str:
    resp = await client.get(
        f"{GITHUB_API}/repos/{settings.github_repo}/contents/{path.lstrip('/')}",
        headers=_gh_headers(),
        params={"ref": "main"},
    )
    if resp.status_code == 404:
        return f"File not found: {path}"
    resp.raise_for_status()
    data = resp.json()
    if data.get("encoding") != "base64":
        return f"Unexpected encoding for {path}: {data.get('encoding')}"
    try:
        content = base64.b64decode(data["content"]).decode("utf-8")
    except UnicodeDecodeError:
        return f"{path} is a binary file, cannot display as text."
    # Cap what we feed back to the model — large generated files (bundles,
    # lockfiles) would blow the context budget for no benefit.
    if len(content) > 20000:
        content = content[:20000] + "\n... [truncated, file is longer]"
    return content


async def _propose_changes(
    client: httpx.AsyncClient,
    files: list[dict],
    commit_message: str,
    pr_title: str,
    pr_body: str,
) -> str:
    repo = settings.github_repo
    # 1. Base branch tip
    ref_resp = await client.get(f"{GITHUB_API}/repos/{repo}/git/ref/heads/main", headers=_gh_headers())
    ref_resp.raise_for_status()
    base_sha = ref_resp.json()["object"]["sha"]

    # 2. New branch off that tip
    import time
    branch = f"agent/dev-{int(time.time())}"
    create_ref = await client.post(
        f"{GITHUB_API}/repos/{repo}/git/refs",
        headers=_gh_headers(),
        json={"ref": f"refs/heads/{branch}", "sha": base_sha},
    )
    create_ref.raise_for_status()

    # 3. One commit per changed file on that branch
    for f in files:
        path = f["path"].lstrip("/")
        content_b64 = base64.b64encode(f["content"].encode("utf-8")).decode("ascii")
        existing_sha = None
        existing = await client.get(
            f"{GITHUB_API}/repos/{repo}/contents/{path}",
            headers=_gh_headers(),
            params={"ref": branch},
        )
        if existing.status_code == 200:
            existing_sha = existing.json()["sha"]
        body = {"message": commit_message, "content": content_b64, "branch": branch}
        if existing_sha:
            body["sha"] = existing_sha
        put_resp = await client.put(
            f"{GITHUB_API}/repos/{repo}/contents/{path}", headers=_gh_headers(), json=body
        )
        put_resp.raise_for_status()

    # 4. Open the PR
    pr_resp = await client.post(
        f"{GITHUB_API}/repos/{repo}/pulls",
        headers=_gh_headers(),
        json={"title": pr_title, "head": branch, "base": "main", "body": pr_body},
    )
    pr_resp.raise_for_status()
    return pr_resp.json()["html_url"]


TOOLS = [
    {
        "name": "list_directory",
        "description": "List files and subdirectories at a path in the repo (relative to repo root, e.g. 'backend/app/routers'). Use '' for repo root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file's full contents by its path relative to the repo root, e.g. 'backend/app/routers/admin.py'.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "propose_changes",
        "description": (
            "Open a pull request with one or more file changes. Never edits main directly — "
            "always creates a branch and a PR. Use this once you have the final content of "
            "every file you want to change (send the FULL new file content, not a diff)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
                "commit_message": {"type": "string"},
                "pr_title": {"type": "string"},
                "pr_body": {"type": "string", "description": "Explain root cause, fix, and what you verified."},
            },
            "required": ["files", "commit_message", "pr_title", "pr_body"],
        },
    },
]


async def run_dev_agent_chat(user_message: str) -> str:
    """Run one turn of the interactive developer-agent chat and return the reply text."""
    if not settings.anthropic_api_key:
        return "⚠️ ANTHROPIC_API_KEY не налаштовано — чат з агентом поки недоступний."
    if not settings.github_token:
        return "⚠️ GITHUB_TOKEN не налаштовано — агент не може читати репозиторій чи відкривати PR."

    messages = [{"role": "user", "content": user_message}]

    async with httpx.AsyncClient(timeout=60.0) as client:
        for _ in range(MAX_TOOL_ITERATIONS):
            resp = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": MODEL,
                    "max_tokens": 4096,
                    "system": _charter(),
                    "messages": messages,
                    "tools": TOOLS,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            content_blocks = data.get("content", [])
            messages.append({"role": "assistant", "content": content_blocks})

            tool_uses = [b for b in content_blocks if b.get("type") == "tool_use"]
            if not tool_uses:
                text_blocks = [b["text"] for b in content_blocks if b.get("type") == "text"]
                return "\n".join(text_blocks) or "(агент не дав відповіді)"

            tool_results = []
            for tu in tool_uses:
                try:
                    if tu["name"] == "list_directory":
                        result = await _list_directory(client, tu["input"]["path"])
                    elif tu["name"] == "read_file":
                        result = await _read_file(client, tu["input"]["path"])
                    elif tu["name"] == "propose_changes":
                        pr_url = await _propose_changes(
                            client,
                            tu["input"]["files"],
                            tu["input"]["commit_message"],
                            tu["input"]["pr_title"],
                            tu["input"]["pr_body"],
                        )
                        result = f"PR opened: {pr_url}"
                    else:
                        result = f"Unknown tool: {tu['name']}"
                except Exception as e:
                    logger.error(f"[DEV_AGENT] Tool '{tu['name']}' failed: {e}")
                    result = f"Error running {tu['name']}: {e}"
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu["id"], "content": result}
                )
            messages.append({"role": "user", "content": tool_results})

    return "⚠️ Забагато кроків — зупиняюсь. Спробуйте сформулювати задачу вужче."
