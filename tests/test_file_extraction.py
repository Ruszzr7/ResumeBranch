import unittest

import httpx

from backend.file_extraction import (
    build_files_url,
    extract_kimi_file_content,
    is_kimi_file_api_url,
)


class KimiFileExtractionTests(unittest.IsolatedAsyncioTestCase):
    def test_recognizes_open_platform_but_not_coding_subscription(self):
        self.assertTrue(is_kimi_file_api_url("https://api.moonshot.cn/v1"))
        self.assertFalse(is_kimi_file_api_url("https://api.kimi.com/coding/v1"))

    def test_builds_files_url_from_common_api_inputs(self):
        self.assertEqual(
            build_files_url("https://api.moonshot.cn/v1"),
            "https://api.moonshot.cn/v1/files",
        )
        self.assertEqual(
            build_files_url("https://api.moonshot.cn/v1/chat/completions"),
            "https://api.moonshot.cn/v1/files",
        )

    async def test_uploads_extracts_and_deletes_the_file(self):
        requests = []

        def handler(request: httpx.Request):
            requests.append((request.method, request.url.path, request.headers.get("Authorization")))
            if request.method == "POST":
                body = request.content
                self.assertIn(b'file-extract', body)
                self.assertIn(b'resume.pdf', body)
                return httpx.Response(200, json={"id": "file-123"})
            if request.method == "GET":
                return httpx.Response(200, text="姓名：张三\n项目经历：订单系统")
            return httpx.Response(200, json={"deleted": True})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            extracted = await extract_kimi_file_content(
                b"%PDF",
                filename="resume.pdf",
                content_type="application/pdf",
                api_key="secret",
                base_url="https://api.moonshot.cn/v1",
                client=client,
            )

        self.assertIn("张三", extracted)
        self.assertEqual(
            requests,
            [
                ("POST", "/v1/files", "Bearer secret"),
                ("GET", "/v1/files/file-123/content", "Bearer secret"),
                ("DELETE", "/v1/files/file-123", "Bearer secret"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
