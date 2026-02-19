## Setup

**1. Install**
Copy main.py in to your own file. 

pip install -r requirements.txt (in powershell/shell)

**2. Get Bot Token**
- Go to https://discord.com/developers/applications
- Click "New Application" -> "Bot" -> "Add Bot"
- Enable "Message Content Intent" and "Server Members Intent"
- Copy your token

**3. Configure**
Create `.env` file:
```
BOT_TOKEN=bot_token_here
ALERT_CHANNEL_ID=alert_channel_id_here
```

**4. Invite Bot**
- Developer Portal -> "OAuth2" -> "URL Generator"
- Select `bot` scope
- Select permissions: `View Channels`, `Send Messages`, `Manage Messages`, `Moderate Members`, `Ban Members`
- Use the URL to invite bot to your server

**5. Run**
```bash
python main.py
```

## Config (ONLY IF YOU WANT TOO)
Edit `main.py` line 15:

```python
'RATE_LIMITS': {
    'MAX_MESSAGES': 5,    # Messages per 5 seconds
    'MAX_MENTIONS': 3,    # Mentions per 5 seconds
    'MAX_LINKS': 2,       # Links per 5 seconds
}

'IGNORED_ROLES': ['Moderator', 'Admin']  # Roles to exempt
```

Increase numbers for more active servers.
