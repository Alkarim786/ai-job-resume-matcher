"""PDF -> structured resume: text, sections, skills, titles, years of experience, embedding chunks."""

import io
import re
from dataclasses import dataclass, field
from datetime import date

from pypdf import PdfReader

from app.skills import extract_skills

SECTION_ALIASES = {
    "summary": {"summary", "profile", "objective", "about", "professional summary", "career objective"},
    "experience": {"experience", "work experience", "professional experience", "employment", "employment history", "work history"},
    "education": {"education", "academic background", "qualifications"},
    "skills": {"skills", "technical skills", "core skills", "key skills", "skills & tools", "tech stack"},
    "projects": {"projects", "personal projects", "selected projects", "academic projects"},
    "certifications": {"certifications", "certificates", "awards", "achievements"},
}
_HEADING_TO_SECTION = {alias: sec for sec, aliases in SECTION_ALIASES.items() for alias in aliases}

_MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_DATE = r"(?:(?P<{m}>[A-Za-z]{{3,9}})\.?,?\s+)?(?P<{y}>(?:19|20)\d{{2}})"
_RANGE = re.compile(
    _DATE.format(m="m1", y="y1") + r"\s*(?:-|–|—|to)\s*(?:(?P<now>present|current|now|till date|ongoing)|" + _DATE.format(m="m2", y="y2") + ")",
    re.IGNORECASE,
)
_YEARS_CLAIM = re.compile(r"(\d{1,2})\s*\+?\s*(?:years|yrs)\b", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")


@dataclass
class ParsedResume:
    text: str
    name: str = ""
    headline: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    years_experience: float = 0.0
    chunks: list[str] = field(default_factory=list)

    def as_json(self) -> dict:
        return {
            "name": self.name,
            "headline": self.headline,
            "sections": {k: v[:2000] for k, v in self.sections.items()},
            "skills": self.skills,
            "titles": self.titles,
            "years_experience": self.years_experience,
            "chunk_count": len(self.chunks),
        }


class ResumeParseError(ValueError):
    pass


_BULLET = re.compile(r"^\s*[•\-*▪◦]\s*")


def _unwrap(text: str) -> str:
    """Re-join bullet items that the PDF layout wrapped onto several lines (continuation = long unbulleted line after a bullet)."""
    out: list[str] = []
    in_bullet = False
    for line in text.splitlines():
        stripped = line.strip()
        is_heading = re.sub(r"[:\s]+$", "", stripped.lower()) in _HEADING_TO_SECTION
        if _BULLET.match(stripped):
            out.append(stripped)
            in_bullet = True
        elif in_bullet and out and stripped and not is_heading and not _RANGE.search(stripped) and len(out[-1]) >= 60:
            out[-1] += " " + stripped
            if stripped.endswith("."):
                in_bullet = False
        else:
            out.append(line)
            in_bullet = False
    return "\n".join(out)


def extract_text(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [(p.extract_text() or "") for p in reader.pages]
    except Exception as exc:  # pypdf raises many types for corrupt files
        raise ResumeParseError(f"cannot read PDF: {exc}") from exc
    text = "\n".join(pages).replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # de-hyphenate wrapped words
    text = _unwrap(re.sub(r"\n{3,}", "\n\n", text).strip())
    if len(text) < 40:
        raise ResumeParseError("no extractable text (scanned/image-only PDF? OCR is on the roadmap)")
    return text


def split_sections(text: str) -> tuple[list[str], dict[str, str]]:
    """Return (header_lines, {section: body}). Headings are short standalone lines matching known aliases."""
    header: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        key = re.sub(r"[:\s]+$", "", line.lower())
        if key in _HEADING_TO_SECTION and len(line) <= 40:
            current = _HEADING_TO_SECTION[key]
            sections.setdefault(current, [])
        elif current is None:
            header.append(line)
        else:
            sections[current].append(line)
    return header, {k: "\n".join(v) for k, v in sections.items()}


def _to_month_index(month: str | None, year: str) -> int:
    m = _MONTHS.get((month or "")[:3].lower(), 1)
    return int(year) * 12 + (m - 1)


def _date_ranges(text: str, today: date) -> list[tuple[int, int]]:
    ranges = []
    for mt in _RANGE.finditer(text):
        start = _to_month_index(mt.group("m1"), mt.group("y1"))
        end = _to_month_index(None, str(today.year)) + (today.month - 1) if mt.group("now") else _to_month_index(mt.group("m2"), mt.group("y2"))
        if mt.group("m2") is None and not mt.group("now"):
            end += 11  # "2019 - 2021" means through the end of 2021
        if end >= start and end - start <= 12 * 50:
            ranges.append((start, end + 1))  # end month is inclusive
    return ranges


def years_from_text(experience_text: str, whole_text: str, today: date | None = None) -> float:
    """Union of date ranges in the experience section (overlaps counted once); falls back to an 'N years' claim."""
    today = today or date.today()
    spans = sorted(_date_ranges(experience_text, today))
    total = 0
    cur_s = cur_e = None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    if total > 0:
        return round(total / 12, 1)
    claims = [int(x) for x in _YEARS_CLAIM.findall(whole_text)]
    return float(max(claims)) if claims and max(claims) <= 40 else 0.0


def extract_titles(experience_text: str) -> list[str]:
    titles = []
    for line in experience_text.splitlines():
        if not _RANGE.search(line):
            continue
        head = _RANGE.sub("", line)
        head = re.split(r"\s*[|•·]\s*|\s+at\s+|\s+@\s+|,\s+", head)[0].strip(" -–—()")
        if 3 <= len(head) <= 70 and head.lower() not in titles:
            titles.append(head)
    return titles


def make_chunks(sections: dict[str, str], header_text: str, max_words: int = 70) -> list[str]:
    """Group consecutive lines of the content sections into ~max_words chunks (each chunk stays inside one section)."""
    chunks: list[str] = []
    order = ["summary", "experience", "projects", "skills", "certifications"]
    for sec in order:
        body = sections.get(sec)
        if not body:
            continue
        buf: list[str] = []
        words = 0
        for line in body.splitlines():
            n = len(line.split())
            if buf and words + n > max_words:
                chunks.append(" ".join(buf))
                buf, words = [], 0
            buf.append(line.lstrip("•-* "))
            words += n
        if buf:
            chunks.append(" ".join(buf))
    if not chunks:  # unstructured resume: window the whole text
        toks = header_text.split()
        chunks = [" ".join(toks[i : i + max_words]) for i in range(0, len(toks), max_words)]
    return chunks


def parse_resume_text(text: str, today: date | None = None) -> ParsedResume:
    header, sections = split_sections(text)
    name = header[0] if header else ""
    headline = ""
    for line in header[1:4]:
        if not _EMAIL.search(line) and not _PHONE.search(line) and len(line) <= 90:
            headline = line
            break
    exp = sections.get("experience", "")
    skills = extract_skills(text, sections.get("skills", ""))
    return ParsedResume(
        text=text,
        name=name,
        headline=headline,
        sections=sections,
        skills=skills,
        titles=extract_titles(exp),
        years_experience=years_from_text(exp, text, today),
        chunks=make_chunks(sections, text),
    )


def parse_resume_pdf(pdf_bytes: bytes, today: date | None = None) -> ParsedResume:
    return parse_resume_text(extract_text(pdf_bytes), today)
