#!/bin/bash
# 快速部署 - 只更新代码并重启（不重新安装依赖）

SERVER_IP="8.216.39.214"
SERVER_USER="root"

echo "打包代码..."
tar --exclude='node_modules' --exclude='__pycache__' --exclude='.git' --exclude='venv' --exclude='*.log' --exclude='data/*.db' --exclude='data/*.pkl' \
    -czf /tmp/crypto_grid_update.tar.gz .

echo "上传到服务器..."
scp /tmp/crypto_grid_update.tar.gz ${SERVER_USER}@${SERVER_IP}:/tmp/

echo "更新代码..."
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
cd /www/wwwroot/crypto_grid
tar -xzf /tmp/crypto_grid_update.tar.gz
ENDSSH

echo "重启服务..."
ssh ${SERVER_USER}@${SERVER_IP} 'pm2 restart crypto_grid'

echo "✓ 快速部署完成！"
echo "访问: http://${SERVER_IP}:8000"
