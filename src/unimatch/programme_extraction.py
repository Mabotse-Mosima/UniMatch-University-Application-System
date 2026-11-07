"""Conservative extraction of programme candidates from prospectus text with Gemini AI enrichment.

This module extracts qualification candidates from prospectus text. It uses regex heuristics
for reliable fast candidate spotting and, when configured, enriches candidate drafts using
Google Gemini to automatically extract minimum APS, compulsory subject requirements, faculty,
application fees, and deadlines.
"""

from __future__ import annotations

from decimal import Decimal
import json
import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger(__name__)


_QUALIFICATION = re.compile(
    r"\b(?:Bachelor(?:'s)?\b|BSc\b|BCom\b|BA\b|BEng\b|BEd\b|"
    r"MBChB\b|LLB\b|Diploma\b|Higher Certificate\b|National Diploma\b|"
    r"Advanced Diploma\b|Postgraduate Diploma\b|Master(?:'s)?\b|"
    r"MSc\b|MCom\b|PhD\b)",
    re.IGNORECASE,
)
_NON_PROGRAMME_CONTEXT = re.compile(
    r"\b(?:degree pass|bachelor'?s? pass|admission requirements?|"
    r"minimum requirements?|applicants? must|pass requirements?|"
    r"minimum aps|aps score)\b",
    re.IGNORECASE,
)
_APS = re.compile(
    r"\b(?:minimum\s+)?(?:APS|admission\s+point\s+score|points?)\s*"
    r"(?:of|minimum|:|=)?\s*(\d{1,2})\b",
    re.IGNORECASE,
)
_FLAT_HEADING = re.compile(
    r"(?<![A-Z])(?P<kind>HIGHER CERTIFICATE IN|NATIONAL DIPLOMA IN|"
    r"ADVANCED DIPLOMA IN|POSTGRADUATE DIPLOMA IN|DIPLOMA IN|"
    r"BACHELOR OF|BACHELOR IN|BSC|BCOM|BENG|BED|BA|MBCHB|LLB|"
    r"MASTER OF|MSC|MCOM|PHD)\s+"
    r"(?P<title>[A-Z0-9&'’()/,-]+(?![a-z])(?!\s+[a-z])"
    r"(?:\s+[A-Z0-9&'’()/,-]+(?![a-z])(?!\s+[a-z])){0,11})"
)
_FACULTY = re.compile(
    r"\bFACULTY OF\s+([A-Z][A-Za-z&,'’()-]*(?:\s+[A-Z][A-Za-z&,'’()-]*){0,5})",
    re.IGNORECASE,
)
_AMBIGUOUS_APS_PATH = re.compile(r"(?<!\d)\d{2}\s*\(M\).*?(?<!\d)\d{2}\s*\(ML\)", re.IGNORECASE)


def _aps_for_section(section: str) -> int | None:
    """Read APS only when the prospectus exposes one unambiguous minimum."""
    if _AMBIGUOUS_APS_PATH.search(section):
        return None
    labeled = re.search(r"APS SCORE METHOD OPTION(.{0,1200})", section, re.IGNORECASE)
    if labeled:
        first_number = re.search(r"(?<!\d)(\d{2})(?!\d)", labeled.group(1))
        if first_number:
            value = int(first_number.group(1))
            return value if 0 <= value <= 42 else None
    explicit = _APS.search(section)
    if explicit:
        value = int(explicit.group(1))
        return value if 0 <= value <= 42 else None
    return None


def _clean_faculty(fac: str | None) -> str | None:
    if not fac:
        return None
    cleaned = re.split(
        r"\b(?:BACHELOR|DIPLOMA|HIGHER CERTIFICATE|NATIONAL DIPLOMA|ADVANCED DIPLOMA|POSTGRADUATE DIPLOMA|BSC|BCOM|BA|BENG|BED|MBCHB|LLB|MASTER|MSC|MCOM|PHD)\b",
        fac,
        flags=re.IGNORECASE,
    )[0].strip(" :;,-–—")
    if not cleaned:
        return None
    cleaned_lower = cleaned.lower()
    if cleaned_lower.startswith("faculty of "):
        rest = cleaned[11:].strip()
        return f"Faculty of {rest.title()}"[:255]
    if cleaned_lower.startswith("faculty "):
        rest = cleaned[8:].strip()
        return f"Faculty of {rest.title()}"[:255]
    return f"Faculty of {cleaned.title()}"[:255]


