import unittest

from terraria_wiki.models import LookupResult, StructuredRecipe, WikiArticle
from terraria_wiki.rendering import format_card_text, format_plain_text


class RenderingTests(unittest.TestCase):
    def test_format_card_text_contains_footer(self):
        result = LookupResult(article=WikiArticle(title="泰拉瑞亚", extract="沙盒游戏"), exact_match=True)
        text = format_card_text(result)
        self.assertIn("Terraria Wiki", text)
        self.assertIn("原链接：", text)

    def test_format_plain_text_shows_alternatives(self):
        result = LookupResult(
            article=WikiArticle(title="泰拉瑞亚", extract="沙盒游戏"),
            alternative_titles=["泰拉棱镜"],
            exact_match=False,
        )
        text = format_plain_text(result)
        self.assertIn("可能还想查：泰拉棱镜", text)

    def test_format_plain_text_shows_structured_summary(self):
        article = WikiArticle(
            title="铜短剑",
            extract="近战武器",
            structured_summary=["类型：近战武器", "伤害：5", "配方：材料：铜锭 x5；产出：铜短剑 x1；制作站：铁砧", "用于：铜宽剑"],
            recipes=[StructuredRecipe(result="铜短剑", amount="1", station="铁砧", ingredients=["铜锭5"])],
            used_in=[StructuredRecipe(result="铜宽剑", station="铁砧", ingredients=["铜短剑1"])],
            transmutations=[StructuredRecipe(result="真铜短剑", amount="1", station="微光", ingredients=["铜短剑1"])],
        )
        result = LookupResult(article=article, exact_match=True)
        text = format_plain_text(result)
        self.assertIn("核心属性", text)
        self.assertIn("类型：近战武器", text)
        self.assertIn("配方：\n- 材料：铜锭 x5\n- 产出：铜短剑 x1\n- 制作站：铁砧", text)
        self.assertIn("用于：\n- 铜宽剑（制作站：铁砧）", text)
        self.assertIn("微光嬗变：\n- 真铜短剑 x1", text)
        self.assertEqual(text.count("配方："), 1)

    def test_format_card_text_shows_recipe_details(self):
        article = WikiArticle(
            title="铜短剑",
            extract="近战武器",
            recipes=[StructuredRecipe(result="铜短剑", amount="1", station="铁砧", ingredients=["铜锭5"])],
            used_in=[StructuredRecipe(result="铜宽剑", station="铁砧", ingredients=["铜短剑1"])],
            transmutations=[StructuredRecipe(result="真铜短剑", amount="1", station="微光", ingredients=["铜短剑1"])],
        )
        result = LookupResult(article=article, exact_match=True)
        text = format_card_text(result)
        self.assertIn("核心属性：", text)
        self.assertIn("配方：", text)
        self.assertIn("· 材料：铜锭 x5", text)
        self.assertIn("用于：", text)
        self.assertIn("· 铜宽剑", text)
        self.assertIn("微光嬗变：", text)
        self.assertIn("· 真铜短剑 x1", text)

    def test_format_plain_text_prefers_structured_over_guide_sections(self):
        article = WikiArticle(
            title="泰拉刃",
            extract="武器摘要",
            guide_like=True,
            guide_sections=[],
            structured_summary=["类型：武器"],
            recipes=[StructuredRecipe(result="泰拉刃", amount="1", station="秘银砧或山铜砧", ingredients=["断裂英雄剑1", "真断钢剑1", "真永夜刃1"])],
            used_in=[StructuredRecipe(result="天顶剑", amount="1", station="秘银砧或山铜砧")],
        )
        result = LookupResult(article=article, exact_match=True)
        text = format_plain_text(result)
        self.assertIn("核心属性：", text)
        self.assertIn("配方：", text)
        self.assertIn("用于：", text)
        self.assertNotIn("关键章节：", text)


if __name__ == "__main__":
    unittest.main()
