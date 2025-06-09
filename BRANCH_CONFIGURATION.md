# 🌿 Branch Configuration for Database Auto-Updates

## ✅ **CURRENT SETUP - Both Branches Supported!**

Your BarberQMS Backend now supports **automatic database migrations** on both branches:

### 🚀 **Production Environment**
- **Branch:** `main`
- **App Platform Config:** `app.yaml`
- **GitHub Actions:** ✅ Tests + Deployment trigger
- **Database Migrations:** ✅ Auto-run before deployment
- **Environment:** `production`

### 🧪 **Staging Environment** 
- **Branch:** `test-deploy`
- **App Platform Config:** `app-staging.yaml` (optional separate app)
- **GitHub Actions:** ✅ Tests + Deployment trigger
- **Database Migrations:** ✅ Auto-run before deployment
- **Environment:** `staging`

---

## 🔄 **Workflow Summary**

### For Production Deployment:
```bash
# 1. Develop and test locally
alembic revision --autogenerate -m "Add new feature"
alembic upgrade head

# 2. Deploy to staging first (optional)
git add .
git commit -m "Add new feature with migration"
git push origin test-deploy

# 3. Deploy to production
git checkout main
git merge test-deploy  # or cherry-pick specific commits
git push origin main
```

### For Quick Staging Deployment:
```bash
# Direct to staging
git add .
git commit -m "Test new feature"
git push origin test-deploy
```

---

## 🎯 **What Happens When You Push**

### Any push to `main` or `test-deploy`:

1. **GitHub Actions** (`.github/workflows/deploy.yml`):
   ✅ Runs tests with PostgreSQL  
   ✅ Linting and code quality checks  
   ✅ Triggers deployment notification  

2. **App Platform** (`app.yaml` or `app-staging.yaml`):
   ✅ Builds Docker container  
   ✅ Runs `alembic upgrade head` (PRE_DEPLOY job)  
   ✅ Deploys new app version if migration succeeds  
   ✅ Switches traffic to new version  
   ✅ Health check on `/ping` endpoint  

---

## 🏗️ **App Platform Options**

### Option 1: Single App (Current)
- **Production:** `app.yaml` → `main` branch
- **Staging:** Change `app.yaml` branch to `test-deploy` when needed

### Option 2: Separate Apps (Recommended)
- **Production App:** Use `app.yaml` → `main` branch
- **Staging App:** Use `app-staging.yaml` → `test-deploy` branch

To create staging app:
1. Go to [DigitalOcean Apps](https://cloud.digitalocean.com/apps)
2. Create new app from `app-staging.yaml`
3. Connect to `test-deploy` branch

---

## 🛡️ **Safety Features**

✅ **Automatic Rollback:** If migration fails, deployment stops  
✅ **Zero Downtime:** New version only receives traffic after health checks pass  
✅ **Database Backups:** Managed PostgreSQL creates automatic daily backups  
✅ **Health Monitoring:** `/ping` endpoint monitored every 10 seconds  

---

## 🔧 **Files Updated**

| File | Change |
|------|--------|
| `.github/workflows/deploy.yml` | ✅ Now triggers on both `main` and `test-deploy` |
| `app.yaml` | ✅ Updated to use `main` branch for production |
| `app-staging.yaml` | ✅ NEW - Staging configuration using `test-deploy` |
| `DEPLOYMENT.md` | ✅ Updated with branch strategy |

---

## 🎉 **Result**

**Before:** Only `test-deploy` had auto-migrations  
**After:** Both `main` and `test-deploy` have auto-migrations  

Now you can:
- Push to `test-deploy` for staging/testing
- Push to `main` for production deployment  
- Get automatic database migrations on both branches
- Have separate environments with different databases 