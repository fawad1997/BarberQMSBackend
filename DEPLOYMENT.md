# 🚀 Deployment Guide for BarberQMS Backend on DigitalOcean App Platform

This guide explains how to deploy your FastAPI application to **DigitalOcean App Platform** with automated CI/CD and database migrations.

## 📋 Prerequisites

- GitHub repository with your FastAPI code
- DigitalOcean account
- DigitalOcean API token (for optional advanced features)

## 🎯 App Platform vs Droplets

You're using **DigitalOcean App Platform** (not Droplets), which means:
- ✅ **No server management** - DigitalOcean handles infrastructure
- ✅ **Built-in CI/CD** - Automatic deployments from GitHub
- ✅ **Managed database integration** - Easy PostgreSQL setup
- ✅ **Auto-scaling** - Handles traffic spikes automatically
- ✅ **Zero downtime deployments** - Seamless updates

## 📁 Required Files in Your Repository

Ensure you have these files (already created for you):

```
BarberQMSBackend/
├── Dockerfile                    # ✅ Created - App Platform container config
├── app.yaml                      # ✅ Created - App Platform specification
├── .github/workflows/deploy.yml  # ✅ Created - GitHub Actions for testing
├── requirements.txt              # ✅ Updated - Python dependencies
├── alembic/env.py                # ✅ Configured - Reads DATABASE_URL
├── main.py                       # ✅ Has /health endpoint
└── ... your FastAPI app files
```

## 🚀 Step-by-Step Deployment

### Step 1: Prepare Your Repository

1. **Commit all files:**
   ```bash
   git add .
   git commit -m "Prepare for App Platform deployment"
   git push origin test-deploy
   ```

### Step 2: Create DigitalOcean App

