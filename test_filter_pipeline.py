"""Regression tests for mandatory controls, their audit and bundled v2 data."""

from functools import lru_cache
from pathlib import Path
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

from drainage_data import (
    MasterData,
    discover_local_workbooks,
    filter_flat_input,
    load_all_workbooks,
    mandatory_requirements_from_filters,
    mandatory_requirements_table,
    prepare_benchmark_data,
)


ROOT = Path(__file__).resolve().parent


def prepare(frame):
    return prepare_benchmark_data(
        frame,
        pd.read_csv(ROOT / "config/classification_rules.csv", dtype="string", keep_default_na=False),
        pd.read_csv(ROOT / "config/length_rules.csv", dtype="string", keep_default_na=False),
    )


@lru_cache(maxsize=1)
def widget_master():
    rows = [
        ("a600", "maker-a", "linear_drain", "Alpha", 600, None, 0.8, 80, "yes", "system"),
        ("a800", "maker-a", "linear_drain", "Alpha", 800, None, 1.0, 90, "unknown", "system"),
        ("a900", "maker-a", "linear_drain", "Alpha", 900, None, None, None, "unknown", "system"),
        ("w300", "wedi", "integrated_shower_element_system", "Test integrated linear-drain systems", 1200, 300, 0.7, 60, "no", "system"),
        ("point", "maker-p", "point_drain", "Point", 1200, None, 0.6, 40, "no", "system"),
        ("blocked", "dallmer", "linear_drain", "Dallmer CeraWall Select N", 1300, None, 0.5, 70, "unknown", "system"),
        ("missing", "maker-unknown", "linear_drain", "Missing", None, None, None, None, None, "system"),
        ("pump", "jung-pumpen", "accessory", "Pump", 1800, None, 6.0, 300, "no", "component"),
    ]
    records = []
    for record_id, maker, category, family, length, channel, flow, height, v4a, entity in rows:
        records.append({
            "record_id": record_id,
            "system_key": record_id,
            "manufacturer_key": maker,
            "manufacturer_name": maker,
            "manufacturer_article_no": record_id,
            "product_category": category,
            "product_family_name": family,
            "model_name": record_id,
            "variant_name": record_id,
            "benchmark_entity_type": entity,
            "candidate_type": "complete_system" if entity == "system" else "component",
            "length_mm": length,
            "channel_length_mm": channel,
            "flow_rate_primary_lps": flow,
            "flow_rate_primary_head_mm": 10,
            "flow_rate_20mm_lps": None if flow is None else flow + 0.1,
            "height_adj_min_mm": height,
            "material_v4a": v4a,
            "point_top_shape": "square" if record_id == "point" else None,
        })
    return MasterData(
        flat=prepare(pd.DataFrame(records)),
        bom=pd.DataFrame(), evidence=pd.DataFrame(), warnings=[], source_count=1,
    )


APP_SCRIPT = """
from unittest.mock import patch
import streamlit as st
import app
from test_filter_pipeline import widget_master

def show_candidates(master, filtered, **kwargs):
    st.session_state['_test_candidates'] = filtered['record_id'].tolist()
    st.session_state['_test_payload'] = kwargs['filter_payload']

st.session_state['_test_candidates'] = []
with patch.object(app, 'load_master_data', return_value=widget_master()), \\
     patch.object(app, 'render_hierarchy_status'), \\
     patch.object(app, 'render_v2_data_status'), \\
     patch.object(app, 'render_single_parameter_ranking', side_effect=show_candidates), \\
     patch.object(app, 'render_multi_parameter_ranking', side_effect=show_candidates):
    app.main()
"""


