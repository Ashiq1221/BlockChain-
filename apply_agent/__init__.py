"""Apply Pilot — self-learning job-application agent orchestra.

Pipeline:  job link → fetch posting → 3-agent structured debate
        → critic → decision (APPLY/SKIP) → tailored cover letter
        → Playwright form autofill → screenshot review → (optional) submit
        → outcome logged to SQLite + CF Vectorize episodic memory.
"""
from .orchestrator import evaluate_job, ApplyPlan
from .profile import PROFILE, RESUME_PATH