def _clean_json_text(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_mark(val: Any) -> int | None:
    if isinstance(val, (int, float)):
        int_val = int(val)
        return int_val if 0 <= int_val <= 100 else None
    if isinstance(val, str):
        match = re.search(r"(\d{1,3})", val)
        if match:
            int_val = int(match.group(1))
            return int_val if 0 <= int_val <= 100 else None
    return None


def _parse_aps(val: Any) -> int | None:
    if isinstance(val, (int, float)):
        int_val = int(val)
        return int_val if 0 <= int_val <= 42 else None
    if isinstance(val, str):
        match = re.search(r"(\d{1,2})", val)
        if match:
            int_val = int(match.group(1))
            return int_val if 0 <= int_val <= 42 else None
    return None


def _parse_fee(val: Any) -> Decimal | None:
    if isinstance(val, (int, float)):
        return Decimal(str(val)) if val >= 0 else None
    if isinstance(val, str):
        cleaned = re.sub(r"[^\d.]", "", val)
        if cleaned:
            try:
                dec = Decimal(cleaned)
                return dec if dec >= 0 else None
            except Exception:
                return None
    return None


def _extract_candidates_regex(text: str) -> list[dict[str, Any]]:
    """Heuristic extraction of programme candidates via regex patterns."""
    flat_text = re.sub(r"\s+", " ", text).strip()
    lines = [
        re.sub(r"\s+", " ", line).strip(" \t|•·-")
        for line in text.splitlines()
    ]
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    headings = list(_FLAT_HEADING.finditer(flat_text))
    faculty_matches = list(_FACULTY.finditer(flat_text))
    for heading_index, heading in enumerate(headings):
        name = f"{heading.group('kind')} {heading.group('title')}".strip(" :;,-–—")
        name = re.sub(r"\s+", " ", name)
        if len(name) < 5 or len(name) > 255 or _NON_PROGRAMME_CONTEXT.search(name):
            continue
        section_end = headings[heading_index + 1].start() if heading_index + 1 < len(headings) else len(flat_text)
        section = flat_text[heading.start():section_end]
        aps_value = _aps_for_section(section)
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        faculty = next(
            (match.group(1).strip() for match in reversed(faculty_matches) if match.start() < heading.start()),
            None,
        )
        candidates.append({
            "name": name[:255],
            "faculty": _clean_faculty(faculty),
            "minimum_aps": aps_value,
            "application_deadline": None,
            "application_fee": None,
            "required_documents": [],
            "required_subjects": {},
            "source_evidence": section[:4000],
            "extraction_notes": (
                "Programme heading was recognized in the prospectus. "
                + ("A single nearby APS minimum was detected. " if aps_value is not None else "APS was not populated because the value was absent or ambiguous. ")
                + "Verify all admission requirements against this source before approval."
            ),
            "status": "NeedsReview",
        })

    for index, line in enumerate(lines):
        if (
            not line
            or len(line) < 5
            or len(line) > 255
            or not _QUALIFICATION.match(line)
            or ":" in line
            or _NON_PROGRAMME_CONTEXT.search(line)
        ):
            continue
        if not re.match(
            r"^(?:(?:HIGHER CERTIFICATE|NATIONAL DIPLOMA|ADVANCED DIPLOMA|"
            r"POSTGRADUATE DIPLOMA|DIPLOMA|BACHELOR|MASTER)\s+(?:IN|OF)\s+|"
            r"(?:BSC|BCOM|BA|BENG|BED|MBCHB|LLB|MSC|MCOM|PHD)\s+)",
            line,
            re.IGNORECASE,
        ):
            continue
        candidate_name = re.split(
            r"\b(?:minimum\s+)?(?:APS|admission\s+point\s+score|points?)\b",
            line,
            flags=re.IGNORECASE,
        )[0].strip(" :;,-–—")
        if len(candidate_name) < 5:
            continue
        evidence_lines = [line]
        aps_match = _APS.search(line)
        if aps_match is None:
            for following in lines[index + 1:index + 3]:
                if not following:
                    continue
                if _QUALIFICATION.match(following):
                    break
                evidence_lines.append(following)
                aps_match = _APS.search(following)
                if aps_match is not None:
                    break
        aps_value = int(aps_match.group(1)) if aps_match is not None else None
        if aps_value is not None and not 0 <= aps_value <= 42:
            aps_value = None
        key = candidate_name.casefold()
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            "name": candidate_name[:255],
            "faculty": None,
            "minimum_aps": aps_value,
            "application_deadline": None,
            "application_fee": None,
            "required_documents": [],
            "required_subjects": {},
            "source_evidence": "\n".join(evidence_lines)[:4000],
            "extraction_notes": (
                "Programme name is a heuristic candidate. "
                + ("An explicit nearby APS value was detected. " if aps_value is not None else "No nearby APS value was detected. ")
                + "Verify every requirement against the cited prospectus before approval."
            ),
            "status": "NeedsReview",
        })
    return candidates