class MandatoryWidgetTests(unittest.TestCase):
    """Run the real sidebar and final eligibility pipeline through Streamlit."""

    def setUp(self):
        self.at = AppTest.from_string(APP_SCRIPT, default_timeout=30)
        self.at.session_state["authenticated"] = True
        self.at.run()
        self.assert_ok()

    def assert_ok(self):
        self.assertEqual([error.message for error in self.at.exception], [])

    def drain_form(self, label):
        next(w for w in self.at.selectbox if w.label == "Drain form").select(label).run()
        self.assert_ok()

    def candidates(self):
        self.assert_ok()
        return set(self.at.session_state["_test_candidates"])

    def test_manufacturers_follow_scope_and_exclude_component_only_makers(self):
        self.assertNotIn("jung-pumpen", self.at.multiselect(key="manufacturer_filter").options)
        self.drain_form("Point drain")
        self.assertEqual(self.at.multiselect(key="manufacturer_filter").options, ["maker-p"])
        self.assertEqual(self.candidates(), {"point"})

    def test_length_filters_declared_exact_size_without_using_shower_panel_size(self):
        self.drain_form("Linear drain")
        self.at.checkbox(key="activate_length_requirement").check().run()
        self.at.slider(key="drain_length_range").set_value((800, 800)).run()
        self.assertEqual(self.candidates(), {"a800"})
        self.at.slider(key="drain_length_range").set_value((300, 300)).run()
        self.assertEqual(self.candidates(), {"w300"})
        self.assertEqual(self.at.session_state["_test_payload"]["length_range_mm"], [300.0, 300.0])

    def test_active_length_without_supported_bounds_returns_no_products(self):
        self.drain_form("Linear drain")
        self.at.multiselect(key="manufacturer_filter").set_value(["dallmer"]).run()
        self.at.checkbox(key="activate_length_requirement").check().run()
        self.assertEqual(self.candidates(), set())
        tables = [w.value for w in self.at.dataframe if "Requirement" in w.value.columns]
        self.assertTrue(any("Drain element length" in table["Requirement"].tolist() for table in tables))
        self.at.multiselect(key="manufacturer_filter").set_value(["wedi"]).run()
        self.assertEqual(self.candidates(), {"w300"})

    def test_flow_independent_of_length_uses_scoped_bounds_and_decimal_step(self):
        self.drain_form("Linear drain")
        self.at.checkbox(key="activate_flow_requirement").check().run()
        slider = self.at.slider(key="flow_range")
        self.assertEqual(slider.proto.max, 1.0)  # The component's 6 l/s is irrelevant.
        self.assertEqual(slider.proto.step, 0.01)
        slider.set_value((0.8, 1.0)).run()
        self.assertEqual(self.candidates(), {"a600", "a800"})
        self.assertIsNone(self.at.session_state["_test_payload"]["length_range_mm"])
        self.assertEqual(self.at.session_state["_test_payload"]["primary_flow_rate_range_lps"], [0.8, 1.0])

    def test_combined_length_and_flow_keep_inclusive_boundaries(self):
        self.drain_form("Linear drain")
        self.at.checkbox(key="activate_length_requirement").check().run()
        self.at.slider(key="drain_length_range").set_value((600, 800)).run()
        self.at.checkbox(key="activate_flow_requirement").check().run()
        self.at.slider(key="flow_range").set_value((0.8, 0.8)).run()
        self.assertEqual(self.candidates(), {"a600"})

    def test_scope_change_reconciles_ranges_and_inapplicable_length(self):
        self.drain_form("Linear drain")
        self.at.multiselect(key="manufacturer_filter").set_value(["maker-a"]).run()
        self.at.checkbox(key="activate_flow_requirement").check().run()
        self.at.slider(key="flow_range").set_value((0.8, 0.9)).run()
        self.at.multiselect(key="manufacturer_filter").set_value(["wedi"]).run()
        self.assertEqual(self.candidates(), {"w300"})
        self.drain_form("Point drain")
        self.assertEqual(self.candidates(), {"point"})
        self.assertFalse(self.at.session_state["_test_payload"]["require_length"])
        self.assertEqual(self.at.multiselect(key="manufacturer_filter").value, ["maker-p"])

    def test_active_flow_without_values_returns_no_products(self):
        self.drain_form("Linear drain")
        self.at.multiselect(key="manufacturer_filter").set_value(["maker-unknown"]).run()
        self.at.checkbox(key="activate_flow_requirement").check().run()
        self.assertEqual(self.candidates(), set())
        self.at.checkbox(key="activate_flow_requirement").uncheck().run()
        self.assertEqual(self.candidates(), {"missing"})

    def test_empty_selection_remains_empty_in_result_and_audit(self):
        self.at.multiselect(key="manufacturer_filter").set_value([]).run()
        self.assertEqual(self.candidates(), set())
        tables = [w.value for w in self.at.dataframe if "Requirement" in w.value.columns]
        manufacturer = next(t[t["Requirement"].eq("Manufacturer")] for t in tables if t["Requirement"].eq("Manufacturer").any())
        self.assertEqual(manufacturer.iloc[0]["Value"], "None selected")

    def test_upstream_change_removes_invalid_material_selection(self):
        self.drain_form("Linear drain")
        self.at.multiselect(key="attribute_material_v4a").set_value(["yes"]).run()
        self.assertEqual(self.candidates(), {"a600"})
        self.at.multiselect(key="manufacturer_filter").set_value(["wedi"]).run()
        self.assertEqual(self.at.multiselect(key="attribute_material_v4a").value, ["no"])
        self.assertEqual(self.candidates(), {"w300"})

    def test_ranking_method_and_weights_do_not_change_eligibility(self):
        self.drain_form("Linear drain")
        self.at.checkbox(key="activate_flow_requirement").check().run()
        self.at.slider(key="flow_range").set_value((0.8, 1.0)).run()
        expected = self.candidates()
        next(w for w in self.at.radio if w.label == "Result method").set_value("Multi-parameter ranking").run()
        self.assertEqual(self.candidates(), expected)
        weight_slider = next(w for w in self.at.slider if str(w.key).startswith("multi_weight_"))
        weight_slider.set_value(9).run()
        self.assertEqual(self.candidates(), expected)


class BundledFilterIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = load_all_workbooks(discover_local_workbooks(ROOT / "data"))
        cls.frame = prepare(cls.master.flat)

    def filtered(self, **kwargs):
        settings = dict(include_incomplete=False, manufacturers=None, flow_range=None,
                        height_range=None, attribute_filters={}, drain_forms=["linear"])
        settings.update(kwargs)
        return filter_flat_input(self.frame, **settings)

    def test_wedi_channels_participate_as_exact_lengths(self):
        wedi = self.filtered(manufacturers=["wedi"])
        declared = pd.to_numeric(wedi["channel_length_mm"], errors="coerce").gt(0)
        self.assertEqual(int(declared.sum()), 720)
        self.assertTrue(wedi.loc[declared, "length_filter_ready"].eq("yes").all())
        self.assertTrue(wedi.loc[declared, "length_min_mm"].eq(wedi.loc[declared, "length_max_mm"]).all())
        exact = self.filtered(manufacturers=["wedi"], length_range=(300, 300), require_length=True)
        self.assertGreater(len(exact), 0)
        self.assertTrue(exact["drain_element_length_mm"].eq(300).all())
        self.assertFalse(exact["nominal_length_mm"].eq(300).all())

    def test_length_and_flow_ranges_filter_the_actual_bundled_selection(self):
        for kwargs in (
            {"length_range": (700, 800)},
            {"flow_range": (0.8, 1.0)},
            {"length_range": (700, 800), "flow_range": (0.8, 1.0)},
        ):
            with self.subTest(kwargs=kwargs):
                result = self.filtered(**kwargs)
                self.assertFalse(result.empty)
                self.assertTrue(result["mapped_drain_form"].eq("linear").all())
                if "length_range" in kwargs:
                    self.assertTrue(result["length_filter_ready"].eq("yes").all())
                    self.assertTrue(result["length_max_mm"].ge(700).all())
                    self.assertTrue(result["length_min_mm"].le(800).all())
                if "flow_range" in kwargs:
                    self.assertTrue(pd.to_numeric(result["flow_rate_primary_lps"]).between(0.8, 1.0).all())

    def test_longer_shortenable_profiles_explain_their_supported_range(self):
        result = self.filtered(length_range=(800, 800))
        longer = result[result["drain_element_length_mm"].gt(800)]
        self.assertFalse(longer.empty)
        self.assertTrue(longer["length_min_mm"].le(800).all())
        self.assertTrue(longer["supported_length_label"].str.contains("verified range", regex=False).all())
        declared = result[result["length_mode"].eq("declared_exact_only")]
        self.assertTrue(declared["drain_element_length_mm"].eq(800).all())
        self.assertTrue(declared["supported_length_label"].str.contains("declared exact", regex=False).all())

    def test_approved_length_restrictions_remain_blocked(self):
        blocked = self.frame[self.frame["length_rule_id"].isin(
            ["L014_DALLMER_CERAWALL_SELECT_N_DUO", "L015_DALLMER_CERAWALL_SELECT_N"]
        )]
        self.assertGreater(len(blocked), 0)
        self.assertTrue(blocked["length_filter_ready"].eq("no").all())

    def test_integrated_linear_overall_length_never_substitutes_for_channel(self):
        integrated = self.frame[
            self.frame["mapped_drain_form"].eq("linear")
            & self.frame["mapped_solution_type"].isin(["integrated_shower_element", "heat_recovery_shower_system"])
        ]
        absent = pd.to_numeric(integrated["channel_length_mm"], errors="coerce").isna()
        self.assertGreater(int(absent.sum()), 0)
        self.assertTrue(integrated.loc[absent, "drain_element_length_mm"].isna().all())

    def test_active_unavailable_requirements_are_present_in_audit(self):
        requirements = mandatory_requirements_from_filters({
            "require_length": True, "required_numeric_fields": ["flow_rate_primary_lps"],
            "manufacturers": [],
        })
        fields = {row["field"] for row in requirements}
        self.assertTrue({"installable_length_mm", "flow_rate_primary_lps", "manufacturer_key"}.issubset(fields))
        table = mandatory_requirements_table(requirements).set_index("Field")
        self.assertEqual(table.loc["manufacturer_key", "Value"], "None selected")


if __name__ == "__main__":
    unittest.main()
