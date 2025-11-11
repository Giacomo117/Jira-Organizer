# Deployment Guide

This guide covers deploying the Jira Meeting Organizer to production environments.

## Deployment Architecture

```
┌─────────────────┐
│  Users/Browser  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Frontend (CDN) │ ← React Static Files
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Backend API    │ ← FastAPI + Uvicorn
└────────┬────────┘
         │
    ┌────┴────┬───────────┐
    ▼         ▼           ▼
┌────────┐  ┌────────┐  ┌────────────┐
│MongoDB │  │ Azure  │  │    Jira    │
│        │  │ OpenAI │  │    API     │
└────────┘  └────────┘  └────────────┘
```

## Prerequisites

- Server with Python 3.9+ (for backend)
- Web server for static files (Nginx, Apache, or CDN)
- MongoDB instance (MongoDB Atlas recommended)
- Azure OpenAI resource
- Jira Cloud instance
- Domain name and SSL certificate

## Option 1: Deploy with Docker (Recommended)

### 1. Create Docker Files

**Backend Dockerfile** (`backend/Dockerfile`):
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Frontend Dockerfile** (`frontend/Dockerfile`):
```dockerfile
FROM node:18-alpine as build

WORKDIR /app

# Install dependencies
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

# Copy source and build
COPY . .
RUN yarn build

# Production stage
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**Nginx Configuration** (`frontend/nginx.conf`):
```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # React Router support
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location /static/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

**Docker Compose** (`docker-compose.yml`):
```yaml
version: '3.8'

services:
  mongodb:
    image: mongo:7
    container_name: jira-organizer-mongo
    restart: unless-stopped
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_USERNAME}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD}
    volumes:
      - mongodb_data:/data/db
    ports:
      - "27017:27017"
    networks:
      - jira-organizer-network

  backend:
    build: ./backend
    container_name: jira-organizer-backend
    restart: unless-stopped
    environment:
      MONGO_URL: mongodb://${MONGO_USERNAME}:${MONGO_PASSWORD}@mongodb:27017/
      DB_NAME: ${DB_NAME}
      AZURE_OPENAI_API_KEY: ${AZURE_OPENAI_API_KEY}
      AZURE_OPENAI_ENDPOINT: ${AZURE_OPENAI_ENDPOINT}
      AZURE_OPENAI_API_VERSION: ${AZURE_OPENAI_API_VERSION}
      AZURE_OPENAI_DEPLOYMENT_NAME: ${AZURE_OPENAI_DEPLOYMENT_NAME}
      CORS_ORIGINS: ${CORS_ORIGINS}
    ports:
      - "8000:8000"
    depends_on:
      - mongodb
    networks:
      - jira-organizer-network

  frontend:
    build:
      context: ./frontend
      args:
        REACT_APP_BACKEND_URL: ${BACKEND_URL}
    container_name: jira-organizer-frontend
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      - backend
    networks:
      - jira-organizer-network

volumes:
  mongodb_data:

networks:
  jira-organizer-network:
    driver: bridge
```

**Environment File** (`.env` in project root):
```env
# MongoDB
MONGO_USERNAME=admin
MONGO_PASSWORD=your_secure_password_here
DB_NAME=jira_organizer

# Azure OpenAI
AZURE_OPENAI_API_KEY=your_api_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4

# Backend
BACKEND_URL=https://api.yourdomain.com
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### 2. Deploy with Docker Compose

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Update and restart
docker-compose pull
docker-compose up -d --build
```

## Option 2: Manual Deployment

### Backend Deployment

#### Using systemd (Ubuntu/Debian)

1. **Install Python and dependencies**:
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv nginx
```

2. **Set up the application**:
```bash
cd /opt
sudo git clone https://github.com/Giacomo117/Jira-Organizer.git
cd Jira-Organizer/backend
sudo python3.11 -m venv venv
sudo venv/bin/pip install -r requirements.txt
```

3. **Create environment file**:
```bash
sudo nano /opt/Jira-Organizer/backend/.env
# Add your configuration
```

4. **Create systemd service** (`/etc/systemd/system/jira-organizer.service`):
```ini
[Unit]
Description=Jira Organizer Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/Jira-Organizer/backend
Environment="PATH=/opt/Jira-Organizer/backend/venv/bin"
ExecStart=/opt/Jira-Organizer/backend/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

5. **Enable and start service**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable jira-organizer
sudo systemctl start jira-organizer
sudo systemctl status jira-organizer
```

### Frontend Deployment

1. **Build the frontend**:
```bash
cd frontend
npm install
REACT_APP_BACKEND_URL=https://api.yourdomain.com npm run build
```

2. **Configure Nginx** (`/etc/nginx/sites-available/jira-organizer`):
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Frontend
    root /opt/Jira-Organizer/frontend/build;
    index index.html;

    # React Router support
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Backend API proxy
    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;

    # Gzip
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss application/rss+xml font/truetype font/opentype application/vnd.ms-fontobject image/svg+xml;
}
```

3. **Enable site and restart Nginx**:
```bash
sudo ln -s /etc/nginx/sites-available/jira-organizer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## SSL Certificate with Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
sudo systemctl reload nginx
```

## Cloud Platform Deployments

### Deploy to Azure

1. **Azure App Service (Backend)**:
```bash
az webapp up --runtime PYTHON:3.11 --sku B1 --name jira-organizer-api
az webapp config appsettings set --name jira-organizer-api --settings @backend/.env
```

2. **Azure Static Web Apps (Frontend)**:
```bash
cd frontend
npm install
npm run build
az staticwebapp create --name jira-organizer-frontend --resource-group myResourceGroup --source ./build
```

