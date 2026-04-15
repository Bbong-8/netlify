#!/usr/bin/env bash
# Start script for Render.com
cd backend
uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001}
