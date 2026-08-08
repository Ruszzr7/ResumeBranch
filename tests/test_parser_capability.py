import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.llm_gateway import GatewayConfig
from backend.parser_capability import ASSET_DIR, verify_parser_capabilities


class ParserCapabilityTests(unittest.IsolatedAsyncioTestCase):
    def test_fixtures_are_small_and_present(self):
        for name in ("parser_fixture.pdf", "parser_fixture.png"):
            path = ASSET_DIR / name
            self.assertTrue(path.exists())
            self.assertLess(path.stat().st_size, 350_000)

    async def test_gemini_auto_negotiates_native_pdf_and_validates_visual_codes(self):
        async def response(*args, **kwargs):
            filename = kwargs["filename"]
            code = "PDF-7319" if filename.endswith(".pdf") else "IMG-4827"
            return json.dumps({
                "name": "LIN YANZHEN", "phone": "13800001234",
                "email": "parser-check@example.com", "school": "QINGLAN UNIVERSITY",
                "visual_code": code, "columns": 2, "avatar_present": True,
            })

        config = GatewayConfig("parser", "https://relay.example/v1", "gemini-test", "key")
        with patch("backend.parser_capability.invoke_document", AsyncMock(side_effect=response)) as invoke:
            result = await verify_parser_capabilities(config)

        self.assertTrue(result["success"])
        self.assertEqual(result["adapter"], "gemini_native")
        self.assertEqual(invoke.await_count, 2)
        self.assertTrue(all(result["checks"].values()))

    async def test_openai_chat_pdf_data_url_is_not_claimed_as_native(self):
        payload = json.dumps({
            "name": "LIN YANZHEN", "phone": "13800001234",
            "email": "parser-check@example.com", "school": "QINGLAN UNIVERSITY",
            "visual_code": "PDF-7319", "columns": 2, "avatar_present": True,
        })

        async def response(*args, **kwargs):
            if kwargs["filename"].endswith(".png"):
                return payload.replace("PDF-7319", "IMG-4827")
            return payload

        config = GatewayConfig(
            "parser", "https://relay.example/v1", "vision-model", "key", "openai_chat"
        )
        with patch("backend.parser_capability.invoke_document", AsyncMock(side_effect=response)):
            result = await verify_parser_capabilities(config)

        self.assertFalse(result["success"])
        self.assertFalse(result["checks"]["native_pdf"])

    async def test_http_success_with_wrong_content_does_not_pass(self):
        config = GatewayConfig("parser", "https://relay.example/v1", "model", "key")
        with patch("backend.parser_capability.invoke_document", AsyncMock(return_value='{"name":"wrong"}')):
            result = await verify_parser_capabilities(config)

        self.assertFalse(result["success"])
        self.assertFalse(result["checks"]["pdf_vision"])
        self.assertFalse(result["checks"]["image"])


if __name__ == "__main__":
    unittest.main()
