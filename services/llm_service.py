import os, json, httpx, asyncio
from jinja2 import Environment, FileSystemLoader, select_autoescape

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
RESOURCES_DIR  = os.getenv("RESOURCES_DIR", "/app/resources")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is required")

_jinja = Environment(
    loader=FileSystemLoader(RESOURCES_DIR),
    autoescape=select_autoescape(disabled_extensions=("txt",))
)

def render_template(path: str, context: dict) -> str:
    return _jinja.get_template(path).render(**(context or {}))

class LLMService:
    _BASE = "https://generativelanguage.googleapis.com/v1beta"

    async def generate(self, prompt_text: str, temperature: float = 0.2) -> str:
        if not GEMINI_MODEL:
            raise RuntimeError("GEMINI_MODEL is required")

        url = f"{self._BASE}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {"temperature": temperature}
        }

        timeout = httpx.Timeout(connect=10.0, read=240.0, write=15.0, pool=30.0)
        limits  = httpx.Limits(max_connections=20, max_keepalive_connections=10)

        for attempt, backoff in enumerate((0.5, 1.0, 2.0, 4.0), start=1):
            try:
                async with httpx.AsyncClient(timeout=timeout, limits=limits, http2=True) as client:
                    r = await client.post(url, json=payload)
                r.raise_for_status()
                data = r.json()
                candidates = data.get("candidates") or []
                parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
                if not parts or "text" not in parts[0]:
                    raise RuntimeError(f"Invalid LLM response: {json.dumps(data)[:500]}")
                return parts[0]["text"]

            except (httpx.ReadTimeout, httpx.ConnectTimeout):
                if attempt == 4:
                    raise
                await asyncio.sleep(backoff)
            except httpx.HTTPStatusError as e:
                try:
                    detail = json.dumps(e.response.json(), ensure_ascii=False)[:700]
                except Exception:
                    detail = (e.response.text or "")[:700]
                raise RuntimeError(f"Gemini {e.response.status_code}: {detail}") from e
