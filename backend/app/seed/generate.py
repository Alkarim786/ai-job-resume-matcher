"""Synthetic resumes (rendered to real PDFs) and jobs with generator-defined relevance labels.

The labels come from the generating role family, not from human judgement:
  2 = same family, 1 = adjacent family, 0 = unrelated. Say so wherever results are quoted.
"""

import io
import random
from dataclasses import dataclass, field
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

REFERENCE_DATE = date(2026, 11, 1)  # "today" for years-of-experience, so results are reproducible

FAMILIES: dict[str, dict] = {
    "backend": {
        "titles": ["Backend Engineer", "Senior Backend Engineer", "Software Engineer, Platform", "API Developer"],
        "core": ["python", "java", "spring boot", "fastapi", "django", "postgresql", "redis", "kafka", "rest api", "microservices", "docker", "grpc"],
        "extra": ["aws", "git", "sql", "mysql"],
        "bullets": [
            "Designed and shipped {s} services handling millions of requests per day with strict latency budgets.",
            "Built a {s} based order processing pipeline that cut end to end response time by 40 percent.",
            "Modelled relational schemas, wrote migrations and tuned slow queries behind high traffic endpoints.",
            "Introduced idempotent request handling and retries so payment APIs stayed consistent under failures.",
            "Split a monolith into independently deployable services communicating over {s} and message queues.",
            "Added caching and rate limiting in front of hot endpoints, reducing database load significantly.",
            "Wrote integration tests and load tests for server side APIs and fixed concurrency bugs found under load.",
        ],
        "reqs": [
            "Design, build and operate scalable server side services and APIs used by millions of customers.",
            "Strong experience with {s} and relational database design, indexing and query tuning.",
            "Own the reliability, latency and correctness of backend systems in production.",
            "Work with message queues and asynchronous processing to decouple services.",
            "Write clean, well tested code and review the code of teammates.",
        ],
    },
    "frontend": {
        "titles": ["Frontend Engineer", "Senior Frontend Developer", "UI Engineer", "Web Developer"],
        "core": ["javascript", "typescript", "react", "next.js", "html", "css", "redux", "tailwind", "graphql", "cypress", "figma"],
        "extra": ["git", "rest api", "node.js", "vue"],
        "bullets": [
            "Built responsive, accessible user interfaces in {s} used by hundreds of thousands of customers.",
            "Improved page load time and Core Web Vitals by code splitting, lazy loading and image optimisation.",
            "Created a shared component library and design system adopted by six product teams.",
            "Implemented complex client side state management and form workflows with optimistic updates.",
            "Translated design mockups into pixel accurate pages and animations across browsers and devices.",
            "Wrote component tests and end to end browser tests that caught regressions before release.",
            "Integrated the user interface with backend endpoints and handled loading, error and empty states.",
        ],
        "reqs": [
            "Build fast, accessible and responsive user interfaces for our web application.",
            "Deep experience with {s} and modern component based frontend architecture.",
            "Collaborate with designers to turn mockups into polished interactive pages.",
            "Care about browser performance, bundle size and Core Web Vitals.",
            "Write component tests and browser end to end tests for the interface.",
        ],
    },
    "fullstack": {
        "titles": ["Full Stack Developer", "Full Stack Engineer", "Software Engineer, Web", "Senior Full Stack Developer"],
        "core": ["node.js", "express", "react", "typescript", "postgresql", "mongodb", "rest api", "docker", "next.js", "git"],
        "extra": ["javascript", "redis", "aws", "css"],
        "bullets": [
            "Delivered customer facing features end to end, from the {s} interface to the server and the database.",
            "Built a {s} web application with authentication, role based access and an admin dashboard.",
            "Designed REST endpoints and the matching React screens for a subscription billing product.",
            "Set up deployment with containers and continuous integration so the whole team shipped weekly.",
            "Owned a product feature from prototype to production, including schema design and the user interface.",
            "Added real time updates to the dashboard using websockets and a lightweight event layer.",
            "Wrote tests across the stack and fixed bugs in both the client and the server code.",
        ],
        "reqs": [
            "Build product features end to end across the web interface, the API and the database.",
            "Experience with {s} on both the client and the server.",
            "Ship quickly, iterate with customers and own what you build in production.",
            "Design database schemas and REST endpoints that the interface can rely on.",
            "Comfortable deploying with containers and continuous integration.",
        ],
    },
    "ml": {
        "titles": ["Machine Learning Engineer", "Data Scientist", "Applied Scientist", "NLP Engineer"],
        "core": ["python", "pytorch", "tensorflow", "scikit-learn", "pandas", "numpy", "nlp", "deep learning", "machine learning", "llm", "hugging face", "statistics", "mlops"],
        "extra": ["sql", "docker", "git", "aws"],
        "bullets": [
            "Trained and evaluated {s} models that improved recommendation click through rate in online experiments.",
            "Fine tuned transformer language models on domain text and cut annotation effort with active learning.",
            "Built feature engineering pipelines and cross validated gradient boosted models for churn prediction.",
            "Reduced inference latency of a neural network by 3x using quantisation and batching.",
            "Designed offline evaluation metrics and ran statistical tests to decide whether a new model shipped.",
            "Deployed models behind a prediction service and monitored data drift and model quality over time.",
            "Explored large datasets, found label noise and built cleaner training sets for classifiers.",
        ],
        "reqs": [
            "Train, evaluate and deploy machine learning models that solve real product problems.",
            "Hands on experience with {s} and rigorous offline and online evaluation.",
            "Build data and feature pipelines for model training and monitor models in production.",
            "Fine tune and evaluate language models and neural networks on large datasets.",
            "Communicate experiment results and trade offs clearly to non technical partners.",
        ],
    },
    "data_eng": {
        "titles": ["Data Engineer", "Senior Data Engineer", "Analytics Engineer", "Big Data Developer"],
        "core": ["python", "sql", "spark", "airflow", "kafka", "dbt", "snowflake", "etl", "data modeling", "bigquery", "hadoop", "aws"],
        "extra": ["docker", "git", "postgresql", "bash"],
        "bullets": [
            "Built batch and streaming {s} pipelines moving terabytes of events into the warehouse every day.",
            "Orchestrated hundreds of scheduled workflows with retries, backfills and data quality checks.",
            "Modelled star schema warehouse tables so analysts could answer questions with simple queries.",
            "Migrated legacy nightly jobs to incremental loads and cut pipeline run time from six hours to one.",
            "Added data quality tests and lineage so broken upstream feeds were caught before dashboards.",
            "Optimised slow warehouse queries and storage layout to reduce monthly compute cost by 30 percent.",
            "Ingested clickstream and transactional data from many sources into a central lake.",
        ],
        "reqs": [
            "Design and maintain reliable batch and streaming data pipelines at large scale.",
            "Strong skills in {s} and warehouse data modelling.",
            "Build data quality checks, monitoring and lineage for the data platform.",
            "Partner with analysts and scientists to deliver clean, trusted datasets.",
            "Optimise pipeline performance and warehouse cost.",
        ],
    },
    "devops": {
        "titles": ["DevOps Engineer", "Site Reliability Engineer", "Platform Engineer", "Cloud Infrastructure Engineer"],
        "core": ["kubernetes", "docker", "terraform", "ansible", "aws", "ci/cd", "linux", "prometheus", "grafana", "helm", "bash", "sre", "gcp"],
        "extra": ["python", "git", "nginx", "azure"],
        "bullets": [
            "Managed production clusters with {s} and automated rollouts with zero downtime deployments.",
            "Codified cloud infrastructure so environments could be recreated from version control in minutes.",
            "Built deployment pipelines that ran tests, built images and promoted releases automatically.",
            "Defined service level objectives, alerts and dashboards and cut paging noise by half.",
            "Led incident response and wrote blameless postmortems that removed recurring outage causes.",
            "Reduced cloud spend by 25 percent through right sizing, autoscaling and spot capacity.",
            "Hardened servers and networks, automated patching and managed secrets for all services.",
        ],
        "reqs": [
            "Run and scale production infrastructure with high availability.",
            "Experience with {s} and infrastructure as code.",
            "Build deployment pipelines, alerting and dashboards for engineering teams.",
            "Lead incident response and improve reliability through postmortems.",
            "Automate repetitive operations and manage cloud cost.",
        ],
    },
    "mobile": {
        "titles": ["Android Developer", "iOS Engineer", "Mobile Engineer", "Senior Mobile Developer"],
        "core": ["kotlin", "android", "swift", "ios", "flutter", "react native", "rest api", "git"],
        "extra": ["java", "typescript", "graphql", "figma"],
        "bullets": [
            "Built and published {s} apps with millions of installs and a 4.7 store rating.",
            "Implemented offline first screens with local storage and background synchronisation.",
            "Reduced app startup time and memory use and fixed crashes found through crash reporting.",
            "Integrated push notifications, in app purchases and deep links into the mobile application.",
            "Worked with designers on native navigation, gestures and smooth animations on phones and tablets.",
            "Set up automated builds and staged rollouts to the app stores.",
            "Wrote unit and interface tests for view models and screens on real devices.",
        ],
        "reqs": [
            "Build and ship high quality mobile applications to the app stores.",
            "Strong experience with {s} and native mobile interface patterns.",
            "Make apps fast, stable and usable offline on unreliable networks.",
            "Integrate push notifications, payments and analytics into the app.",
            "Partner with designers on smooth, native feeling screens.",
        ],
    },
    "qa": {
        "titles": ["QA Automation Engineer", "SDET", "Test Engineer", "Quality Engineer"],
        "core": ["selenium", "pytest", "junit", "cypress", "test automation", "ci/cd", "jira", "python", "java", "agile"],
        "extra": ["git", "sql", "docker", "rest api"],
        "bullets": [
            "Built a {s} regression suite that covered 80 percent of critical user flows and ran on every commit.",
            "Reduced flaky tests by isolating test data and adding deterministic waits and retries.",
            "Designed test plans, edge case matrices and exploratory sessions for each release.",
            "Automated API checks and contract tests so integration bugs surfaced before staging.",
            "Triaged defects with developers, reproduced issues and tracked them to closure.",
            "Integrated the automated suites into the build pipeline with parallel execution and reports.",
            "Introduced performance and smoke checks that blocked bad releases.",
        ],
        "reqs": [
            "Design and maintain automated test suites for web and API products.",
            "Experience with {s} and test frameworks.",
            "Own release quality: test plans, defect triage and regression coverage.",
            "Make tests fast, stable and part of the build pipeline.",
            "Work closely with developers to find issues early.",
        ],
    },
}

