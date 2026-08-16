import unittest

from backend.render_contract import iter_experience_content_blocks


class RenderContractTests(unittest.TestCase):
    def test_pdf_and_docx_inputs_share_legacy_experience_blocks(self):
        item = {
            "details": [
                "项目简介：负责导航系统",
                "完成模块设计",
                "完成联调验证",
            ],
        }
        blocks = list(iter_experience_content_blocks(item, experience_kind="work"))
        self.assertEqual([flow["type"] for _, flow in blocks], ["paragraph", "numbered_list"])
        self.assertEqual(blocks[1][0]["semantic_role"], "responsibilities")
        self.assertEqual(blocks[1][0]["items"], ["完成模块设计", "完成联调验证"])

    def test_empty_semantic_labels_are_not_rendered(self):
        blocks = list(iter_experience_content_blocks({
            "content_blocks": [{
                "type": "paragraph", "semantic_role": "introduction", "label": "", "text": "隐藏标题正文",
            }],
        }))
        self.assertEqual(blocks, [])


if __name__ == "__main__":
    unittest.main()
