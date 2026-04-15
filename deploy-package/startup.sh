#!/bin/bash
# Startup script for Drive Slideshow backend
cd "$(dirname "$0")"

# Activate virtual environment
source venv/bin/activate

# Start uvicorn
exec uvicorn server:app --host 127.0.0.1 --port 8001 --workers 2
