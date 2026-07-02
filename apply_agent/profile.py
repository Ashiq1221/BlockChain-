"""Candidate profile — single source of truth for every application.

Built from apply_agent/data/Ashiq_Resume_ATS.docx. Values the resume doesn't
state (last name, salary, notice period) come from env so they're never
invented by the AI.
"""
import os
from pathlib import Path

RESUME_PATH = str(Path(__file__).parent / "data" / "Ashiq_Resume_ATS.docx")

PROFILE: dict = {
    "first_name": os.getenv("APPLY_FIRST_NAME", "Ashiq"),
    "last_name":  os.getenv("APPLY_LAST_NAME", "Ah"),
    "full_name":  os.getenv("APPLY_FULL_NAME", "Ashiq Ah"),
    "email":      os.getenv("APPLY_EMAIL", "naveeddurfi@gmail.com"),
    "phone":      os.getenv("APPLY_PHONE", ""),
    "location":   "Kashmir, India (Open to Remote)",
    "city":       "Srinagar",
    "country":    "India",
    "links": {
        "linkedin": "https://linkedin.com/in/ashiq-ah-705334395",
        "twitter":  "https://x.com/ganaie__suhail",
        "telegram": "@ashiq80",
        "discord":  "ashiq1581",
        "portfolio": os.getenv("APPLY_PORTFOLIO", "https://x.com/ganaie__suhail"),
        "github":   os.getenv("APPLY_GITHUB", ""),
        "website":  os.getenv("APPLY_WEBSITE", ""),
        # Proof of work — the communities behind the resume's growth claims
        "tg_channel": "https://t.me/icpcollectible",
        "tg_group":   "https://t.me/icpcollectiblediscus",
    },
    "headline": ("AI Operations Specialist | Agentic AI & Automation Practitioner "
                 "| Community Builder | Content Creator"),
    "summary": (
        "AI Operations Specialist and Agentic AI Practitioner with hands-on experience in "
        "agentic AI workflows, AI automation, data annotation, chatbot testing, prompt "
        "engineering, and AI content creation. Certified in AI Tools & ChatGPT (be10x) and "
        "Python Using AI (AI FOR TECHIES). Grew a Web3 Twitter/X account to 16,000+ followers "
        "organically and built a 6,000+ member community across Telegram, Discord, and X. "
        "Multilingual: English, Hindi, Urdu, and Kashmiri."
    ),
    "skills": [
        "Agentic AI", "AI Automation & Workflow Optimization", "Prompt Engineering",
        "AI Data Annotation & Labeling", "Chatbot Testing & Evaluation",
        "AI Model Training Support", "Data Quality Assurance", "Python with AI",
        "AI Content Generation", "LLMs", "ChatGPT", "Claude AI", "Generative AI",
        "Community Management", "Content Moderation", "Social Media Management",
        "Twitter/X", "Telegram", "Discord", "Copywriting", "Short-Form Video",
        "Localization & Translation Data (English, Hindi, Urdu, Kashmiri)",
    ],
    "experience": [
        {
            "title": "AI Data Annotator, Content Creator & QA Contributor",
            "company": "AI Projects — Freelance / Contract",
            "dates": "2024 – Present",
            "bullets": [
                "High-quality data labeling and annotation for AI model training across multiple projects.",
                "Designed agentic AI workflows automating data-processing and reporting, cutting manual effort 40%.",
                "Tested and evaluated chatbots/AI systems via structured feedback loops.",
                "Prompt engineering to refine AI outputs; built educational and marketing content for AI products.",
            ],
        },
        {
            "title": "Community Manager & Moderator",
            "company": "AI & Web3 Communities — Telegram, Discord, X",
            "dates": "2023 – Present",
            "bullets": [
                "Managed communities with daily support for 6,000+ members.",
                "Drove engagement via AI-assisted programming, onboarding flows, automated announcements.",
            ],
        },
        {
            "title": "Social, Content & Community Operator",
            "company": "EMC Protocol — Web3 / AI Compute Protocol",
            "dates": "2024 – Present",
            "bullets": [
                "Owned Twitter/X and Telegram content strategy and brand voice for an AI compute protocol.",
                "Built AI-automated posting pipelines; operated a 6,000+ member community.",
            ],
        },
        {
            "title": "Founder, Social Media & Content Lead",
            "company": "ICPCollectible",
            "dates": "2023 – Present",
            "bullets": [
                "Grew a Web3 Twitter/X account from zero to 16,000+ followers — 100% organic.",
            ],
        },
    ],
    "achievements": [
        "16,000+ follower Web3 X account, 100% organic growth",
        "6,000+ member community across Telegram, OpenChat, DSCVR",
        "Agentic AI pipelines reduced manual workloads ~40%",
        "Public voice and growth channel for 6+ Web3/AI protocols",
    ],
    "certifications": [
        "Python Using AI Workshop — AI FOR TECHIES (June 2026)",
        "AI Tools and ChatGPT Workshop — be10x (June 2026)",
    ],
    "education": [
        {"degree": "Bachelor of Technology (B.Tech)", "school": "Kashmir University",
         "dates": "2019 – 2023"},
    ],
    "languages": ["English", "Hindi", "Urdu", "Kashmiri"],
    "target_roles": [
        "AI Operations Specialist", "Agentic AI Specialist", "AI Automation Engineer",
        "Prompt Engineer", "Social Media Manager (Web3/AI)", "Content Writer",
        "Community Manager", "Growth Manager", "Content Moderator",
        "AI Data Annotator", "AI Model Evaluation & Testing",
        "AI Translation Data Provider", "Voice Recording Artist",
    ],
    # Honest defaults for common screener questions — override via env.
    "qa_defaults": {
        "work_authorization": "Authorized to work in India; open to remote contracts worldwide.",
        "requires_sponsorship": "For on-site roles outside India, yes; fully available for remote work without sponsorship.",
        "salary_expectation": os.getenv("APPLY_SALARY", "Negotiable, aligned with market rate for the role"),
        "notice_period": os.getenv("APPLY_NOTICE", "Immediately available"),
        "years_experience": "2+ years",
        "relocation": "Open to remote-first; relocation negotiable for the right role.",
        "how_heard": "Found the role while researching the company.",
        "gender": os.getenv("APPLY_GENDER", "Prefer not to say"),
        "veteran_status": "Not applicable",
        "disability": "Prefer not to say",
        "race_ethnicity": "Prefer not to say",
    },
}


