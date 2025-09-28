from config import Config
from pyrogram import Client, idle
import asyncio
from logger import LOGGER
from modules.retasks import recover_incomplete_batches
from modules.scheduler import start_daily_schedulers

# --- Dummy web server for Render port binding ---
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_web():
    port = int(os.getenv("PORT", 8080))  # Render provides PORT
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Web server running on port {port}")
    server.serve_forever()

# Start the dummy web server in background
threading.Thread(target=run_web, daemon=True).start()
# -------------------------------------------------

if __name__ == "__main__":
    bot = Client(
        "Bot",
        bot_token=Config.BOT_TOKEN,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        sleep_threshold=30,
        plugins=dict(root="plugins"),
        workers=1000,
    )
    
    async def main():
        await bot.start()
        bot_info = await bot.get_me()
        LOGGER.info(f"<--- @{bot_info.username} Started --->")
        # Start background tasks
        asyncio.create_task(recover_incomplete_batches(bot))
        asyncio.create_task(start_daily_schedulers(bot))
        LOGGER.info("Daily update schedulers started")
        await idle()  # keeps the bot running until Ctrl+C or stop
        await bot.stop()  # stop bot when idle exits

    try:
        asyncio.get_event_loop().run_until_complete(main())
    except KeyboardInterrupt:
        LOGGER.info("<--- Bot Interrupted by user --->")
    finally:
        # Cancel any pending tasks to prevent warnings
        pending = asyncio.all_tasks()
        for task in pending:
            task.cancel()
        asyncio.get_event_loop().run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        asyncio.get_event_loop().close()
        LOGGER.info("<--- Bot Stopped --->")
