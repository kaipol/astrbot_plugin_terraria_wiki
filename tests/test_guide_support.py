import unittest

from terraria_wiki.guide_support import build_guide_sections, is_guide_like, select_key_sections, summarize_parsed_html, summarize_wikitext


class GuideSupportTests(unittest.TestCase):
    def test_is_guide_like_for_large_page(self):
        self.assertTrue(is_guide_like("泰拉攻略", [], 60000, 2))

    def test_summarize_wikitext_extracts_plain_text(self):
        summary = summarize_wikitext("== 标题 ==\n'''这是''' 一个 [[测试]] 段落。", 50)
        self.assertIn("这是 一个 测试 段落", summary)

    def test_summarize_parsed_html_keeps_translated_terms(self):
        summary = summarize_parsed_html(
            "<div><p><b>生命水晶</b>是一种消耗品，使用后它会永久性地将玩家的最大生命值增加 20。</p></div>",
            80,
        )
        self.assertEqual(summary, "生命水晶是一种消耗品，使用后它会永久性地将玩家的最大生命值增加 20。")

    def test_summarize_parsed_html_skips_full_fallback_when_disabled(self):
        summary = summarize_parsed_html("<div><span>目录</span><table><tr><td>配方</td></tr></table></div>", 80, allow_full_fallback=False)
        self.assertEqual(summary, "")

    def test_summarize_parsed_html_supports_list_sections(self):
        summary = summarize_parsed_html(
            "<div><h3>影响</h3><ul><li>在地表的敌怪生成率有所提高，并且会生成更多敌怪。</li><li>夜晚氛围会发生变化。</li></ul></div>",
            80,
            allow_full_fallback=False,
        )
        self.assertEqual(summary, "在地表的敌怪生成率有所提高，并且会生成更多敌怪。")

    def test_select_key_sections_skips_notes(self):
        sections = select_key_sections(
            [
                {"index": "1", "line": "制作", "anchor": "制作", "toclevel": 1},
                {"index": "2", "line": "备注", "anchor": "备注", "toclevel": 1},
            ]
        )
        self.assertEqual([section["line"] for section in sections], ["制作"])

    def test_build_guide_sections_omits_blank_summaries(self):
        sections = build_guide_sections(
            "https://terraria.wiki.gg/zh/wiki/Guide:Walkthrough",
            [
                {"index": "1", "line": "开局", "anchor": "开局"},
                {"index": "2", "line": "备注", "anchor": "备注"},
            ],
            {"1": "先砍树，再建房。", "2": ""},
        )
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].title, "开局")
        self.assertIn("#", sections[0].url)


if __name__ == "__main__":
    unittest.main()
