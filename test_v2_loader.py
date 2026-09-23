from pathlib import Path
import unittest

import pandas as pd

from drainage_data import (
    filter_flat_input,
    load_all_workbooks,
    prepare_benchmark_data,
)


ROOT = Path(__file__).resolve().parent
WEDI = ROOT / "data" / "WEDI_FINAL_v2_TECHNICAL_LOCK.xlsx"


class V2LoaderIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not WEDI.exists():
            raise unittest.SkipTest("WEDI v2 integration workbook is not present")
        stats = WEDI.stat()
        cls.master = load_all_workbooks(((str(WEDI), stats.st_mtime_ns, stats.st_size),))
        classification = pd.read_csv(
            ROOT / "config" / "classification_rules.csv",
            dtype="string",
            keep_default_na=False,
        )
        length_rules = pd.read_csv(
            ROOT / "config" / "length_rules.csv",
            dtype="string",
            keep_default_na=False,
        )
        cls.prepared = prepare_benchmark_data(
            cls.master.flat, classification, length_rules
        )

    def test_secondary_archive_layers_are_loaded_with_expected_wedi_counts(self):
        master = self.master
        self.assertEqual(len(master.flat), 2142)
        self.assertEqual(len(master.bom), 3597)
        self.assertEqual(len(master.evidence), 36117)
        self.assertEqual(len(master.prices), 794)
        self.assertEqual(len(master.hydraulics), 1234)
        self.assertEqual(len(master.technical), 23639)
        self.assertEqual(len(master.technical_audit), 1398)
        self.assertEqual(len(master.record_lifecycle), 2142)
        self.assertEqual(len(master.controlled_gaps), 738)
        self.assertEqual(master.warnings, [])

    def test_archive_contract_is_reported_for_diagnostics(self):
        metadata = self.master.workbook_metadata.iloc[0]
        self.assertEqual(
            metadata["archive_contract"],
            "WEDI_COMBINED_SECONDARY_ARCHIVE_BZ2_V2_CONTROLLED_REBASE_20260922",
        )
        self.assertEqual(int(metadata["archive_layers_loaded"]), 12)

    def test_wedi_systems_classify_to_linear_or_point_without_unknowns(self):
        systems = self.prepared[
            self.prepared["benchmark_entity_type"]
            .astype("string")
            .str.casefold()
            .eq("system")
        ]
        self.assertEqual(len(systems), 1398)
        self.assertEqual(set(systems["mapped_drain_form"].dropna()), {"linear", "point"})
        self.assertEqual(int(systems["mapped_drain_form"].eq("linear").sum()), 727)
        self.assertEqual(int(systems["mapped_drain_form"].eq("point").sum()), 671)
        self.assertEqual(int(systems["leaderboard_visibility"].eq("active").sum()), 1398)

    def test_point_specific_v2_fields_are_projected_to_application_view(self):
        flat = self.prepared
        self.assertIn("point_top_shape", flat.columns)
        self.assertIn("visible_grate_diameter_mm", flat.columns)
        self.assertIn("overall_body_diameter_mm", flat.columns)
        self.assertIn("channel_length_mm", flat.columns)
        self.assertGreater(int(flat["point_top_shape"].notna().sum()), 0)
        self.assertGreater(int(flat["channel_length_mm"].notna().sum()), 0)

        point_systems = flat[
            flat["benchmark_entity_type"].astype("string").str.casefold().eq("system")
            & flat["mapped_drain_form"].eq("point")
        ]
        self.assertEqual(int(point_systems["drain_element_length_mm"].notna().sum()), 0)

    def test_solution_type_and_point_numeric_filters_work_together(self):
        filtered = filter_flat_input(
            self.prepared,
            include_incomplete=False,
            manufacturers=["wedi"],
            flow_range=None,
            height_range=None,
            attribute_filters={"point_top_shape": ["round"]},
            drain_forms=["point"],
            solution_types=["drainage_system"],
            numeric_filters={"visible_grate_diameter_mm": (115.0, 115.0)},
        )
        self.assertFalse(filtered.empty)
        self.assertTrue(filtered["mapped_drain_form"].eq("point").all())
        self.assertTrue(filtered["mapped_solution_type"].eq("drainage_system").all())
        self.assertTrue(filtered["point_top_shape"].astype("string").eq("round").all())

    def test_price_layer_fills_only_missing_flat_prices(self):
        systems = self.master.flat[
            self.master.flat["benchmark_entity_type"]
            .astype("string")
            .str.casefold()
            .eq("system")
        ]
        self.assertEqual(int(systems["sales_price_value"].notna().sum()), 78)
        self.assertEqual(int(systems["sales_price_basis"].notna().sum()), 35)


if __name__ == "__main__":
    unittest.main()