_ADJACENT = {
    frozenset(p)
    for p in [
        ("backend", "fullstack"),
        ("frontend", "fullstack"),
        ("backend", "devops"),
        ("backend", "data_eng"),
        ("data_eng", "ml"),
        ("frontend", "mobile"),
        ("backend", "qa"),
        ("fullstack", "qa"),
    ]
}

FIRST = "Aarav Priya Rohan Ananya Vikram Sneha Arjun Meera Karthik Divya Rahul Kavya Imran Zara Noah Maya Liam Sofia Ethan Isha Omar Leila Diego Chen Yuki Fatima Tomas Nadia Kofi Ines".split()
LAST = "Sharma Iyer Patel Nair Reddy Khan Singh Gupta Rao Das Mehta Joshi Kapoor Verma Silva Garcia Kim Nguyen Okafor Novak Rossi Ahmed Fischer Haddad Mendes".split()
COMPANIES = "Northwind Lumen Brightloop Quanta Helix Stackwise Orbit Tessera Nimbus Kestrel Paperplane Vantage Cobalt Juniper Meridian".split()
CITIES = ["Bengaluru", "Hyderabad", "Chennai", "Pune", "Mumbai", "Delhi", "Remote"]


def relevance(resume_family: str, job_family: str) -> int:
    if resume_family == job_family:
        return 2
    return 1 if frozenset((resume_family, job_family)) in _ADJACENT else 0


