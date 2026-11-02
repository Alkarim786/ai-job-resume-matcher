import io
import random
from datetime import date

import pytest
from reportlab.pdfgen import canvas

from app.parsing import ResumeParseError, extract_titles, parse_resume_pdf, parse_resume_text, years_from_text
from app.seed.generate import FAMILIES, REFERENCE_DATE, make_resume, render_pdf
from app.skills import canonical_skill, extract_skills

TODAY = date(2026, 11, 1)


def test_ambiguous_skills_only_count_in_skills_section():
    prose = "I like to Go to the market and R is a letter. Worked on a C level strategy."
    assert extract_skills(prose, skills_section="") == []
    assert set(extract_skills("Skills\nGo, Rust, R, C, Python", skills_section="Go, Rust, R, C, Python")) >= {"go", "rust", "r", "c", "python"}


def test_cpp_and_csharp_do_not_trigger_c():
    found = extract_skills("Built engines in C++ and services in C#.", "")
    assert "c++" in found and "c#" in found and "c" not in found


def test_alias_matching():
    found = extract_skills("Deployed on K8s with Postgres, Node.js and GitHub Actions; used scikit-learn and sklearn.", "")
    assert {"kubernetes", "postgresql", "node.js", "ci/cd", "scikit-learn"} <= set(found)


def test_no_substring_false_positives():
    assert "java" not in extract_skills("I know javascript only", "")
    assert "sql" not in extract_skills("nosqlish stuff", "")
    assert canonical_skill("K8S") == "kubernetes"
    assert canonical_skill("not-a-skill") is None


def test_years_union_counts_overlap_once():
    exp = "Engineer | A | Jan 2019 - Dec 2020\nEngineer | B | Jun 2020 - Dec 2021"
    assert years_from_text(exp, exp, TODAY) == pytest.approx(3.0)


def test_years_present_and_year_only_ranges():
    assert years_from_text("Dev | X | Jan 2024 - Present", "", date(2026, 1, 1)) == pytest.approx(2.1, abs=0.1)
    assert years_from_text("Dev | X | 2018 - 2020", "", TODAY) == pytest.approx(3.0)


def test_years_falls_back_to_claim():
    assert years_from_text("", "Seasoned engineer with 7+ years of experience", TODAY) == 7.0
    assert years_from_text("", "no numbers here", TODAY) == 0.0


def test_titles_extracted_from_dated_lines():
    exp = "Senior Backend Engineer | Acme | Jan 2020 - Present\n• built things\nBackend Engineer at Foo, Mar 2017 - Dec 2019"
    assert extract_titles(exp) == ["Senior Backend Engineer", "Backend Engineer"]


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_generated_pdf_round_trip(family):
    spec = make_resume(random.Random(3), family, 3)
    parsed = parse_resume_pdf(render_pdf(spec), today=REFERENCE_DATE)
    assert parsed.name == spec.name
    assert set(parsed.sections) >= {"summary", "experience", "education", "skills"}
    assert parsed.years_experience == pytest.approx(spec.years, abs=0.1)
    assert parsed.titles, "titles should be extracted from the experience section"
    assert parsed.chunks and all(len(c.split()) <= 140 for c in parsed.chunks)
    # bullets wrapped by the PDF layout are re-joined into whole sentences
    assert all(b.rstrip().endswith(".") for line in parsed.sections["experience"].splitlines() if line.startswith("•") for b in [line])


def test_skill_extraction_precision_recall_on_generated_pdfs():
    tp = fp = fn = 0
    for i in range(40):
        spec = make_resume(random.Random(i), sorted(FAMILIES)[i % len(FAMILIES)], i, stuffed=i % 6 == 5)
        got = set(parse_resume_pdf(render_pdf(spec), today=REFERENCE_DATE).skills)
        truth = set(spec.skills)
        tp, fp, fn = tp + len(got & truth), fp + len(got - truth), fn + len(truth - got)
    precision, recall = tp / (tp + fp), tp / (tp + fn)
    assert recall >= 0.95, recall
    assert precision >= 0.85, precision


def test_image_only_pdf_is_rejected_with_clear_error():
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(10, 10, 100, 100, fill=1)
    c.save()
    with pytest.raises(ResumeParseError, match="no extractable text"):
        parse_resume_pdf(buf.getvalue())


def test_corrupt_pdf_is_rejected():
    with pytest.raises(ResumeParseError):
        parse_resume_pdf(b"%PDF-1.4 this is not really a pdf")


def test_unstructured_resume_still_gets_chunks():
    text = "Jane Doe\n" + "Experienced engineer who built distributed systems in Python and Kafka. " * 30
    parsed = parse_resume_text(text, TODAY)
    assert parsed.chunks and "python" in parsed.skills and "kafka" in parsed.skills
