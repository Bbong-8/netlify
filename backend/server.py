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
    """Fetch entire folder tree using parallel HTTP requests, preserving folder order"""
    entries, folder_name = fetch_folder_entries(folder_id)

    # Level 1: classify top-level entries, preserving original order
    top_images = []
    top_folders = []  # preserves order from Google Drive
    for entry in entries:
        if is_image_file(entry['name']):
            top_images.append(FolderItem(
                id=entry["id"], name=entry["name"], type='image',
                path=entry["name"], parent_folder=folder_name
            ))
        else:
            top_folders.append(entry)

    if max_depth <= 1:
        all_items = []
        for f in top_folders:
            all_items.append(FolderItem(id=f["id"], name=f["name"], type='folder', path=f["name"], parent_folder=folder_name))
        all_items.extend(top_images)
        return all_items, folder_name

    # Level 2: scan all top-level folders in parallel, but collect results per folder
    level2_futures = {}
    for folder_entry in top_folders:
        future = executor.submit(scan_folder_parallel, folder_entry["id"], folder_entry["name"], folder_entry["name"])
        level2_futures[future] = folder_entry["id"]

    # Collect results keyed by folder ID
    level2_results = {}
    for future in as_completed(level2_futures):
        fid = level2_futures[future]
        try:
            items, subfolders = future.result()
            level2_results[fid] = (items, subfolders)
        except Exception as e:
            logger.error(f"Error scanning folder: {e}")
            level2_results[fid] = ([], [])

    # Level 3: collect all subfolders and scan in parallel
    level3_queue = []  # (folder_id, folder_name, path, top_folder_id)
    for folder_entry in top_folders:
        fid = folder_entry["id"]
        if fid in level2_results:
            _, subfolders = level2_results[fid]
            for sf_id, sf_name, sf_path in subfolders:
                level3_queue.append((sf_id, sf_name, sf_path, fid))

    level3_results = {}
    if max_depth > 2 and level3_queue:
        level3_futures = {}
        for sf_id, sf_name, sf_path, top_fid in level3_queue:
            future = executor.submit(scan_folder_parallel, sf_id, sf_path, sf_path)
            level3_futures[future] = (sf_id, top_fid)

        for future in as_completed(level3_futures):
            sf_id, top_fid = level3_futures[future]
            try:
                items, subfolders = future.result()
                level3_results[sf_id] = (items, subfolders)
            except Exception as e:
                level3_results[sf_id] = ([], [])

    # Level 4: go one more level deep
    level4_queue = []
    for sf_id, sf_name, sf_path, top_fid in level3_queue:
        if sf_id in level3_results:
            _, subfolders = level3_results[sf_id]
            for ssf_id, ssf_name, ssf_path in subfolders:
                level4_queue.append((ssf_id, ssf_name, ssf_path, sf_id))

    level4_results = {}
    if max_depth > 3 and level4_queue:
        level4_futures = {}
        for ssf_id, ssf_name, ssf_path, parent_sf_id in level4_queue:
            future = executor.submit(scan_folder_parallel, ssf_id, ssf_path, ssf_path)
            level4_futures[future] = ssf_id

        for future in as_completed(level4_futures):
            ssf_id = level4_futures[future]
            try:
                items, _ = future.result()
                level4_results[ssf_id] = items
            except:
                level4_results[ssf_id] = []

    # ASSEMBLE in correct order: iterate top folders in original order
    all_items = []
    for folder_entry in top_folders:
        fid = folder_entry["id"]
        folder_path = folder_entry["name"]

        # Add the top-level folder item
        all_items.append(FolderItem(
            id=fid, name=folder_entry["name"], type='folder',
            path=folder_path, parent_folder=folder_name
        ))

        if fid not in level2_results:
            continue

        level2_items, level2_subfolders = level2_results[fid]

        # Separate sub-images and sub-folders from level 2
        l2_images = [i for i in level2_items if i.type == 'image']
        l2_folders = [i for i in level2_items if i.type == 'folder']

        # For each subfolder in level 2 (in order), add folder + its images
        for sf_item in l2_folders:
            all_items.append(sf_item)  # Add subfolder header

            # Add level 3 items for this subfolder
            if sf_item.id in level3_results:
                l3_items, l3_subfolders = level3_results[sf_item.id]
                l3_images = [i for i in l3_items if i.type == 'image']
                l3_folders = [i for i in l3_items if i.type == 'folder']

                for l3f in l3_folders:
                    all_items.append(l3f)
                    # Add level 4 items
                    if l3f.id in level4_results:
                        all_items.extend(level4_results[l3f.id])

                all_items.extend(l3_images)

        # Add direct images of this top folder last
        all_items.extend(l2_images)

    # Add any root-level images at the end
    all_items.extend(top_images)

    return all_items, folder_name


@api_router.get("/")
async def root():
    return {"message": "Google Drive Slideshow API"}


@api_router.post("/drive/folder")
async def get_folder_structure(request: DriveLinkRequest):
    """Get folder structure from a public Drive link - always fresh scan"""
    try:
        folder_id = extract_folder_id(request.drive_link)
        logger.info(f"Fetching folder structure for ID: {folder_id}")

        # Always do a fresh scan (no cache) so new images show up
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
