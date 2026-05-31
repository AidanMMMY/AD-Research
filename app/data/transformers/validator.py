"""Four-layer data quality validation module for ETF data."""

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd


@dataclass
class ValidationResult:
    """Result of a validation run."""

    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    data: pd.DataFrame = field(default_factory=pd.DataFrame)


REQUIRED_COLUMNS = ["etf_code", "trade_date", "open", "high", "low", "close"]


def validate_level1_format(df: pd.DataFrame) -> ValidationResult:
    """L1 format validation: check required columns and missing values."""
    result = ValidationResult(data=df)

    # Check required columns exist
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        result.is_valid = False
        result.errors.append(f"Missing required columns: {missing_cols}")
        return result

    # Check for missing values in required columns
    for col in REQUIRED_COLUMNS:
        null_count = df[col].isna().sum()
        if null_count > 0:
            result.is_valid = False
            result.errors.append(f"Column '{col}' has {null_count} missing values")

    return result


def validate_level2_business(df: pd.DataFrame) -> ValidationResult:
    """L2 business validation: check logical price/volume constraints."""
    result = ValidationResult(data=df)

    # high >= low
    invalid_hl = df[df["high"] < df["low"]]
    if not invalid_hl.empty:
        result.is_valid = False
        result.errors.append(
            f"high < low on {len(invalid_hl)} row(s): indices {invalid_hl.index.tolist()}"
        )

    # close in [low, high] (allow 0.1% tolerance)
    tolerance = 0.001
    invalid_close = df[
        (df["close"] < df["low"] * (1 - tolerance))
        | (df["close"] > df["high"] * (1 + tolerance))
    ]
    if not invalid_close.empty:
        result.is_valid = False
        result.errors.append(
            f"close outside [low, high] on {len(invalid_close)} row(s): "
            f"indices {invalid_close.index.tolist()}"
        )

    # volume >= 0
    if "volume" in df.columns:
        invalid_vol = df[df["volume"] < 0]
        if not invalid_vol.empty:
            result.is_valid = False
            result.errors.append(
                f"volume < 0 on {len(invalid_vol)} row(s): indices {invalid_vol.index.tolist()}"
            )

    return result


def validate_level3_timeseries(df: pd.DataFrame) -> ValidationResult:
    """L3 time-series validation: warnings only, does not block."""
    result = ValidationResult(data=df)

    if "change_pct" in df.columns:
        extreme = df[df["change_pct"].abs() > 20]
        if not extreme.empty:
            for idx in extreme.index:
                result.warnings.append(
                    f"Row {idx}: change_pct = {extreme.loc[idx, 'change_pct']:.2f}% "
                    f"(exceeds 20% threshold)"
                )

    return result


def validate_level4_completeness(
    df: pd.DataFrame, expected_codes: Optional[List[str]] = None
) -> ValidationResult:
    """L4 completeness validation: warnings only, does not block."""
    result = ValidationResult(data=df)

    if expected_codes is None or expected_codes == []:
        return result

    actual_codes = set(df["etf_code"].dropna().unique())
    missing_codes = set(expected_codes) - actual_codes
    if missing_codes:
        result.warnings.append(
            f"Missing expected ETF codes: {sorted(missing_codes)}"
        )

    return result


def validate_all(
    df: pd.DataFrame, expected_codes: Optional[List[str]] = None
) -> ValidationResult:
    """Run all four validation levels.

    L1/L2 failures set is_valid=False and stop further validation.
    L3/L4 only add warnings and never block.
    """
    result = ValidationResult(data=df)

    # L1: Format
    l1 = validate_level1_format(df)
    if not l1.is_valid:
        result.is_valid = False
        result.errors.extend(l1.errors)
        return result

    # L2: Business
    l2 = validate_level2_business(df)
    if not l2.is_valid:
        result.is_valid = False
        result.errors.extend(l2.errors)
        return result

    # L3: Time-series (warnings only)
    l3 = validate_level3_timeseries(df)
    result.warnings.extend(l3.warnings)

    # L4: Completeness (warnings only)
    l4 = validate_level4_completeness(df, expected_codes)
    result.warnings.extend(l4.warnings)

    return result
