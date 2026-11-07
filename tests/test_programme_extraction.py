import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

from unimatch.programme_extraction import (
    _aps_for_section,
    _clean_faculty,
    _clean_json_text,
    _parse_aps,
    _parse_fee,
    _parse_mark,
    extract_programme_drafts,
)


def test_clean_faculty():
    assert _clean_faculty("FACULTY OF SCIENCE") == "Faculty of Science"
    assert _clean_faculty("Faculty of Engineering") == "Faculty of Engineering"
    assert _clean_faculty("SCIENCE BACHELOR OF SCIENCE") == "Faculty of Science"
    assert _clean_faculty(None) is None


def test_parsers():
    assert _parse_mark(60) == 60
    assert _parse_mark("60%") == 60
    assert _parse_mark("Level 5 (60%)") == 5
    assert _parse_mark(150) is None
    assert _parse_mark(-5) is None

    assert _parse_aps(34) == 34
    assert _parse_aps("APS 34") == 34
    assert _parse_aps(50) is None

    assert _parse_fee(150) == Decimal("150")
    assert _parse_fee("R150.00") == Decimal("150.00")
    assert _parse_fee(-10) is None


def test_clean_json_text():
    assert _clean_json_text('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _clean_json_text('  {"a": 1}  ') == '{"a": 1}'


def test_regex_extraction_without_gemini():
    text = (
        "FACULTY OF ENGINEERING\n\n"
        "BACHELOR OF SCIENCE IN ELECTRICAL ENGINEERING\n"
        "Minimum APS of 36 required.\n"
        "Mathematics 70%, Physical Sciences 65%."
    )
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        drafts = extract_programme_drafts(text, api_key="")
        assert len(drafts) == 1
        draft = drafts[0]
        assert "ELECTRICAL ENGINEERING" in draft["name"]
        assert draft["minimum_aps"] == 36
        assert draft["status"] == "NeedsReview"


def test_gemini_enrichment_mocked():
    text = (
        "FACULTY OF SCIENCE\n\n"
        "BACHELOR OF SCIENCE IN COMPUTER SCIENCE\n"
        "Admission Requirements:\n"
        "Minimum APS 34. Mathematics 60%, Physical Sciences 50%.\n"
        "Closing date: 2026-09-30. Application fee: R150."
    )
    mock_response = MagicMock()
    mock_response.text = (
        '[\n'
        '  {\n'
        '    "index": 0,\n'
        '    "minimum_aps": 34,\n'
        '    "faculty": "Faculty of Science",\n'
        '    "required_subjects": {"Mathematics": 60, "Physical Sciences": 50},\n'
        '    "application_deadline": "2026-09-30",\n'
        '    "application_fee": 150,\n'
        '    "required_documents": ["Certified ID Copy"]\n'
        '  }\n'
        ']'
    )
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        drafts = extract_programme_drafts(text, api_key="fake-key-for-test")
        assert len(drafts) == 1
        d = drafts[0]
        assert d["minimum_aps"] == 34
        assert d["faculty"] == "Faculty of Science"
        assert d["required_subjects"] == {"Mathematics": 60, "Physical Sciences": 50}
        assert d["application_deadline"] == "2026-09-30"
        assert d["application_fee"] == Decimal("150")
        assert d["required_documents"] == ["Certified ID Copy"]
        assert "Gemini AI extracted requirements" in d["extraction_notes"]
