import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from groq import BadRequestError

from app.errors import ProviderError
from app.services.llm_gemini import GeminiVoice
from app.services.llm_groq import GroqBrain
from tests.fakes import personas, settings


def rejection(code="json_validate_failed", message="Generated JSON does not match expected schema"):
    return BadRequestError(message, response=httpx.Response(400, request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")),
                           body={"error": {"code": code, "message": message}})


def valid_response():
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps({
        "trigger": "CASUAL", "mode": "BANTER", "relevance": 0.8, "reply_to": None,
    })))])


def brain_with_responses(responses):
    brain = GroqBrain(settings(groq_api_key="provider-unit-test-placeholder"))
    create = AsyncMock(side_effect=responses)
    brain.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return brain, create


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_enum_rejection_retries_once_with_strict_low_settings_and_reminder(self):
        brain, create = brain_with_responses([rejection(), valid_response()])
        result = await brain.evaluate_reflex(personas(2)[0], "systems", [])
        self.assertEqual(result.trigger, "CASUAL")
        self.assertEqual(create.await_count, 2)
        for call in create.await_args_list:
            self.assertEqual(call.kwargs["model"], "openai/gpt-oss-20b")
            self.assertEqual(call.kwargs["reasoning_effort"], "low")
            self.assertFalse(call.kwargs["stream"])
            self.assertTrue(call.kwargs["response_format"]["json_schema"]["strict"])
        self.assertEqual(len(create.await_args_list[0].kwargs["messages"]), 1)
        retry_prompt = create.await_args_list[1].kwargs["messages"][-1]["content"]
        self.assertIn("BANTER is a mode, never a trigger", retry_prompt)

    async def test_unrelated_400_is_not_retried(self):
        brain, create = brain_with_responses([rejection("invalid_request_error", "Unsupported request parameter")])
        with self.assertRaises(ProviderError):
            await brain.evaluate_reflex(personas(2)[0], "systems", [])
        self.assertEqual(create.await_count, 1)

    async def test_repeated_structured_rejection_stops_after_one_retry(self):
        brain, create = brain_with_responses([rejection(), rejection()])
        with self.assertRaises(ProviderError):
            await brain.evaluate_reflex(personas(2)[0], "systems", [])
        self.assertEqual(create.await_count, 2)

    async def test_gemini_thinking_and_function_calling_disabled_with_exact_model(self):
        async def chunks():
            yield SimpleNamespace(text="hello|||again")
        generate = AsyncMock(return_value=chunks())
        voice = GeminiVoice(settings(gemini_api_key="provider-unit-test-placeholder"))
        voice.client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate)))
        result = [chunk async for chunk in voice.stream(personas(2)[0], "systems", [], "DEEP_DIVE")]
        self.assertEqual(result, ["hello|||again"])
        kwargs = generate.await_args.kwargs
        self.assertEqual(kwargs["model"], "gemini-2.5-flash")
        self.assertEqual(kwargs["config"].thinking_config.thinking_budget, 0)
        self.assertEqual(kwargs["config"].max_output_tokens, 350)
        self.assertEqual(kwargs["config"].temperature, 0.88)
        self.assertTrue(kwargs["config"].automatic_function_calling.disable)
