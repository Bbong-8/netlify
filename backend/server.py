from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import List
from datetime import datetime, timezone
import re
import io
import requests as http_requests
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=15)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.tiff', '.heic', '.heif'}


class DriveLinkRequest(BaseModel):
    drive_link: str

class FolderItem(BaseModel):
    id: str
    name: str
    type: str
    path: str
    parent_folder: str = ""

class FolderStructureResponse(BaseModel):
    items: List[FolderItem]
    folder_name: str
    total_images: int
    total_folders: int


def extract_folder_id(drive_link: str) -> str:
    patterns = [
        r'folders/([a-zA-Z0-9-_]+)',
        r'id=([a-zA-Z0-9-_]+)',
        r'drive\.google\.com/drive/u/\d+/folders/([a-zA-Z0-9-_]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, drive_link)
        if match:
            return match.group(1)
    if re.match(r'^[a-zA-Z0-9-_]+$', drive_link.strip()):
        return drive_link.strip()
    raise ValueError("Invalid Drive link format.")


def is_image_file(name: str) -> bool:
    return any(name.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)


def fetch_folder_entries(folder_id: str):
    """Fetch entries from a public Google Drive folder"""
    url = f'https://drive.google.com/embeddedfolderview?id={folder_id}'
    resp = http_requests.get(url, timeout=15)
    if resp.status_code != 200:
        return [], "Unknown Folder"

    title_match = re.search(r'<title>(.*?)</title>', resp.text)
    folder_name = title_match.group(1) if title_match else "Drive Folder"

    entry_ids = re.findall(r'id="entry-([a-zA-Z0-9_-]+)"', resp.text)
    entry_titles = re.findall(r'<div class="flip-entry-title">(.*?)</div>', resp.text)

    return [{"id": eid, "name": etitle} for eid, etitle in zip(entry_ids, entry_titles)], folder_name


def scan_folder_parallel(folder_id, folder_name_prefix, parent_folder):
    """Scan a single folder and return its items (images + subfolder entries)"""
    entries, _ = fetch_folder_entries(folder_id)
    items = []
    subfolders = []

    for entry in entries:
        item_path = f"{folder_name_prefix}/{entry['name']}" if folder_name_prefix else entry['name']
        if is_image_file(entry['name']):
            items.append(FolderItem(
                id=entry["id"], name=entry["name"], type='image',
                path=item_path, parent_folder=parent_folder
            ))
        else:
            # Assume non-image entries are folders
            items.append(FolderItem(
                id=entry["id"], name=entry["name"], type='folder',
                path=item_path, parent_folder=parent_folder
            ))
            subfolders.append((entry["id"], entry["name"], item_path))

    return items, subfolders


def fetch_all_recursive(folder_id, max_depth=4):
    """Fetch entire folder tree using parallel HTTP requests at each level"""
    entries, folder_name = fetch_folder_entries(folder_id)
    all_items = []

    # Level 1: classify top-level entries
    top_images = []
    top_folders = []
    for entry in entries:
        if is_image_file(entry['name']):
            top_images.append(FolderItem(
                id=entry["id"], name=entry["name"], type='image',
                path=entry["name"], parent_folder=folder_name
            ))
        else:
            top_folders.append(entry)
            all_items.append(FolderItem(
                id=entry["id"], name=entry["name"], type='folder',
                path=entry["name"], parent_folder=folder_name
            ))
    all_items.extend(top_images)

    if max_depth <= 1:
        return all_items, folder_name

    # Level 2: scan all top-level folders in parallel
    level2_futures = {}
    for folder_entry in top_folders:
        future = executor.submit(
            scan_folder_parallel,
            folder_entry["id"],
            folder_entry["name"],
            folder_entry["name"]
        )
        level2_futures[future] = folder_entry

    level3_queue = []  # (folder_id, path, parent)
    for future in as_completed(level2_futures):
        parent_entry = level2_futures[future]
        try:
            items, subfolders = future.result()
            all_items.extend(items)
            if max_depth > 2:
                level3_queue.extend(subfolders)
        except Exception as e:
            logger.error(f"Error scanning folder {parent_entry['name']}: {e}")

    if max_depth <= 2 or not level3_queue:
        return all_items, folder_name

    # Level 3: scan all subfolders in parallel
    level3_futures = {}
    for fid, fname, fpath in level3_queue:
        future = executor.submit(scan_folder_parallel, fid, fpath, fpath)
        level3_futures[future] = (fid, fname, fpath)

    level4_queue = []
    for future in as_completed(level3_futures):
        parent_info = level3_futures[future]
        try:
            items, subfolders = future.result()
            all_items.extend(items)
            if max_depth > 3:
                level4_queue.extend(subfolders)
        except Exception as e:
            logger.error(f"Error scanning subfolder {parent_info[1]}: {e}")

    if max_depth <= 3 or not level4_queue:
        return all_items, folder_name

    # Level 4: one more level deep
    level4_futures = {}
    for fid, fname, fpath in level4_queue:
        future = executor.submit(scan_folder_parallel, fid, fpath, fpath)
        level4_futures[future] = (fid, fname, fpath)

    for future in as_completed(level4_futures):
        try:
            items, _ = future.result()
            all_items.extend(items)
        except Exception as e:
            pass

    return all_items, folder_name


@api_router.get("/")
async def root():
    return {"message": "Google Drive Slideshow API"}


@api_router.post("/drive/folder")
async def get_folder_structure(request: DriveLinkRequest):
    """Get folder structure from a public Drive link"""
    try:
        folder_id = extract_folder_id(request.drive_link)
        logger.info(f"Fetching folder structure for ID: {folder_id}")

        # Check cache first
        cached = await db.folder_cache.find_one({"folder_id": folder_id}, {"_id": 0})
        if cached:
            logger.info(f"Returning cached result for '{cached['folder_name']}'")
            return cached

        items, folder_name = fetch_all_recursive(folder_id)

        if not items:
            raise HTTPException(
                status_code=400,
                detail="No content found. Make sure the folder is shared publicly and contains files."
            )

        total_images = sum(1 for i in items if i.type == 'image')
        total_folders = sum(1 for i in items if i.type == 'folder')

        logger.info(f"Found {total_images} images and {total_folders} folders in '{folder_name}'")

        result = {
            "folder_id": folder_id,
            "folder_name": folder_name,
            "items": [item.model_dump() for item in items],
            "total_images": total_images,
            "total_folders": total_folders,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.folder_cache.update_one(
            {"folder_id": folder_id}, {"$set": result}, upsert=True
        )

        return FolderStructureResponse(
            items=items, folder_name=folder_name,
            total_images=total_images, total_folders=total_folders
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching folder: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}. Make sure the folder is shared publicly.")


@api_router.delete("/drive/cache/{folder_id}")
async def clear_cache(folder_id: str):
    """Clear cached folder data to force re-scan"""
    await db.folder_cache.delete_one({"folder_id": folder_id})
    return {"message": "Cache cleared"}


@api_router.get("/drive/image/{file_id}")
async def get_drive_image(file_id: str):
    """Proxy image from public Google Drive"""
    try:
        thumb_url = f'https://drive.google.com/thumbnail?id={file_id}&sz=w1920'
        resp = http_requests.get(thumb_url, timeout=15, allow_redirects=True)

        if resp.status_code != 200:
            view_url = f'https://drive.google.com/uc?export=view&id={file_id}'
            resp = http_requests.get(view_url, timeout=15, allow_redirects=True)

        if resp.status_code != 200:
            raise HTTPException(status_code=404, detail="Image not found")

        content_type = resp.headers.get('content-type', 'image/jpeg')
        return StreamingResponse(
            io.BytesIO(resp.content),
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=3600"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching image {file_id}: {str(e)}")
        raise HTTPException(status_code=404, detail=f"Image not found: {str(e)}")


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
