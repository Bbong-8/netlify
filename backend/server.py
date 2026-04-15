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
CACHE_TTL_SECONDS = 300  # 5 minutes


# ── Models ──

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


# ── Helpers ──

def extract_folder_id(drive_link: str) -> str:
    """Extract folder ID from various Google Drive link formats."""
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
    """Fetch entries from a public Google Drive folder via embedded view."""
    url = f'https://drive.google.com/embeddedfolderview?id={folder_id}'
    resp = http_requests.get(url, timeout=15)
    if resp.status_code != 200:
        return [], "Unknown Folder"

    title_match = re.search(r'<title>(.*?)</title>', resp.text)
    folder_name = title_match.group(1) if title_match else "Drive Folder"

    entry_ids = re.findall(r'id="entry-([a-zA-Z0-9_-]+)"', resp.text)
    entry_titles = re.findall(r'<div class="flip-entry-title">(.*?)</div>', resp.text)

    return [{"id": eid, "name": etitle} for eid, etitle in zip(entry_ids, entry_titles)], folder_name


def classify_entries(entries, path_prefix, parent_folder):
    """Classify a list of entries into FolderItems and subfolder references."""
    items = []
    subfolders = []
    for entry in entries:
        item_path = f"{path_prefix}/{entry['name']}" if path_prefix else entry['name']
        if is_image_file(entry['name']):
            items.append(FolderItem(id=entry["id"], name=entry["name"], type='image', path=item_path, parent_folder=parent_folder))
        else:
            items.append(FolderItem(id=entry["id"], name=entry["name"], type='folder', path=item_path, parent_folder=parent_folder))
            subfolders.append((entry["id"], entry["name"], item_path))
    return items, subfolders


def scan_folder(folder_id, path_prefix, parent_folder):
    """Scan a single folder: fetch entries and classify them."""
    entries, _ = fetch_folder_entries(folder_id)
    return classify_entries(entries, path_prefix, parent_folder)


def scan_level_parallel(queue):
    """Scan a list of folders in parallel. Returns dict: folder_id -> (items, subfolders)."""
    results = {}
    if not queue:
        return results

    futures = {}
    for fid, _fname, fpath, *_rest in queue:
        future = executor.submit(scan_folder, fid, fpath, fpath)
        futures[future] = fid

    for future in as_completed(futures):
        fid = futures[future]
        try:
            results[fid] = future.result()
        except Exception as e:
            logger.error(f"Error scanning folder {fid}: {e}")
            results[fid] = ([], [])

    return results


def assemble_folder_tree(top_folders, folder_name, level2, level3, level4):
    """Assemble flat item list in correct folder order from scan results."""
    all_items = []

    for folder_entry in top_folders:
        fid = folder_entry["id"]
        all_items.append(FolderItem(id=fid, name=folder_entry["name"], type='folder', path=folder_entry["name"], parent_folder=folder_name))

        if fid not in level2:
            continue

        l2_items, _ = level2[fid]
        l2_images = [i for i in l2_items if i.type == 'image']
        l2_folders = [i for i in l2_items if i.type == 'folder']

        for sf in l2_folders:
            all_items.append(sf)
            if sf.id in level3:
                l3_items, _ = level3[sf.id]
                l3_images = [i for i in l3_items if i.type == 'image']
                l3_folders = [i for i in l3_items if i.type == 'folder']
                for l3f in l3_folders:
                    all_items.append(l3f)
                    if l3f.id in level4:
                        all_items.extend(level4[l3f.id])
                all_items.extend(l3_images)

        all_items.extend(l2_images)

    return all_items


