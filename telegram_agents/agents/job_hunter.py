"""
Agent 3 — Job Hunter
Scans Telegram groups and the web for job posts matching user-defined keywords,
crafts personalized application messages, and sends them.
"""
import asyncio
from telegram_agents.base_agent import BaseAgent
from telegram_agents.tools import ai_tools, web_tools, telegram_tools
from telegram_agents.config import Config

DEFAULT_PROFILE = """Experienced software engineer with 5+ years in Python, blockchain, and backend systems.
Open to remote roles. Strong track record delivering scalable APIs and smart contracts.
GitHub: github.com/user | Portfolio: available on request."""


class JobHunterAgent(BaseAgent):
    name = "JobHunter"
    emoji = "💼"

    async def run(self, goal: str = "", user_profile: str = DEFAULT_PROFILE, apply: bool = True, **kwargs):
        keywords = Config.JOB_KEYWORDS
        if goal:
            extra = ai_tools.think(
                system_addon="Extract job-search keywords from a goal. Return comma-separated only.",
                user_prompt=f"Goal: {goal}\n\nJob keywords:",
            )
            keywords += [k.strip() for k in extra.split(",") if k.strip()]

        self.log(f"Hunting jobs with keywords: {keywords}")
        jobs_found: list[dict] = []

        # Scan joined groups for job posts
        groups = await self.db.get_groups(joined=True)
        for group in groups[:20]:
            try:
                chat_id = group["tg_id"]
                history = await telegram_tools.get_chat_history(self.client, chat_id, limit=50)
                for msg in history:
                    text = msg.get("text", "")
                    if any(kw.lower() in text.lower() for kw in keywords):
                        extracted = ai_tools.extract_jobs(text)
                        for job in extracted:
                            job["source"] = f"tg:{group['title']}"
                            job["group_id"] = chat_id
                            job["msg_id"] = msg["id"]
                            jobs_found.append(job)
            except Exception as e:
                self.log_warn(f"Error scanning group {group.get('title')}: {e}")

        # Web search for jobs
        for kw in keywords[:3]:
            results = await web_tools.web_search(f"telegram job {kw} remote 2024", num=5)
            for r in results:
                page_text = await web_tools.fetch_page(r["url"])
                extracted = ai_tools.extract_jobs(page_text or r["snippet"])
                for job in extracted:
                    job["source"] = r["url"]
                    jobs_found.append(job)

        # Deduplicate by title+company
        seen = set()
        unique_jobs = []
        for j in jobs_found:
            key = f"{j.get('title','')}|{j.get('company','')}".lower()
            if key not in seen and key != "|":
                seen.add(key)
                unique_jobs.append(j)

        self.log(f"Found {len(unique_jobs)} unique jobs")

        applied_count = 0
        for job in unique_jobs:
            await self.db.save_job(
                source=job.get("source", ""),
                title=job.get("title", ""),
                company=job.get("company", ""),
                description=job.get("description", "")[:500],
                url=job.get("url", ""),
            )

            if apply:
                relevance = ai_tools.score_relevance(
                    f"{job.get('title')} {job.get('description','')[:200]}",
                    " ".join(keywords),
                )
                if relevance < 6:
                    continue

                message = ai_tools.craft_job_application(job, user_profile)
                sent = False

                # Try to send application to source group
                if job.get("group_id"):
                    try:
                        m = await telegram_tools.send_message(self.client, job["group_id"], message)
                        if m:
                            sent = True
                            await self.db.log_message("out", job["group_id"], "group", message, m.id)
                    except Exception as e:
                        self.log_warn(f"Could not send to group: {e}")

                if sent:
                    jobs_db = await self.db.get_jobs(applied=False)
                    for jdb in jobs_db:
                        if jdb["title"] == job.get("title"):
                            await self.db.mark_job_applied(jdb["id"], message)
                            break
                    applied_count += 1
                    self.log_success(f"Applied: {job.get('title')} @ {job.get('company','?')}")
                    await asyncio.sleep(5)

        self.log_success(f"Job hunt done. Found {len(unique_jobs)}, applied to {applied_count}.")
        await self.db.log_event("job_hunt", {"found": len(unique_jobs), "applied": applied_count})
        return {"found": len(unique_jobs), "applied": applied_count, "jobs": unique_jobs}
