import re
from collections import defaultdict
from datetime import datetime

import pandas as pd


MISSING_PLACEHOLDERS = ("Not Provided", "N/A", "Not Available")
ORIGINAL_ROW_NUMBER_COLUMN = "__data_cleanpro_original_row_number__"

_IDENTIFIER_TOKENS = {
    "id",
    "ids",
    "identifier",
    "identifiers",
    "phone",
    "mobile",
    "telephone",
    "zip",
    "zipcode",
    "postal",
    "ssn",
}

_TYPE_ALIASES = {
    "text": "text",
    "string": "text",
    "str": "text",
    "varchar": "text",
    "integer": "integer",
    "int": "integer",
    "decimal": "decimal",
    "float": "decimal",
    "number": "decimal",
    "double": "decimal",
    "date": "date",
    "datetime": "date",
}


def _get_original_row_numbers(dataframe):
    original_row_numbers = dataframe.attrs.get("original_row_numbers")
    if original_row_numbers is None:
        original_row_numbers = list(range(len(dataframe)))
        dataframe.attrs["original_row_numbers"] = original_row_numbers
    return list(original_row_numbers)


def _set_original_row_numbers(dataframe, values):
    dataframe.attrs["original_row_numbers"] = list(values)
    return dataframe


def is_identifier_column(column):
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(column))
    tokens = re.findall(r"[a-z0-9]+", name.casefold())
    return bool(_IDENTIFIER_TOKENS.intersection(tokens))


def normalize_expected_type(expected_type):
    if expected_type is None:
        return "text"
    normalized = str(expected_type).strip().casefold()
    return _TYPE_ALIASES.get(normalized, normalized)


def read_csv_for_cleaning(stream):
    stream.seek(0)
    columns = pd.read_csv(stream, nrows=0).columns
    identifier_types = {
        column: "string" for column in columns if is_identifier_column(column)
    }
    stream.seek(0)
    dataframe = pd.read_csv(
        stream,
        dtype=identifier_types,
        dtype_backend="numpy_nullable",
    )
    return _set_original_row_numbers(dataframe, list(range(len(dataframe))))


def _is_missing_value(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return bool(pd.isna(value))


def _value_for_error_display(value):
    if value is None:
        return ""
    if isinstance(value, (float, int)) and pd.isna(value):
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _validate_integer(value):
    if _is_missing_value(value):
        return True, "Missing value"
    if isinstance(value, bool):
        return False, "Boolean values are not valid integers"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not value.is_integer():
            return False, "Value is not a whole number"
        return True, "Integer value is valid"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return True, "Missing value"
        if re.fullmatch(r"[-+]?\d+", text):
            return True, "Integer value is valid"
        return False, "Value is not a valid integer"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False, "Value is not a valid integer"
    if not numeric.is_integer():
        return False, "Value is not a whole number"
    return True, "Integer value is valid"


def _validate_decimal(value):
    if _is_missing_value(value):
        return True, "Missing value"
    if isinstance(value, bool):
        return False, "Boolean values are not valid numeric values"
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return True, "Missing value"
        return True, "Numeric value is valid"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return True, "Missing value"
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
            return True, "Numeric value is valid"
        return False, "Value is not a valid decimal number"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False, "Value is not a valid decimal number"
    if pd.isna(numeric):
        return True, "Missing value"
    return True, "Numeric value is valid"


def _date_from_string(value):
    text = str(value).strip()
    if not text:
        return None
    for format_string in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, format_string).date()
        except ValueError:
            continue
    return None


def _validate_date(value):
    if _is_missing_value(value):
        return True, "Missing value"
    if isinstance(value, pd.Timestamp):
        return True, "Date value is valid"
    if isinstance(value, str):
        if not value.strip():
            return True, "Missing value"
        text = value.strip()
        if "/" in text:
            pieces = text.split("/")
            if len(pieces) == 3 and all(part.isdigit() for part in pieces):
                if int(pieces[0]) <= 12 and int(pieces[1]) <= 12:
                    return False, "Date is ambiguous and was rejected to avoid incorrect parsing"
        parsed = _date_from_string(text)
        if parsed is not None:
            return True, "Date value is valid"
        return False, "Value is not a supported date format"
    try:
        parsed = pd.to_datetime(value, errors="raise")
    except (TypeError, ValueError):
        return False, "Value is not a supported date format"
    if pd.isna(parsed):
        return True, "Missing value"
    return True, "Date value is valid"


def validate_value(value, expected_type):
    type_name = normalize_expected_type(expected_type)
    if type_name == "text":
        if _is_missing_value(value):
            return True, "Missing value"
        return True, "Text value is valid"
    if type_name == "integer":
        return _validate_integer(value)
    if type_name == "decimal":
        return _validate_decimal(value)
    if type_name == "date":
        return _validate_date(value)
    if _is_missing_value(value):
        return True, "Missing value"
    return True, "Text value is valid"


def add_new_column(dataframe, column_name, *, default_value=None, fill_empty=False):
    working_dataframe = dataframe.copy()
    working_dataframe.attrs = dict(dataframe.attrs)
    if column_name is None:
        raise ValueError("Column name is required.")
    cleaned_name = str(column_name).strip()
    if not cleaned_name:
        raise ValueError("Column name cannot be blank.")
    normalized_names = {str(existing).strip().casefold() for existing in working_dataframe.columns}
    if cleaned_name.casefold() in normalized_names:
        raise ValueError(f"Column '{cleaned_name}' already exists.")

    row_count = len(working_dataframe)
    if fill_empty or default_value is None:
        working_dataframe[cleaned_name] = [None] * row_count
    else:
        working_dataframe[cleaned_name] = [default_value] * row_count
    _set_original_row_numbers(working_dataframe, _get_original_row_numbers(dataframe))
    return working_dataframe


