# 阿里云 ECS 部署手册（小白版）

本手册面向没有服务器运维经验的同学，一步一步教你把 **AD-Research** 平台部署到阿里云 ECS 云服务器上。

只要照着做，一般 15～30 分钟就能完成。

---

## 目录

1. [部署前你需要准备什么](#一部署前你需要准备什么)
2. [第一步：购买阿里云 ECS 服务器](#二第一步购买阿里云-ecs-服务器)
3. [第二步：配置安全组（放行端口）](#三第二步配置安全组放行端口)
4. [第三步：连接你的服务器](#四第三步连接你的服务器)
5. [第四步：把代码传到服务器](#五第四步把代码传到服务器)
6. [第五步：运行一键部署脚本](#六第五步运行一键部署脚本)
7. [第六步：访问平台](#七第六步访问平台)
8. [第七步：配置 Tushare Token（重要）](#八第七步配置-tushare-token重要)
9. [日常运维命令](#九日常运维命令)
10. [常见问题排查](#十常见问题排查)
11. [安全建议](#十一安全建议)
12. [备份建议](#十二备份建议)

---

## 一、部署前你需要准备什么

### 1.1 必备条件

- [ ] 一个阿里云账号（并完成实名认证）
- [ ] 一台可以上网的电脑（Mac 或 Windows 都行）
- [ ] 你的本地已经能运行 Git 命令（如果不会，下面会教）

### 1.2 大概要花多少钱

按本手册推荐的配置，阿里云 ECS 首年大约 **100～300 元**（取决于活动和地域）。如果你只是测试，可以随时释放实例，按量付费更便宜。

### 1.3 需要准备的数据

- [ ] **Tushare Pro Token**（可选但强烈建议）
  - 这是获取中国 A 股数据的 API Token
  - 没有它，平台能启动，但很多数据功能无法使用
  - 获取方式：访问 https://tushare.pro 注册并获取 Token

---

## 二、第一步：购买阿里云 ECS 服务器

### 2.1 进入 ECS 控制台

1. 打开阿里云官网：https://www.aliyun.com
2. 登录你的账号
3. 在顶部搜索框输入 **"云服务器 ECS"**，点击进入

### 2.2 点击创建实例

在 ECS 控制台页面，找到 **"创建实例"** 按钮，点击进入购买页面。

### 2.3 选择配置（按下面表格选）

| 配置项 | 推荐选择 | 说明 |
|--------|----------|------|
| **计费方式** | 按量付费 或 包年包月 | 测试选按量付费，长期使用选包年包月 |
| **地域** | 华东 1（杭州）或 华东 2（上海） | 离你和数据源越近越好 |
| **实例规格** | `ecs.c7.large` 或 `ecs.u1-c1m2.large` | 2 核 4G，够用了 |
| **镜像** | **Ubuntu 24.04 LTS**（推荐）<br>或 Ubuntu 26.04 / Alibaba Cloud Linux 3 | 本项目已在 **Ubuntu 24.04 LTS** 上充分测试；<br>Ubuntu 26.04 也可用，部署脚本会自动兼容 Docker 仓库 |
| **系统盘** | 40GB ESSD | 系统和 Docker 镜像 |
| **数据盘** | 100GB ESSD（可选但建议） | 放数据库数据，更安全 |
| **公网 IP** | 勾选分配公网 IPv4 地址 | 否则你无法访问 |
| **带宽** | 按量付费，5 Mbps | 初期够用 |
| **登录方式** | 密码登录 或 密钥对登录 | 新手建议选密码登录，记得保存密码 |

> **预算有限怎么办？** 可以选 `ecs.t6-c1m1.large`（1 核 2G），但只建议体验和测试，正式使用会卡。

### 2.4 确认订单并创建

1. 检查配置无误后，点击 **"立即购买"** 或 **"确认订单"**
2. 支付完成后，等待 1～2 分钟，实例状态变成 **"运行中"**
3. 在实例列表中，找到你的服务器，记录下 **公网 IP**（类似 `47.xxx.xxx.xxx`）

---

## 三、第二步：配置安全组（放行端口）

安全组是阿里云的防火墙，默认只放行 22 端口（SSH）。我们需要放行 8000 端口，才能通过浏览器访问平台。

### 3.1 找到安全组配置

1. 在 ECS 控制台，点击你的实例名称
2. 左侧菜单找到 **"安全组"**，点击
3. 点击 **"管理规则"** 或 **"配置规则"**

### 3.2 添加放行规则

点击 **"手动添加"** 或 **"添加安全组规则"**，添加以下规则：

| 类型 | 端口范围 | 授权对象 | 描述 |
|------|----------|----------|------|
| 自定义 TCP | 8000 | 0.0.0.0/0 | AD-Research 平台访问端口 |
| 自定义 TCP | 22 | 你的本地 IP/32 | SSH 远程连接（更安全） |

> `0.0.0.0/0` 表示允许任何 IP 访问。如果你有自己的固定 IP，建议把授权对象改成你的 IP，更安全。

### 3.3 保存规则

点击 **"保存"** 或 **"确认"**。

---

## 四、第三步：连接你的服务器

### 4.1 Mac 用户

打开 **终端（Terminal）**，输入：

```bash
ssh root@你的服务器公网IP
```

例如：

```bash
ssh root@47.239.13.111
```

第一次连接会提示：

```text
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

输入 `yes` 回车，然后输入你设置的密码（密码不会显示，直接输完回车）。

### 4.2 Windows 用户

Windows 10/11 自带 SSH，打开 **PowerShell** 或 **命令提示符**，输入：

```bash
ssh root@你的服务器公网IP
```

如果提示没有 ssh 命令，可以下载 [PuTTY](https://www.putty.org/) 或使用 Windows Terminal。

### 4.3 连接成功后的样子

看到类似下面的提示，说明连接成功：

```text
Welcome to Alibaba Cloud Elastic Compute Service !
[root@iZbp1xxxxxx ~]#
```

---

## 五、第四步：把代码传到服务器

### 方式一：用 Git 克隆（推荐，最简单）

#### 5.1.1 在服务器上安装 Git

连接服务器后，根据系统选择命令：

**Alibaba Cloud Linux / CentOS：**

```bash
yum install -y git
```

**Ubuntu（包括 Ubuntu 24.04 / 26.04）：**

```bash
apt-get update
apt-get install -y git
```

> 如果你用的是 **Ubuntu 26.04**，系统刚创建时可能提示找不到某些包，先执行一次 `apt-get update` 即可解决。

#### 5.1.2 克隆代码

```bash
cd /opt
git clone 你的代码仓库地址 ad-research
```

例如：

```bash
cd /opt
git clone https://github.com/yourname/ad-research.git ad-research
```

#### 5.1.3 进入项目目录

```bash
cd ad-research
```

### 方式二：用 zip 上传（不会 Git 就用这个）

#### 5.2.1 在本地打包代码

1. 在你的电脑上，打开终端/命令行
2. 进入项目文件夹
3. 执行：

```bash
zip -r ad-research.zip . -x "*.git*" -x "node_modules/*" -x ".venv/*" -x "web/node_modules/*"
```

#### 5.2.2 上传到服务器

**Mac/Linux：**

```bash
scp ad-research.zip root@你的服务器公网IP:/opt/
```

**Windows：**

用 WinSCP 或 Xftp 等工具上传 `/opt/` 目录。

#### 5.2.3 在服务器上解压

```bash
cd /opt
unzip ad-research.zip -d ad-research
cd ad-research
```

---

## 六、第五步：运行一键部署脚本

### 6.1 进入部署目录

```bash
cd /opt/ad-research/deploy/aliyun-ecs
```

### 6.2 给脚本执行权限

```bash
chmod +x deploy.sh
```

### 6.3 运行部署脚本

```bash
./deploy.sh
```

> **Ubuntu 26.04 用户注意：**
> Docker 官方暂未提供 Ubuntu 26.04 (plucky) 的专属仓库，部署脚本会自动临时使用 Ubuntu 24.04 (noble) 的仓库来安装 Docker。这是安全的，已经验证可用。如果你希望更稳妥，也可以在购买 ECS 时直接选择 **Ubuntu 24.04 LTS**。

### 6.4 脚本会做什么

运行后，脚本会自动完成以下事情：

1. **安装 Docker**（如果还没装）
2. **安装 Docker Compose 插件**（随 Docker 一起安装）
3. **生成 .env 文件**（从 .env.example 复制，并自动生成强密码）
4. **构建 Docker 镜像**（包含前端和后端）
5. **启动 PostgreSQL 和 Redis**
6. **执行数据库迁移**（创建表结构）
7. **初始化管理员账号**（在数据库中创建 `admin` 用户，仅首次执行）
8. **启动后端服务**
9. **健康检查**（确认服务正常）

### 6.5 过程中可能需要你输入

脚本生成 `.env` 文件后，会显示自动生成的管理员密码，并停下来让你按回车继续。**请务必把这个密码记下来**，这是你第一次登录后台的密码。

### 6.6 部署成功后的输出

如果一切正常，你会看到类似输出：

```text
[INFO] ✅ 部署成功！
[INFO] 访问地址：http://47.239.13.111:8000
[INFO] API 文档：http://47.239.13.111:8000/docs
[INFO] 健康检查：http://47.239.13.111:8000/health
```

---

## 七、第六步：访问平台

### 7.1 用浏览器打开

把脚本输出的地址复制到浏览器：

```text
http://你的服务器公网IP:8000
```

例如：

```text
http://47.239.13.111:8000
```

### 7.2 登录

- 用户名：`admin`（默认管理员账号，可在 `.env` 中通过 `AUTH_ADMIN_USERNAME` 修改）
- 密码：部署脚本显示的那个密码（在 `.env` 文件里也能看到 `AUTH_ADMIN_PASSWORD`）

登录后，你可以在左侧菜单的 **"管理员用户管理"** 页面创建、启用/禁用或重置其他用户的密码。

### 7.3 如果打不开怎么办

先不要着急，跳到 [第十步：常见问题排查](#十常见问题排查)。

---

## 八、第七步：配置 Tushare Token（重要）

平台启动后已经可以使用了，但如果要做中国 A 股的数据分析，必须配置 Tushare Token。

### 8.1 编辑 .env 文件

```bash
vim /opt/ad-research/deploy/aliyun-ecs/.env
```

### 8.2 找到 TUSHARE_TOKEN 并修改

```bash
TUSHARE_TOKEN=your_tushare_token_here
```

改成你从 Tushare 获取的真实 Token：

```bash
TUSHARE_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 8.3 保存并退出

- 按 `Esc` 键
- 输入 `:wq` 回车

### 8.4 重启服务让配置生效

```bash
cd /opt/ad-research/deploy/aliyun-ecs
docker compose restart backend
```

---

## 九、日常运维命令

以下命令都需要先进入部署目录：

```bash
cd /opt/ad-research/deploy/aliyun-ecs
```

### 9.1 查看服务状态

```bash
docker compose ps
```

### 9.2 查看后端日志

```bash
docker compose logs -f backend
```

按 `Ctrl + C` 退出日志查看。

### 9.3 查看数据库日志

```bash
docker compose logs -f postgres
```

### 9.4 重启所有服务

```bash
docker compose restart
```

### 9.5 停止所有服务（保留数据）

```bash
docker compose down
```

### 9.6 完全停止并删除数据（⚠️ 慎用）

```bash
docker compose down -v
```

### 9.7 更新代码后重新部署

```bash
cd /opt/ad-research
git pull  # 如果用 Git
cd deploy/aliyun-ecs
docker compose down
docker compose build --no-cache
docker compose up -d
```

> **注意：** 更新后 `backend` 容器启动时会自动执行数据库迁移。如果更新涉及用户表变更，或你想重新初始化管理员账号，可以手动执行：
>
> ```bash
> docker compose run --rm backend python scripts/seed_users.py
> ```
>
> 该命令是幂等的：如果 `admin` 用户已存在则跳过，不会重复创建。

---

## 十、常见问题排查

### Q1：浏览器访问 `http://IP:8000` 打不开

**检查清单：**

1. 服务是否真的启动了？
   ```bash
   docker compose ps
   ```
   应该看到 `etf-backend`、`etf-postgres`、`etf-redis` 都是 `running`。

2. 安全组是否放行了 8000 端口？
   - 回到阿里云控制台 → ECS → 安全组 → 确认有 8000 端口的规则

3. 防火墙是否拦截？
   ```bash
   systemctl stop firewalld
   ```
   （仅临时测试，确认后建议重新开启并放行 8000）

4. 后端服务是否健康？
   ```bash
   curl http://localhost:8000/health
   ```
   在服务器上执行，应该返回 `{"status":"ok"...}`。

### Q2：部署脚本提示 "源数据库 etf_research 不存在"

这是正常的。说明你是全新部署，没有旧数据需要迁移。脚本会自动创建 `ad_research` 数据库。

### Q3：部署脚本提示 "未检测到 docker compose 插件"

这种情况很少见，如果发生，手动安装：

```bash
mkdir -p ~/.docker/cli-plugins
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose
```

然后重新运行 `./deploy.sh`。

### Q4：忘记管理员密码

查看 `.env` 文件：

```bash
cat /opt/ad-research/deploy/aliyun-ecs/.env | grep AUTH_ADMIN_PASSWORD
```

如果要修改，编辑 `.env` 文件后重启 backend：

```bash
docker compose restart backend
```

### Q5：如何查看平台日志找错误

```bash
cd /opt/ad-research/deploy/aliyun-ecs
docker compose logs -f backend
```

看到红色 `ERROR` 字样，把错误信息复制给我，我帮你排查。

### Q6：服务器重启后平台没自动启动

正常情况下容器设置了 `restart: unless-stopped`，重启服务器后会自动启动。如果没有，手动执行：

```bash
cd /opt/ad-research/deploy/aliyun-ecs
docker compose up -d
```

---

## 十一、安全建议

平台现在是 HTTP + IP 访问，虽然方便但不安全。正式使用前建议：

1. **修改默认密码**
   - 部署后尽快修改 `AUTH_ADMIN_PASSWORD`
   - 修改 `AUTH_SECRET_KEY`（脚本已自动生成，通常不用改）

2. **限制安全组**
   - 不要把 22 端口放行给 `0.0.0.0/0`
   - 只放行你自己的 IP

3. **后续升级 HTTPS**
   - 购买域名并解析到 ECS IP
   - 安装 Nginx + SSL 证书
   - 这是另一个话题，需要时我可以单独写手册

4. **数据库独立化**
   - 正式上线后，建议把 PostgreSQL 迁到阿里云 RDS
   - Redis 迁到阿里云云数据库 Redis

---

## 十二、备份建议

当前数据库数据存在 Docker Volume 里，虽然方便但不如云盘安全。建议：

### 12.1 定期备份数据库

```bash
cd /opt/ad-research/deploy/aliyun-ecs
docker compose exec postgres pg_dump -U etf -d ad_research > /opt/ad-research-backup-$(date +%Y%m%d).sql
```

### 12.2 下载备份到本地

**Mac/Linux：**

```bash
scp root@你的服务器公网IP:/opt/ad-research-backup-20260623.sql ./
```

**Windows：** 用 WinSCP 下载。

### 12.3 为 ECS 挂载独立数据盘

如果还没买，可以在阿里云控制台为 ECS 挂载一块数据盘，并把数据库 volume 放在数据盘上。具体操作可以问我。

---

## 附录：文件说明

```
deploy/aliyun-ecs/
├── docker-compose.yml   # 生产环境 Docker 编排配置
├── .env.example         # 环境变量模板
├── deploy.sh            # 一键部署脚本
└── README.md            # 本手册
```

如果你在任何一步卡住，把报错信息复制发给我，我会继续帮你解决。