### Deploy to AWS

1. **Elastic Beanstalk (Backend)**:
```bash
eb init -p python-3.11 jira-organizer-api
eb create jira-organizer-prod
eb setenv AZURE_OPENAI_API_KEY=xxx MONGO_URL=xxx ...
eb deploy
```

2. **S3 + CloudFront (Frontend)**:
```bash
cd frontend
npm run build
aws s3 sync build/ s3://jira-organizer-frontend
aws cloudfront create-invalidation --distribution-id YOUR_DIST_ID --paths "/*"
```

### Deploy to Heroku

1. **Backend**:
```bash
cd backend
heroku create jira-organizer-api
heroku config:set AZURE_OPENAI_API_KEY=xxx MONGO_URL=xxx ...
git push heroku main
```

2. **Frontend** (Netlify/Vercel recommended for React apps)

## MongoDB Setup

### MongoDB Atlas (Recommended)

1. Create account at https://www.mongodb.com/cloud/atlas
2. Create a free cluster
3. Add your IP to IP whitelist (or 0.0.0.0/0 for all IPs)
4. Create a database user
5. Get connection string
6. Update `MONGO_URL` in your environment

### Self-hosted MongoDB

```bash
# Install MongoDB
sudo apt-get install mongodb-org

# Start MongoDB
sudo systemctl start mongod
sudo systemctl enable mongod

# Secure MongoDB
mongo
> use admin
> db.createUser({user: "admin", pwd: "secure_password", roles: ["root"]})

# Update mongod.conf to enable auth
sudo nano /etc/mongod.conf
# Add: security.authorization: enabled

sudo systemctl restart mongod
```

## Monitoring and Logging

### Application Logging

The backend logs to stdout/stderr. Capture logs with:

**Docker**:
```bash
docker-compose logs -f backend
```

**Systemd**:
```bash
sudo journalctl -u jira-organizer -f
```

### Monitor with Prometheus + Grafana

Add to your backend application:
```python
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import Response

request_count = Counter('requests_total', 'Total requests')
request_duration = Histogram('request_duration_seconds', 'Request duration')

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

## Backup Strategy

### MongoDB Backups

**Automated daily backups**:
```bash
#!/bin/bash
# backup-mongodb.sh
DATE=$(date +%Y%m%d_%H%M%S)
mongodump --uri="$MONGO_URL" --out="/backups/mongodb_$DATE"
# Keep only last 7 days
find /backups -name "mongodb_*" -mtime +7 -exec rm -rf {} \;
```

**Cron job**:
```bash
0 2 * * * /path/to/backup-mongodb.sh
```

### MongoDB Atlas Automated Backups

MongoDB Atlas automatically backs up your data continuously.

## Security Checklist

- [ ] Use HTTPS/SSL for all connections
- [ ] Store secrets in environment variables, not code
- [ ] Use strong passwords for MongoDB
- [ ] Enable MongoDB authentication
- [ ] Restrict MongoDB network access (IP whitelist)
- [ ] Keep dependencies updated (`pip list --outdated`)
- [ ] Set up firewall rules (only ports 80, 443 open)
- [ ] Enable rate limiting on API endpoints
- [ ] Monitor logs for suspicious activity
- [ ] Regular security audits
- [ ] Set up Azure Key Vault for secrets (production)

## Performance Optimization

1. **Enable caching**:
   - Cache Jira ticket data (Redis/Memcached)
   - Browser caching for static assets

2. **Database indexing**:
```javascript
db.meeting_analyses.createIndex({ "created_at": -1 })
db.meeting_analyses.createIndex({ "status": 1 })
db.jira_configs.createIndex({ "id": 1 }, { unique: true })
```

3. **CDN for frontend**:
   - Use CloudFlare, AWS CloudFront, or Azure CDN

4. **Horizontal scaling**:
   - Run multiple backend instances behind a load balancer

## Health Checks

Add health check endpoints:

```python
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/health/db")
async def db_health_check():
    try:
        await db.command('ping')
        return {"status": "healthy", "database": "connected"}
    except:
        raise HTTPException(status_code=503, detail="Database unavailable")
```

## Troubleshooting Production Issues

### High Memory Usage

- Check for memory leaks in Python
- Limit MongoDB connection pool
- Add memory limits to Docker containers

### Slow API Responses

- Enable APM (Application Performance Monitoring)
- Check database query performance
- Review Azure OpenAI response times
- Add caching layer

### Database Connection Issues

- Check network connectivity
- Verify MongoDB is running
- Check connection string
- Review MongoDB logs

## Cost Optimization

1. **MongoDB**: Use Atlas M0 (free tier) for testing, M10+ for production
2. **Azure OpenAI**: Monitor token usage, implement caching
3. **Hosting**: Start with small instances, scale as needed
4. **CDN**: Enable caching to reduce bandwidth costs

## Maintenance

### Regular Tasks

- **Weekly**: Review logs for errors
- **Monthly**: Update dependencies
- **Quarterly**: Review and optimize costs
- **Yearly**: Security audit

### Update Procedure

```bash
# Backup database
./backup-mongodb.sh

# Pull latest code
git pull origin main

# Update backend
cd backend
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart jira-organizer

# Update frontend
cd ../frontend
npm install
npm run build
```

## Rollback Procedure

```bash
# Revert to previous version
git checkout <previous-commit-hash>

# Restore database from backup
mongorestore --uri="$MONGO_URL" /backups/mongodb_YYYYMMDD_HHMMSS/

# Restart services
sudo systemctl restart jira-organizer
sudo systemctl restart nginx
```

---

For additional support or questions about deployment, please open an issue on GitHub.