1. **Go to DigitalOcean Dashboard:**
   - Navigate to [DigitalOcean Apps](https://cloud.digitalocean.com/apps)
   - Click "Create App"

2. **Connect GitHub:**
   - Select "GitHub" as source
   - Authorize DigitalOcean to access your repositories
   - Choose your `BarberQMSBackend` repository
   - Select branch: `test-deploy`

3. **Choose Deployment Method:**
   - **Option A: Use app.yaml (Recommended)**
     - Check "Use app spec" when configuring
     - App Platform will read your `app.yaml` file
   - **Option B: Manual Configuration**
     - Continue with UI-based setup

### Step 3: Configure Your App (Option A: Using app.yaml)

1. **Update app.yaml:**
   - Open `app.yaml` in your repository
   - Replace `YOUR_GITHUB_USERNAME/BarberQMSBackend` with your actual GitHub repo path
   - Commit and push changes

2. **App Platform will:**
   - Create a PostgreSQL database
   - Set up the migration job
   - Configure the web service
   - Connect everything automatically

### Step 3 Alternative: Manual Configuration (Option B)

If you prefer manual setup:

1. **Database Setup:**
   - App Platform detects your need for PostgreSQL
   - Create a new Managed Database or connect existing one
   - Note: DATABASE_URL will be automatically provided

2. **Service Configuration:**
   - **Name:** `barber-qms-backend`
   - **Run Command:** `alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8080`
   - **HTTP Port:** `8080`
   - **Health Check Path:** `/health`

3. **Environment Variables:**
   Add these in the App Platform UI:
   ```
   DATABASE_URL: ${db.DATABASE_URL}  # Auto-provided if using DO Managed DB
   ENVIRONMENT: production
   SECRET_KEY: your_secret_key_here
   JWT_SECRET_KEY: your_jwt_secret_here
   ```

### Step 4: Optional GitHub Secrets

For advanced features, add these GitHub secrets:

| Secret Name | Description | Required |
|-------------|-------------|----------|
| `DO_TOKEN` | Your DigitalOcean API token | Optional |
| `DO_APP_ID` | Your App Platform app ID | Optional |

**To find your App ID:**
1. Go to your app in DigitalOcean dashboard
2. Look at the URL: `https://cloud.digitalocean.com/apps/{APP_ID}`

### Step 5: Deploy!

1. **Automatic Deployment:**
   - App Platform automatically deploys when you push to `test-deploy`
   - Monitor deployment in the DigitalOcean dashboard

2. **Deployment Process:**
   ```
   GitHub Push → App Platform detects change → 
   Build Docker image → Run migration job → 
   Deploy new version → Health check → 
   Switch traffic to new version
   ```

## 🔄 Your Development Workflow

### Making Changes:

1. **Develop locally:**
   ```bash
   # Make model changes
   alembic revision --autogenerate -m "Add new feature"
   alembic upgrade head  # Test locally
   ```

2. **Deploy to production:**
   ```bash
   git add .
   git commit -m "Add new feature with migration"
   git push origin test-deploy
   ```

3. **App Platform automatically:**
   - Builds your app
   - Runs `alembic upgrade head` (migration job)
   - Deploys new version if migration succeeds
   - Switches traffic to new version

## 🏥 Monitoring and Health Checks

### App Platform Dashboard:
- **Deployments:** Track deployment history and status
- **Runtime Logs:** View application and migration logs  
- **Metrics:** Monitor CPU, memory, and response times
- **Health Checks:** Uses your `/health` endpoint

### Checking Status:
```bash
# Your app URL (provided by App Platform)
curl https://your-app-name.ondigitalocean.app/health

# Response should be:
{
  "status": "healthy",
  "timestamp": "2025-01-09T...",
  "environment": "production",
  "version": "1.0.0"
}
```

## 🛠️ Troubleshooting

### Common Issues:

1. **Migration Fails:**
   - Check Runtime Logs in App Platform dashboard
   - Migration job logs show Alembic errors
   - Fix migration script and push again

2. **App Won't Start:**
   - Check if health check endpoint is accessible
   - Verify environment variables are set correctly
   - Check Python import errors in logs

3. **Database Connection Issues:**
   - Verify DATABASE_URL is properly set
   - Check if managed database is in same region
   - Ensure database credentials are correct

### Useful Commands:

```bash
# View app info via API (if you have DO_TOKEN)
curl -X GET \
  -H "Authorization: Bearer YOUR_DO_TOKEN" \
  "https://api.digitalocean.com/v2/apps/YOUR_APP_ID"

# Trigger manual deployment
curl -X POST \
  -H "Authorization: Bearer YOUR_DO_TOKEN" \
  "https://api.digitalocean.com/v2/apps/YOUR_APP_ID/deployments"
```

## 💡 Pro Tips

1. **Environment-based Deployments:**
   - Use `test-deploy` branch for staging
   - Use `main` branch for production
   - Create separate apps for different environments

2. **Database Backups:**
   - DigitalOcean Managed Database automatically creates daily backups
   - Create manual snapshots before major migrations

3. **Scaling:**
   - Increase instance size/count in App Platform dashboard
   - App Platform can auto-scale based on traffic

4. **Custom Domains:**
   - Add your domain in App Platform dashboard
   - App Platform provides free SSL certificates

## 🎉 Success!

Once deployed, your app will be available at:
- **App Platform URL:** `https://your-app-name.ondigitalocean.app`
- **Health Check:** `https://your-app-name.ondigitalocean.app/health`
- **Dashboard:** [DigitalOcean Apps Dashboard](https://cloud.digitalocean.com/apps)

### What You've Achieved:

✅ **Zero-downtime deployments** with automatic rollback on failure  
✅ **Automatic database migrations** before each deployment  
✅ **Health monitoring** with built-in checks  
✅ **Scalable infrastructure** managed by DigitalOcean  
✅ **CI/CD pipeline** triggered by GitHub pushes  

---

🎯 **No more manual SSH, no more broken deployments!** Every push to `test-deploy` automatically updates your production app with proper database migrations. 