@dataclass
class ResumeSpec:
    name: str
    family: str
    skills: list[str]
    years: float
    lines: list[str]
    stuffed: bool = False
    email: str = ""

    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass
class JobSpec:
    title: str
    family: str
    company: str
    description: str
    must_have: list[str]
    nice_to_have: list[str]
    min_years: float
    extra: dict = field(default_factory=dict)


def _fmt(month_idx: int) -> str:
    y, m = divmod(month_idx, 12)
    return f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m]} {y}"


def make_resume(rng: random.Random, family: str, idx: int, stuffed: bool = False) -> ResumeSpec:
    fam = FAMILIES[family]
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    skills = rng.sample(fam["core"], k=min(len(fam["core"]), rng.randint(5, 8))) + rng.sample(fam["extra"], k=rng.randint(1, 2))
    if stuffed:  # buzzword stuffing: skills of another family in the Skills list, but experience stays in the true family
        other = rng.choice([f for f in FAMILIES if f != family and relevance(family, f) == 0])
        skills += rng.sample(FAMILIES[other]["core"], k=6)
    skills = list(dict.fromkeys(skills))
    total_years = rng.choice([1, 2, 3, 4, 5, 6, 8, 10])
    end = REFERENCE_DATE.year * 12 + REFERENCE_DATE.month - 1
    n_jobs = 1 if total_years <= 2 else rng.randint(2, 3)
    cuts = sorted(rng.sample(range(1, total_years * 12), n_jobs - 1)) if n_jobs > 1 else []
    bounds = [end - total_years * 12] + [end - total_years * 12 + c for c in cuts] + [end]
    lines = [name, rng.choice(fam["titles"]), f"{name.split()[0].lower()}.{name.split()[-1].lower()}{idx}@mail.example | +91 98{rng.randint(10000000, 99999999)} | {rng.choice(CITIES)}"]
    lines += ["SUMMARY", f"{rng.choice(fam['titles'])} with {total_years} years of experience building products people use every day."]
    lines.append("EXPERIENCE")
    used = [s for s in skills if s in fam["core"] or s in fam["extra"]]
    for j in range(n_jobs - 1, -1, -1):
        start, stop = bounds[j], bounds[j + 1]
        stop_txt = "Present" if j == n_jobs - 1 else _fmt(stop)
        lines.append(f"{rng.choice(fam['titles'])} | {rng.choice(COMPANIES)} | {_fmt(start)} - {stop_txt}")
        for b in rng.sample(fam["bullets"], k=3):
            lines.append("• " + b.format(s=rng.choice(used)))
    lines += ["EDUCATION", f"B.Tech Computer Science, {rng.choice(COMPANIES)} Institute of Technology (2014 - 2018)"]
    lines += ["SKILLS", ", ".join(s.title() if len(s) > 3 else s.upper() for s in skills)]
    return ResumeSpec(name=name, family=family, skills=sorted(skills), years=float(total_years), lines=lines, stuffed=stuffed, email=f"{name.split()[0].lower()}{idx}@example.com")


