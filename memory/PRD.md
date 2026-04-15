# Drive Slideshow App - PRD

## Original Problem Statement
Create a web app where if I upload my drive link in the main folder they open like an image slideshow where every folder and subfolder name is written on photos.

## Architecture
- **Backend**: FastAPI + MongoDB + Google Drive API (OAuth only)
- **Frontend**: React + Tailwind CSS + Shadcn UI + Phosphor Icons
- **Auth**: Google OAuth 2.0 (read-only Drive access)
- **Design**: Swiss Minimal (Archetype 4) - Cabinet Grotesk + IBM Plex Sans

## User Personas
- Users who want to visualize Google Drive folder structures as slideshows
- Photographers/content creators organizing images in Drive folders

## Core Requirements
1. Google OAuth authentication for Drive access
2. Recursive folder/subfolder fetching from Drive
3. Image slideshow with folder names overlaid
4. Manual and auto-play navigation controls
5. Sidebar folder tree view

## What's Been Implemented (Feb 2026)
- [x] Google OAuth flow (connect, callback, session management)
- [x] Backend: Folder structure fetching (recursive), image proxy, session status
- [x] Frontend: Landing page, Dashboard (folder link input), Slideshow viewer
- [x] Slideshow controls: Next/Prev, Play/Pause, Progress bar, Slide counter
- [x] Sidebar folder tree with click-to-navigate
- [x] Folder name overlay on images (Swiss brutalist typography)
- [x] Fallback images for empty folders
- [x] Swiss minimal design with correct fonts and colors

## Prioritized Backlog
### P0 (Critical)
- None remaining

### P1 (High)
- Keyboard shortcuts for slideshow navigation (arrow keys, spacebar)
- Thumbnail previews in sidebar

### P2 (Medium)
- Fullscreen mode toggle
- Image zoom/pan capability
- Download slideshow as PDF
- Share slideshow via link

## Next Tasks
1. User to test full OAuth flow with real Google Drive folder
2. Add keyboard navigation support
3. Add fullscreen mode
