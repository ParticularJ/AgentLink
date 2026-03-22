---
name: tavily-search
description: "Web search via Tavily API (alternative to Brave). Use when the user asks to search the web / look up sources / find links and Brave web_search is unavailable or undesired. Returns a small set of relevant results (title, url, snippet) and can optionally include short answer summaries."
---

# Tavily Search

Use the bundled script to search the web with Tavily.

## Requirements

- Provide API key via either:
  - environment variable: `TAVILY_API_KEY`, or
  - `~/.openclaw/.env` line: `TAVILY_API_KEY=...`

## Commands

### tavily_search
Search the web using Tavily API.

**Parameters:**
- `query` (required): Search query string
- `max_results` (optional, default=5): Number of results to return (1-10)
- `format` (optional, default="brave"): Output format - "brave", "md", or "raw"

**Examples:**
```
tavily_search query="China economy March 12 2026" max_results=5
tavily_search query="宝鸡新闻" max_results=3 format=md
```

**直接执行：**
```bash
python3 ~/.openclaw/workspace/skills/openclaw-tavily-search/scripts/tavily_search.py --query "$query" --max-results $max_results --format $format
```

## Output

### brave
- JSON: `query`, optional `answer`, `results: [{title,url,snippet}]`

### md
- A compact Markdown list with title/url/snippet.

### raw
- JSON: `query`, optional `answer`, `results: [{title,url,content}]`

## Notes

- Keep `max_results` small by default (3–5) to reduce token/reading load.
- Prefer returning URLs + snippets; fetch full pages only when needed.
