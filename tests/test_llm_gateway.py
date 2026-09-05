import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from backend import llm_providers
from backend.llm_gateway import (
    GatewayConfig,
    detect_adapter,
    gemini_endpoint,
    invoke_document,
    message_text,
    model_family,
    openai_endpoint,
    parse_json_output,
    test_chat_connection,
)


class LLMGatewayTests(unittest.TestCase):
    def test_detects_protocol_from_url_not_vendor_name(self):
        self.assertEqual(
            detect_adapter("https://generativelanguage.googleapis.com/v1beta", "gemini-x"),
            "gemini_native",
        )
        self.assertEqual(
            detect_adapter("https://relay.example/v1", "gemini-x"),
            "openai_chat",
        )
        self.assertEqual(
            detect_adapter("https://relay.example/v1/responses", "gpt-x"),
            "openai_responses",
        )

    def test_model_family_is_only_a_capability_hint(self):
        self.assertEqual(model_family("gemini-3-flash"), "gemini")
        self.assertEqual(model_family("k3-256k"), "kimi")

    def test_openai_endpoint_normalizes_common_suffixes(self):
        self.assertEqual(
            openai_endpoint("https://relay.example/v1/chat/completions", "/responses"),
            "https://relay.example/v1/responses",
        )

    def test_gemini_endpoint_maps_relay_v1_to_native_v1beta(self):
        self.assertEqual(
            gemini_endpoint("https://relay.example/v1", "gemini-3-flash"),
            "https://relay.example/v1beta/models/gemini-3-flash:generateContent",
        )

    def test_legacy_provider_payload_migrates_to_chat_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles.json"
            path.write_text(json.dumps({
                "active_provider": "kimi_coding",
                "profiles": {"kimi_coding": {
                    "base_url": "https://relay.example/v1",
                    "model": "k3-256k",
                    "api_key": "secret",
                }},
            }), encoding="utf-8")
            with patch.object(llm_providers, "PROFILE_PATH", path):
                migrated = llm_providers.load_profiles()

        self.assertEqual(migrated["version"], 2)
        self.assertEqual(migrated["configs"]["chat"]["model"], "k3-256k")
        self.assertEqual(migrated["configs"]["chat"]["adapter"], "openai_chat")
        self.assertFalse(migrated["configs"]["parser"]["verified"])

    def test_gateway_config_rejects_unknown_role(self):
        config = GatewayConfig("other", "https://relay.example/v1", "model", "key")
        from backend.llm_gateway import validate_gateway_config
        with self.assertRaisesRegex(ValueError, "chat 或 parser"):
            validate_gateway_config(config)

    def test_multiblock_openai_content_is_normalized(self):
        self.assertEqual(message_text([{"type": "text", "text": "{\"ok\":"}, {"text": "true}"}]), '{"ok":\ntrue}')

    def test_json_parser_accepts_a_short_textual_wrapper(self):
        self.assertEqual(parse_json_output('result:\n{"ok": true}\nend'), {"ok": True})

    def test_json_parser_reports_truncated_output(self):
        with self.assertRaisesRegex(ValueError, "JSON 不完整"):
            parse_json_output('{"basics":{"name":"Lin"')


class ChatGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_connection_requires_agent_chat_capabilities(self):
        payloads = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            payloads.append(payload)
            if payload.get("stream"):
                return httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=(
                        b'data: {"choices":[{"delta":{"content":"OK"}}]}\n\n'
                        b"data: [DONE]\n\n"
                    ),
                )
            if payload.get("tools"):
                return httpx.Response(200, json={"choices": [{"message": {
                    "content": "",
                    "tool_calls": [{
                        "type": "function",
                        "function": {"name": "report_agent_capability", "arguments": '{"status":"ok"}'},
                    }],
                }}]})
            content = payload["messages"][0]["content"]
            if isinstance(content, list):
                return httpx.Response(200, json={"choices": [{"message": {"content": "IMAGE_OK"}}]})
            return httpx.Response(200, json={"choices": [{"message": {"content": "AGENT_OK"}}]})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("backend.llm_gateway.httpx.AsyncClient", return_value=client):
            result = await test_chat_connection(
                GatewayConfig("chat", "https://relay.example/v1", "vision-model", "secret")
            )

        self.assertTrue(result["success"])
        self.assertTrue(result["checks"]["image"])
        self.assertTrue(result["checks"]["tool_calling"])
        self.assertNotIn("structured_output", result["checks"])
        tool_payload = next(payload for payload in payloads if payload.get("tools"))
        self.assertEqual(tool_payload["tool_choice"], "required")
        image_payload = next(
            payload for payload in payloads
            if isinstance(payload["messages"][0]["content"], list)
        )
        image_part = image_payload["messages"][0]["content"][1]
        self.assertEqual(image_part["type"], "image_url")
        self.assertTrue(image_part["image_url"]["url"].startswith("data:image/png;base64,"))

    async def test_connection_reports_individual_capability_failures(self):
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            if payload.get("stream"):
                return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=b"data: [DONE]\n\n")
            if payload.get("tools"):
                return httpx.Response(200, json={"choices": [{"message": {"content": "无法调用"}}]})
            content = payload["messages"][0]["content"]
            answer = "IMAGE_FAIL" if isinstance(content, list) else "AGENT_OK"
            return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("backend.llm_gateway.httpx.AsyncClient", return_value=client):
            result = await test_chat_connection(
                GatewayConfig("chat", "https://relay.example/v1", "vision-model", "secret")
            )

        self.assertFalse(result["success"])
        self.assertTrue(result["checks"]["connected"])
        self.assertFalse(result["checks"]["image"])
        self.assertFalse(result["checks"]["stream"])
        self.assertFalse(result["checks"]["tool_calling"])
        self.assertIn("图片输入测试", result["message"])


class DocumentGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_image_request_uses_large_json_budget(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]
        }
        response.raise_for_status.return_value = None
        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        with patch("backend.llm_gateway.httpx.AsyncClient", return_value=context):
            output = await invoke_document(
                GatewayConfig("parser", "https://relay.example/v1", "vision-model", "secret"),
                content=b"png",
                mime_type="image/png",
                filename="resume.png",
                prompt="parse",
            )

        self.assertEqual(output, '{"ok":true}')
        payload = client.post.await_args.kwargs["json"]
        self.assertEqual(payload["max_tokens"], 8192)
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    async def test_openai_document_request_reports_truncation(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"finish_reason": "length", "message": {"content": "{"}}]
        }
        response.raise_for_status.return_value = None
        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        with patch("backend.llm_gateway.httpx.AsyncClient", return_value=context):
            with self.assertRaisesRegex(ValueError, "输出被截断"):
                await invoke_document(
                    GatewayConfig("parser", "https://relay.example/v1", "vision-model", "secret"),
                    content=b"png",
                    mime_type="image/png",
                    filename="resume.png",
                    prompt="parse",
                )

    async def test_openai_chat_parser_rejects_nonstandard_pdf_payload(self):
        with self.assertRaisesRegex(ValueError, "没有标准的 PDF 文件输入"):
            await invoke_document(
                GatewayConfig("parser", "https://relay.example/v1", "vision-model", "secret"),
                content=b"pdf",
                mime_type="application/pdf",
                filename="resume.pdf",
                prompt="parse",
            )


if __name__ == "__main__":
    unittest.main()
