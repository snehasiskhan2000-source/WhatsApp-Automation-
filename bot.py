import asyncio
import os
import datetime
from pyrogram import Client, filters, idle
from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from playwright.async_api import async_playwright
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

# --- CONFIGURATION ---
API_ID = os.environ.get("API_ID", "YOUR_API_ID")
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")

app = Client("whatsapp_scheduler_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
scheduler = AsyncIOScheduler()

# Global variables to hold state and Playwright instances
user_states = {}
user_data = {}
wa_page = None
wa_context = None

# --- RENDER WEB SERVER ---
async def handle_ping(request):
    return web.Response(text="WhatsApp Bot is Alive! 💀")

async def start_web_server():
    webapp = web.Application()
    webapp.router.add_get('/', handle_ping)
    runner = web.AppRunner(webapp)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# --- WHATSAPP AUTOMATION (PLAYWRIGHT) ---
async def init_whatsapp():
    global wa_page, wa_context
    p = await async_playwright().start()
    # Saves session so you don't log out after the first time
    wa_context = await p.chromium.launch_persistent_context(
        user_data_dir="./wa_session", 
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox"]
    )
    wa_page = await wa_context.new_page()
    await wa_page.goto("https://web.whatsapp.com/")
    await asyncio.sleep(5)

async def check_wa_login():
    # If the search bar exists, we are already logged in
    try:
        await wa_page.wait_for_selector('div[title="Search input textbox"]', timeout=5000)
        return True
    except:
        return False

async def get_pairing_code(phone_number):
async def get_pairing_code(phone_number):
    try:
        print("Waiting for 'Link with phone number' button to load...")
        # Give Render up to 30 seconds to fully load the heavy WhatsApp page
        await wa_page.wait_for_selector('span[role="button"]:has-text("Link with phone number")', timeout=30000)
        await wa_page.click('span[role="button"]:has-text("Link with phone number")')
        
        await asyncio.sleep(2)
        print("Typing phone number...")
        await wa_page.wait_for_selector('input[type="text"]', timeout=10000)
        await wa_page.fill('input[type="text"]', phone_number)
        
        await wa_page.click('div[role="button"]:has-text("Next")')
        
        print("Waiting for pairing code to generate...")
        # Give WhatsApp up to 20 seconds to connect to their servers and generate the code
        await wa_page.wait_for_selector('div[data-testid="link-device-code-screen"] div[aria-details]', timeout=20000)
        
        # Extract the code
        code_element = await wa_page.query_selector('div[data-testid="link-device-code-screen"] div[aria-details]')
        if code_element:
            code = await code_element.inner_text()
            print(f"Successfully generated code: {code}")
            return code
            
    except Exception as e:
        print(f"Playwright UI Error: {e}")
        return None

async def send_whatsapp_message(target, message, files=None):
    try:
        # Search for the target
        await wa_page.fill('div[title="Search input textbox"]', target)
        await asyncio.sleep(2)
        await wa_page.keyboard.press("Enter")
        await asyncio.sleep(2)
        
        # Type and send message
        await wa_page.fill('div[title="Type a message"]', message)
        await wa_page.keyboard.press("Enter")
        await asyncio.sleep(2)

        # TODO: Add logic here to attach and send files if `files` list is not empty
        
        # Confirmation to personal inbox
        await wa_page.fill('div[title="Search input textbox"]', "You")
        await asyncio.sleep(2)
        await wa_page.keyboard.press("Enter")
        await asyncio.sleep(1)
        await wa_page.fill('div[title="Type a message"]', "Your Schedule Message Sent Successfully🎉")
        await wa_page.keyboard.press("Enter")
        
    except Exception as e:
        print(f"Failed to send: {e}")

# --- TELEGRAM BOT LOGIC ---
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    chat_id = message.chat.id
    await message.reply("Checking WhatsApp status... ⏳")
    is_logged_in = await check_wa_login()
    
    if is_logged_in:
        menu = ReplyKeyboardMarkup(
            [[KeyboardButton("Schedule A Message 🔥")]],
            resize_keyboard=True
        )
        await message.reply("Whatsapp Session Active,You Don't Have To Log-in Again🤗", reply_markup=menu)
        user_states[chat_id] = "IDLE"
    else:
        await message.reply("Send Your Number📱\n(Include country code without +, e.g., 919876543210)", reply_markup=ReplyKeyboardRemove())
        user_states[chat_id] = "WAITING_NUMBER"

@app.on_message(filters.private & filters.text)
async def handle_text(client, message):
    chat_id = message.chat.id
    state = user_states.get(chat_id, "IDLE")
    text = message.text

    if state == "WAITING_NUMBER":
        await message.reply("Fetching pairing code... Please wait ⏳")
        code = await get_pairing_code(text)
        if code:
            await message.reply(f"Your pairing code is:\n`{code}`\n\nPaste this in WhatsApp. I will detect when you login.")
            # Poll for successful login
            for _ in range(30): # Wait up to 60 seconds
                await asyncio.sleep(2)
                if await check_wa_login():
                    menu = ReplyKeyboardMarkup([[KeyboardButton("Schedule A Message 🔥")]], resize_keyboard=True)
                    await message.reply("Log-in Successful🎉", reply_markup=menu)
                    user_states[chat_id] = "IDLE"
                    return
            await message.reply("Login timed out. Send /start to try again.")
        else:
            await message.reply("Failed to get code. Ensure the number is correct.")

    elif text == "Schedule A Message 🔥":
        await message.reply("Send Message To Schedule👋", reply_markup=ReplyKeyboardRemove())
        user_states[chat_id] = "WAITING_MESSAGE"

    elif state == "WAITING_MESSAGE":
        user_data[chat_id] = {"message": text, "files": []}
        menu = ReplyKeyboardMarkup(
            [[KeyboardButton("Yes")], [KeyboardButton("No,Continue")]],
            resize_keyboard=True
        )
        await message.reply("Want To Attach Any Files?🤔", reply_markup=menu)
        user_states[chat_id] = "ASK_FILE"

    elif state == "ASK_FILE":
        if text == "Yes":
            await message.reply("Send Files To Attached🤗", reply_markup=ReplyKeyboardRemove())
            user_states[chat_id] = "WAITING_FILE"
        elif text == "No,Continue":
            await message.reply("Send Time To Schedule⏳\n\nExample- If Time Is 14/03/26 15:35!!\nSend 1403261535", reply_markup=ReplyKeyboardRemove())
            user_states[chat_id] = "WAITING_TIME"

    elif state == "WAITING_TIME":
        try:
            # Parse 1403261535 -> DDMMYYHHMM
            dt = datetime.datetime.strptime(text, "%d%m%y%H%M")
            # Set target contact (Change "My Boss" to the name of the contact you want to schedule to, or modify code to ask for it)
            target = "My Boss" 
            
            # Schedule the job
            scheduler.add_job(
                send_whatsapp_message, 
                'date', 
                run_date=dt, 
                args=[target, user_data[chat_id]["message"], user_data[chat_id]["files"]]
            )
            
            menu = ReplyKeyboardMarkup([[KeyboardButton("Schedule A Message 🔥")]], resize_keyboard=True)
            await message.reply("Message Schedule Successfull🎉", reply_markup=menu)
            user_states[chat_id] = "IDLE"
        except ValueError:
            await message.reply("Invalid time format! Please use DDMMYYHHMM (e.g., 1403261535). Try again:")

@app.on_message(filters.private & (filters.document | filters.photo | filters.video))
async def handle_files(client, message):
    chat_id = message.chat.id
    if user_states.get(chat_id) == "WAITING_FILE":
        # Save file path locally
        file_path = await message.download()
        user_data[chat_id]["files"].append(file_path)
        
        menu = ReplyKeyboardMarkup(
            [[KeyboardButton("Yes")], [KeyboardButton("No,Continue")]],
            resize_keyboard=True
        )
        await message.reply("Want To Attach More Files?🤔", reply_markup=menu)
        user_states[chat_id] = "ASK_FILE"

# --- MAIN RUNNER ---
async def main():
    await start_web_server()
    await init_whatsapp()
    scheduler.start()
    await app.start()
    print("Bot is running... 💀")
    await idle()
    await app.stop()

if __name__ == "__main__":
    # Bulletproof loop handling for Python 3.11+
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    loop.run_until_complete(main())
