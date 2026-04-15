#!/usr/bin/env bash
# Build script for Render.com - installs both backend and frontend
set -e

echo "==> Installing Python dependencies..."
cd backend
pip install -r requirements.txt

echo "==> Installing frontend dependencies..."
cd ../frontend
yarn install

echo "==> Building frontend..."
REACT_APP_BACKEND_URL="" yarn build

echo "==> Build complete!"
