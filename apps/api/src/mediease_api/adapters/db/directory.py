"""The directory search read over PostgreSQL with ``pg_trgm`` (M6c-P6; ADR-0021).

A reviewed cross-clinic read (ports/directory.py): it reads only the columns a clinic publishes
(name, place, specialties; a doctor's name, specialty and languages) and returns IDs, a score and
a place rank. Every value from the searcher is a bound parameter; words are compared with
``word_similarity`` and ``strpos``, never ``LIKE``, so no input is a pattern.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from mediease_api.ports.directory import Candidate, DirectoryFilter

# A candidate needs at least this relevance when words were given.
MIN_SCORE = 0.3

_PUBLIC_DOCTOR = "d.is_active AND d.verified_at IS NOT NULL AND d.visible"
_LISTED_CLINIC = "c.listed AND c.status = 'ACTIVE' AND c.verified_at IS NOT NULL"

_PLACE = """
    CASE
        WHEN :pincode <> '' AND c.pincode = :pincode THEN 0
        WHEN :city <> '' AND lower(c.city) = :city THEN 1
        WHEN :pincode <> '' AND left(c.pincode, 3) = left(:pincode, 3) THEN 2
        ELSE 3
    END
"""

_FILTERS = f"""
    AND (:specialty = '' OR lower(:specialty) = ANY (SELECT lower(s) FROM unnest(c.specialties) s)
         OR EXISTS (SELECT 1 FROM doctors sd WHERE sd.clinic_id = c.id
                    AND sd.is_active AND sd.verified_at IS NOT NULL AND sd.visible
                    AND lower(sd.specialty) = lower(:specialty)))
    AND (:language = '' OR EXISTS (SELECT 1 FROM doctors ld WHERE ld.clinic_id = c.id
                    AND ld.is_active AND ld.verified_at IS NOT NULL AND ld.visible
                    AND :language = ANY (ld.languages)))
    AND ((:pincode = '' AND :city = '') OR ({_PLACE}) <= 2)
"""

_CLINICS = f"""
SELECT clinic_id, NULL::uuid AS doctor_id, score, place FROM (
    SELECT c.id AS clinic_id,
        CASE WHEN :q = '' THEN 0 ELSE GREATEST(
            word_similarity(:q, lower(c.name)),
            COALESCE((SELECT max(word_similarity(:q, lower(d.display_name))) FROM doctors d
                      WHERE d.clinic_id = c.id AND {_PUBLIC_DOCTOR}), 0),
            CASE WHEN EXISTS (SELECT 1 FROM unnest(c.specialties) s
                              WHERE strpos(lower(s), :q) > 0) THEN 0.9 ELSE 0 END,
            CASE WHEN EXISTS (SELECT 1 FROM doctors d WHERE d.clinic_id = c.id
                              AND {_PUBLIC_DOCTOR} AND strpos(lower(d.specialty), :q) > 0)
                 THEN 0.9 ELSE 0 END
        ) END AS score,
        {_PLACE} AS place,
        c.name AS name
    FROM clinics c
    WHERE {_LISTED_CLINIC} {_FILTERS}
) ranked
WHERE :q = '' OR score >= :min_score
ORDER BY round(score::numeric, 1) DESC, place, name
LIMIT :limit
"""

_DOCTORS = f"""
SELECT clinic_id, doctor_id, score, place FROM (
    SELECT c.id AS clinic_id, d.id AS doctor_id,
        CASE WHEN :q = '' THEN 0 ELSE GREATEST(
            word_similarity(:q, lower(d.display_name)),
            word_similarity(:q, lower(c.name)) * 0.8,
            CASE WHEN strpos(lower(coalesce(d.specialty, '')), :q) > 0 THEN 0.9 ELSE 0 END,
            CASE WHEN EXISTS (SELECT 1 FROM unnest(c.specialties) s
                              WHERE strpos(lower(s), :q) > 0) THEN 0.7 ELSE 0 END
        ) END AS score,
        {_PLACE} AS place,
        d.display_name AS name
    FROM doctors d JOIN clinics c ON c.id = d.clinic_id
    WHERE {_PUBLIC_DOCTOR} AND {_LISTED_CLINIC}
        AND (:specialty = '' OR lower(d.specialty) = lower(:specialty)
             OR lower(:specialty) = ANY (SELECT lower(s) FROM unnest(c.specialties) s))
        AND (:language = '' OR :language = ANY (d.languages))
        AND ((:pincode = '' AND :city = '') OR ({_PLACE}) <= 2)
) ranked
WHERE :q = '' OR score >= :min_score
ORDER BY round(score::numeric, 1) DESC, place, name
LIMIT :limit
"""


class SqlAlchemyDirectoryReader:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _params(f: DirectoryFilter, limit: int) -> dict[str, Any]:
        return {
            "q": f.q,
            "city": f.city or "",
            "pincode": f.pincode or "",
            "specialty": f.specialty or "",
            "language": f.language or "",
            "min_score": MIN_SCORE,
            "limit": limit,
        }

    def _run(self, sql: str, f: DirectoryFilter, limit: int) -> Sequence[Candidate]:
        rows = self._session.execute(text(sql), self._params(f, limit))
        return [Candidate(r.clinic_id, r.doctor_id, float(r.score), int(r.place)) for r in rows]

    def clinics(self, f: DirectoryFilter, *, limit: int) -> Sequence[Candidate]:
        return self._run(_CLINICS, f, limit)

    def doctors(self, f: DirectoryFilter, *, limit: int) -> Sequence[Candidate]:
        return self._run(_DOCTORS, f, limit)
