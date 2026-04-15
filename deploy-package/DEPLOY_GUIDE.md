# Drive Slideshow - Plesk Server Deployment Guide

## Prerequisites
- Plesk server with:
  - **Python 3.11+** (via Plesk Python extension)
  - **Node.js 18+** (via Plesk Node.js extension)
  - **MongoDB 6+** (installed on server or use MongoDB Atlas)
- A domain/subdomain configured in Plesk

---

## Folder Structure
```
deploy-package/
├── backend/              # FastAPI Python backend
│   ├── server.py         # Main application
│   ├── requirements.txt  # Python dependencies
│   ├── .env.example      # Environment template
│   └── wsgi.py           # WSGI entry point for Plesk
├── frontend/
│   └── build/            # Pre-built React app (static files)
├── nginx-plesk.conf      # Nginx config snippet for Plesk
├── startup.sh            # Backend startup script
└── DEPLOY_GUIDE.md       # This file
```

---

## Step-by-Step Deployment

### Step 1: Upload Files
1. Upload the entire `deploy-package/` folder to your Plesk server via **File Manager** or **SFTP**
2. Place it in your domain's root directory (e.g., `/var/www/vhosts/yourdomain.com/`)

### Step 2: Setup MongoDB
**Option A: MongoDB on your server**
```bash
# Install MongoDB (Ubuntu/Debian)
sudo apt install -y mongodb
sudo systemctl enable mongodb
sudo systemctl start mongodb
```

**Option B: MongoDB Atlas (Cloud - Free Tier)**
1. Go to https://cloud.mongodb.com
2. Create a free cluster
3. Get connection string: `mongodb+srv://user:pass@cluster.mongodb.net/drive_slideshow`

### Step 3: Configure Backend Environment
```bash
cd /var/www/vhosts/yourdomain.com/deploy-package/backend/
cp .env.example .env
nano .env
```

Edit `.env` with your values:
```
MONGO_URL=mongodb://localhost:27017    # or your Atlas URL
DB_NAME=drive_slideshow
CORS_ORIGINS=https://yourdomain.com
```

### Step 4: Install Python Dependencies
```bash
cd /var/www/vhosts/yourdomain.com/deploy-package/backend/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 5: Test Backend
```bash
cd backend/
source venv/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8001
# Visit http://yourserver:8001/api/ - should see {"message":"Google Drive Slideshow API"}
# Press Ctrl+C to stop
```

### Step 6: Setup Backend as Service (systemd)
Create `/etc/systemd/system/drive-slideshow.service`:
```ini
[Unit]
Description=Drive Slideshow Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/vhosts/yourdomain.com/deploy-package/backend
Environment=PATH=/var/www/vhosts/yourdomain.com/deploy-package/backend/venv/bin
ExecStart=/var/www/vhosts/yourdomain.com/deploy-package/backend/venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Then enable it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable drive-slideshow
sudo systemctl start drive-slideshow
sudo systemctl status drive-slideshow  # Should show "active (running)"
```

### Step 7: Deploy Frontend
1. In Plesk, go to your domain → **Hosting & DNS** → **Document Root**
2. Set document root to: `/var/www/vhosts/yourdomain.com/deploy-package/frontend/build`
3. Or copy build files:
```bash
cp -r /var/www/vhosts/yourdomain.com/deploy-package/frontend/build/* /var/www/vhosts/yourdomain.com/httpdocs/
```

### Step 8: Configure Nginx in Plesk
1. Go to your domain in Plesk → **Apache & nginx Settings**
2. Scroll to **Additional nginx directives**
3. Paste the following:

```nginx
# Proxy API requests to FastAPI backend
location /api/ {
    proxy_pass http://127.0.0.1:8001/api/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
    proxy_connect_timeout 300s;
}

# Handle React SPA routing
location / {
    try_files $uri $uri/ /index.html;
}
```

4. Click **Apply**

### Step 9: Update Frontend API URL
The pre-built frontend uses relative URLs (`/api/...`), so the nginx proxy config above handles routing automatically. No changes needed.

### Step 10: Test
1. Visit `https://yourdomain.com` — should see the Drive Slideshow landing page
2. Paste a public Google Drive folder link and click Load
3. Browse folders and view images

---

## Troubleshooting

### Backend not starting
```bash
sudo journalctl -u drive-slideshow -f   # Check logs
```

### MongoDB connection error
```bash
mongosh   # Test MongoDB is running
# Or check Atlas connection string in .env
```

### 502 Bad Gateway
- Backend service not running: `sudo systemctl restart drive-slideshow`
- Check port 8001 is not blocked: `netstat -tlnp | grep 8001`

### Images not loading
- Google Drive folder must be shared publicly ("Anyone with the link")
- Check backend logs for timeout errors

### Slow first load
- First scan of a large folder (500+ images) takes 1-2 minutes
- Subsequent loads use 5-minute cache and are instant

---

## Security Notes
- Set `CORS_ORIGINS` to your actual domain (not `*`)
- Use HTTPS (Plesk has free Let's Encrypt SSL)
- MongoDB: set up authentication if exposed to network
