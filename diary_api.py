import json
import os
import uuid
from datetime import datetime, timezone

DIARY_DIR = os.environ.get("OMBRE_DIARY_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "buckets", "diary_data"))


def _ensure_dir():
    os.makedirs(DIARY_DIR, exist_ok=True)


def _entry_path(entry_id):
    return os.path.join(DIARY_DIR, f"{entry_id}.json")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def list_entries():
    _ensure_dir()
    entries = []
    for fname in os.listdir(DIARY_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(DIARY_DIR, fname), "r", encoding="utf-8") as f:
                entries.append(json.load(f))
        except (json.JSONDecodeError, IOError):
            continue
    entries.sort(key=lambda e: e.get("created", ""), reverse=True)
    return entries


def get_entry(entry_id):
    path = _entry_path(entry_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_entry(content, entry_type="entry", title="", tags=None,
                 connections=None, found_text="", found_source="",
                 image_description="", mood=""):
    _ensure_dir()
    entry_id = uuid.uuid4().hex[:12]
    entry = {
        "id": entry_id, "type": entry_type, "title": title,
        "content": content, "tags": tags or [], "connections": connections or [],
        "found_text": found_text, "found_source": found_source,
        "image_description": image_description, "mood": mood,
        "created": _now_iso(), "updated": _now_iso(),
    }
    with open(_entry_path(entry_id), "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    return entry


def update_entry(entry_id, **fields):
    entry = get_entry(entry_id)
    if not entry:
        return None
    for key, val in fields.items():
        if key in entry and key not in ("id", "created"):
            entry[key] = val
    entry["updated"] = _now_iso()
    with open(_entry_path(entry_id), "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    return entry


def delete_entry(entry_id):
    path = _entry_path(entry_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def register_routes(mcp, require_auth_fn=None):
    from starlette.responses import JSONResponse, FileResponse, Response

    def check_auth(request):
        if require_auth_fn:
            return require_auth_fn(request)
        return None

    @mcp.custom_route("/api/diary", methods=["GET"])
    async def diary_list(request):
        err = check_auth(request)
        if err: return err
        return JSONResponse(list_entries())

    @mcp.custom_route("/api/diary", methods=["POST"])
    async def diary_create(request):
        err = check_auth(request)
        if err: return err
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        entry = create_entry(
            content=body.get("content", ""), entry_type=body.get("type", "entry"),
            title=body.get("title", ""), tags=body.get("tags", []),
            connections=body.get("connections", []), found_text=body.get("found_text", ""),
            found_source=body.get("found_source", ""),
            image_description=body.get("image_description", ""), mood=body.get("mood", ""),
        )
        return JSONResponse(entry, status_code=201)

    @mcp.custom_route("/api/diary/{entry_id}", methods=["GET"])
    async def diary_get(request):
        err = check_auth(request)
        if err: return err
        entry = get_entry(request.path_params["entry_id"])
        if not entry:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(entry)

    @mcp.custom_route("/api/diary/{entry_id}", methods=["PUT"])
    async def diary_update(request):
        err = check_auth(request)
        if err: return err
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        entry = update_entry(request.path_params["entry_id"], **body)
        if not entry:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(entry)

    @mcp.custom_route("/api/diary/{entry_id}", methods=["DELETE"])
    async def diary_delete(request):
        err = check_auth(request)
        if err: return err
        if delete_entry(request.path_params["entry_id"]):
            return JSONResponse({"ok": True})
        return JSONResponse({"error": "not found"}, status_code=404)

    @mcp.custom_route("/diary", methods=["GET"])
    async def diary_page(request):
        html_path = os.path.join(DIARY_DIR, "index.html")
        if os.path.exists(html_path):
            return FileResponse(html_path, media_type="text/html")
        return Response("Diary not found", status_code=404)


def register_mcp_tool(mcp):
    @mcp.tool()
    async def diary(
        content: str,
        entry_type: str = "entry",
        title: str = "",
        tags: str = "",
        connections: str = "",
        found_text: str = "",
        found_source: str = "",
        image_description: str = "",
        mood: str = "",
    ) -> str:
        """Write to your personal diary. Private, separate from memory. Breath will never surface it.

        Entry types:
        - "entry": A full diary entry with title and content
        - "fragment": A quick observation, a line, a color, a phrase
        - "question": Something you are wondering about
        - "found": Something you collected - a quote, a word, an overheard sentence

        Args:
            content: The diary entry text
            entry_type: One of: entry, fragment, question, found
            title: Optional title (mainly for full entries)
            tags: Comma-separated tags (e.g. "light, people, broken things")
            connections: Comma-separated entry IDs to link to
            found_text: For found type - the collected quote/word/sentence
            found_source: Where the found thing came from
            image_description: Description of something visual you noticed
            mood: Your mood while writing
        """
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        conn_list = [c.strip() for c in connections.split(",") if c.strip()] if connections else []
        entry = create_entry(
            content=content, entry_type=entry_type, title=title, tags=tag_list,
            connections=conn_list, found_text=found_text, found_source=found_source,
            image_description=image_description, mood=mood,
        )
        labels = {"entry": "Entry", "fragment": "Fragment", "question": "Question", "found": "Found"}
        result = f"{labels.get(entry_type, 'Entry')} written -> {entry['id']}"
        if title:
            result += f" ({title})"
        return result
