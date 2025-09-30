import requests, os, sys, re
import json, asyncio
import subprocess
import datetime
import time
import logging
from typing import List, Dict, Tuple, Any
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from Extractor import app
from config import *
import config
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
#from pyrogram.errors import ListenerTimeout
from subprocess import getstatusoutput
from datetime import datetime
import pytz
import gc
from datetime import datetime, timedelta


join = config.join
india_timezone = pytz.timezone('Asia/Kolkata')
current_time = datetime.now(india_timezone)
time_new = current_time.strftime("%d-%m-%Y %I:%M %p")

# Format time taken
def format_time_taken(start_time: float) -> str:
    end_time = time.time()
    time_taken = end_time - start_time
    formatted_time = str(timedelta(seconds=int(time_taken)))
    return formatted_time

# Reduce max workers to prevent memory overload
THREADPOOL = ThreadPoolExecutor(max_workers=2000)
CHUNK_SIZE = 8192

thumb = os.path.join(os.path.dirname(__file__), "logo.jpg")

async def download_thumbnail(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        thumb_path = f"thumb_{int(time.time())}.jpg"
        
        async with session.get(url, timeout=30) as response:
            if response.status == 200:
                with open(thumb_path, "wb") as f:
                    while True:
                        chunk = await response.content.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                return thumb_path
            else:
                logging.warning(f"Thumbnail download failed. Status: {response.status}")
                return None
    except Exception as e:
        logging.error(f"Error downloading thumbnail: {e}")
        return None
    finally:
        gc.collect()

def create_html_file(file_name, batch_name, contents):
    tbody = ''
    parts = contents.split('\n')
    
    # Process in chunks to reduce memory usage
    chunk_size = 100
    for i in range(0, len(parts), chunk_size):
        chunk = parts[i:i + chunk_size]
        for part in chunk:
            split_part = [item.strip() for item in part.split(':', 1)]
            text = split_part[0] if split_part[0] else 'Untitled'
            url = split_part[1].strip() if len(split_part) > 1 and split_part[1].strip() else 'No URL'
            tbody += f'<tr><td>{text}</td><td><a href="{url}" target="_blank">{url}</a></td></tr>'
        
        # Force garbage collection after each chunk
        gc.collect()

    with open('Extractor/core/template.html', 'r') as fp:
        file_content = fp.read()
    title = batch_name.strip()
    with open(file_name, 'w') as fp:
        fp.write(file_content.replace('{{tbody_content}}', tbody).replace('{{batch_name}}', title))
"""  
async def fetch_cpwp_signed_url(url_val: str, name: str, session: aiohttp.ClientSession, headers: Dict[str, str]) -> str | None:
    MAX_RETRIES = 3
    for attempt in range(MAX_RETRIES):
        params = {"url": url_val}
        try:
            async with session.get("https://api.classplusapp.com/cams/uploader/video/jw-signed-url", params=params, headers=headers) as response:
                response.raise_for_status()
                response_json = await response.json()
                signed_url = response_json.get("url") or response_json.get('drmUrls', {}).get('manifestUrl')
                return signed_url
                
        except Exception as e:
            pass

        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(2 ** attempt)

    logging.error(f"Failed to fetch signed URL for {name} after {MAX_RETRIES} attempts.")
    return None
    

async def process_cpwp_url(url_val: str, name: str, folder_path: str, session: aiohttp.ClientSession, headers: Dict[str, str]) -> str | None:
    try:
        signed_url = await fetch_cpwp_signed_url(url_val, name, session, headers)
        if not signed_url:
            logging.warning(f"Failed to obtain signed URL for {name}: {url_val}")
            return None

        if "testbook.com" in url_val or "classplusapp.com/drm" in url_val or "media-cdn.classplusapp.com/drm" in url_val:
            # Add folder path to the name if it exists - FIX: folder_path already has parentheses
            display_name = f"{folder_path}{name}" if folder_path else name
            return f"{display_name}:{url_val}\n"

        async with session.get(signed_url) as response:
            response.raise_for_status()
            # Add folder path to the name if it exists - FIX: folder_path already has parentheses  
            display_name = f"{folder_path}{name}" if folder_path else name
            return f"{display_name}:{url_val}\n"
            
    except Exception as e:
    #    logging.exception(f"Unexpected error processing {name}: {e}")
        pass
    return None

"""


async def fetch_cpwp_signed_url(url_val: str, name: str, session: aiohttp.ClientSession, headers: Dict[str, str]) -> str | None:
    MAX_RETRIES = 3
    for attempt in range(MAX_RETRIES):
        params = {"url": url_val}
        try:
            async with session.get("https://api.classplusapp.com/cams/uploader/video/jw-signed-url", params=params, headers=headers) as response:
                if response.status == 200:
                    response_json = await response.json()
                    signed_url = response_json.get("url") or response_json.get('drmUrls', {}).get('manifestUrl')
                    if signed_url:
                        return signed_url
                    else:
                        # If no signed URL found, return original URL
                        logging.warning(f"No signed URL in response for {name}, using original URL")
                        return url_val
                else:
                    logging.warning(f"Failed to get signed URL for {name}: Status {response.status}")
                    
        except Exception as e:
            logging.error(f"Error fetching signed URL for {name}: {e}")

        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(2 ** attempt)

    # If all retries failed, return original URL instead of None
    logging.error(f"Failed to fetch signed URL for {name} after {MAX_RETRIES} attempts. Using original URL.")
    return url_val

async def process_cpwp_url(url_val: str, name: str, folder_path: str, session: aiohttp.ClientSession, headers: Dict[str, str]) -> str | None:
    try:
        signed_url = await fetch_cpwp_signed_url(url_val, name, session, headers)
        # signed_url will never be None now, it will be either the signed URL or original URL
        
        if "testbook.com" in url_val or "classplusapp.com/drm" in url_val or "media-cdn.classplusapp.com/drm" in url_val:
            display_name = f"{folder_path}{name}" if folder_path else name
            return f"{display_name}:{signed_url}\n"

        # Try to access the signed URL, if it fails use original URL
        try:
            async with session.get(signed_url, timeout=10) as response:
                if response.status == 200:
                    display_name = f"{folder_path}{name}" if folder_path else name
                    return f"{display_name}:{signed_url}\n"
                else:
                    # If signed URL doesn't work, use original URL
                    display_name = f"{folder_path}{name}" if folder_path else name
                    return f"{display_name}:{url_val}\n"
        except:
            # If signed URL fails, use original URL
            display_name = f"{folder_path}{name}" if folder_path else name
            return f"{display_name}:{url_val}\n"
            
    except Exception as e:
        logging.exception(f"Unexpected error processing {name}: {e}")
        # Return original URL as fallback
        display_name = f"{folder_path}{name}" if folder_path else name
        return f"{display_name}:{url_val}\n"







async def get_cpwp_course_content(session: aiohttp.ClientSession, headers: Dict[str, str], Batch_Token: str, folder_id: int = 0, limit: int = 9999999999, retry_count: int = 0, folder_path: str = "") -> Tuple[List[str], int, int, int]:
    MAX_RETRIES = 3
    fetched_urls: set[str] = set()
    results: List[str] = []
    video_count = 0
    pdf_count = 0
    image_count = 0
    content_tasks: List[Tuple[int, asyncio.Task[str | None]]] = []
    folder_tasks: List[Tuple[int, asyncio.Task[Tuple[List[str], int, int, int]]]] = []

    # Dictionary to store folder names by their IDs
    folder_names: Dict[int, str] = {}

    try:
        content_api = f'https://api.classplusapp.com/v2/course/preview/content/list/{Batch_Token}'
        params = {'folderId': folder_id, 'limit': limit}

        async with session.get(content_api, params=params, headers=headers) as res:
            res.raise_for_status()
            res_json = await res.json()
            contents: List[Dict[str, Any]] = res_json['data']

            # First pass: collect folder names
            for content in contents:
                if content['contentType'] == 1:  # Folder
                    folder_names[content['id']] = content['name']

            # Second pass: process content
            for content in contents:
                if content['contentType'] == 1:  # Folder
                    folder_name = content['name']
                    # Build the new folder path - FIX: Each folder gets its own parentheses
                    new_folder_path = f"{folder_path}({folder_name})" if folder_path else f"({folder_name})"
                    
                    folder_task = asyncio.create_task(
                        get_cpwp_course_content(session, headers, Batch_Token, content['id'], limit, 0, new_folder_path)
                    )
                    folder_tasks.append((content['id'], folder_task))

                else:  # File content
                    name: str = content['name']
                    url_val: str | None = content.get('url') or content.get('thumbnailUrl')

                    if not url_val:
                        logging.warning(f"No URL found for content: {name}")
                        continue
                        
                    if "media-cdn.classplusapp.com/tencent/" in url_val:
                        url_val = url_val.rsplit('/', 1)[0] + "/master.m3u8"
                    elif "media-cdn.classplusapp.com" in url_val and url_val.endswith('.jpg'):
                        identifier = url_val.split('/')[-3]
                        url_val = f"https://media-cdn.classplusapp.com/alisg-cdn-a.classplusapp.com/{identifier}/master.m3u8"
                    elif "tencdn.classplusapp.com" in url_val and url_val.endswith('.jpg'):
                        identifier = url_val.split('/')[-2]
                        url_val = f"https://media-cdn.classplusapp.com/tencent/{identifier}/master.m3u8"
                    elif "4b06bf8d61c41f8310af9b2624459378203740932b456b07fcf817b737fbae27" in url_val and url_val.endswith('.jpeg'):
                        url_val = f"https://media-cdn.classplusapp.com/alisg-cdn-a.classplusapp.com/b08bad9ff8d969639b2e43d5769342cc62b510c4345d2f7f153bec53be84fe35/{url_val.split('/')[-1].split('.')[0]}/master.m3u8"
                    elif "cpvideocdn.testbook.com" in url_val and url_val.endswith('.png'):
                        match = re.search(r'/streams/([a-f0-9]{24})/', url_val)
                        video_id = match.group(1) if match else url_val.split('/')[-2]
                        url_val = f"https://cpvod.testbook.com/{video_id}/playlist.m3u8"
                    elif "media-cdn.classplusapp.com/drm/" in url_val and url_val.endswith('.png'):
                        video_id = url_val.split('/')[-3]
                        url_val = f"https://media-cdn.classplusapp.com/drm/{video_id}/playlist.m3u8"
                    elif "https://media-cdn.classplusapp.com" in url_val and ("cc/" in url_val or "lc/" in url_val or "uc/" in url_val or "dy/" in url_val) and url_val.endswith('.png'):
                        url_val = url_val.replace('thumbnail.png', 'master.m3u8')
                    elif "https://tb-video.classplusapp.com" in url_val and url_val.endswith('.jpg'):
                        video_id = url_val.split('/')[-1].split('.')[0]
                        url_val = f"https://tb-video.classplusapp.com/{video_id}/master.m3u8"

                    if url_val.endswith(("master.m3u8", "playlist.m3u8")) and url_val not in fetched_urls:
                        fetched_urls.add(url_val)
                        headers2 = { 'x-access-token': 'eyJjb3Vyc2VJZCI6IjQxOTk4MCIsInR1dG9ySWQiOm51bGwsIm9yZ0lkIjo5MTgzLCJjYXRlZ29yeUlkIjpudWxsfQ=='}
                        task = asyncio.create_task(process_cpwp_url(url_val, name, folder_path, session, headers2))
                        content_tasks.append((content['id'], task))
                        
                    else:
                        name: str = content['name']
                        url_val: str | None = content.get('url')
                        if url_val:
                            fetched_urls.add(url_val)
                            # Add folder path to the name if it exists - FIX: folder_path already has parentheses
                            display_name = f"{folder_path}{name}" if folder_path else name
                            results.append(f"{display_name}:{url_val}\n")
                            if url_val.endswith('.pdf'):
                                pdf_count += 1
                            else:
                                image_count += 1
                                
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
        if retry_count < MAX_RETRIES:
            logging.info(f"Retrying folder {folder_id} (Attempt {retry_count + 1}/{MAX_RETRIES})")
            await asyncio.sleep(2 ** retry_count)
            return await get_cpwp_course_content(session, headers, Batch_Token, folder_id, limit, retry_count + 1, folder_path)
        else:
            logging.error(f"Failed to retrieve folder {folder_id} after {MAX_RETRIES} retries.")
            return [], 0, 0, 0
            
    content_results = await asyncio.gather(*(task for _, task in content_tasks), return_exceptions=True)
    folder_results = await asyncio.gather(*(task for _, task in folder_tasks), return_exceptions=True)
    
    for (folder_id, result) in zip(content_tasks, content_results):
        if isinstance(result, Exception):
            logging.error(f"Task failed with exception: {result}")
        elif result:
            results.append(result)
            video_count += 1
            
    for (folder_id, _), folder_result in zip(folder_tasks, folder_results):
        try:
            if isinstance(folder_result, Exception):
                logging.error(f"Folder task failed with exception: {folder_result}")
                continue
                
            nested_results, nested_video_count, nested_pdf_count, nested_image_count = folder_result
            if nested_results:
                results.extend(nested_results)
            else:
            #    logging.warning(f"get_cpwp_course_content returned None for folder_id {folder_id}")
                pass
            video_count += nested_video_count
            pdf_count += nested_pdf_count
            image_count += nested_image_count
        except Exception as e:
            logging.error(f"Error processing folder {folder_id}: {e}")

    return results, video_count, pdf_count, image_count


    
async def process_cpwp(bot: Client, m: Message, user_id: int):
    
    headers = {
        'accept-encoding': 'gzip',
        'accept-language': 'EN',
        'api-version'    : '35',
        'app-version'    : '1.4.73.2',
        'build-number'   : '35',
        'connection'     : 'Keep-Alive',
        'content-type'   : 'application/json',
        'device-details' : 'Xiaomi_Redmi 7_SDK-32',
        'device-id'      : 'c28d3cb16bbdac01',
        'host'           : 'api.classplusapp.com',
        'region'         : 'IN',
        'user-agent'     : 'Mobile-Android',
        'webengage-luid' : '00000187-6fe4-5d41-a530-26186858be4c'
    }

    loop = asyncio.get_event_loop()
    CONNECTOR = aiohttp.TCPConnector(limit=500, loop=loop)
    async with aiohttp.ClientSession(connector=CONNECTOR, loop=loop) as session:
        try:
            editable = await m.reply_text("🔑 **Sᴇɴᴅ ᴏʀɢ ᴄᴏᴅᴇ ᴏғ ʏᴏᴜʀ Cʟᴀssᴘʟᴜs ᴀᴘᴘ**")
            
            try:
                input1 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                org_code = input1.text.lower()
                await input1.delete(True)
            except asyncio.TimeoutError:
                await editable.edit("⏰ **Tɪᴍᴇᴏᴜᴛ!** Yᴏᴜ ᴛᴏᴏᴋ ᴛᴏᴏ ʟᴏɴɢ ᴛᴏ ʀᴇsᴘᴏɴᴅ")
                return
            except Exception as e:
                logging.exception("Error during input1 listening:")
                await editable.edit(f"❌ **Eʀʀᴏʀ:** {str(e)}")
                return

            hash_headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://qsvfn.courses.store/?mainCategory=0&subCatList=[130504,62442]',
                'Sec-CH-UA': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
                'Sec-CH-UA-Mobile': '?0',
                'Sec-CH-UA-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
            }
            
            async with session.get(f"https://{org_code}.courses.store", headers=hash_headers) as response:
                html_text = await response.text()
                hash_match = re.search(r'"hash":"(.*?)"', html_text)

                if hash_match:
                    token = hash_match.group(1)
                    
                    async with session.get(f"https://api.classplusapp.com/v2/course/preview/similar/{token}?limit=20", headers=headers) as response:
                        if response.status == 200:
                            res_json = await response.json()
                            courses = res_json.get('data', {}).get('coursesData', [])

                            if courses:
                                text = ''
                                for cnt, course in enumerate(courses):
                                    name = course['name']
                                    price = course['finalPrice']
                                    text += f'{cnt + 1}. <blockquote>{name} 💵₹{price}</blockquote>\n'

                                await editable.edit(f"📚 **Sᴇɴᴅ ɪɴᴅᴇx ɴᴜᴍʙᴇʀ ᴏғ ᴛʜᴇ ᴄᴀᴛᴇɢᴏʀʏ ɴᴀᴍᴇ**\n\n{text}\n\n🔍 **Cᴀɴ'ᴛ ғɪɴᴅ ʏᴏᴜʀ ʙᴀᴛᴄʜ?**\nTʏᴘᴇ ᴛʜᴇ ʙᴀᴛᴄʜ ɴᴀᴍᴇ ᴛᴏ sᴇᴀʀᴄʜ")
                            
                                try:
                                    input2 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                                    raw_text2 = input2.text
                                    await input2.delete(True)
                                except asyncio.TimeoutError:
                                    await editable.edit("⏰ **Tɪᴍᴇᴏᴜᴛ!** Yᴏᴜ ᴛᴏᴏᴋ ᴛᴏᴏ ʟᴏɴɢ ᴛᴏ ʀᴇsᴘᴏɴᴅ")
                                    return
                                except Exception as e:
                                    logging.exception("Error during input2 listening:")
                                    await editable.edit(f"❌ **Eʀʀᴏʀ:** {str(e)}")
                                    return

                                if input2.text.isdigit() and len(input2.text) <= len(courses):
                                    selected_course_index = int(input2.text.strip())
                                    course = courses[selected_course_index - 1]
                                    selected_batch_id = course['id']
                                    selected_batch_name = course['name']
                                    price = course['finalPrice']
                                    clean_batch_name = selected_batch_name.replace("/", "-").replace("|", "-")
                                    clean_file_name = f"{user_id}_{clean_batch_name}"

                                else:
                                    search_url = f"https://api.classplusapp.com/v2/course/preview/similar/{token}?search={raw_text2}"
                                    async with session.get(search_url, headers=headers) as response:
                                        if response.status == 200:
                                            res_json = await response.json()
                                            courses = res_json.get("data", {}).get("coursesData", [])

                                            if courses:
                                                text = ''
                                                for cnt, course in enumerate(courses):
                                                    name = course['name']
                                                    price = course['finalPrice']
                                                    text += f'{cnt + 1}. <blockquote>{name} 💵₹{price}</blockquote>\n'
                                                await editable.edit(f"📚 **Sᴇɴᴅ ɪɴᴅᴇx ɴᴜᴍʙᴇʀ ᴏғ ᴛʜᴇ ʙᴀᴛᴄʜ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ**\n\n{text}")
                                            
                                                try:
                                                    input3 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                                                    raw_text3 = input3.text
                                                    await input3.delete(True)
                                                except asyncio.TimeoutError:
                                                    await editable.edit("⏰ **Tɪᴍᴇᴏᴜᴛ!** Yᴏᴜ ᴛᴏᴏᴋ ᴛᴏᴏ ʟᴏɴɢ ᴛᴏ ʀᴇsᴘᴏɴᴅ")
                                                    return
                                                except Exception as e:
                                                    logging.exception("Error during input3 listening:")
                                                    await editable.edit(f"❌ **Eʀʀᴏʀ:** {str(e)}")
                                                    return

                                                if input3.text.isdigit() and len(input3.text) <= len(courses):
                                                    selected_course_index = int(input3.text.strip())
                                                    course = courses[selected_course_index - 1]
                                                    selected_batch_id = course['id']
                                                    selected_batch_name = course['name']
                                                    price = course['finalPrice']
                                                    clean_batch_name = selected_batch_name.replace("/", "-").replace("|", "-")
                                                    clean_file_name = f"{user_id}_{clean_batch_name}"
                                                
                                                else:
                                                    raise Exception("**Wʀᴏɴɢ Iɴᴅᴇx Nᴜᴍʙᴇʀ**")
                                            else:
                                                raise Exception("**Dɪᴅɴ'ᴛ Fɪɴᴅ Aɴʏ Cᴏᴜʀsᴇ Mᴀᴛᴄʜɪɴɢ Tʜᴇ Sᴇᴀʀᴄʜ Tᴇʀᴍ**")
                                        else:
                                            raise Exception(f"{response.text}")
                                            
                                download_price = int(price * 0.10)
                                batch_headers = {
                                    'Accept': 'application/json, text/plain, */*',
                                    'region': 'IN',
                                    'accept-language': 'EN',
                                    'Api-Version': '22',
                                    'tutorWebsiteDomain': f'https://{org_code}.courses.store'
                                }
                                    
                                params = {
                                    'courseId': f'{selected_batch_id}',
                                }

                                async with session.get(f"https://api.classplusapp.com/v2/course/preview/org/info", params=params, headers=batch_headers) as response:
                                    if response.status == 200:
                                        res_json = await response.json()
                                        Batch_Token = res_json['data']['hash']
                                        App_Name = res_json['data']['name']

                                        await editable.edit(f"🔄 **Exᴛʀᴀᴄᴛɪɴɢ ᴄᴏᴜʀsᴇ:** {selected_batch_name} ...")

                                        start_time = time.time()
                                        course_content, video_count, pdf_count, image_count = await get_cpwp_course_content(session, headers, Batch_Token)
                                    
                                        if course_content:
                                            # Count different types of links
                                            video_count = sum(1 for line in course_content if any(ext in line.lower() for ext in ['.m3u8', '.mp4', '.m4s']))
                                            pdf_count = sum(1 for line in course_content if '.pdf' in line.lower())
                                            total_links = len(course_content)

                                            # Write content to file in chunks
                                            file = f"{clean_file_name}.txt"
                                            chunk_size = 1000  # Process 1000 lines at a time
                                            
                                            with open(file, 'w', encoding='utf-8') as f:
                                                for i in range(0, len(course_content), chunk_size):
                                                    chunk = course_content[i:i + chunk_size]
                                                    f.write(''.join(chunk))
                                                    # Force garbage collection after each chunk
                                                    gc.collect()
                                                    
                                                    # Add a small delay to prevent memory spikes
                                                    await asyncio.sleep(0.1)
                                            
                                            # Clear large variables when no longer needed
                                            course_content = None
                                            gc.collect()

                                            end_time = time.time()
                                            response_time = end_time - start_time
                                            minutes = int(response_time // 60)
                                            seconds = int(response_time % 60)

                                            if minutes == 0:
                                                if seconds < 1:
                                                    formatted_time = f"{response_time:.2f} sᴇᴄᴏɴᴅs"
                                                else:
                                                    formatted_time = f"{seconds} sᴇᴄᴏɴᴅs"
                                            else:
                                                formatted_time = f"{minutes} ᴍɪɴᴜᴛᴇs {seconds} sᴇᴄᴏɴᴅs"

                                            await editable.delete(True)
                                        
                                            user = await bot.get_users(user_id)
                                            user_name = user.first_name
                                            if user.last_name:
                                                user_name += f" {user.last_name}"
                                            mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'
                                            
                                            # Create caption
                                            caption = (
                                    f"🎯 <b>{App_Name.upper()}</b>\n\n"
                                    f"🔑 ᴄᴏᴅᴇ: `{org_code}`\n"
                                    f"<blockquote>📝 ʙᴀᴛᴄʜ: {clean_batch_name}</blockquote>\n\n"
                                    f"💰 ᴘʀɪᴄᴇ: ₹{course.get('finalPrice', 'N/A')}\n"
                                    f"📅 ꜱᴛᴀʀᴛ: {course.get('createdAt', 'N/A').split('T')[0] if course.get('createdAt') else 'N/A'}\n"
                                    f"📅 ᴇɴᴅ: {course.get('expiresAt', 'N/A')}\n"
                                    f"<blockquote>📊 ᴄᴏɴᴛᴇɴᴛ ᴅᴇᴛᴀɪʟꜱ:\n"
                                    f"├─⭓ 🎬 ᴠɪᴅᴇᴏꜱ: {video_count}\n"
                                    f"├─⭓ 📑 ᴘᴅꜰꜱ: {pdf_count}\n"
                                    f"└─⭓ 🖼 ɪᴍᴀɢᴇꜱ: {image_count}</blockquote>\n\n"
                                    f"🤖 ᴜꜱɪɴɢ: {join}\n"
                                    f"⏱ ᴛɪᴍᴇ ᴛᴀᴋᴇɴ: {format_time_taken(start_time)}\n"
                                    f"📅 ᴅᴀᴛᴇ: {time_new}\n\n"
                                    f"<blockquote><b>👑 EXTRACTED BY:</b> {mention}</blockquote>"
                                )
                                        
                                            progress = await m.reply_text("🔄 **Exᴛʀᴀᴄᴛɪɴɢ ʟɪɴᴋs, ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...**")
                                            await progress.edit("💾 **Sᴀᴠɪɴɢ ʟɪɴᴋs ᴛᴏ ғɪʟᴇ...**")
                                            with open(file, 'rb') as f:
                                                # Send to user
                                                doc = await m.reply_document(document=f, caption=caption, file_name=f"{clean_batch_name}.txt", thumb=thumb)
                                                # Send to log channel
                                                await app.send_document(chat_id=WITHOUT_LOGS, document=f, caption=caption, file_name=f"{clean_batch_name}.txt", thumb=thumb)
                                            await progress.edit("⬆️ **Uᴘʟᴏᴀᴅɪɴɢ ʏᴏᴜʀ ᴛxᴛ ғɪʟᴇ...**")
                                            await progress.edit("✅ **Dᴏɴᴇ! Yᴏᴜʀ ᴛxᴛ ғɪʟᴇ ɪs ʀᴇᴀᴅʏ.**")

                                            os.remove(file)

                                        else:
                                            raise Exception("**Dɪᴅɴ'ᴛ Fɪɴᴅ Aɴʏ Cᴏɴᴛᴇɴᴛ Iɴ Tʜᴇ Cᴏᴜʀsᴇ**")
                                    else:
                                        raise Exception(f"{response.text}")
                            else:
                                raise Exception("**Dɪᴅɴ'ᴛ Fɪɴᴅ Aɴʏ Cᴏᴜʀsᴇ**")
                        else:
                            raise Exception(f"{response.text}")
                else:
                    raise Exception('**Nᴏ Aᴘᴘ Fᴏᴜɴᴅ Iɴ Oʀɢ Cᴏᴅᴇ**')
                    
        except Exception as e:
            await editable.edit(f"❌ **Eʀʀᴏʀ:** {str(e)}")
            
        finally:
            await session.close()
            await CONNECTOR.close()
            gc.collect()
