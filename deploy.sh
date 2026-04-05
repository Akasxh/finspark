#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "╔═══════════════════════════════════════╗"
echo "║   AdaptConfig — Railway Deployment    ║"
echo "╚═══════════════════════════════════════╝"
echo ""

# Step 1: Re-authenticate
echo "Step 1: Login to Railway..."
railway login
echo ""

# Step 2: Link project
echo "Step 2: Linking project..."
railway link 2>/dev/null || true
echo ""

# Step 3: Add PostgreSQL
echo "Step 3: Adding PostgreSQL database..."
railway add --database postgres || echo "Database may already exist"
echo ""

# Step 4: Set environment variables
echo "Step 4: Setting environment variables..."
SECRET_KEY=$(openssl rand -hex 32)

# Read Gemini key from .env
GEMINI_KEY=$(grep -E "^(FINSPARK_)?GEMINI_API_KEY=" .env 2>/dev/null | head -1 | cut -d= -f2)

railway variables set \
  APP_ENV=production \
  APP_DEBUG=false \
  "APP_SECRET_KEY=$SECRET_KEY" \
  GEMINI_MODEL=gemini-3-flash-preview \
  AI_ENABLED=true \
  "GEMINI_API_KEY=$GEMINI_KEY" \
  LOG_LEVEL=INFO \
  LOG_FORMAT=json \
  2>/dev/null || echo "Set variables manually in Railway dashboard"
echo ""

# Step 5: Deploy
echo "Step 5: Deploying backend..."
railway up --detach
echo ""

echo "╔═══════════════════════════════════════╗"
echo "║   Deployment initiated!               ║"
echo "║                                       ║"
echo "║   Check status: railway status        ║"
echo "║   View logs:    railway logs          ║"
echo "║   Open app:     railway open          ║"
echo "╚═══════════════════════════════════════╝"
