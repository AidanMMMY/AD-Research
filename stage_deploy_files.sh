#!/bin/bash
set -e
cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform

# Stage all new deployment files
git add app/services/deployment_service.py
git add app/api/v1/deployments.py
git add app/schemas/deployment.py
git add web/src/types/deployment.ts
git add web/src/api/deployments.ts
git add web/src/hooks/useDeployments.ts
git add web/src/pages/AdminDeployments/index.tsx

# Stage all modified files
git add deploy/aliyun-ecs/docker-compose.yml
git add deploy/aliyun-ecs/nginx.conf
git add .env.example
git add app/config.py
git add app/main.py
git add web/src/api/index.ts
git add web/src/components/AppLayout.tsx
git add web/src/routes.tsx

echo "Staged files:"
git diff --cached --name-only