def validate_dataframe(dataframe, expected_types):
    working_dataframe = dataframe.copy()
    working_dataframe.attrs = dict(dataframe.attrs)
    if len(working_dataframe) == 0:
        return {
            "invalid_cells": [],
            "total_invalid_cells": 0,
            "distinct_rows_with_errors": 0,
            "error_counts_by_column": {},
            "validated_columns": list(expected_types.keys()) if isinstance(expected_types, dict) else [],
        }

    if isinstance(expected_types, dict):
        validation_map = {
            str(column).strip(): normalize_expected_type(type_name)
            for column, type_name in expected_types.items()
        }
    elif isinstance(expected_types, list):
        validation_map = {}
        for entry in expected_types:
            if isinstance(entry, dict):
                column_name = str(entry.get("column", "")).strip()
                if column_name:
                    validation_map[column_name] = normalize_expected_type(entry.get("expected_type", "text"))
    else:
        validation_map = {}

    invalid_cells = []
    error_counts_by_column = defaultdict(int)
    distinct_row_numbers = set()
    original_row_numbers = _get_original_row_numbers(working_dataframe)
    for column_name, expected_type in validation_map.items():
        if column_name not in working_dataframe.columns:
            continue
        for position, value in enumerate(working_dataframe[column_name].tolist()):
            valid, message = validate_value(value, expected_type)
            if valid:
                continue
            row_number = int(original_row_numbers[position]) + 2
            invalid_cells.append({
                "row_number": row_number,
                "column": column_name,
                "value": _value_for_error_display(value),
                "expected_type": normalize_expected_type(expected_type),
                "message": message,
            })
            error_counts_by_column[column_name] += 1
            distinct_row_numbers.add(row_number)

    return {
        "invalid_cells": invalid_cells,
        "total_invalid_cells": len(invalid_cells),
        "distinct_rows_with_errors": len(distinct_row_numbers),
        "error_counts_by_column": dict(sorted(error_counts_by_column.items())),
        "validated_columns": list(validation_map.keys()),
    }


def remove_invalid_rows(dataframe, *, column_name=None, validation_report=None, include_all=False):
    working_dataframe = dataframe.copy()
    working_dataframe.attrs = dict(dataframe.attrs)
    if len(working_dataframe) == 0:
        return working_dataframe

    if validation_report is None:
        return working_dataframe

    original_row_numbers = _get_original_row_numbers(working_dataframe)
    rows_to_remove = set()
    if include_all:
        for entry in validation_report.get("invalid_cells", []):
            row_number = int(entry["row_number"]) - 2
            if row_number in original_row_numbers:
                rows_to_remove.add(original_row_numbers.index(row_number))
    elif column_name:
        for entry in validation_report.get("invalid_cells", []):
            if entry.get("column") != column_name:
                continue
            row_number = int(entry["row_number"]) - 2
            if row_number in original_row_numbers:
                rows_to_remove.add(original_row_numbers.index(row_number))

    if not rows_to_remove:
        return working_dataframe

    retained_positions = [position for position in range(len(original_row_numbers)) if position not in rows_to_remove]
    filtered = working_dataframe.iloc[retained_positions].copy()
    filtered = filtered.reset_index(drop=True)
    filtered.attrs = dict(working_dataframe.attrs)
    filtered.attrs["original_row_numbers"] = [original_row_numbers[position] for position in retained_positions]
    return filtered


def get_data_quality_stats(dataframe):
    return {
        "total_rows": len(dataframe),
        "missing_values": int(dataframe.isna().sum().sum()),
        "duplicate_rows": int(dataframe.duplicated().sum()),
        "empty_rows": int(dataframe.isna().all(axis=1).sum()),
    }


def clean_dataframe(
    dataframe,
    *,
    remove_empty_rows,
    remove_duplicates,
    trim_whitespace,
    handle_missing,
    missing_strategy,
    missing_placeholder="Not Provided",
):
    cleaned = dataframe.copy()
    cleaned.attrs = dict(dataframe.attrs)
    if trim_whitespace:
        cleaned = cleaned.map(
            lambda value: value.strip() if isinstance(value, str) else value
        )
    if remove_empty_rows:
        cleaned = cleaned.dropna(how="all")
    if remove_duplicates:
        cleaned = cleaned.drop_duplicates()

    unfilled_columns = []
    if handle_missing:
        if missing_strategy == "remove":
            cleaned = cleaned.dropna(how="any")
        else:
            for column in cleaned.columns:
                values = cleaned[column]
                if values.isna().any():
                    cleaned[column] = values.astype(object).fillna(missing_placeholder)

    if len(cleaned) == 0:
        cleaned.attrs["original_row_numbers"] = []
    else:
        original_row_numbers = _get_original_row_numbers(dataframe)
        cleaned.attrs["original_row_numbers"] = [
            original_row_numbers[position] for position in cleaned.index.tolist()
        ]
    return cleaned, unfilled_columns
