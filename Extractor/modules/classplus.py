# -------------------- Part 1/3 --------------------
import requests
import json
import uuid
import asyncio
import aiohttp
import os
import base64
from urllib.parse import urlparse
from pyrogram import Client, filters
from Extractor import app
from config import PREMIUM_LOGS, BOT_TEXT
from Extractor.core.utils import forward_to_log
from datetime import datetime
import pytz

india_timezone = pytz.timezone('Asia/Kolkata')
current_time = datetime.now(india_timezone)
time_new = current_time.strftime("%d-%m-%Y %I:%M %p")

apiurl = "https://api.classplusapp.com/v2"
s = requests.Session()

# -------------------- Helper: Encode Partial URL --------------------
def encode_partial_url(url):
    if not url:
        return ""
    parsed = urlparse(url)
    base_part = f"{parsed.scheme}://{parsed.netloc}"
    path_part = url[len(base_part):]
    encoded_path = base64.b64encode(path_part.encode()).decode()
    return f"{base_part}{encoded_path}"

# -------------------- Helper: Fetch Course Content --------------------
def get_course_content(session, course_id, folder_id=0, folder_path=""):
    fetched_contents = []
    params = {'courseId': course_id, 'folderId': folder_id}
    res = session.get(f'{apiurl}/course/content/get', params=params)
    if res.status_code == 200:
        res_json = res.json()
        contents = res_json['data']['courseContent']
        for content in contents:
            content_type = content.get("contentType")
            name = content.get("name", "Untitled")
            url = content.get("url", "")
            content_hash = content.get("contentHashId", "")
            
            if content_type == 1:  # Folder
                resources = content.get('resources', {})
                if resources.get('videos') or resources.get('files'):
                    sub_contents = get_course_content(session, course_id, content['id'], folder_path + name + " - ")
                    fetched_contents += sub_contents
            else:  # Video/PDF
                if url:
                    encoded_url = encode_partial_url(url)
                    if content_hash:
                        encoded_url += f"*UGxCP_hash={content_hash}\n"
                    fetched_contents.append(f"{folder_path}{name}: {encoded_url}")
    return fetched_contents
# -------------------- Part 2/3 --------------------
@app.on_message(filters.command(["cp"]))
async def classplus_txt(app, message):
    # Step 1: Ask for credentials
    details = await app.ask(
        message.chat.id,
        "🔹 <b>UG EXTRACTOR PRO</b> 🔹\n\n"
        "Send **Org Code & Mobile** or **Access Token**:\n"
        "<code>ORG_CODE*Mobile</code>\n"
        "or direct token.\n\n"
        "Example:\n"
        "- <code>ABCD*9876543210</code>\n"
        "- <code>eyJhbGciOiJIUzI1NiIsInR5cCI6...</code>"
    )
    await forward_to_log(details, "Classplus Extractor")
    user_input = details.text.strip()

    if "*" in user_input:
        try:
            org_code, mobile = user_input.split("*")
            device_id = str(uuid.uuid4()).replace("-", "")
            headers = {
                "Accept": "application/json, text/plain, */*",
                "region": "IN",
                "accept-language": "en",
                "Content-Type": "application/json;charset=utf-8",
                "Api-Version": "51",
                "device-id": device_id
            }

            # Step 2: Fetch Org details
            org_resp = s.get(f"{apiurl}/orgs/{org_code}", headers=headers).json()
            org_id = org_resp["data"]["orgId"]
            org_name = org_resp["data"]["orgName"]

            # Step 3: Generate OTP
            otp_payload = {
                "countryExt": "91",
                "mobile": mobile,
                "viaSms": 1,
                "orgId": org_id,
                "eventType": "login",
                "otpHash": "j7ej6eW5VO"  # same working hash from your working code
            }
            otp_resp = s.post(f"{apiurl}/otp/generate", data=json.dumps(otp_payload), headers=headers)
            if otp_resp.status_code != 200:
                await message.reply("❌ Failed to generate OTP. Please check your details.")
                return
            session_id = otp_resp.json()['data']['sessionId']

            # Step 4: Ask user for OTP
            user_otp = await app.ask(message.chat.id, "📱 Enter OTP sent to your mobile:", timeout=300)
            otp = user_otp.text.strip()
            if not otp.isdigit():
                await message.reply("❌ Invalid OTP. Enter numbers only.")
                return

            # Step 5: Verify OTP
            fingerprint_id = str(uuid.uuid4()).replace("-", "")
            verify_payload = {
                "otp": otp,
                "sessionId": session_id,
                "orgId": org_id,
                "fingerprintId": fingerprint_id,
                "countryExt": "91",
                "mobile": mobile
            }
            verify_resp = s.post(f"{apiurl}/users/verify", data=json.dumps(verify_payload), headers=headers)
            if verify_resp.status_code != 200:
                await message.reply("❌ OTP verification failed. Try again.")
                return

            token = verify_resp.json()['data']['token']
            s.headers['x-access-token'] = token
            await message.reply_text(f"✅ Login Successful!\nAccess Token:\n<code>{token}</code>")
            
            # Step 6: Fetch courses
            headers['x-access-token'] = token
            course_resp = s.get(f"{apiurl}/v2/courses?tabCategoryId=1", headers=headers)
            if course_resp.status_code == 200:
                courses = course_resp.json()["data"]["courses"]
                s.session_data = {"token": token, "courses": {c["id"]: c["name"] for c in courses}}
                await fetch_batches(app, message, org_name)
            else:
                await message.reply("❌ No courses found.")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
