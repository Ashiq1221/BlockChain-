#!/bin/bash
# One-click setup — just run this once
echo ""
echo "======================================"
echo "  TELEGRAM AI AGENT — SETUP"
echo "======================================"
echo ""

# Install dependencies
echo "Installing packages..."
pip install -r requirements.txt --quiet

# Create .env if missing
if [ ! -f ".env" ]; then
    echo ""
    echo "Enter your details:"
    echo ""

    read -p "Telegram API ID: " api_id
    read -p "Telegram API Hash: " api_hash
    read -p "Your phone number (with +country code): " phone
    read -p "Anthropic API Key: " anthropic_key

    cat > .env << EOF
TELEGRAM_API_ID=$api_id
TELEGRAM_API_HASH=$api_hash
TELEGRAM_PHONE=$phone
TELEGRAM_SESSION_NAME=my_session
ANTHROPIC_API_KEY=$anthropic_key
AGENT_LANGUAGE=en
MAX_DM_PER_HOUR=10
MAX_GROUP_POSTS_PER_HOUR=5
RATE_LIMIT_SLEEP=3
AUTO_RESPOND=true
JOB_KEYWORDS=python developer,blockchain engineer,backend engineer,remote developer
EOF

    echo ""
    echo "✅ .env created!"
fi

echo ""
echo "✅ Setup complete! Starting menu..."
echo ""
python menu.py
