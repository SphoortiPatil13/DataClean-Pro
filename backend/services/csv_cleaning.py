import re

import pandas as pd


MISSING_PLACEHOLDERS = ("Not Provided", "N/A", "Not Available")


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


def is_identifier_column(column):
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(column))
    tokens = re.findall(r"[a-z0-9]+", name.casefold())
    return bool(_IDENTIFIER_TOKENS.intersection(tokens))


def read_csv_for_cleaning(stream):
    stream.seek(0)
    columns = pd.read_csv(stream, nrows=0).columns
    identifier_types = {
        column: "string" for column in columns if is_identifier_column(column)
    }
    stream.seek(0)
    return pd.read_csv(
        stream,
        dtype=identifier_types,
        dtype_backend="numpy_nullable",
    )


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

    return cleaned, unfilled_columns
