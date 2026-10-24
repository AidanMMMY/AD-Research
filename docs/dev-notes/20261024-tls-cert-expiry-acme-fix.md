# 2026-10-24 TLS 证书过期致全站断访事故 + acme.sh 自动续期上线

## 事故

- **现象**：用户报「admin 登录不了」。实际是全站 HTTPS 不可用——
  浏览器被证书错误页拦死，登录页根本打不开。
- **根因**：阿里云免费 DV 证书（DigiCert Encryption Everywhere，
  90 天期）2026-07-03 手动安装，**2026-09-30 到期**，已过期 24 天。
  服务器上没有任何续期机制（无 acme.sh / certbot / cron）。
  这是 SSL 第二次咬人（第一次：2026-08-18 游离 ssl 目录 +
  私钥在 git 的 CRITICAL 陷阱）。
- **排查路径**（以后照抄）：本地 curl HTTP 000 → 容器全绿 →
  ECS 本机 curl 公网域名也 000 → `curl -sv` 看 TLS 握手 →
  `SSL certificate verify result: certificate has expired (10)`。
  口诀：**登录不了先别查账号，curl -sv 看证书。**

## 修复：acme.sh + Let's Encrypt（永久解决）

```bash
# 1. webroot 预热：nginx.conf 的 80 端口 server 块早已预留
#    location /.well-known/ { alias /etc/nginx/ssl/.well-known/; }
#    宿主机映射 /data/alloy-research/ssl -> /etc/nginx/ssl
mkdir -p /data/alloy-research/ssl/.well-known/acme-challenge

# 2. 坑 1：/data/alloy-research/ssl 是 drwx------(501)，nginx worker
#    (uid 101) 无法穿越 → 403。chmod 711（可穿越、不可列举、私钥安全）
chmod 711 /data/alloy-research/ssl

# 3. 安装 acme.sh（自带续期 cron）
curl https://get.acme.sh | sh -s email=admin@alloyresearch.net

# 4. 签发。坑 2：-w webroot 会被 acme.sh 自己拼上
#    /.well-known/acme-challenge——传 /data/alloy-research/ssl/.well-known
#    会写出双重目录 .../.well-known/.well-known/... 致 LE 404。
#    正确：-w /data/alloy-research/ssl
/root/.acme.sh/acme.sh --issue --server letsencrypt \
  -d www.alloyresearch.net -d alloyresearch.net \
  -w /data/alloy-research/ssl -k 2048

# 5. 安装 + reload 钩子（旧证书先备份成 .expired-20260930.bak）
/root/.acme.sh/acme.sh --install-cert -d www.alloyresearch.net \
  --fullchain-file /data/alloy-research/ssl/www.alloyresearch.net.pem \
  --key-file /data/alloy-research/ssl/www.alloyresearch.net.key \
  --reloadcmd "docker exec alloyresearch-nginx nginx -s reload"
```

- 续期：acme.sh cron 已自动安装（`25 5,11,17,23 * * *`），
   Let's Encrypt 90 天期，ARI 建议窗口 2026-12-23 前后，续期后
  自动跑 reloadcmd reload nginx。**无需再人工干预。**
- 阿里云控制台的免费证书流程从此废弃（每 90 天手动重签的模式
  已经咬了两次）。

## 验证

- `https://www.alloyresearch.net/health` 全绿（db/redis/scheduler/
  data/llm 全 ok，git_sha 023f98e）
- 登录接口对错误密码正确返回 401——接口从未坏过
- 证书链：Let's Encrypt R10/R11，有效期至 2027-01 下旬

## 遗留

- 若用户之后仍报密码错误，走 `docs/dev-notes/20260701-admin-password-reset-runbook.md`
  （docker exec 重置，禁止裸 SQL UPDATE password_hash）。
- 旧证书备份 `.expired-20260930.bak` / `.key.bak` 留在
  /data/alloy-research/ssl/，确认无回滚需要后可删。
- site_watchdog 目前只拨测 HTTP 层，建议加「证书剩余天数 < 14 天」
  告警（acme.sh 已兜底，告警是第二道保险）。