def fetch_all_recursive(folder_id, max_depth=4):
    """Fetch entire folder tree using parallel HTTP requests, preserving folder order."""
    entries, folder_name = fetch_folder_entries(folder_id)

    top_images = []
    top_folders = []
    for entry in entries:
        if is_image_file(entry['name']):
            top_images.append(FolderItem(id=entry["id"], name=entry["name"], type='image', path=entry["name"], parent_folder=folder_name))
        else:
            top_folders.append(entry)

    if max_depth <= 1:
        shallow = [FolderItem(id=f["id"], name=f["name"], type='folder', path=f["name"], parent_folder=folder_name) for f in top_folders]
        return shallow + top_images, folder_name

    # Level 2
    l2_queue = [(f["id"], f["name"], f["name"], None) for f in top_folders]
    level2 = scan_level_parallel(l2_queue)

    # Level 3
    l3_queue = []
    if max_depth > 2:
        for f in top_folders:
            if f["id"] in level2:
                _, subs = level2[f["id"]]
                l3_queue.extend([(sid, sn, sp, f["id"]) for sid, sn, sp in subs])
    level3 = scan_level_parallel(l3_queue)

    # Level 4
    l4_queue = []
    if max_depth > 3:
        for sid, _sn, sp, _parent in l3_queue:
            if sid in level3:
                _, subs = level3[sid]
                l4_queue.extend([(ssid, ssn, ssp, sid) for ssid, ssn, ssp in subs])
    level4_raw = scan_level_parallel(l4_queue)
    level4 = {fid: items for fid, (items, _) in level4_raw.items()}

    all_items = assemble_folder_tree(top_folders, folder_name, level2, level3, level4)
    all_items.extend(top_images)

    return all_items, folder_name


# ── Cache helpers ──

async def get_cached_result(folder_id):
    """Return cached folder data if fresh enough, else None."""
    cached = await db.folder_cache.find_one({"folder_id": folder_id}, {"_id": 0})
    if not cached or not cached.get("created_at"):
        return None
    try:
        cached_time = datetime.fromisoformat(cached["created_at"])
        age = (datetime.now(timezone.utc) - cached_time).total_seconds()
        if age < CACHE_TTL_SECONDS:
            logger.info(f"Cache hit for '{cached['folder_name']}' (age: {int(age)}s)")
            return cached
    except (ValueError, TypeError):
        pass
    return None


async def store_cache(folder_id, folder_name, items, total_images, total_folders):
    """Store scan result in MongoDB cache."""
    doc = {
        "folder_id": folder_id,
        "folder_name": folder_name,
        "items": [item.model_dump() for item in items],
        "total_images": total_images,
        "total_folders": total_folders,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.folder_cache.update_one({"folder_id": folder_id}, {"$set": doc}, upsert=True)


# ── Routes ──

@api_router.get("/")
async def root():
    return {"message": "Google Drive Slideshow API"}


@api_router.post("/drive/folder")
async def get_folder_structure(request: DriveLinkRequest, refresh: bool = False):
    """Get folder structure from a public Drive link. Use refresh=true to force re-scan."""
    try:
        folder_id = extract_folder_id(request.drive_link)
        logger.info(f"Fetching folder ID: {folder_id}, refresh={refresh}")

        if not refresh:
            cached = await get_cached_result(folder_id)
            if cached:
                return cached

        items, folder_name = fetch_all_recursive(folder_id)

        if not items:
            raise HTTPException(status_code=400, detail="No content found. Make sure the folder is shared publicly.")

        total_images = sum(1 for i in items if i.type == 'image')
        total_folders = sum(1 for i in items if i.type == 'folder')
        logger.info(f"Found {total_images} images and {total_folders} folders in '{folder_name}'")

        await store_cache(folder_id, folder_name, items, total_images, total_folders)

        return FolderStructureResponse(items=items, folder_name=folder_name, total_images=total_images, total_folders=total_folders)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching folder: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}. Make sure the folder is shared publicly.")


@api_router.delete("/drive/cache/{folder_id}")
async def clear_cache(folder_id: str):
    """Clear cached folder data to force re-scan."""
    await db.folder_cache.delete_one({"folder_id": folder_id})
    return {"message": "Cache cleared"}


@api_router.get("/drive/image/{file_id}")
async def get_drive_image(file_id: str):
    """Proxy image from public Google Drive."""
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


# ── App setup ──

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
