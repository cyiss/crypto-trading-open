# Crypto Trading Open - 服务器部署手册

## 📋 服务器信息

- **IP地址**: 8.216.39.214
- **用户名**: root
- **部署路径**: /www/wwwroot/crypto_grid
- **进程名**: crypto_grid
- **Web端口**: 8000

---

## 🚀 方式1: 自动部署（从本地执行）

### 前置条件
确保你的本地机器可以SSH到服务器：
```bash
# 测试连接
ssh root@8.216.39.214

# 如果需要密码，配置SSH密钥
ssh-copy-id root@8.216.39.214
```

### 执行部署
```bash
# 首次部署（完整安装）
./deploy.sh

# 后续更新（快速部署）
./quick-deploy.sh
```

---

## 🛠️ 方式2: 手动部署（在服务器上执行）

### 步骤1: SSH登录服务器
```bash
ssh root@8.216.39.214
```

### 步骤2: 克隆代码
```bash
# 创建目录
mkdir -p /www/wwwroot/crypto_grid
cd /www/wwwroot/crypto_grid

# 克隆代码（首次部署）
git clone -b dev_best https://github.com/cyiss/crypto-trading-open.git .

# 或者更新代码（已有代码）
git pull origin dev_best
```

### 步骤3: 配置环境变量
```bash
# 创建 .env 文件（从模板复制）
cp env.template .env

# 编辑 .env 文件，填入你的 Lighter 交易所配置
nano .env
# 或
vi .env

# 确保包含以下配置：
```

**.env 文件内容（Lighter交易所配置）**:
```bash
# Lighter 交易所配置
LIGHTER_URL=https://mainnet.zklighter.elliot.ai
LIGHTER_WS_URL=wss://mainnet.zklighter.elliot.ai/stream
LIGHTER_ACCOUNT_INDEX=281474976641659
LIGHTER_PRIVATE_KEY=896cf4cb6cdc1247999adb542bffc875bedea34844c52b4f1ba4f1e947e76166cedecc25e0321c10
LIGHTER_API_INDEX=2
LIGHTER_L1_ADDRESS=0x139A68A8Ec299d9377bDc35f8Fc3058788F66101

# 市场配置
MARKET_INDEX=1
MARKET_SYMBOL=BTC

# Dashboard API密钥（已内置默认值，可选配置）
DASHBOARD_API_KEY=internal-grid-ops-6f9b2d4e91c84a6d
GRID_MODEL_SIGNING_KEY=internal-grid-sign-2d1f7a8c3e4b95d0

# 日志配置
LOG_LEVEL=INFO
```

### 步骤4: 安装依赖
```bash
cd /www/wwwroot/crypto_grid

# 创建虚拟环境（推荐）
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt
```

### 步骤5: 配置PM2
```bash
# 安装 PM2（如果未安装）
npm install -g pm2

# 或使用 yarn
yarn global add pm2

# 启动服务（使用虚拟环境）
cd /www/wwwroot/crypto_grid
source venv/bin/activate
pm2 start ecosystem.config.json

# 保存PM2配置
pm2 save

# 设置开机自启
pm2 startup
```

### 步骤6: 验证服务
```bash
# 查看进程状态
pm2 status

# 查看日志
pm2 logs crypto_grid

# 实时查看日志
pm2 logs crypto_grid --lines 100

# 查看错误日志
tail -f /root/.pm2/logs/crypto_grid-error.log

# 查看输出日志
tail -f /root/.pm2/logs/crypto_grid-out.log
```

---

## 🌐 访问Web Dashboard

部署成功后，访问以下地址：

```
http://8.216.39.214:8000
```

### Dashboard功能页面

1. **主页** - 实时扫描排名
   ```
   http://8.216.39.214:8000/
   ```

2. **扫描器历史** - 历史记录查询
   ```
   http://8.216.39.214:8000/scanner
   ```

3. **网格绩效** - 网格交易绩效分析
   ```
   http://8.216.39.214:8000/performance
   ```

4. **自动交易** - 自动网格启动器状态
   ```
   http://8.216.39.214:8000/auto-trading
   ```

---

## 📊 运行完整系统（可选）

如果需要同时运行扫描器和训练ML模型：

### 启动扫描器
```bash
# SSH登录服务器
ssh root@8.216.39.214

cd /www/wwwroot/crypto_grid
source venv/bin/activate

# 启动扫描器（带Web持久化）
nohup python grid_volatility_scanner/run_scanner.py --web --exchange lighter > logs/scanner.log 2>&1 &

# 或使用 screen
screen -S grid_scanner
python grid_volatility_scanner/run_scanner.py --web --exchange lighter
# 按 Ctrl+A+D 分离会话
```

### 训练ML模型
```bash
cd /www/wwwroot/crypto_grid
source venv/bin/activate

# 训练模型
python scripts/train_grid_param_model.py --db data/grid_scanner.db
```

---

## 🔧 常用运维命令

