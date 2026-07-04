# Ubuntu Server Deployment Guide

This guide provides instructions for deploying the **Live Translation Backend** (via Docker Compose) and the **React Frontend** (via host Nginx) on a clean Ubuntu Server.

---

## 📋 Prerequisites

Install the required packages on your Ubuntu Server:

```bash
# Update repositories
sudo apt update && sudo apt upgrade -y

# Install Docker
sudo apt install apt-transport-https ca-certificates curl software-properties-common -y
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io -y

# Enable and start Docker service
sudo systemctl enable docker
sudo systemctl start docker

# Add your user to the docker group (to run docker without sudo)
sudo usermod -aG docker $USER
# Log out and log back in for group changes to take effect!

# Install Nginx & Git
sudo apt install nginx git -y
```

---

## 🛠️ Step 1: Deploy the FastAPI Backend

1. **Clone the Backend Repository**:
   ```bash
   git clone https://github.com/vaisakhpv033/live-translation-backend.git /opt/live-translation-backend
   cd /opt/live-translation-backend
   ```

2. **Configure Environment Variables**:
   Create a `.env` file in `/opt/live-translation-backend`:
   ```bash
   nano .env
   ```
   Add your credentials matching the translation worker:
   ```env
   LIVEKIT_URL=wss://your-project.livekit.cloud
   LIVEKIT_API_KEY=your_api_key
   LIVEKIT_API_SECRET=your_api_secret
   PORT=8000
   ALLOWED_ORIGINS=https://your-domain.com,http://localhost:3000,http://localhost:5173
   ```

3. **Start the Backend Container**:
   Build and start the container in detached mode:
   ```bash
   docker compose up -d --build
   ```
   Verify that it is running successfully:
   ```bash
   docker ps
   # Check logs:
   docker logs translation-backend
   ```

---

## 🎨 Step 2: Deploy the React Frontend

1. **Build the Frontend locally** (on your development machine):
   Make sure you create an `.env` file in the frontend project root:
   ```env
   VITE_BACKEND_URL=https://your-domain.com
   VITE_LIVEKIT_URL=wss://your-project.livekit.cloud
   ```
   Compile the production assets:
   ```bash
   npm run build
   ```
   This will generate a `dist/` directory containing optimized HTML, CSS, and JS.

2. **Upload static files to Ubuntu Server**:
   Compress and upload the files to your server (replace `<server-ip>` with your host IP):
   ```bash
   # Create target directory on server
   ssh user@<server-ip> "sudo mkdir -p /var/www/translation-agent-frontend && sudo chown -R $USER:$USER /var/www/translation-agent-frontend"

   # Transfer dist contents
   scp -r dist/* user@<server-ip>:/var/www/translation-agent-frontend/
   ```

---

## 🌐 Step 3: Configure Host Nginx

1. **Add Site Configuration**:
   Copy the `nginx.conf` file from the backend repository to Nginx configuration files:
   ```bash
   sudo cp /opt/live-translation-backend/nginx.conf /etc/nginx/sites-available/translation-agent
   ```

2. **Edit Domain Name**:
   Update `server_name` with your domain:
   ```bash
   sudo nano /etc/nginx/sites-available/translation-agent
   # Change: server_name _; 
   # To: server_name your-domain.com;
   ```

3. **Enable Site & Restart Nginx**:
   ```bash
   # Enable the site configuration link
   sudo ln -s /etc/nginx/sites-available/translation-agent /etc/nginx/sites-enabled/

   # Remove default configuration if present to avoid conflicts
   sudo rm /etc/nginx/sites-enabled/default

   # Test Nginx syntax
   sudo nginx -t

   # Reload Nginx config
   sudo systemctl restart nginx
   ```

---

## 🔒 Step 4: Setup SSL Certificates (Certbot)

To secure WebRTC signaling and microphone permission requests, HTTPS is **strictly required** by browsers.

1. **Install Certbot**:
   ```bash
   sudo apt install snapd -y
   sudo snap install core; sudo snap refresh core
   sudo snap install --classic certbot
   sudo ln -s /snap/bin/certbot /usr/bin/certbot
   ```

2. **Acquire SSL Certificate**:
   Let Certbot automatically adjust Nginx rules for SSL redirection:
   ```bash
   sudo certbot --nginx -d your-domain.com
   ```
   Follow the prompts. Nginx will restart automatically and serve HTTPS.

---

## ⚡ Step 5: Configure LiveKit Webhooks

To receive status reports when calls are finished or users connect, set up Webhooks in your **LiveKit Console**:

1. Go to your **LiveKit Cloud Console** (or self-hosted admin panel).
2. Navigate to **Webhooks** section.
3. Click **Add Webhook**.
4. Enter the Endpoint URL:
   `https://your-domain.com/api/v1/webhooks`
5. Select events to listen to:
   * `room_started`
   * `room_finished`
   * `participant_joined`
   * `participant_left`
6. Click **Save**.
