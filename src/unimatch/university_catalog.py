"""Curated South African public university directory metadata.

The public university names are based on the Department of Higher Education
and Training's public ``Universities in South Africa`` directory. The DHET
private higher education register is a separate, frequently updated register;
it must be imported as data rather than conflated with the public-university
list. This module deliberately contains no programme or admissions rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5


_NAMESPACE = UUID("8aaae526-4c7a-5b14-8b19-a5746e98f880")
DHET_PUBLIC_UNIVERSITIES_URL = "https://www.dhet.gov.za/SitePages/UniversitiesinSA.aspx"


@dataclass(frozen=True, slots=True)
class UniversityCatalogEntry:
    university_id: UUID
    name: str
    abbreviation: str
    institution_type: str = "Public university"
    source_url: str = DHET_PUBLIC_UNIVERSITIES_URL


_PUBLIC_UNIVERSITIES = (
    ("Cape Peninsula University of Technology", "CPUT"),
    ("Central University of Technology, Free State", "CUT"),
    ("Durban University of Technology", "DUT"),
    ("Mangosuthu University of Technology", "MUT"),
    ("Nelson Mandela University", "NMU"),
    ("North-West University", "NWU"),
    ("Rhodes University", "RU"),
    ("Sefako Makgatho Health Sciences University", "SMU"),
    ("Sol Plaatje University", "SPU"),
    ("Stellenbosch University", "SU"),
    ("Tshwane University of Technology", "TUT"),
    ("University of Cape Town", "UCT"),
    ("University of Fort Hare", "UFH"),
    ("University of Johannesburg", "UJ"),
    ("University of KwaZulu-Natal", "UKZN"),
    ("University of Limpopo", "UL"),
    ("University of Mpumalanga", "UMP"),
    ("University of Pretoria", "UP"),
    ("University of South Africa", "UNISA"),
    ("University of the Free State", "UFS"),
    ("University of the Western Cape", "UWC"),
    ("University of the Witwatersrand", "Wits"),
    ("University of Zululand", "UNIZULU"),
    ("University of Venda", "UNIVEN"),
    ("Vaal University of Technology", "VUT"),
    ("Walter Sisulu University", "WSU"),
)

PUBLIC_UNIVERSITIES = tuple(
    UniversityCatalogEntry(
        university_id=uuid5(_NAMESPACE, abbreviation),
        name=name,
        abbreviation=abbreviation,
    )
    for name, abbreviation in _PUBLIC_UNIVERSITIES
)

PUBLIC_UNIVERSITY_BY_ID = {entry.university_id: entry for entry in PUBLIC_UNIVERSITIES}
PUBLIC_UNIVERSITY_BY_CODE = {
    entry.abbreviation.casefold(): entry for entry in PUBLIC_UNIVERSITIES
}
