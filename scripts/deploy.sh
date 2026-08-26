#!/bin/bash
# ================================================================
# deploy.sh — Run this on your EC2 instance to set up Aurora
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
# ================================================================

set -e  # exit on any error

echo "Installing Docker..."
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git curl

# Add ubuntu user to docker group (no sudo needed)
sudo usermod -aG docker ubuntu
newgrp docker

echo "Cloning Aurora..."
git clone https://github.com/Parth-Dhola/aurora.git
cd aurora

echo "Setting up .env..."
cp .env.example .env
echo ""
echo "IMPORTANT: Edit .env now and add your GEMINI_API_KEY and SECRET_KEY"
echo "Run: nano .env"
echo ""
read -p "Press Enter after editing .env..."

echo "Starting Aurora..."
docker compose up -d --build

echo ""
echo "Aurora is running!"
echo "Backend: http://$(curl -s ifconfig.me):8000"
echo "API docs: http://$(curl -s ifconfig.me):8000/docs"
echo "MLflow: http://$(curl -s ifconfig.me):5001"

echo "Installing Nginx..."
sudo apt install -y nginx certbot python3-certbot-nginx
sudo cp nginx.conf /etc/nginx/sites-available/aurora
sudo ln -sf /etc/nginx/sites-available/aurora /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

echo "Done! Aurora is deployed."
