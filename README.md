# Kaluzz Support Center - Telegram Bot

Production customer support bot with a staff backoffice for Render.com.

## Project Structure
- `bot.py` - Core application (Telegram bot polling + Render HTTP health check listener)
- `requirements.txt` - Python dependencies
- `.gitignore` - Ignores local database, environment variables, and cache
- `.env.example` - Template for your environment variables

## Deploying to Render.com

1. Create a GitHub repository and push these files.
2. Go to [Render Dashboard](https://dashboard.render.com).
3. Click **New +** -> **Web Service**.
4. Connect your repository.
5. Settings:
   - **Name:** `kaluzz-support-bot`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Instance Type:** `Free`
6. Add **Environment Variables**:
   - `BOT_TOKEN`: Your token from @BotFather
   - `STAFF_CHAT_ID`: Telegram group ID where staff receives tickets (e.g. `-100xxxxxxxxxx`)
7. Click **Deploy Web Service**.