def make_job(rng: random.Random, family: str) -> JobSpec:
    fam = FAMILIES[family]
    must = rng.sample(fam["core"], k=rng.randint(3, 5))
    nice = rng.sample([s for s in fam["core"] + fam["extra"] if s not in must], k=2)
    title = rng.choice(fam["titles"])
    reqs = [r.format(s=", ".join(must[:3])) for r in fam["reqs"]]
    desc = f"We are hiring a {title}. " + " ".join(reqs)
    return JobSpec(title=title, family=family, company=rng.choice(COMPANIES), description=desc, must_have=must, nice_to_have=nice, min_years=float(rng.choice([1, 2, 3, 4, 5])))


def build_dataset(n_resumes: int, n_jobs: int, seed: int = 7, stuffed_frac: float = 1 / 6):
    rng = random.Random(seed)
    fams = list(FAMILIES)
    resumes = []
    for i in range(n_resumes):
        resumes.append(make_resume(rng, fams[i % len(fams)], i, stuffed=(i % round(1 / stuffed_frac) == 5)))
    jobs = [make_job(rng, fams[i % len(fams)]) for i in range(n_jobs)]
    return resumes, jobs


def render_pdf(spec: ResumeSpec) -> bytes:
    """Lay the resume out as a real text PDF (headings bold, wrapped paragraphs) via reportlab."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    left, top, bottom = 50, height - 50, 50
    y = top
    for i, line in enumerate(spec.lines):
        heading = line.isupper() and len(line) < 20
        font, size = ("Helvetica-Bold", 12) if (heading or i == 0) else ("Helvetica", 10)
        wrapped = simpleSplit(line, font, size, width - 2 * left)
        for k, w in enumerate(wrapped):
            if y < bottom:
                c.showPage()
                y = top
            c.setFont(font, size)
            c.drawString(left + (12 if k and line.startswith("•") else 0), y, w)
            y -= size + 3
        if heading:
            y -= 2
    c.save()
    return buf.getvalue()