# -------------------- Part 3/3 --------------------
async def fetch_batches(app, message, org_name):
    session_data = s.session_data
    if "courses" not in session_data:
        await app.send_message(message.chat.id, "❌ No courses found in session.")
        return

    courses = session_data["courses"]
    text = "📚 <b>Available Batches</b>\n\n"
    course_list = []
    for idx, (course_id, course_name) in enumerate(courses.items(), start=1):
        text += f"{idx}. <code>{course_name}</code>\n"
        course_list.append((idx, course_id, course_name))

    await app.send_message(PREMIUM_LOGS, f"<blockquote>{text}</blockquote>")
    selected_index = await app.ask(
        message.chat.id,
        f"{text}\nSend the index number of the batch to download.",
        timeout=180
    )

    if not selected_index.text.isdigit():
        await app.send_message(message.chat.id, "❌ Invalid input. Send a number.")
        return

    selected_idx = int(selected_index.text.strip())
    if not (1 <= selected_idx <= len(course_list)):
        await app.send_message(message.chat.id, "❌ Invalid batch index.")
        return

    selected_course_id = course_list[selected_idx - 1][1]
    selected_course_name = course_list[selected_idx - 1][2]
    await app.send_message(
        message.chat.id,
        "🔄 <b>Processing Course</b>\n"
        f"└─ Current: <code>{selected_course_name}</code>"
    )
    await extract_batch(app, message, org_name, selected_course_id)


async def extract_batch(app, message, org_name, batch_id):
    session_data = s.session_data
    if "token" not in session_data:
        await app.send_message(message.chat.id, "❌ Access token missing.")
        return

    batch_name = session_data["courses"][batch_id]
    headers = {
        'x-access-token': session_data["token"],
        'user-agent': 'Mobile-Android',
        'app-version': '1.4.73.2',
        'api-version': '35',
        'device-id': '39F093FF35F201D9'
    }

    def encode_partial_url(url):
        if not url:
            return ""
        parsed = urlparse(url)
        base_part = f"{parsed.scheme}://{parsed.netloc}"
        path_part = url[len(base_part):]
        encoded_path = base64.b64encode(path_part.encode()).decode()
        return f"{base_part}{encoded_path}"

    async def fetch_live_videos(course_id):
        outputs = []
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{apiurl}/v2/course/live/list/videos?type=2&entityId={course_id}&limit=9999&offset=0"
                async with session.get(url, headers=headers) as resp:
                    data = await resp.json()
                    for video in data.get("data", {}).get("list", []):
                        name = video.get("name", "Unknown Video")
                        video_url = video.get("url", "")
                        content_hash = video.get("contentHashId", "")
                        if video_url:
                            encoded_url = encode_partial_url(video_url)
                            outputs.append(f"{name}:\n{encoded_url}\ncontentHashId: {content_hash}\n")
            except Exception as e:
                print(f"Error fetching live videos: {e}")
        return outputs

    async def process_course_contents(course_id, folder_id=0, folder_path=""):
        result = []
        url = f"{apiurl}/v2/course/content/get?courseId={course_id}&folderId={folder_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                course_data = await resp.json()
                course_data = course_data["data"]["courseContent"]

        tasks = []
        for item in course_data:
            content_type = str(item.get("contentType"))
            sub_id = item.get("id")
            sub_name = item.get("name", "Untitled")
            video_url = item.get("url", "")
            content_hash = item.get("contentHashId", "")

            if content_type in ("2", "3"):
                if video_url:
                    encoded_url = encode_partial_url(video_url)
                    if content_hash:
                        encoded_url += f"*UGxCP_hash={content_hash}\n"
                    result.append(f"{folder_path}{sub_name}: {encoded_url}")
            elif content_type == "1":
                new_folder_path = f"{folder_path}{sub_name} - "
                tasks.append(process_course_contents(course_id, sub_id, new_folder_path))

        sub_contents = await asyncio.gather(*tasks)
        for sub_content in sub_contents:
            result.extend(sub_content)
        return result

    async def write_to_file(extracted_data):
        invalid_chars = '\t:/+#|@*.'
        clean_name = ''.join(c for c in batch_name if c not in invalid_chars).replace('_', ' ')
        file_path = f"{clean_name}.txt"
        with open(file_path, "w", encoding='utf-8') as f:
            f.write(''.join(extracted_data))
        return file_path

    extracted_data, live_videos = await asyncio.gather(
        process_course_contents(batch_id),
        fetch_live_videos(batch_id)
    )
    extracted_data.extend(live_videos)
    file_path = await write_to_file(extracted_data)

    video_count = sum(1 for line in extracted_data if "Video" in line or ".mp4" in line)
    pdf_count = sum(1 for line in extracted_data if ".pdf" in line)
    total_links = len(extracted_data)
    other_count = total_links - (video_count + pdf_count)

    caption = (
        f"🎓 <b>COURSE EXTRACTED</b>\n\n"
        f"📱 <b>APP:</b> {org_name}\n"
        f"📚 <b>BATCH:</b> {batch_name}\n"
        f"📅 <b>DATE:</b> {time_new} IST\n\n"
        f"📊 <b>CONTENT STATS</b>\n"
        f"├─ 📁 Total Links: {total_links}\n"
        f"├─ 🎬 Videos: {video_count}\n"
        f"├─ 📄 PDFs: {pdf_count}\n"
        f"└─ 📦 Others: {other_count}\n\n"
        f"🚀 Extracted by @{(await app.get_me()).username}\n\n"
        f"<code>╾───• {BOT_TEXT} •───╼</code>"
    )

    await app.send_document(message.chat.id, file_path, caption=caption)
    await app.send_document(PREMIUM_LOGS, file_path, caption=caption)
    os.remove(file_path)