def _enrich_candidates_with_gemini(
    candidates: list[dict[str, Any]],
    api_key: str,
    model: str = "gemini-3.5-flash-lite",
) -> list[dict[str, Any]]:
    """Enrich candidate drafts with minimum APS and compulsory subject requirements using Gemini."""
    if not candidates:
        return candidates
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.warning("google.genai is not installed; skipping Gemini programme enrichment.")
        return candidates

    try:
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        logger.warning("Failed to initialize Gemini client: %s", exc)
        return candidates

    batch_size = 4
    candidate_models = [model]
    for fallback in ("gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.1-flash-lite"):
        if fallback not in candidate_models:
            candidate_models.append(fallback)

    for start in range(0, len(candidates), batch_size):
        batch = candidates[start : start + batch_size]
        payload = [
            {
                "index": i,
                "name": c["name"],
                "faculty": c.get("faculty"),
                "evidence": c.get("source_evidence", "")[:3000],
            }
            for i, c in enumerate(batch)
        ]
        prompt = (
            "You are an expert admissions analyzer for South African universities (NSC/CAPS).\n"
            "Analyze the candidate qualification items below and extract their requirements strictly from the evidence.\n\n"
            "Rules for South African admissions requirements:\n"
            "1. minimum_aps: South African Admission Point Score (integer 0 to 42). Return null if absent or ambiguous.\n"
            "2. required_subjects: JSON object mapping compulsory subject name to minimum mark percentage (integer 0 to 100).\n"
            "   - Convert NSC achievement levels to minimum percentages: Level 7 -> 80, Level 6 -> 70, Level 5 -> 60, Level 4 -> 50, Level 3 -> 40, Level 2 -> 30.\n"
            "   - Example: {\"Mathematics\": 60, \"Physical Sciences\": 50, \"English\": 50}.\n"
            "   - If no specific compulsory subject marks are specified, return an empty object {}.\n"
            "3. faculty: Faculty or school name (string) or null.\n"
            "4. application_fee: Application fee as a numeric value in Rands (e.g. 100 or 150) or null.\n"
            "5. application_deadline: Application deadline date in YYYY-MM-DD format or null.\n"
            "6. required_documents: Array of required document strings (e.g. ['Certified copy of ID', 'Grade 12 Results']) or [].\n\n"
            f"Input candidates:\n{json.dumps(payload, ensure_ascii=False)}"
        )

        response_text: str | None = None
        for m in candidate_models:
            for attempt in range(2):
                try:
                    res = client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1,
                        ),
                    )
                    if res.text:
                        response_text = res.text
                        break
                except Exception as call_err:
                    logger.debug("Gemini attempt %d on %s failed: %s", attempt, m, call_err)
                    time.sleep(1.0)
            if response_text:
                break

        if not response_text:
            continue

        try:
            parsed = json.loads(_clean_json_text(response_text))
            if isinstance(parsed, dict) and "candidates" in parsed:
                parsed = parsed["candidates"]
            if not isinstance(parsed, list):
                continue
            for item_idx, item in enumerate(parsed):
                if not isinstance(item, dict):
                    continue
                idx = item.get("index")
                if not isinstance(idx, int) or idx < 0 or idx >= len(batch):
                    idx = item_idx
                if idx < 0 or idx >= len(batch):
                    continue
                target = batch[idx]

                # Minimum APS
                aps = _parse_aps(item.get("minimum_aps"))
                if aps is not None:
                    target["minimum_aps"] = aps

                # Faculty
                faculty_val = _clean_faculty(item.get("faculty"))
                if faculty_val:
                    target["faculty"] = faculty_val
                elif target.get("faculty"):
                    target["faculty"] = _clean_faculty(target["faculty"])

                # Application Fee
                fee_val = _parse_fee(item.get("application_fee"))
                if fee_val is not None:
                    target["application_fee"] = fee_val

                # Application Deadline
                deadline_val = item.get("application_deadline")
                if isinstance(deadline_val, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", deadline_val.strip()):
                    target["application_deadline"] = deadline_val.strip()

                # Required Documents
                docs_val = item.get("required_documents")
                if isinstance(docs_val, list):
                    clean_docs = [str(d).strip() for d in docs_val if str(d).strip()]
                    if clean_docs:
                        target["required_documents"] = clean_docs[:10]

                # Required Subjects
                subj_val = item.get("required_subjects")
                if isinstance(subj_val, dict):
                    valid_subjects: dict[str, int] = {}
                    for s_name, s_mark in subj_val.items():
                        if isinstance(s_name, str) and s_name.strip():
                            m_int = _parse_mark(s_mark)
                            if m_int is not None:
                                valid_subjects[s_name.strip()] = m_int
                    if valid_subjects:
                        target["required_subjects"] = valid_subjects

                # Extraction Notes
                notes = ["Gemini AI extracted requirements from prospectus."]
                if target.get("minimum_aps") is not None:
                    notes.append(f"APS: {target['minimum_aps']}.")
                if target.get("required_subjects"):
                    subj_summary = ", ".join(f"{s} ({m}%)" for s, m in target["required_subjects"].items())
                    notes.append(f"Compulsory subjects: {subj_summary}.")
                notes.append("Verify requirements before approval.")
                target["extraction_notes"] = " ".join(notes)
        except Exception as parse_err:
            logger.warning("Failed to parse Gemini response for batch: %s", parse_err)
            continue

    return candidates


def _extract_candidates_gemini_direct(
    text: str,
    api_key: str,
    model: str = "gemini-3.5-flash-lite",
) -> list[dict[str, Any]]:
    """Direct qualification extraction using Gemini when regex pattern matching yields no results."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return []

    try:
        client = genai.Client(api_key=api_key)
    except Exception:
        return []

    sample_text = text[:15000].strip()
    if not sample_text:
        return []

    prompt = (
        "You are an expert admissions analyzer for South African universities.\n"
        "Extract all university qualifications/programmes described in the text into a JSON array of objects.\n"
        "For each programme, provide:\n"
        "- name: Full qualification title (string)\n"
        "- faculty: Faculty or school name (string or null)\n"
        "- minimum_aps: Integer (0-42) or null\n"
        "- required_subjects: Object mapping compulsory subject name to minimum mark percentage (integer 0-100)\n"
        "- application_deadline: YYYY-MM-DD or null\n"
        "- application_fee: Number or null\n"
        "- required_documents: Array of strings\n"
        "- source_evidence: Excerpt from text supporting these requirements\n\n"
        f"Prospectus text:\n{sample_text}"
    )

    candidate_models = [model, "gemini-3.5-flash-lite", "gemini-3.5-flash"]
    response_text: str | None = None
    for m in candidate_models:
        try:
            res = client.models.generate_content(
                model=m,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            if res.text:
                response_text = res.text
                break
        except Exception:
            time.sleep(1.0)

    if not response_text:
        return []

    results: list[dict[str, Any]] = []
    try:
        parsed = json.loads(_clean_json_text(response_text))
        if isinstance(parsed, dict) and "programmes" in parsed:
            parsed = parsed["programmes"]
        if not isinstance(parsed, list):
            return []
        for item in parsed:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            name = str(item["name"]).strip()[:255]
            if len(name) < 5:
                continue
            minimum_aps = _parse_aps(item.get("minimum_aps"))
            
            valid_subjects: dict[str, int] = {}
            if isinstance(item.get("required_subjects"), dict):
                for s_name, s_mark in item["required_subjects"].items():
                    if isinstance(s_name, str) and s_name.strip():
                        m_int = _parse_mark(s_mark)
                        if m_int is not None:
                            valid_subjects[s_name.strip()] = m_int

            fee = _parse_fee(item.get("application_fee"))

            deadline_val = item.get("application_deadline")
            deadline = deadline_val.strip() if isinstance(deadline_val, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", deadline_val.strip()) else None

            docs_val = item.get("required_documents")
            docs = [str(d).strip() for d in docs_val if str(d).strip()][:10] if isinstance(docs_val, list) else []

            evidence = str(item.get("source_evidence") or name)[:4000]

            results.append({
                "name": name,
                "faculty": str(item.get("faculty") or "")[:255] or None,
                "minimum_aps": minimum_aps,
                "application_deadline": deadline,
                "application_fee": fee,
                "required_documents": docs,
                "required_subjects": valid_subjects,
                "source_evidence": evidence,
                "extraction_notes": "Extracted directly with Gemini AI. Verify all requirements before approval.",
                "status": "NeedsReview",
            })
    except Exception as exc:
        logger.warning("Failed to parse direct Gemini extraction: %s", exc)

    return results


def extract_programme_drafts(
    text: str,
    api_key: str | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """Return likely qualification headings with requirements, enriched by Gemini when available."""
    candidates = _extract_candidates_regex(text)
    effective_key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
    effective_model = model or os.environ.get("RAG_GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

    if effective_key:
        if candidates:
            candidates = _enrich_candidates_with_gemini(candidates, effective_key, effective_model)
        else:
            candidates = _extract_candidates_gemini_direct(text, effective_key, effective_model)

    return candidates
