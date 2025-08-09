import pandas as pd
import great_expectations as ge

REQUIRED_COLS = ["id", "title", "description", "url", "deadline"]

def validate_df(df: pd.DataFrame):
    for c in REQUIRED_COLS:
        assert c in df.columns, f"Missing column: {c}"
    gdf = ge.from_pandas(df)
    gdf.expect_column_values_to_not_be_null("id")
    gdf.expect_column_values_to_not_be_null("title")
    gdf.expect_column_values_to_not_be_null("description")
    gdf.expect_column_values_to_match_regex("url", r"^https?://")
    res = gdf.validate()
    assert res.success, "Data validation failed"
    return True
