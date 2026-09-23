import unittest

import pandas as pd

from drainage_data import (
    add_point_drain_geometry_columns,
    add_product_hierarchy_keys,
    advanced_scoring_audit_tables,
    aggregate_presentation_groups,
    build_ranking_request,
    concatenate_and_deduplicate,
    execute_ranking_request,
    execute_reference_product_comparison,
    filter_reference_comparables,
    filter_flat_input,
    hierarchy_audit_tables,
    hierarchy_summary,
    mandatory_requirements_from_filters,
    mandatory_requirements_table,
    multi_parameter_weight_column,
    normalise_ranking_weights,
    rank_multiple_parameters,
    rank_single_parameter,
    ranking_request_tables,
    related_rows,
    score_advanced_product_groups,
    score_filtered_systems,
)


class DrainageDataTests(unittest.TestCase):

    def test_point_geometry_normalisation_uses_only_explicit_point_fields(self):
        frame = pd.DataFrame(
            [
                {
                    "mapped_drain_form": "point",
                    "visible_grate_length_mm": 100,
                    "visible_grate_width_mm": 90,
                    "length_mm": 120,
                    "width_mm": 120,
                },
                {
                    "mapped_drain_form": "point",
                    "visible_grate_length_mm": 120,
                    "visible_grate_width_mm": 120,
                    "grate_diameter_mm": 120,
                },
                {
                    "mapped_drain_form": "point",
                    "length_mm": 150,
                    "width_mm": 150,
                },
            ]
        )

        enriched = add_point_drain_geometry_columns(frame)

        self.assertEqual(enriched.loc[0, "point_grate_size"], "100 × 90 mm")
        self.assertEqual(enriched.loc[1, "point_grate_size"], "Ø120 mm")
        self.assertTrue(pd.isna(enriched.loc[2, "point_grate_size"]))
        self.assertTrue(pd.isna(enriched.loc[2, "point_grate_length_mm"]))
        self.assertTrue(pd.isna(enriched.loc[2, "point_grate_width_mm"]))

    def test_point_geometry_conflicts_remain_blank_and_are_traceable(self):
        frame = pd.DataFrame(
            [
                {
                    "mapped_drain_form": "point",
                    "visible_grate_diameter_mm": 120,
                    "grate_diameter_mm": 115,
                }
            ]
        )

        enriched = add_point_drain_geometry_columns(frame)

        self.assertTrue(pd.isna(enriched.loc[0, "point_grate_diameter_mm"]))
        self.assertTrue(pd.isna(enriched.loc[0, "point_grate_size"]))
        self.assertTrue(
            str(enriched.loc[0, "point_grate_diameter_mm_source"]).startswith("conflict:")
        )

    def test_concatenation_deduplicates_required_keys(self):
        flat, bom, evidence = concatenate_and_deduplicate(
            {
                "flat": [
                    pd.DataFrame(
                        [
                            {"record_id": "001", "variant_name": "first"},
                            {"record_id": "001", "variant_name": "duplicate"},
                        ]
                    )
                ],
                "bom": [
                    pd.DataFrame(
                        [
                            {"parent_system_key": "001", "component_article_no": "0001"},
                            {"parent_system_key": "001", "component_article_no": "0001"},
                        ]
                    )
                ],
                "evidence": [
                    pd.DataFrame(
                        [
                            {"linked_record_id": "001", "source_url": "https://one"},
                            {"linked_record_id": "001", "source_url": "https://two"},
                        ]
                    )
                ],
            }
        )

        self.assertEqual(flat.to_dict("records"), [{"record_id": "001", "variant_name": "first"}])
        self.assertEqual(len(bom), 1)
        self.assertEqual(
            evidence.to_dict("records"),
            [
                {"linked_record_id": "001", "source_url": "https://one"},
                {"linked_record_id": "001", "source_url": "https://two"},
            ],
        )


    def test_evidence_deduplication_keeps_distinct_fields_and_removes_exact_duplicates(self):
        _, _, evidence = concatenate_and_deduplicate(
            {
                "evidence": [
                    pd.DataFrame(
                        [
                            {
                                "linked_record_id": "001",
                                "field_name": "flow_rate_20mm_lps",
                                "normalized_value": "0.8",
                                "source_url": "https://example",
                                "source_excerpt": "0.8 l/s at 20 mm",
                            },
                            {
                                "linked_record_id": "001",
                                "field_name": "flow_rate_20mm_lps",
                                "normalized_value": "0.8",
                                "source_url": "https://example",
                                "source_excerpt": "0.8 l/s at 20 mm",
                            },
                            {
                                "linked_record_id": "001",
                                "field_name": "water_seal_mm",
                                "normalized_value": "50",
                                "source_url": "https://example",
                                "source_excerpt": "Water seal 50 mm",
                            },
                        ]
                    )
                ]
            }
        )

        self.assertEqual(len(evidence), 2)
        self.assertEqual(
            evidence["field_name"].tolist(),
            ["flow_rate_20mm_lps", "water_seal_mm"],
        )

    def test_filters_keep_missing_numeric_values_until_a_range_is_restricted(self):
        source = pd.DataFrame(
            [
                {"record_id": "A", "candidate_type": "complete_system", "flow_rate_primary_lps": 0.5},
                {"record_id": "B", "candidate_type": "assembled_system", "flow_rate_primary_lps": None},
                {"record_id": "C", "candidate_type": "component", "flow_rate_primary_lps": 0.8},
            ]
        )

        no_range = filter_flat_input(
            source,
            include_incomplete=False,
            manufacturers=None,
            flow_range=None,
            height_range=None,
            attribute_filters={},
        )
        restricted_range = filter_flat_input(
            source,
            include_incomplete=False,
            manufacturers=None,
            flow_range=(0.4, 0.6),
            height_range=None,
            attribute_filters={},
        )

        self.assertEqual(no_range["record_id"].tolist(), ["A", "B"])
        self.assertEqual(restricted_range["record_id"].tolist(), ["A"])

    def test_scoring_uses_current_filtered_minimum_and_maximum_and_missing_is_zero(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "A",
                    "flow_rate_primary_lps": 0.4,
                    "height_adj_min_mm": 50,
                    "material_v4a": "yes",
                    "sales_price_value": 100,
                    "colours_count": 1,
                },
                {
                    "record_id": "B",
                    "flow_rate_primary_lps": 0.8,
                    "height_adj_min_mm": 100,
                    "material_v4a": "unknown",
                    "sales_price_value": 200,
                    "colours_count": None,
                },
            ]
        )
        weights = {
            "flow_rate": 1,
            "installation_height": 1,
            "v4a": 1,
            "sales_price": 1,
            "colours": 1,
        }

        scored = score_filtered_systems(source, weights).set_index("record_id")

        self.assertEqual(scored.loc["A", "Final_Score_%"], 80)
        self.assertEqual(scored.loc["B", "Final_Score_%"], 20)

    def test_advanced_scoring_collapses_finishes_and_uses_group_values(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "a-black",
                    "manufacturer_key": "maker",
                    "manufacturer_name": "Maker",
                    "product_family_key": "family",
                    "model_key": "model-a",
                    "model_name": "Model A",
                    "candidate_type": "assembled_system",
                    "nominal_length_mm": 900,
                    "flow_rate_primary_lps": 0.8,
                    "height_adj_min_mm": 60,
                    "material_v4a": "yes",
                    "sales_price_value": 120,
                    "sales_price_currency": "EUR",
                    "colours_count": None,
                    "finish_name": "Black",
                },
                {
                    "record_id": "a-white",
                    "manufacturer_key": "maker",
                    "manufacturer_name": "Maker",
                    "product_family_key": "family",
                    "model_key": "model-a",
                    "model_name": "Model A",
                    "candidate_type": "assembled_system",
                    "nominal_length_mm": 900,
                    "flow_rate_primary_lps": 0.8,
                    "height_adj_min_mm": 60,
                    "material_v4a": "yes",
                    "sales_price_value": 100,
                    "sales_price_currency": "EUR",
                    "colours_count": None,
                    "finish_name": "White",
                },
                {
                    "record_id": "b-steel",
                    "manufacturer_key": "maker",
                    "manufacturer_name": "Maker",
                    "product_family_key": "family",
                    "model_key": "model-b",
                    "model_name": "Model B",
                    "candidate_type": "assembled_system",
                    "nominal_length_mm": 900,
                    "flow_rate_primary_lps": 0.7,
                    "height_adj_min_mm": 55,
                    "material_v4a": "unknown",
                    "sales_price_value": 90,
                    "sales_price_currency": "EUR",
                    "colours_count": 1,
                    "finish_name": "Steel",
                },
            ]
        )
        weights = {
            "flow_rate": 0,
            "installation_height": 0,
            "v4a": 0,
            "sales_price": 1,
            "colours": 1,
        }

        scored, members = score_advanced_product_groups(source, weights)

        self.assertEqual(len(scored), 2)
        self.assertEqual(len(members), 3)
        model_a = scored.loc[scored["model_name"].eq("Model A")].iloc[0]
        self.assertEqual(model_a["group_member_count"], 2)
        self.assertEqual(model_a["sales_price_value"], 100)
        self.assertEqual(model_a["sales_price_currency"], "EUR")
        self.assertEqual(model_a["colours_count"], 2)
        self.assertEqual(
            model_a["sales_price_group_basis"],
            "minimum observed article/finish price",
        )
        self.assertEqual(
            model_a["colours_count_source"],
            "grouped finish variants fallback",
        )

    def test_advanced_require_complete_excludes_missing_active_metrics(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "complete",
                    "flow_rate_primary_lps": 1.0,
                    "height_adj_min_mm": 50,
                },
                {
                    "record_id": "missing-height",
                    "flow_rate_primary_lps": 1.2,
                    "height_adj_min_mm": None,
                },
            ]
        )
        weights = {
            "flow_rate": 9,
            "installation_height": 1,
            "v4a": 0,
            "sales_price": 0,
            "colours": 0,
        }

        scored = score_filtered_systems(
            source,
            weights,
            missing_data_policy="require_complete",
        )

        self.assertEqual(scored["record_id"].tolist(), ["complete"])
        self.assertEqual(scored.iloc[0]["Data_Completeness_%"], 100.0)
        self.assertEqual(scored.iloc[0]["Available_Criteria"], 2)
        self.assertEqual(scored.iloc[0]["Required_Criteria"], 2)
        self.assertEqual(scored.iloc[0]["Missing_Ranking_Fields"], "")
        self.assertEqual(scored.iloc[0]["Final_Score_%"], 100.0)

    def test_advanced_zero_score_keeps_incomplete_products_and_reports_completeness(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "complete",
                    "flow_rate_primary_lps": 1.0,
                    "height_adj_min_mm": 50,
                },
                {
                    "record_id": "missing-height",
                    "flow_rate_primary_lps": 1.2,
                    "height_adj_min_mm": None,
                },
            ]
        )
        weights = {
            "flow_rate": 9,
            "installation_height": 1,
            "v4a": 0,
            "sales_price": 0,
            "colours": 0,
        }

        scored = score_filtered_systems(
            source,
            weights,
            missing_data_policy="allow_incomplete_zero_score",
        ).set_index("record_id")

        self.assertEqual(len(scored), 2)
        self.assertEqual(scored.loc["missing-height", "Data_Completeness_%"], 50.0)
        self.assertEqual(
            scored.loc["missing-height", "Weighted_Data_Completeness_%"],
            90.0,
        )
        self.assertEqual(
            scored.loc["missing-height", "Missing_Ranking_Fields"],
            "height_adj_min_mm",
        )
        self.assertEqual(scored.loc["missing-height", "Final_Score_%"], 90.0)

    def test_advanced_proportional_penalty_uses_available_score_and_count_completeness(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "complete",
                    "flow_rate_primary_lps": 1.0,
                    "height_adj_min_mm": 50,
                },
                {
                    "record_id": "missing-height",
                    "flow_rate_primary_lps": 1.2,
                    "height_adj_min_mm": None,
                },
            ]
        )
        weights = {
            "flow_rate": 9,
            "installation_height": 1,
            "v4a": 0,
            "sales_price": 0,
            "colours": 0,
        }

        scored = score_filtered_systems(
            source,
            weights,
            missing_data_policy="allow_incomplete_proportional_penalty",
        ).set_index("record_id")

        self.assertEqual(
            scored.loc["missing-height", "Score_Before_Completeness_Penalty_%"],
            100.0,
        )
        self.assertEqual(
            scored.loc["missing-height", "Completeness_Penalty_Factor"],
            0.5,
        )
        self.assertEqual(scored.loc["missing-height", "Final_Score_%"], 50.0)

    def test_advanced_group_price_with_mixed_currencies_is_not_scored(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "eur",
                    "manufacturer_key": "maker",
                    "product_family_key": "family",
                    "model_key": "model",
                    "nominal_length_mm": 900,
                    "sales_price_value": 100,
                    "sales_price_currency": "EUR",
                    "finish_name": "Black",
                },
                {
                    "record_id": "usd",
                    "manufacturer_key": "maker",
                    "product_family_key": "family",
                    "model_key": "model",
                    "nominal_length_mm": 900,
                    "sales_price_value": 90,
                    "sales_price_currency": "USD",
                    "finish_name": "White",
                },
            ]
        )

        scored, _ = score_advanced_product_groups(
            source,
            {
                "flow_rate": 0,
                "installation_height": 0,
                "v4a": 0,
                "sales_price": 1,
                "colours": 0,
            },
        )
        row = scored.iloc[0]

        self.assertTrue(pd.isna(row["sales_price_value"]))
        self.assertEqual(row["sales_price_currency_count"], 2)
        self.assertEqual(row["Score_Sales_Price_%"], 0)
        self.assertEqual(
            row["sales_price_group_basis"],
            "mixed currencies; excluded from price score",
        )

    def test_advanced_scoring_audit_links_exact_variants_to_group_rank(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "black",
                    "manufacturer_key": "maker",
                    "product_family_key": "family",
                    "model_key": "model",
                    "nominal_length_mm": 900,
                    "flow_rate_primary_lps": 0.8,
                    "finish_name": "Black",
                },
                {
                    "record_id": "white",
                    "manufacturer_key": "maker",
                    "product_family_key": "family",
                    "model_key": "model",
                    "nominal_length_mm": 900,
                    "flow_rate_primary_lps": 0.8,
                    "finish_name": "White",
                },
            ]
        )
        weights = {
            "flow_rate": 1,
            "installation_height": 0,
            "v4a": 0,
            "sales_price": 0,
            "colours": 0,
        }
        scored, members = score_advanced_product_groups(source, weights)
        scored = scored.sort_values("Final_Score_%", ascending=False).reset_index(drop=True)
        scored.insert(0, "Rank", range(1, len(scored) + 1))

        tables = advanced_scoring_audit_tables(scored, members, weights)

        self.assertEqual(
            set(tables),
            {
                "Advanced_Leaderboard",
                "Advanced_Settings",
                "Advanced_Weights",
                "Ranked_Variants",
            },
        )
        self.assertEqual(
            tables["Advanced_Settings"].iloc[0]["missing_data_policy"],
            "allow_incomplete_zero_score",
        )
        self.assertEqual(len(tables["Advanced_Leaderboard"]), 1)
        self.assertEqual(len(tables["Ranked_Variants"]), 2)
        self.assertTrue(tables["Ranked_Variants"]["Rank"].eq(1).all())
        self.assertAlmostEqual(
            tables["Advanced_Weights"]["normalised_weight_percent"].sum(),
            100.0,
        )

    def test_finish_variants_are_grouped_but_technical_variants_remain_separate(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "black",
                    "manufacturer_key": "maker",
                    "manufacturer_name": "Maker",
                    "model_key": "model",
                    "model_name": "Model",
                    "candidate_type": "assembled_system",
                    "nominal_length_mm": 900,
                    "height_adj_min_mm": 60,
                    "flow_rate_primary_lps": 0.8,
                    "finish_name": "Black",
                    "product_url": "https://example/product",
                },
                {
                    "record_id": "white",
                    "manufacturer_key": "maker",
                    "manufacturer_name": "Maker",
                    "model_key": "model",
                    "model_name": "Model",
                    "candidate_type": "assembled_system",
                    "nominal_length_mm": 900,
                    "height_adj_min_mm": 60,
                    "flow_rate_primary_lps": 0.8,
                    "finish_name": "White",
                    "product_url": "https://example/product",
                },
                {
                    "record_id": "flat",
                    "manufacturer_key": "maker",
                    "manufacturer_name": "Maker",
                    "model_key": "model",
                    "model_name": "Model",
                    "candidate_type": "assembled_system",
                    "nominal_length_mm": 900,
                    "height_adj_min_mm": 45,
                    "flow_rate_primary_lps": 0.6,
                    "finish_name": "Black",
                    "product_url": "https://example/product",
                },
            ]
        )

        groups, members = aggregate_presentation_groups(source)

        self.assertEqual(len(groups), 2)
        self.assertEqual(len(members), 3)
        grouped_regular = groups.loc[groups["height_adj_min_mm"].eq(60)].iloc[0]
        self.assertEqual(grouped_regular["finish_variant_count"], 2)
        self.assertEqual(grouped_regular["article_variant_count"], 2)
        self.assertEqual(grouped_regular["available_finishes"], "Black; White")
        self.assertEqual(grouped_regular["product_link"], "https://example/product")

    def test_single_parameter_ranking_orders_and_excludes_missing_values(self):
        source = pd.DataFrame(
            [
                {"record_id": "A", "manufacturer_name": "A", "model_name": "A", "flow": 0.8},
                {"record_id": "B", "manufacturer_name": "B", "model_name": "B", "flow": None},
                {"record_id": "C", "manufacturer_name": "C", "model_name": "C", "flow": 1.2},
            ]
        )

        ranked = rank_single_parameter(
            source, "flow", higher_is_better=True
        )

        self.assertEqual(ranked["record_id"].tolist(), ["C", "A"])
        self.assertEqual(ranked["Rank"].tolist(), [1, 2])
        self.assertEqual(ranked["Ranking_Score_%"].tolist(), [100.0, 0.0])

    def test_multi_parameter_ranking_finds_best_equal_weight_combination(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "A",
                    "manufacturer_name": "A",
                    "model_name": "A",
                    "flow": 1.0,
                    "height": 100,
                },
                {
                    "record_id": "B",
                    "manufacturer_name": "B",
                    "model_name": "B",
                    "flow": 0.8,
                    "height": 60,
                },
                {
                    "record_id": "C",
                    "manufacturer_name": "C",
                    "model_name": "C",
                    "flow": 0.6,
                    "height": 40,
                },
                {
                    "record_id": "missing",
                    "manufacturer_name": "D",
                    "model_name": "D",
                    "flow": 1.2,
                    "height": None,
                },
            ]
        )

        ranked = rank_multiple_parameters(
            source,
            {"flow": True, "height": False},
        )

        self.assertEqual(ranked["record_id"].tolist(), ["B", "A", "C"])
        self.assertEqual(ranked["Rank"].tolist(), [1, 2, 3])
        self.assertAlmostEqual(ranked.loc[0, "Ranking_Score_%"], 58.3333333333)
        self.assertNotIn("missing", ranked["record_id"].tolist())

    def test_multi_parameter_ranking_supports_future_custom_weights(self):
        source = pd.DataFrame(
            [
                {"record_id": "flow", "flow": 1.0, "height": 100},
                {"record_id": "balanced", "flow": 0.8, "height": 60},
                {"record_id": "height", "flow": 0.6, "height": 40},
            ]
        )

        ranked = rank_multiple_parameters(
            source,
            {"flow": True, "height": False},
            weights={"flow": 3, "height": 1},
        )

        self.assertEqual(ranked.iloc[0]["record_id"], "flow")


    def test_ranking_weights_are_normalised_and_auditable(self):
        criteria = {"flow": True, "height": False}

        normalised = normalise_ranking_weights(
            criteria,
            weights={"flow": 7, "height": 3},
        )

        self.assertAlmostEqual(normalised["flow"], 0.7)
        self.assertAlmostEqual(normalised["height"], 0.3)

        source = pd.DataFrame(
            [
                {"record_id": "flow", "flow": 1.0, "height": 100},
                {"record_id": "balanced", "flow": 0.8, "height": 60},
                {"record_id": "height", "flow": 0.6, "height": 40},
            ]
        )
        ranked = rank_multiple_parameters(
            source,
            criteria,
            weights={"flow": 7, "height": 3},
        )

        self.assertEqual(ranked.iloc[0]["record_id"], "flow")
        self.assertAlmostEqual(
            ranked.iloc[0][multi_parameter_weight_column("flow")],
            70.0,
        )
        self.assertAlmostEqual(
            ranked.iloc[0][multi_parameter_weight_column("height")],
            30.0,
        )
        self.assertAlmostEqual(ranked.iloc[0]["Ranking_Weight_Sum_%"], 100.0)

    def test_zero_ranking_weights_fall_back_to_equal_weights(self):
        normalised = normalise_ranking_weights(
            {"flow": True, "height": False},
            weights={"flow": 0, "height": 0},
        )

        self.assertEqual(normalised, {"flow": 0.5, "height": 0.5})

    def test_structured_multi_parameter_request_is_normalised_and_executable(self):
        request = build_ranking_request(
            mode="multi_parameter",
            criteria={"flow": True, "height": False},
            weights={"flow": 7, "height": 3},
            criterion_labels={"flow": "Flow rate", "height": "Installation height"},
            top_n=2,
            filters={"drain_form": "linear", "manufacturers": ["all"]},
        )

        self.assertEqual(request["schema_version"], "1.1")
        self.assertEqual(request["criteria"][0]["normalised_weight"], 0.7)
        self.assertEqual(request["criteria"][1]["normalised_weight"], 0.3)
        self.assertEqual(
            request["mandatory_requirements"][0]["field"],
            "mapped_drain_form",
        )

        source = pd.DataFrame(
            [
                {"record_id": "flow", "flow": 1.0, "height": 100},
                {"record_id": "balanced", "flow": 0.8, "height": 60},
                {"record_id": "height", "flow": 0.6, "height": 40},
            ]
        )
        execution = execute_ranking_request(source, request)

        self.assertEqual(len(execution.ranking), 2)
        self.assertEqual(execution.ranking.iloc[0]["record_id"], "flow")
        self.assertEqual(
            execution.request["grouping_policy"],
            "explicit_or_derived_hierarchy_v2",
        )
        self.assertEqual(execution.request["hierarchy_schema_version"], "1.0")

    def test_ranking_request_tables_expose_structured_mandatory_requirements(self):
        request = build_ranking_request(
            mode="single_parameter",
            criteria={"flow": True},
            top_n=5,
            filters={
                "drain_form": "linear",
                "include_incomplete_systems_and_components": False,
                "manufacturers": ["maker-a", "maker-b"],
                "attributes": {"material_v4a": ["yes"]},
                "length_range_mm": [800, 1000],
                "include_unverified_length": False,
            },
        )

        criteria, filters, settings = ranking_request_tables(request)

        self.assertEqual(criteria.iloc[0]["field"], "flow")
        self.assertEqual(settings.iloc[0]["top_n"], 5)
        requirements = filters.set_index("Field")
        self.assertEqual(requirements.loc["mapped_drain_form", "Value"], "linear")
        self.assertEqual(
            requirements.loc["benchmark_scope", "Value"],
            "active complete/assembled systems only",
        )
        self.assertEqual(
            requirements.loc["manufacturer_key", "Value"],
            "maker-a; maker-b",
        )
        self.assertEqual(
            requirements.loc["installable_length_mm", "Value"],
            "800 – 1000",
        )
        self.assertEqual(requirements.loc["material_v4a", "Value"], "yes")

    def test_mandatory_requirements_omit_inactive_all_values_and_keep_active_ranges(self):
        requirements = mandatory_requirements_from_filters(
            {
                "drain_form": "all",
                "include_incomplete_systems_and_components": True,
                "manufacturers": ["all"],
                "primary_flow_rate_range_lps": [0.8, 1.2],
                "installation_height_range_mm": None,
                "attributes": {
                    "material_v4a": ["all"],
                    "din_en_1253_status": ["yes"],
                },
            }
        )
        table = mandatory_requirements_table(requirements).set_index("Field")

        self.assertNotIn("mapped_drain_form", table.index)
        self.assertNotIn("manufacturer_key", table.index)
        self.assertNotIn("material_v4a", table.index)
        self.assertEqual(
            table.loc["benchmark_scope", "Value"],
            "active systems plus incomplete systems/components",
        )
        self.assertEqual(table.loc["flow_rate_primary_lps", "Value"], "0.8 – 1.2")
        self.assertEqual(table.loc["flow_rate_primary_lps", "Unit"], "l/s")
        self.assertEqual(table.loc["din_en_1253_status", "Value"], "yes")

    def test_invalid_single_parameter_request_rejects_multiple_criteria(self):
        with self.assertRaises(ValueError):
            build_ranking_request(
                mode="single_parameter",
                criteria={"flow": True, "height": False},
                top_n=5,
            )


    def test_hierarchy_keys_are_stable_across_cosmetic_changes(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "black",
                    "manufacturer_key": "maker",
                    "product_family_key": "family",
                    "model_key": "model",
                    "finish_name": "Black",
                    "nominal_length_mm": 900,
                    "height_adj_min_mm": 60,
                    "flow_rate_primary_lps": 0.8,
                },
                {
                    "record_id": "white",
                    "manufacturer_key": "maker",
                    "product_family_key": "family",
                    "model_key": "model",
                    "finish_name": "White",
                    "nominal_length_mm": 900,
                    "height_adj_min_mm": 60,
                    "flow_rate_primary_lps": 0.8,
                },
            ]
        )

        keyed = add_product_hierarchy_keys(source)

        self.assertEqual(keyed["technical_model_key"].nunique(), 1)
        self.assertEqual(keyed["technical_variant_key"].nunique(), 1)
        self.assertEqual(keyed["presentation_group_key"].nunique(), 1)
        self.assertTrue(keyed["hierarchy_key_source"].eq("derived_v2").all())

    def test_hierarchy_enrichment_is_idempotent_for_key_source(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "A",
                    "manufacturer_key": "maker",
                    "product_family_key": "family",
                    "model_key": "model",
                }
            ]
        )

        first = add_product_hierarchy_keys(source)
        second = add_product_hierarchy_keys(first)

        self.assertEqual(first.iloc[0]["hierarchy_key_source"], "derived_v2")
        self.assertEqual(second.iloc[0]["hierarchy_key_source"], "derived_v2")
        self.assertEqual(
            first.iloc[0]["presentation_group_key"],
            second.iloc[0]["presentation_group_key"],
        )

    def test_hierarchy_preserves_explicit_database_keys(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "A",
                    "manufacturer_key": "maker",
                    "product_family_key": "family",
                    "model_key": "model",
                    "technical_model_key": "tm-explicit",
                    "technical_variant_key": "tv-explicit",
                    "presentation_group_key": "pg-explicit",
                }
            ]
        )

        keyed = add_product_hierarchy_keys(source).iloc[0]

        self.assertEqual(keyed["technical_model_key"], "tm-explicit")
        self.assertEqual(keyed["technical_variant_key"], "tv-explicit")
        self.assertEqual(keyed["presentation_group_key"], "pg-explicit")
        self.assertEqual(keyed["hierarchy_key_source"], "explicit")

    def test_hierarchy_separates_technical_variants(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "low",
                    "manufacturer_key": "maker",
                    "product_family_key": "family",
                    "model_key": "model",
                    "nominal_length_mm": 900,
                    "height_adj_min_mm": 45,
                },
                {
                    "record_id": "high",
                    "manufacturer_key": "maker",
                    "product_family_key": "family",
                    "model_key": "model",
                    "nominal_length_mm": 900,
                    "height_adj_min_mm": 60,
                },
            ]
        )

        keyed = add_product_hierarchy_keys(source)

        self.assertEqual(keyed["technical_model_key"].nunique(), 1)
        self.assertEqual(keyed["technical_variant_key"].nunique(), 2)
        self.assertEqual(keyed["presentation_group_key"].nunique(), 2)

    def test_hierarchy_audit_tables_are_migration_ready(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "black",
                    "manufacturer_key": "maker",
                    "product_family_key": "family",
                    "model_key": "model",
                    "finish_name": "Black",
                    "nominal_length_mm": 900,
                },
                {
                    "record_id": "white",
                    "manufacturer_key": "maker",
                    "product_family_key": "family",
                    "model_key": "model",
                    "finish_name": "White",
                    "nominal_length_mm": 900,
                },
            ]
        )

        tables = hierarchy_audit_tables(source)
        summary = hierarchy_summary(source)

        self.assertEqual(
            set(tables),
            {"Hierarchy_Record_Map", "Presentation_Groups", "Hierarchy_Validation"},
        )
        self.assertEqual(len(tables["Hierarchy_Record_Map"]), 2)
        self.assertEqual(len(tables["Presentation_Groups"]), 1)
        self.assertEqual(summary["hidden_variants"], 1)
        self.assertEqual(summary["derived_records"], 2)

    def test_related_rows_matches_record_id_as_text(self):
        bom = pd.DataFrame(
            [
                {"parent_system_key": "0001", "component_name": "Outlet"},
                {"parent_system_key": "0002", "component_name": "Frame"},
            ]
        )

        rows = related_rows(bom, "parent_system_key", "0001")

        self.assertEqual(rows["component_name"].tolist(), ["Outlet"])


    def test_reference_filter_uses_hard_tolerances_without_similarity_score(self):
        grouped = pd.DataFrame(
            [
                {
                    "presentation_group_key": "ref",
                    "manufacturer_name": "Maker A",
                    "model_name": "Reference",
                    "mapped_drain_form": "linear",
                    "product_category": "linear_drain",
                    "nominal_length_mm": 1200,
                    "flow_rate_20mm_lps": 0.8,
                    "height_adj_min_mm": 58,
                    "outlet_dn_default": "DN50",
                },
                {
                    "presentation_group_key": "near",
                    "manufacturer_name": "Maker B",
                    "model_name": "Near",
                    "mapped_drain_form": "linear",
                    "product_category": "linear_drain",
                    "nominal_length_mm": 1250,
                    "flow_rate_20mm_lps": 0.9,
                    "height_adj_min_mm": 65,
                    "outlet_dn_default": "DN50",
                },
                {
                    "presentation_group_key": "far",
                    "manufacturer_name": "Maker C",
                    "model_name": "Far",
                    "mapped_drain_form": "linear",
                    "product_category": "linear_drain",
                    "nominal_length_mm": 1500,
                    "flow_rate_20mm_lps": 1.1,
                    "height_adj_min_mm": 70,
                    "outlet_dn_default": "DN50",
                },
            ]
        )

        comparable, audit = filter_reference_comparables(
            grouped,
            "ref",
            numeric_tolerances={
                "nominal_length_mm": {"mode": "absolute", "value": 100},
                "flow_rate_20mm_lps": {"mode": "percent", "value": 25},
                "height_adj_min_mm": {"mode": "absolute", "value": 10},
            },
            exact_match_fields=["mapped_drain_form", "outlet_dn_default"],
        )

        self.assertEqual(set(comparable["presentation_group_key"]), {"ref", "near"})
        self.assertIn("Delta_vs_reference_flow_rate_20mm_lps", comparable.columns)
        self.assertNotIn("Similarity_Score_%", comparable.columns)
        self.assertEqual(len(audit), 5)

    def test_reference_comparison_scores_independently_and_reference_can_lose(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "ref",
                    "presentation_group_key": "ref-group",
                    "technical_variant_key": "ref-variant",
                    "technical_model_key": "ref-model",
                    "hierarchy_key_source": "explicit",
                    "manufacturer_name": "Kaldewei",
                    "manufacturer_key": "kaldewei",
                    "model_name": "FLOWLINE ZERO 1200",
                    "mapped_drain_form": "linear",
                    "product_category": "linear_drain",
                    "candidate_type": "complete_system",
                    "nominal_length_mm": 1200,
                    "flow_rate_20mm_lps": 0.8,
                    "flow_rate_primary_lps": 0.8,
                    "height_adj_min_mm": 58,
                    "water_seal_mm": 30,
                    "outlet_dn_default": "DN50",
                    "material_v4a": "yes",
                },
                {
                    "record_id": "better",
                    "presentation_group_key": "better-group",
                    "technical_variant_key": "better-variant",
                    "technical_model_key": "better-model",
                    "hierarchy_key_source": "explicit",
                    "manufacturer_name": "Competitor",
                    "manufacturer_key": "competitor",
                    "model_name": "Better system",
                    "mapped_drain_form": "linear",
                    "product_category": "linear_drain",
                    "candidate_type": "complete_system",
                    "nominal_length_mm": 1200,
                    "flow_rate_20mm_lps": 1.0,
                    "flow_rate_primary_lps": 1.0,
                    "height_adj_min_mm": 50,
                    "water_seal_mm": 30,
                    "outlet_dn_default": "DN50",
                    "material_v4a": "yes",
                },
                {
                    "record_id": "worse",
                    "presentation_group_key": "worse-group",
                    "technical_variant_key": "worse-variant",
                    "technical_model_key": "worse-model",
                    "hierarchy_key_source": "explicit",
                    "manufacturer_name": "Other",
                    "manufacturer_key": "other",
                    "model_name": "Worse system",
                    "mapped_drain_form": "linear",
                    "product_category": "linear_drain",
                    "candidate_type": "complete_system",
                    "nominal_length_mm": 1250,
                    "flow_rate_20mm_lps": 0.7,
                    "flow_rate_primary_lps": 0.7,
                    "height_adj_min_mm": 65,
                    "water_seal_mm": 30,
                    "outlet_dn_default": "DN50",
                    "material_v4a": "no",
                },
            ]
        )
        weights = {
            "flow_rate": 5,
            "installation_height": 5,
            "v4a": 0,
            "sales_price": 0,
            "colours": 0,
        }

        result = execute_reference_product_comparison(
            source,
            "ref-group",
            numeric_tolerances={
                "nominal_length_mm": {"mode": "absolute", "value": 100},
                "flow_rate_20mm_lps": {"mode": "absolute", "value": 0.3},
                "height_adj_min_mm": {"mode": "absolute", "value": 10},
            },
            exact_match_fields=["mapped_drain_form", "outlet_dn_default"],
            weights=weights,
            top_n=10,
        )

        ranked = result.ranked.set_index("presentation_group_key")
        self.assertEqual(ranked.loc["better-group", "Rank"], 1)
        self.assertGreater(
            ranked.loc["better-group", "Final_Score_%"],
            ranked.loc["ref-group", "Final_Score_%"],
        )
        self.assertEqual(ranked.loc["ref-group", "Reference_Label"], "REFERENCE")
        self.assertNotIn("Similarity_Score_%", ranked.columns)

    def test_reference_with_missing_scoring_data_remains_visible_unranked(self):
        source = pd.DataFrame(
            [
                {
                    "record_id": "ref",
                    "presentation_group_key": "ref-group",
                    "technical_variant_key": "ref-variant",
                    "technical_model_key": "ref-model",
                    "hierarchy_key_source": "explicit",
                    "manufacturer_name": "Maker A",
                    "manufacturer_key": "a",
                    "model_name": "Reference",
                    "mapped_drain_form": "linear",
                    "product_category": "linear_drain",
                    "candidate_type": "complete_system",
                    "nominal_length_mm": 1200,
                    "flow_rate_primary_lps": 0.8,
                    "height_adj_min_mm": None,
                    "outlet_dn_default": "DN50",
                },
                {
                    "record_id": "candidate",
                    "presentation_group_key": "candidate-group",
                    "technical_variant_key": "candidate-variant",
                    "technical_model_key": "candidate-model",
                    "hierarchy_key_source": "explicit",
                    "manufacturer_name": "Maker B",
                    "manufacturer_key": "b",
                    "model_name": "Candidate",
                    "mapped_drain_form": "linear",
                    "product_category": "linear_drain",
                    "candidate_type": "complete_system",
                    "nominal_length_mm": 1200,
                    "flow_rate_primary_lps": 1.0,
                    "height_adj_min_mm": 55,
                    "outlet_dn_default": "DN50",
                },
            ]
        )
        weights = {
            "flow_rate": 5,
            "installation_height": 5,
            "v4a": 0,
            "sales_price": 0,
            "colours": 0,
        }

        result = execute_reference_product_comparison(
            source,
            "ref-group",
            numeric_tolerances={
                "nominal_length_mm": {"mode": "absolute", "value": 50},
            },
            exact_match_fields=["mapped_drain_form", "outlet_dn_default"],
            weights=weights,
            top_n=10,
        )

        reference = result.ranked[
            result.ranked["presentation_group_key"].eq("ref-group")
        ].iloc[0]
        self.assertTrue(pd.isna(reference["Rank"]))
        self.assertTrue(pd.isna(reference["Final_Score_%"]))
        self.assertEqual(reference["Ranking_Status"], "Not rankable — missing data")
        self.assertEqual(reference["Reference_Label"], "REFERENCE")
        self.assertEqual(
            reference["Missing_Data_Policy"],
            "require_complete_reference_retained",
        )


if __name__ == "__main__":
    unittest.main()