def profile_text(max_len: int = 3500) -> str:
    """Flat text rendering of the profile for prompts."""
    lines = [
        f"{PROFILE['full_name']} — {PROFILE['headline']}",
        f"Email: {PROFILE['email']} | Location: {PROFILE['location']}",
        f"Links: {PROFILE['links']['linkedin']} | {PROFILE['links']['twitter']}",
        (f"Portfolio / proof of work: X {PROFILE['links']['twitter']} (16k+ followers) | "
         f"Telegram channel {PROFILE['links']['tg_channel']} | "
         f"community group {PROFILE['links']['tg_group']}"),
        "", "SUMMARY", PROFILE["summary"],
        "", "SKILLS", ", ".join(PROFILE["skills"]),
        "", "EXPERIENCE",
    ]
    for e in PROFILE["experience"]:
        lines.append(f"• {e['title']} — {e['company']} ({e['dates']})")
        lines.extend(f"    - {b}" for b in e["bullets"])
    lines += ["", "ACHIEVEMENTS"] + [f"• {a}" for a in PROFILE["achievements"]]
    lines += ["", "CERTIFICATIONS"] + [f"• {c}" for c in PROFILE["certifications"]]
    lines += ["", "EDUCATION"] + [f"• {e['degree']} — {e['school']} ({e['dates']})"
                                   for e in PROFILE["education"]]
    lines += ["", "LANGUAGES: " + ", ".join(PROFILE["languages"])]
    return "\n".join(lines)[:max_len]
