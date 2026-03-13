#!/bin/bash
# 自动部署脚本 - crypto-trading-open 到远程服务器

set -e  # 遇到错误立即退出

# 配置变量
SERVER_IP="8.216.39.214"
SERVER_USER="root"
SERVER_PATH="/www/wwwroot/crypto_grid"
LOCAL_PATH="."

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Crypto Trading Open - 自动部署${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 步骤1: 打包本地代码
echo -e "${YELLOW}[1/6] 打包代码...${NC}"
tar --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='venv' \
    --exclude='*.log' \
    --exclude='data/*.db' \
    --exclude='data/*.pkl' \
    --exclude='logs/*' \
    -czf /tmp/crypto_grid_deploy.tar.gz \
    -C "${LOCAL_PATH}" .

echo -e "${GREEN}✓ 代码打包完成${NC}"
echo ""

# 步骤2: 上传到服务器
echo -e "${YELLOW}[2/6] 上传代码到服务器...${NC}"
scp /tmp/crypto_grid_deploy.tar.gz ${SERVER_USER}@${SERVER_IP}:/tmp/

echo -e "${GREEN}✓ 上传完成${NC}"
echo ""

# 步骤3: SSH 登录并部署
echo -e "${YELLOW}[3/6] 解压代码到部署目录...${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
set -e

# 创建目录（如果不存在）
mkdir -p /www/wwwroot/crypto_grid
cd /www/wwwroot/crypto_grid

# 备份旧代码（如果存在）
if [ -f "web/app.py" ]; then
    echo "备份旧代码..."
    BACKUP_DIR="/www/wwwroot/crypto_grid_backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p ${BACKUP_DIR}
    cp -r . ${BACKUP_DIR}/
    echo "备份完成: ${BACKUP_DIR}"
fi

# 解压新代码
echo "解压代码..."
tar -xzf /tmp/crypto_grid_deploy.tar.gz -C /www/wwwroot/crypto_grid

# 设置权限
chmod +x /www/wwwroot/crypto_grid/*.py 2>/dev/null || true

echo "代码部署完成"
ENDSSH

echo -e "${GREEN}✓ 解压完成${NC}"
echo ""

# 步骤4: 安装依赖
echo -e "${YELLOW}[4/6] 安装 Python 依赖...${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
cd /www/wwwroot/crypto_grid

# 检查是否需要创建虚拟环境
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境并安装依赖
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "依赖安装完成"
ENDSSH

echo -e "${GREEN}✓ 依赖安装完成${NC}"
echo ""

# 步骤5: 配置环境变量
echo -e "${YELLOW}[5/6] 配置环境变量...${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
cd /www/wwwroot/crypto_grid

# 检查 .env 文件是否存在
if [ ! -f ".env" ]; then
    echo "警告: .env 文件不存在，请手动配置"
    echo "可以从 .env.example 复制并修改"
fi

ENDSSH

echo -e "${GREEN}✓ 环境变量检查完成${NC}"
echo ""

# 步骤6: 启动服务
echo -e "${YELLOW}[6/6] 启动 PM2 服务...${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
cd /www/wwwroot/crypto_grid

# 检查 PM2 是否安装
if ! command -v pm2 &> /dev/null; then
    echo "安装 PM2..."
    npm install -g pm2
fi

# 停止旧进程（如果存在）
pm2 stop crypto_grid 2>/dev/null || true
pm2 delete crypto_grid 2>/dev/null || true

# 使用虚拟环境中的 Python 启动
source venv/bin/activate
pm2 start ecosystem.config.json

# 保存 PM2 配置
pm2 save

echo "服务启动完成"
ENDSSH

echo -e "${GREEN}✓ 服务启动完成${NC}"
echo ""

# 显示访问信息
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  部署成功！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}访问地址:${NC}"
echo -e "  http://${SERVER_IP}:8000"
echo ""
echo -e "${YELLOW}常用命令:${NC}"
echo -e "  查看状态: ssh ${SERVER_USER}@${SERVER_IP} 'pm2 status crypto_grid'"
echo -e "  查看日志: ssh ${SERVER_USER}@${SERVER_IP} 'pm2 logs crypto_grid'"
echo -e "  重启服务: ssh ${SERVER_USER}@${SERVER_IP} 'pm2 restart crypto_grid'"
echo -e "  停止服务: ssh ${SERVER_USER}@${SERVER_IP} 'pm2 stop crypto_grid'"
echo ""
echo -e "${YELLOW}日志文件:${NC}"
echo -e "  /root/.pm2/logs/crypto_grid-out.log"
echo -e "  /root/.pm2/logs/crypto_grid-error.log"
echo ""

# 清理本地临时文件
rm -f /tmp/crypto_grid_deploy.tar.gz

echo -e "${GREEN}部署完成！${NC}"