### PM2 管理
```bash
# 查看状态
pm2 status crypto_grid

# 重启服务
pm2 restart crypto_grid

# 停止服务
pm2 stop crypto_grid

# 删除服务
pm2 delete crypto_grid

# 查看日志
pm2 logs crypto_grid

# 监控
pm2 monit
```

### 系统监控
```bash
# 检查端口
netstat -tlnp | grep 8000

# 检查进程
ps aux | grep "web/app.py"

# 查看系统资源
htop
```

### 数据库管理
```bash
cd /www/wwwroot/crypto_grid

# 查看数据库
sqlite3 data/grid_scanner.db

# 查询最新扫描记录
sqlite3 data/grid_scanner.db "SELECT * FROM scanner_snapshots ORDER BY scan_time DESC LIMIT 10;"

# 清理7天前的数据（自动执行，也可手动）
sqlite3 data/grid_scanner.db "DELETE FROM scanner_snapshots WHERE scan_time < datetime('now', '-7 days');"
```

---

## 🔄 更新部署

### 快速更新（只更新代码）
```bash
# 本地执行
./quick-deploy.sh

# 或在服务器上执行
ssh root@8.216.39.214
cd /www/wwwroot/crypto_grid
git pull origin dev_best
pm2 restart crypto_grid
```

### 完整更新（包括依赖）
```bash
ssh root@8.216.39.214
cd /www/wwwroot/crypto_grid
git pull origin dev_best
source venv/bin/activate
pip install -r requirements.txt
pm2 restart crypto_grid
```

---

## 🐛 故障排查

### 问题1: 服务无法启动
```bash
# 查看错误日志
pm2 logs crypto_grid --err

# 手动启动测试
cd /www/wwwroot/crypto_grid
source venv/bin/activate
python web/app.py --host 0.0.0.0 --port 8000
```

### 问题2: 端口被占用
```bash
# 查看端口占用
lsof -i :8000

# 杀掉占用进程
kill -9 <PID>

# 重启服务
pm2 restart crypto_grid
```

### 问题3: 依赖安装失败
```bash
# 清理缓存重装
cd /www/wwwroot/crypto_grid
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir
```

### 问题4: 数据库锁定
```bash
# 检查是否有多个进程连接
lsof data/grid_scanner.db

# 如果有，杀掉多余进程
kill -9 <PID>

# 重启服务
pm2 restart crypto_grid
```

---

## 🛡️ 安全配置（生产环境）

### 1. 配置防火墙
```bash
# 只允许特定IP访问
ufw allow from 你的IP to any port 22
ufw allow from 你的IP to any port 8000
ufw enable

# 或使用 iptables
iptables -A INPUT -p tcp --dport 8000 -s 你的IP -j ACCEPT
iptables -A INPUT -p tcp --dport 8000 -j DROP
```

### 2. 配置Nginx反向代理（推荐）
```bash
# 安装 Nginx
apt install nginx -y

# 配置反向代理
nano /etc/nginx/sites-available/crypto_grid
```

配置内容：
```nginx
server {
    listen 80;
    server_name your-domain.com;  # 或直接用 8.216.39.214

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用配置：
```bash
ln -s /etc/nginx/sites-available/crypto_grid /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx
```

### 3. 配置HTTPS（可选）
```bash
# 安装 Certbot
apt install certbot python3-certbot-nginx -y

# 获取证书
certbot --nginx -d your-domain.com

# 自动续期
certbot renew --dry-run
```

---

## 📝 日志文件位置

```
PM2 日志:
  /root/.pm2/logs/crypto_grid-out.log    # 标准输出
  /root/.pm2/logs/crypto_grid-error.log  # 错误日志

扫描器日志:
  /www/wwwroot/crypto_grid/logs/grid_scanner_main_*.log
  /www/wwwroot/crypto_grid/logs/grid_scanner_BTC_*.log

数据库:
  /www/wwwroot/crypto_grid/data/grid_scanner.db

ML模型:
  /www/wwwroot/crypto_grid/data/grid_param_model.pkl
```

---

## ✅ 部署检查清单

- [ ] SSH 登录服务器成功
- [ ] 代码克隆/更新成功
- [ ] .env 文件配置正确
- [ ] Python 依赖安装成功
- [ ] PM2 启动成功
- [ ] 访问 http://8.216.39.214:8000 正常
- [ ] Dashboard 页面正常显示
- [ ] 日志无错误信息
- [ ] （可选）扫描器启动成功
- [ ] （可选）ML模型训练成功

---

## 📞 访问地址汇总

| 功能 | 地址 |
|------|------|
| **Web Dashboard** | http://8.216.39.214:8000 |
| 主页 | http://8.216.39.214:8000/ |
| 扫描器历史 | http://8.216.39.214:8000/scanner |
| 网格绩效 | http://8.216.39.214:8000/performance |
| 自动交易 | http://8.216.39.214:8000/auto-trading |
| API文档 | http://8.216.39.214:8000/docs |

---

**部署完成后，请告诉我访问情况，我可以帮你进一步优化配置！**
