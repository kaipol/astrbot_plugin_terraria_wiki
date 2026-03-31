import unittest

from terraria_wiki.structured_support import (
    build_structured_payload,
    format_recipe_summary,
    normalize_recipe_row,
    parse_ingredients,
    select_preferred_recipes,
)


class StructuredSupportTests(unittest.TestCase):
    def test_parse_ingredients_from_cargo_string(self):
        ingredients = parse_ingredients("¦铜锭¦7^¦木材¦2")
        self.assertEqual(ingredients, ["铜锭7", "木材2"])

    def test_normalize_recipe_row(self):
        recipe = normalize_recipe_row({"result": "铜短剑", "station": "铁砧", "ings": "¦铜锭¦7"})
        self.assertEqual(recipe.result, "铜短剑")
        self.assertEqual(recipe.station, "铁砧")
        self.assertEqual(recipe.ingredients, ["铜锭7"])

    def test_normalize_recipe_row_translates_known_station_names(self):
        recipe = normalize_recipe_row({"result": "真铜短剑", "station": "Shimmer", "ings": "¦天顶剑¦1"})
        self.assertEqual(recipe.station, "微光")

    def test_normalize_recipe_row_translates_combined_station_names(self):
        recipe = normalize_recipe_row({"result": "恐慌项链", "station": "Tinkerer's Workshop and Ecto Mist", "ings": "¦生命水晶¦1"})
        self.assertEqual(recipe.station, "工匠作坊 和 灵雾")

    def test_normalize_recipe_row_refines_hardmode_anvil_name(self):
        recipe = normalize_recipe_row({"result": "天顶剑", "station": "困难模式后的砧", "ings": "¦铜短剑¦1"})
        self.assertEqual(recipe.station, "秘银砧或山铜砧")

    def test_select_preferred_recipes_prioritizes_desktop_mobile(self):
        recipes = select_preferred_recipes(
            [
                {"result": "铜短剑", "amount": "1", "station": "铁砧", "ings": "¦铜锭¦7", "version": "old-gen 3ds", "legacy": "1"},
                {"result": "铜短剑", "amount": "1", "station": "铁砧", "ings": "¦铜锭¦5", "version": "desktop console mobile", "legacy": "0"},
            ]
        )
        self.assertEqual(recipes[0].ingredients, ["铜锭5"])
        self.assertEqual(recipes[0].version, "desktop console mobile")

    def test_build_structured_payload(self):
        payload = build_structured_payload(
            "铜短剑",
            [],
            [{"type": "近战武器", "damage": "5", "stack": "1", "sell": "12"}],
            [
                {"result": "铜短剑", "amount": "1", "station": "铁砧", "ings": "¦铜锭¦7", "version": "old-gen 3ds", "legacy": "1"},
                {"result": "铜短剑", "amount": "1", "station": "铁砧", "ings": "¦铜锭¦5", "version": "desktop console mobile", "legacy": "0"},
            ],
            [{"result": "天顶剑", "station": "秘银砧", "ings": "¦铜短剑¦1"}],
        )
        self.assertEqual(payload["entity_type"], "item")
        self.assertEqual(payload["infobox_fields"]["类型"], "近战武器")
        self.assertIn("伤害", payload["infobox_fields"])
        self.assertTrue(payload["recipes"])
        self.assertTrue(payload["used_in"])
        self.assertEqual(payload["recipes"][0].ingredients, ["铜锭5"])
        self.assertIn("配方：材料：铜锭 x5；产出：铜短剑 x1；制作站：铁砧", payload["structured_summary"])
        self.assertIn("用于：天顶剑", payload["structured_summary"])

    def test_build_structured_payload_prefers_primary_platform_fields(self):
        payload = build_structured_payload(
            "铜短剑",
            [],
            [{"type": "weapon^crafting material", "damage": "5 (电脑版、主机版、前代主机版、和移动版)^7 (3DS版)", "damagetype": "melee"}],
            [],
            [],
        )
        self.assertEqual(payload["infobox_fields"]["类型"], "武器 / 制作材料")
        self.assertEqual(payload["infobox_fields"]["伤害"], "5 (电脑版、主机版、前代主机版、和移动版)")
        self.assertEqual(payload["infobox_fields"]["伤害类型"], "近战")

    def test_build_structured_payload_translates_permanent_booster_type(self):
        payload = build_structured_payload(
            "生命水晶",
            [],
            [{"type": "permanent booster^crafting material", "usetime": "30"}],
            [],
            [],
        )
        self.assertEqual(payload["infobox_fields"]["类型"], "永久强化物品 / 制作材料")

    def test_build_structured_payload_separates_shimmer_transmutations(self):
        payload = build_structured_payload(
            "天顶剑",
            [],
            [{"type": "weapon", "damage": "190"}],
            [{"result": "天顶剑", "amount": "1", "station": "困难模式的砧", "ings": "¦铜短剑¦1"}],
            [{"result": "真铜短剑", "amount": "1", "station": "Shimmer", "ings": "¦天顶剑¦1"}],
        )
        self.assertEqual(payload["recipes"][0].station, "秘银砧或山铜砧")
        self.assertEqual(payload["used_in"], [])
        self.assertEqual(payload["transmutations"][0].result, "真铜短剑")


if __name__ == "__main__":
    unittest.main()
