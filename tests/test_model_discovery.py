import unittest

import httpx

from backend.model_discovery import build_models_url, discover_models, extract_model_ids


class ModelDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def test_builds_models_url_from_api_root_or_completion_endpoint(self):
        self.assertEqual(
            build_models_url("https://example.com/v1"),
            "https://example.com/v1/models",
        )
        self.assertEqual(
            build_models_url("https://example.com/v1/chat/completions?ignored=1"),
            "https://example.com/v1/models",
        )
        self.assertEqual(
            build_models_url("https://example.com/v1/models"),
            "https://example.com/v1/models",
        )

    def test_extracts_common_payload_shapes_and_deduplicates(self):
        self.assertEqual(
            extract_model_ids({"data": [{"id": "z-model"}, {"id": "a-model"}, {"id": "a-model"}]}),
            ["a-model", "z-model"],
        )
        self.assertEqual(extract_model_ids({"models": ["manual", {"name": "named"}]}), ["manual", "named"])

    async def test_discovers_models_with_bearer_key(self):
        seen = {}

        def handler(request: httpx.Request):
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"data": [{"id": "model-b"}, {"id": "model-a"}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await discover_models("https://example.com/v1", "secret-key", client=client)

        self.assertTrue(result["success"])
        self.assertEqual(result["models"], ["model-a", "model-b"])
        self.assertEqual(seen["url"], "https://example.com/v1/models")
        self.assertEqual(seen["auth"], "Bearer secret-key")
        self.assertNotIn("secret-key", str(result))

    async def test_unsupported_listing_is_a_manual_entry_fallback(self):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(404, json={"detail": "missing"}))
        ) as client:
            result = await discover_models("https://example.com/v1", "test-key", client=client)

        self.assertFalse(result["success"])
        self.assertEqual(result["models"], [])
        self.assertIn("手动填写", result["message"])

    async def test_public_model_listing_can_be_queried_without_a_key(self):
        def handler(request: httpx.Request):
            self.assertIsNone(request.headers.get("Authorization"))
            return httpx.Response(200, json={"data": [{"id": "public-model"}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await discover_models("https://example.com/v1", client=client)

        self.assertTrue(result["success"])
        self.assertEqual(result["models"], ["public-model"])

    async def test_auth_required_listing_prompts_for_a_key(self):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(401))
        ) as client:
            result = await discover_models("https://example.com/v1", client=client)

        self.assertFalse(result["success"])
        self.assertIn("API Key", result["message"])


if __name__ == "__main__":
    unittest.main()
