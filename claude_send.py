"""
Claude uses this to send commands to your phone agent via GitHub.
Usage: python claude_send.py "your command here"
"""
import sys, json, subprocess
from datetime import datetime, timezone
from pathlib import Path

COMMAND_FILE = "telegram_agents/inbox/command.json"
RESULT_FILE  = "telegram_agents/inbox/result.json"


def send_command(command: str):
    cmd_id = f"cmd_{int(datetime.now().timestamp())}"
    payload = {
        "id":        cmd_id,
        "command":   command,
        "status":    "pending",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    Path(COMMAND_FILE).write_text(json.dumps(payload, indent=2))
    subprocess.run(["git", "add", COMMAND_FILE], capture_output=True)
    subprocess.run(["git", "commit", "-m", f"cmd: {command[:50]}"], capture_output=True)
    subprocess.run(["git", "push", "-q"], capture_output=True, timeout=30)
    print(f"✅ Command sent: {command}")
    print(f"   ID: {cmd_id}")
    print(f"   Agent will execute in ~{90}s and push result back.")
    return cmd_id


def read_result():
    try:
        data = json.loads(Path(RESULT_FILE).read_text())
        print(f"\n📊 RESULT:")
        print(f"   Command:   {data.get('command')}")
        print(f"   Status:    {data.get('status')}")
        print(f"   Timestamp: {data.get('timestamp')}")
        print(f"\n   Output:\n   {data.get('result','(empty)')}")
    except Exception as e:
        print(f"No result yet: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python claude_send.py \"your command\"")
        print("       python claude_send.py --result")
        sys.exit(1)
    if sys.argv[1] == "--result":
        read_result()
    else:
        send_command(" ".join(sys.argv[1:]))
