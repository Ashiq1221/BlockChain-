"""Abstract base class shared by all 10 agents."""
import asyncio
from abc import ABC, abstractmethod
from rich.console import Console
from pyrogram import Client
from telegram_agents.database import Database

console = Console()


class BaseAgent(ABC):
    name: str = "BaseAgent"
    emoji: str = "🤖"

    def __init__(self, client: Client, db: Database):
        self.client = client
        self.db = db
        self._running = False

    def log(self, msg: str, style: str = "cyan"):
        console.print(f"[{style}][{self.emoji} {self.name}][/{style}] {msg}")

    def log_success(self, msg: str):
        self.log(msg, "green")

    def log_warn(self, msg: str):
        self.log(msg, "yellow")

    def log_error(self, msg: str):
        self.log(msg, "red")

    @abstractmethod
    async def run(self, **kwargs):
        """Execute the agent's primary mission."""

    async def stop(self):
        self._running = False
