# 罗德岛凯尔希对话终端
> 基于DeepSeek大模型的高还原度明日方舟同人角色扮演系统

[![GitHub](https://img.shields.io/badge/GitHub-shengshengbuxi000/Rhodes__chat-blue?logo=github)](https://github.com/shengshengbuxi000/Rhodes_chat)
[![Gitee](https://img.shields.io/badge/Gitee-liu--dongjing/kaltsit--chatting-red?logo=gitee)](https://gitee.com/liu-dongjing/kaltsit-chatting)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-yellow.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2+-green.svg)](https://www.djangoproject.com/)

## 📖 项目介绍
本项目是一个垂直领域的AI角色扮演对话系统，深度还原明日方舟核心角色"凯尔希"的性格、语气和行为模式。采用轻量的前后端分离架构，无需复杂配置，10分钟即可完成部署，为粉丝提供沉浸式的AI对话体验。

## ✨ 功能特性
- 🎭 **多场景角色扮演**：支持3个预设场景（办公室·晚宴后/汐斯塔度假/办公室·手术后）+ 自定义场景
- 🤖 **高还原度对话**：基于DeepSeek V4 flash大模型，精心设计的提示词工程，OOC率<5%
- 📝 **完整的对话记录管理**：支持下载/导入/回档/清空全生命周期操作
- 🔒 **无登录体系**：基于Cookie的用户身份识别，打开网页即可使用
- 🚀 **轻量易部署**：单文件前端+Django后端，支持Linux/Windows/macOS全平台
- 🌐 **完全开源**：双仓库同步更新，MIT协议，无任何商业限制
- 📱 **移动端完美适配**：已修复iOS Safari底部网址栏遮挡、灵动岛遮挡等问题

## 🚀 快速部署（5分钟本地启动）
### 1. 环境准备
- Python 3.8 或更高版本
- DeepSeek API 密钥（[免费申请地址](https://platform.deepseek.com/)）

### 2. 克隆项目
```bash
# GitHub
git clone https://github.com/shengshengbuxi000/Rhodes_chat.git

# Gitee（国内推荐）
git clone https://gitee.com/liu-dongjing/kaltsit-chatting.git

cd Rhodes_chat
```

### 3. 安装依赖
```bash
# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Linux/macOS
source venv/bin/activate
# Windows
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 4. 配置API密钥
在项目根目录创建`.env`文件，写入你的DeepSeek API密钥：
```env
DEEPSEEK_API_KEY=你的DeepSeek API密钥
```

### 5. 初始化数据库
```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. 启动开发服务器
```bash
python manage.py runserver 0.0.0.0:8000
```

### 7. 访问系统
打开浏览器访问：`http://localhost:8000`，即可开始使用。

## 🖥️ 生产环境部署（Ubuntu 22.04）
### 1. 服务器基础环境准备
```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装必要工具
sudo apt install python3 python3-pip python3-venv nginx git -y
```

### 2. 部署项目
```bash
# 克隆项目到服务器
cd /home/ubuntu
git clone https://github.com/shengshengbuxi000/Rhodes_chat.git
cd Rhodes_chat

# 创建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn  # 生产环境WSGI服务器

# 配置API密钥
echo "DEEPSEEK_API_KEY=你的DeepSeek API密钥" > .env

# 初始化数据库
python manage.py makemigrations
python manage.py migrate

# 收集静态文件
python manage.py collectstatic --noinput
```

### 3. 配置Gunicorn系统服务
创建系统服务文件：
```bash
sudo nano /etc/systemd/system/rhodes-chat.service
```

写入以下内容：
```ini
[Unit]
Description=Rhodes Chat Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Rhodes_chat
ExecStart=/home/ubuntu/Rhodes_chat/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 Rhodes_chat.wsgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动并设置开机自启：
```bash
sudo systemctl daemon-reload
sudo systemctl start rhodes-chat
sudo systemctl enable rhodes-chat

# 验证服务状态
sudo systemctl status rhodes-chat
```

### 4. 配置Nginx反向代理
创建Nginx配置文件：
```bash
sudo nano /etc/nginx/sites-available/rhodes-chat
```

写入以下内容：
```nginx
server {
    listen 80;
    server_name 你的域名或服务器IP;

    # 静态文件直接由Nginx处理，不经过Python应用
    location /static/ {
        alias /home/ubuntu/Rhodes_chat/static/;
        expires 30d;
    }

    # 所有其他请求转发给Gunicorn
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用配置并重启Nginx：
```bash
sudo ln -s /etc/nginx/sites-available/rhodes-chat /etc/nginx/sites-enabled/
sudo nginx -t  # 验证配置
sudo systemctl restart nginx
```

### 5. 配置HTTPS（可选，推荐）
使用Certbot自动配置免费SSL证书：
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d 你的域名
```

### 6. 开放防火墙端口
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

现在你可以通过`https://你的域名`访问系统了。

## ⚙️ 配置说明
### 核心配置文件
- `.env`：存储敏感信息（API密钥等）
- `kaltsit_prompts.py`：所有提示词配置（角色性格、场景描述等）
- `Rhodes_chat/settings.py`：Django全局配置

### 常用配置项
| 配置项 | 文件 | 说明 | 默认值 |
|--------|------|------|--------|
| `DEEPSEEK_API_KEY` | `.env` | DeepSeek API密钥 | 无 |
| `MODEL_NAME` | `kaltsit_chat/views.py` | 使用的大模型 | `deepseek-v4-pro` |
| `TEMPERATURE` | `kaltsit_chat/views.py` | 模型随机性 | `0.85` |
| `MAX_TOKENS` | `kaltsit_chat/views.py` | 最大生成长度 | `2000` |

### 修改提示词
所有角色和场景提示词都在`kaltsit_prompts.py`文件中，直接修改对应的字典值即可，无需重启服务即可生效。

## 📂 项目结构
```
Rhodes_chat/
├── kaltsit_chat/              # 核心应用目录
│   ├── __init__.py
│   ├── models.py              # 数据库模型
│   ├── views.py               # 接口视图
│   ├── urls.py                # URL路由
│   └── apps.py
├── static/                    # 静态文件目录
│   └── index.html             # 前端单页面
├── templates/                 # Django模板目录（未使用）
├── kaltsit_prompts.py         # 提示词配置文件
├── manage.py                  # Django管理脚本
├── requirements.txt           # 依赖列表
├── .env.example               # 环境变量示例
├── .gitignore                 # Git忽略文件
└── README.md                  # 本文件
```

## ❓ 常见问题
### 1. 启动时提示"Invalid API Key"
检查`.env`文件中的`DEEPSEEK_API_KEY`是否正确，确保没有多余的空格或换行。

### 2. 访问时出现502 Bad Gateway
- 检查Gunicorn服务是否正常运行：`sudo systemctl status rhodes-chat`
- 查看Gunicorn日志：`sudo journalctl -u rhodes-chat -n 50`
- 检查Nginx配置是否正确：`sudo nginx -t`

### 3. iOS端顶部按钮栏被遮挡
已在最新版本中通过`100dvh`和安全区适配修复，更新到最新代码即可。

### 4. 点击发送按钮会发送两条消息
已在最新版本中通过事件去重绑定和前置防抖修复，更新到最新代码即可。

### 5. 如何切换回DeepSeek V4 Flash模型
修改`kaltsit_chat/views.py`中的`MODEL_NAME`为`deepseek-v4-flash`，然后重启服务。

## 🤝 贡献指南
欢迎提交Issue和Pull Request来改进这个项目：
1. Fork 本仓库
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的修改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开一个Pull Request

## 📄 许可证
本项目采用 [MIT 许可证](LICENSE) 开源，你可以自由使用、修改和分发本项目的代码。

## 🙏 致谢
- [DeepSeek](https://www.deepseek.com/) 提供强大的大模型API
- 明日方舟官方提供的角色设定和世界观
- 所有为本项目贡献代码和提出建议的开发者

---

如果这个项目对你有帮助，欢迎给个Star ⭐ 支持一下！