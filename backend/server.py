from fastapi import FastAPI, APIRouter, HTTPException, Query, Response
from fastapi.responses import RedirectResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import re
import io

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Models
class DriveAuthResponse(BaseModel):
    authorization_url: str

class DriveLinkRequest(BaseModel):
    drive_link: str

class FolderItem(BaseModel):
    id: str
    name: str
    type: str  # 'folder' or 'image'
    path: str
    thumbnail_url: Optional[str] = None
    web_view_link: Optional[str] = None

class FolderStructureResponse(BaseModel):
    items: List[FolderItem]
    folder_name: str


# Helper function to extract folder ID from Drive link
def extract_folder_id(drive_link: str) -> str:
    """Extract folder ID from various Google Drive link formats"""
    patterns = [
        r'folders/([a-zA-Z0-9-_]+)',
        r'id=([a-zA-Z0-9-_]+)',
        r'drive\.google\.com/drive/u/\d+/folders/([a-zA-Z0-9-_]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, drive_link)
        if match:
            return match.group(1)
    
    # If it's just an ID
    if re.match(r'^[a-zA-Z0-9-_]+$', drive_link.strip()):
        return drive_link.strip()
    
    raise ValueError("Invalid Drive link format")


# Helper to get Drive service (public or authenticated)
async def get_public_drive_service():
    """Get Drive service for public file access (no auth needed)"""
    return build('drive', 'v3', developerKey=None)


async def get_authenticated_drive_service(session_id: str):
    """Get authenticated Drive service from stored credentials"""
    creds_doc = await db.drive_credentials.find_one({"session_id": session_id})
    if not creds_doc:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please connect your Google Drive first."
        )
    
    creds = Credentials(
        token=creds_doc["access_token"],
        refresh_token=creds_doc.get("refresh_token"),
        token_uri=creds_doc["token_uri"],
        client_id=creds_doc["client_id"],
        client_secret=creds_doc["client_secret"],
        scopes=creds_doc["scopes"]
    )
    
    # Auto-refresh if expired
    if creds.expired and creds.refresh_token:
        logger.info(f"Refreshing expired token for session {session_id}")
        creds.refresh(GoogleRequest())
        
        await db.drive_credentials.update_one(
            {"session_id": session_id},
            {"$set": {
                "access_token": creds.token,
                "expiry": creds.expiry.isoformat() if creds.expiry else None,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
    
    return build('drive', 'v3', credentials=creds)


# Recursive function to get all folders and images
async def get_folder_contents_recursive(service, folder_id: str, current_path: str = "") -> List[FolderItem]:
    """Recursively fetch all folders and images from a Drive folder"""
    items = []
    
    try:
        # Query for folders and images
        query = f"'{folder_id}' in parents and trashed=false and (mimeType='application/vnd.google-apps.folder' or mimeType contains 'image/')"
        
        page_token = None
        while True:
            results = service.files().list(
                q=query,
                spaces='drive',
                fields='nextPageToken, files(id, name, mimeType, thumbnailLink, webViewLink)',
                pageToken=page_token,
                pageSize=100
            ).execute()
            
            files = results.get('files', [])
            
            for file in files:
                item_path = f"{current_path}/{file['name']}" if current_path else file['name']
                
                if file['mimeType'] == 'application/vnd.google-apps.folder':
                    # Add folder
                    items.append(FolderItem(
                        id=file['id'],
                        name=file['name'],
                        type='folder',
                        path=item_path
                    ))
                    
                    # Recursively get contents of subfolder
                    sub_items = await get_folder_contents_recursive(service, file['id'], item_path)
                    items.extend(sub_items)
                
                elif 'image/' in file['mimeType']:
                    # Add image
                    items.append(FolderItem(
                        id=file['id'],
                        name=file['name'],
                        type='image',
                        path=item_path,
                        thumbnail_url=file.get('thumbnailLink'),
                        web_view_link=file.get('webViewLink')
                    ))
            
            page_token = results.get('nextPageToken')
            if not page_token:
                break
    
    except Exception as e:
        logger.error(f"Error fetching folder contents: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error accessing Drive folder: {str(e)}")
    
    return items


# Routes
@api_router.get("/")
async def root():
    return {"message": "Google Drive Slideshow API"}


@api_router.get("/drive/connect")
async def connect_drive():
    """Initiate Google Drive OAuth flow"""
    try:
        session_id = str(uuid.uuid4())
        redirect_uri = os.getenv("GOOGLE_DRIVE_REDIRECT_URI")
        
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri]
                }
            },
            scopes=['https://www.googleapis.com/auth/drive.readonly'],
            redirect_uri=redirect_uri
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=session_id
        )
        
        logger.info(f"Drive OAuth initiated for session {session_id}")
        return {"authorization_url": authorization_url, "session_id": session_id}
    
    except Exception as e:
        logger.error(f"Failed to initiate OAuth: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate OAuth: {str(e)}")


