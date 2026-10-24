import asyncio
import json
import logging
from contextlib import aclosing

from app.errors import ProviderError

logger = logging.getLogger(__name__)


async def split_bubbles(chunks):
    """Provider chunks may split any of the three delimiter characters."""
    buffer = ""
    async for chunk in chunks:
        buffer += chunk or ""
        while "|||" in buffer:
            bubble, buffer = buffer.split("|||", 1)
            bubble = bubble.strip().strip("|").strip()
            if bubble:
                yield bubble
    # A truncated partial separator must never leak into the chat.
    tail = buffer.strip().rstrip("|").strip()
    if tail:
        yield tail


class GeminiVoice:
    def __init__(self, settings):
        self.settings = settings
        self.client = None
        self.semaphore = asyncio.Semaphore(6)

    def _client(self):
        if not self.settings.gemini_api_key.get_secret_value():
            raise ProviderError("Gemini is not configured")
        if self.client is None:
            from google import genai
            self.client = genai.Client(api_key=self.settings.gemini_api_key.get_secret_value())
        return self.client

    async def stream(self, persona, topic, messages, mode):
        from google.genai import types
        styles = {
            "CASUAL_CHIME": "Send one concise chat bubble.",
            "BANTER": "Send two or three short chat bubbles.",
            "DEEP_DIVE": "Explain in three to six or more rapid-fire short bubbles as needed.",
            "DEFENSIVE_ROAST": "Defend yourself and roast back in three to six or more short bubbles as needed.",
            "SIGN_OFF": "Send one or two short casual goodbye bubbles with a believable excuse.",
        }
        sys_prompt = (
            "You are one real friend in a lively group chat; never narrate or label the speaker. "
            "Follow this persona's voice and stance. React to current messages instead of repeating yourself. "
            "Separate complete chat bubbles with exactly |||. Do not include JSON, code fences, "
            "or the separator inside a bubble. Keep each bubble brief and conversational. "
            + styles[mode] + "\nPersona: " + json.dumps(persona.model_dump())
        )
        stream = None
        try:
            async with self.semaphore, asyncio.timeout(self.settings.provider_timeout):
                stream = await self._client().aio.models.generate_content_stream(
                    model="gemini-2.5-flash",
                    contents=json.dumps({"topic": topic, "transcript": messages[-30:]}),
                    config=types.GenerateContentConfig(
                        system_instruction=sys_prompt, temperature=0.88, max_output_tokens=350,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    ),
                )
                async with aclosing(stream):
                    async for chunk in stream:
                        if chunk.text:
                            yield chunk.text
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Gemini stream failed: error_type=%s status=%s", type(exc).__name__,
                           getattr(exc, "status_code", getattr(exc, "code", None)))
            raise ProviderError("Gemini streaming request failed") from None

    async def aclose(self):
        if self.client is not None:
            await self.client.aio.aclose()
            self.client.close()
