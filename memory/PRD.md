# Drive Slideshow App - PRD

## Original Problem Statement
Create a web app where if I upload my drive link in the main folder they open like an image slideshow where every folder and subfolder name is written on photos.

## Architecture
- **Backend**: FastAPI + MongoDB (caching) + Google Drive web scraping (no API key needed)
- **Frontend**: React + Tailwind CSS + Shadcn UI + Phosphor Icons
- **Auth**: None required - works with public Drive links only
- **Design**: Swiss Minimal (Archetype 4) - Cabinet Grotesk + IBM Plex Sans

## What's Been Implemented (Feb 2026)
- [x] Public Drive folder scanning via web scraping (no OAuth/API key needed)
- [x] Parallel HTTP requests for fast folder tree scanning (15 concurrent workers)
- [x] MongoDB caching (first scan ~1-2 min, cached loads instant)
- [x] Image proxy via Google Drive thumbnail URLs
- [x] Slideshow with folder/subfolder names overlaid on images
- [x] Sidebar folder tree with click-to-navigate
- [x] Manual controls: Next/Prev buttons
- [x] Auto-play with Play/Pause toggle (5s per slide)
- [x] Keyboard navigation (Arrow keys, Spacebar)
- [x] Progress bar + slide counter
- [x] Empty state handling
- [x] Swiss minimal design

## Tested With
- Folder: NSO_Pictures_March_26 (497 images, 168 folders, 3 levels deep)
- Backend: 88% pass, Frontend: 100% pass

## Next Tasks
1. Add fullscreen mode toggle
2. Add thumbnail grid view option
3. Add folder filter (show only specific folder's images)