@api_router.get("/drive/callback")
async def drive_callback(code: str = Query(...), state: str = Query(...)):
    """Handle Google Drive OAuth callback"""
    try:
        redirect_uri = os.getenv("GOOGLE_DRIVE_REDIRECT_URI")
        
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri]
                }
            },
            scopes=None,
            redirect_uri=redirect_uri
        )
        
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        logger.info(f"Drive credentials obtained for session {state}")
        
        # Store credentials
        await db.drive_credentials.update_one(
            {"session_id": state},
            {"$set": {
                "session_id": state,
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": credentials.scopes,
                "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        
        # Redirect to frontend
        frontend_url = os.getenv("FRONTEND_URL")
        return RedirectResponse(url=f"{frontend_url}/?drive_connected=true&session_id={state}")
    
    except Exception as e:
        logger.error(f"OAuth callback failed: {str(e)}")
        frontend_url = os.getenv("FRONTEND_URL")
        return RedirectResponse(url=f"{frontend_url}/?error=auth_failed")


@api_router.post("/drive/public/folder")
async def get_public_folder(request: DriveLinkRequest):
    """Get folder structure from a public Drive link"""
    try:
        folder_id = extract_folder_id(request.drive_link)
        logger.info(f"Extracting folder ID: {folder_id}")
        
        # Use service without credentials for public links
        service = build('drive', 'v3', developerKey=None)
        
        # Get folder metadata
        try:
            folder = service.files().get(
                fileId=folder_id,
                fields='id, name'
            ).execute()
            folder_name = folder['name']
        except:
            folder_name = "Drive Folder"
        
        # Get all contents recursively
        items = await get_folder_contents_recursive(service, folder_id)
        
        logger.info(f"Found {len(items)} items in folder")
        return FolderStructureResponse(items=items, folder_name=folder_name)
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching public folder: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error accessing folder: {str(e)}. Make sure the link is public and shared with 'Anyone with the link'.")


@api_router.post("/drive/auth/folder")
async def get_authenticated_folder(request: DriveLinkRequest, session_id: str = Query(...)):
    """Get folder structure from Drive with authentication"""
    try:
        folder_id = extract_folder_id(request.drive_link)
        logger.info(f"Extracting folder ID: {folder_id} for session {session_id}")
        
        service = await get_authenticated_drive_service(session_id)
        
        # Get folder metadata
        folder = service.files().get(
            fileId=folder_id,
            fields='id, name'
        ).execute()
        folder_name = folder['name']
        
        # Get all contents recursively
        items = await get_folder_contents_recursive(service, folder_id)
        
        logger.info(f"Found {len(items)} items in folder")
        return FolderStructureResponse(items=items, folder_name=folder_name)
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching authenticated folder: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error accessing folder: {str(e)}")


@api_router.get("/drive/image/{file_id}")
async def get_drive_image(file_id: str, session_id: Optional[str] = Query(None)):
    """Get image from Drive"""
    try:
        if session_id:
            service = await get_authenticated_drive_service(session_id)
        else:
            service = build('drive', 'v3', developerKey=None)
        
        # Get file metadata
        file_metadata = service.files().get(
            fileId=file_id,
            fields='mimeType, name'
        ).execute()
        
        # Download file
        request = service.files().get_media(fileId=file_id)
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        file_stream.seek(0)
        
        return StreamingResponse(
            file_stream,
            media_type=file_metadata.get('mimeType', 'image/jpeg'),
            headers={"Content-Disposition": f"inline; filename={file_metadata.get('name', 'image.jpg')}"}
        )
    
    except Exception as e:
        logger.error(f"Error fetching image: {str(e)}")
        raise HTTPException(status_code=404, detail=f"Image not found: {str(e)}")


@api_router.get("/drive/status")
async def check_drive_status(session_id: str = Query(...)):
    """Check if Drive is connected for a session"""
    creds_doc = await db.drive_credentials.find_one({"session_id": session_id})
    return {"connected": creds_doc is not None}


# Include the router in the main app
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