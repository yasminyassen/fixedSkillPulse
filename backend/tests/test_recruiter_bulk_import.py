import pandas as pd
import pytest

from app.services.recruiter_bulk_import import parse_candidate_rows_from_dataframe, parse_candidate_upload


def test_parse_csv_upload_with_flexible_headers() -> None:
    content = (
        "Candidate,GitHub URL,branch\n"
        "Alice,https://github.com/acme/book-api-alice,main\n"
        "Bob,acme/book-api-bob,main\n"
    ).encode("utf-8")

    rows, skipped = parse_candidate_upload("candidates.csv", content)

    assert len(rows) == 2
    assert skipped == []
    assert rows[0]["candidate_name"] == "Alice"
    assert rows[0]["full_name"] == "acme/book-api-alice"
    assert rows[1]["full_name"] == "acme/book-api-bob"


def test_parse_dataframe_reports_invalid_rows() -> None:
    df = pd.DataFrame([
        {"candidate_name": "Alice", "repo_url": "not-a-url"},
    ])

    rows, skipped = parse_candidate_rows_from_dataframe(df)
    assert rows == []
    assert len(skipped) == 1


def test_parse_upload_requires_required_columns() -> None:
    content = b"name only\nAlice\n"
    with pytest.raises(ValueError, match="does not match the required format"):
        parse_candidate_upload("bad.csv", content)
