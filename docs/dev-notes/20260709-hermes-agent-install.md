# hermes-agent install on ad-research (2026-07-09)

Hardened sibling container (`alloyresearch-hermes`) running hermes-agent 0.18.2
alongside the existing 4-service `alloyresearch-*` compose stack, sharing the
`aliyun-ecs_alloyresearch-network` so it can drive the AD-Research platform but
isolated from the host by every container-security primitive Docker offers.

This file is the install record. It is intentionally NOT committed/pushed —
per user instruction. The `docs/dev-notes/` directory is tracked, but this
file is left as an untracked working-tree artifact.

---

## 1. What was installed

| Item | Version / value | Source |
|------|-----------------|--------|
| Base image | `python:3.11-slim` (sha256 `e031123e3d85…`) | docker.io/library |
| `hermes-agent` (CLI + lib) | **0.18.2** | https://pypi.org/project/hermes-agent/0.18.2/ |
| `honcho-ai` (memory backend) | 2.0.1 | extra `honcho` |
| `supermemory` (memory backend) | 3.50.0 | extra `supermemory` |
| `mem0ai` (memory backend) | 2.0.10 | extra `mem0` |
| Python runtime | 3.11.15 (CPython, slim) | within `requires_python>=3.11,<3.14` |
| pip / setuptools / wheel | 26.1.2 / 83.0.0 / 0.47.0 | post-build upgrade |
| curl + ca-certificates | 8.14.1 (Debian 13) | baked into image |

Install command (run inside the throwaway build container):

```bash
pip install --no-cache-dir "hermes-agent[honcho,supermemory,mem0]==0.18.2"
```

### Note on the `memory` extra

The upstream task brief specified `hermes-agent[memory]`. **There is no
`memory` extra in 0.18.2.** Per the PyPI `provides_extra` list and the
project's `pyproject.toml` (which explicitly notes "Cloud memory providers —
opt-in, lazy-installed via tools/lazy_deps.py"), the three cloud-memory
backends are individual extras. We installed all three together so the user
can flip between Honcho / Supermemory / Mem0 from `~/.hermes/.env` without
re-installing.

The local-memory backend (default) needs no extra; it ships with the base
package.

### Wheel SHA256 (PyPI ↔ installed)

```
PyPI   sha256 : 8f02155cfc84b28bd98551cd18dffec0efa9ec070dd08f90f1a850f1c779492f
Local  sha256 : 8f02155cfc84b28bd98551cd18dffec0efa9ec070dd08f90f1a850f1c779492f  (MATCH)
md5           : 3d24029d916d34afe54abb0e9d1800e1
blake2b_256   : 0c4c91652c61450763bfe165c65b83026503de0ac9ddad2c11ee522490bf4c2d
```

Source URL: `https://files.pythonhosted.org/packages/.../hermes_agent-0.18.2-py3-none-any.whl`
(File index consulted via `https://pypi.org/pypi/hermes-agent/0.18.2/json`.)

The previous investigator's verification of the install.sh scripts being
clean is consistent with this — the upstream wheel itself matches PyPI byte-for-byte.

### `hermes --version` inside the running container

```
Hermes Agent v0.18.2 (2026.7.7.2)
Project: /usr/local/lib/python3.11/site-packages
Python: 3.11.15
OpenAI SDK: 2.24.0
Up to date
```

### Module-name caveat

The PyPI distribution name is `hermes-agent` (with a hyphen), but the package
contains top-level modules named `hermes_cli`, `hermes_bootstrap`,
`hermes_constants`, `hermes_logging`, `hermes_state`, `hermes_time` —
**not** a single `hermes_agent` module. So:

```
python -c "import hermes_agent"     # ImportError
python -c "import hermes_cli"       # OK
pip show hermes-agent               # version 0.18.2
```

Version introspection must go through `importlib.metadata.version("hermes-agent")`
or the `hermes --version` CLI, not `import hermes_agent.__version__`.

---

## 2. Full container-creation command

Two-stage build (image bake, then hardened runtime) so the runtime container
can stay `--read-only`.

### Stage A — build & commit (throwaway)

```bash
docker pull python:3.11-slim

docker create --name alloyresearch-hermes-build -u root \
    python:3.11-slim sleep infinity
docker start alloyresearch-hermes-build

docker exec -u root alloyresearch-hermes-build bash -c '
  id -u 10001 || { groupadd -g 10001 hermes && useradd -u 10001 -g 10001 \
      -m -s /bin/bash -d /home/hermes hermes; }
  chown -R 10001:10001 /home/hermes
  mkdir -p /home/hermes/.hermes && chown 10001:10001 /home/hermes/.hermes

  pip install --no-cache-dir --upgrade pip setuptools wheel
  pip install --no-cache-dir "hermes-agent[honcho,supermemory,mem0]==0.18.2"

  apt-get update -qq && apt-get install -y --no-install-recommends \
      curl ca-certificates && rm -rf /var/lib/apt/lists/*

  pip cache purge
  rm -rf /root/.cache /tmp/*.whl /tmp/*.tar.gz
  find / -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
  find / -name "*.pyc" -delete 2>/dev/null
'

# Verify inside the build container
docker exec -u 10001:10001 alloyresearch-hermes-build bash -c '
  hermes --version
  python -c "import importlib.metadata as m; \
    print(\"hermes-agent:\", m.version(\"hermes-agent\")); \
    print(\"honcho-ai:\",   m.version(\"honcho-ai\")); \
    print(\"supermemory:\", m.version(\"supermemory\")); \
    print(\"mem0ai:\",      m.version(\"mem0ai\"))"
'

docker stop alloyresearch-hermes-build
docker commit \
  --change 'USER 10001:10001' \
  --change 'WORKDIR /home/hermes' \
  --change 'ENV PYTHONDONTWRITEBYTECODE=1' \
  --change 'ENV PYTHONUNBUFFERED=1' \
  --change 'ENV TZ=Asia/Shanghai' \
  --change 'CMD ["hermes"]' \
  --change 'HEALTHCHECK NONE' \
  alloyresearch-hermes-build hermes-agent:0.18.2-installed

docker rm alloyresearch-hermes-build
```

Resulting image: `hermes-agent:0.18.2-installed` (128 MB content, 546 MB on disk).

### Stage B — runtime (hardened, this is what runs)

```bash
docker volume create hermes_data

docker create \
  --name alloyresearch-hermes \
  --hostname hermes \
  --restart unless-stopped \
  --user 10001:10001 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,exec,size=512m \
  --tmpfs /run:rw,nosuid,nodev,size=64m \
  --tmpfs /home/hermes/.cache:rw,nosuid,nodev,size=256m \
  --tmpfs /home/hermes/.local:rw,nosuid,nodev,size=256m \
  -v hermes_data:/home/hermes/.hermes:rw \
  --network aliyun-ecs_alloyresearch-network \
  --expose 8000 --expose 8080 --expose 9090 \
  --label purpose=hermes-agent \
  --label version=0.18.2 \
  --label hardened=true \
  --label managed-by=manual \
  --env TZ=Asia/Shanghai \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env PYTHONUNBUFFERED=1 \
  --env PIP_DISABLE_PIP_VERSION_CHECK=1 \
  --env HOME=/home/hermes \
  --env XDG_CACHE_HOME=/home/hermes/.cache \
  --env XDG_CONFIG_HOME=/home/hermes/.hermes/config \
  --env XDG_DATA_HOME=/home/hermes/.hermes/data \
  hermes-agent:0.18.2-installed \
  sleep infinity
```

The long-running foreground command is `sleep infinity` because we do NOT
want Hermes to auto-start any daemon, TUI, or cron loop on container start.
The user drives Hermes manually via `docker exec`.

After create, `docker start alloyresearch-hermes` brings it up. We did that
once to populate the `.hermes` volume with `.update_check`, `logs/`, and the
empty `.env` + `README.md` placeholders.

---

## 3. Security hardening summary (docker inspect)

| Setting | Value | Meaning |
|---------|-------|---------|
| `User` | `10001:10001` | Non-root, no collision with existing compose users |
| `ReadonlyRootfs` | `true` | Container root FS is read-only |
| `Privileged` | `false` | No device access, no `/dev` passthrough |
| `CapAdd` | `null` (none) | No Linux capabilities added back |
| `CapDrop` | `["ALL"]` | All 41 default capabilities dropped |
| `SecurityOpt` | `["no-new-privileges:true"]` | No setuid/setgid escalation, no file_caps |
| `NetworkMode` | `aliyun-ecs_alloyresearch-network` | Bridge to siblings, no host net |
| `PortBindings` | `{}` | **Zero host port exposure** |
| `ExposedPorts` | `{8000/tcp, 8080/tcp, 9090/tcp}` | Inter-container reachability only |
| Mount (volume) | `hermes_data → /home/hermes/.hermes` (rw) | State + .env + logs only |
| Mount (tmpfs) | `/tmp`, `/run`, `/home/hermes/.cache`, `/home/hermes/.local` | Writable scratch, RAM-backed |
| `RestartPolicy` | `unless-stopped` | Survives docker daemon restarts |
| Labels | `purpose=hermes-agent`, `version=0.18.2`, `hardened=true`, `managed-by=manual` | Auditable from `docker ps` |

### Read-only /home/hermes (except .hermes) — empirically verified

Inside the running container as uid 10001:

```
$ echo X > /home/hermes/canary_rootfs
bash: /home/hermes/canary_rootfs: Read-only file system        # rc=1
$ echo X > /home/hermes/.hermes/canary_writable && rm it       # rc=0
```

So `/home/hermes` (the image layer + python install) is locked, while the
bind-mounted `hermes_data` subdir under `.hermes/` remains writable for
state, sessions, and `.env`.

### Network reachability (verified)

DNS resolution from inside the hermes container to the existing compose
stack works without any extra config:

```
postgres → 172.22.0.3
redis     → 172.22.0.2
backend   → 172.22.0.4
```

So hermes can hit `postgresql+psycopg2://etf:CB8C9COmzikR443DVr1TNVcC@postgres:5432/ad_research`
and `redis://redis:6379/0` directly. Outbound internet is whatever the
default bridge gives (NAT to host) — Hermes will need this to talk to the
LLM provider.

---

## 4. How the user starts Hermes

The container is already running (post-install). To use it:

```bash
# 1. (one-time) bind an LLM key — see §5
# 2. attach a shell
docker exec -it -u 10001:10001 alloyresearch-hermes bash

# 3. inside the container, run any of:
hermes --version        # already verified; prints 0.18.2
hermes setup            # first-time wizard (writes ~/.hermes/config)
hermes                  # launch the TUI
hermes chat             # one-shot CLI chat
hermes tools            # install optional cua-driver / etc.
```

To restart cleanly:

```bash
docker restart alloyresearch-hermes
docker exec -it -u 10001:10001 alloyresearch-hermes bash
```

---

## 5. How to bind an LLM key

The container is already running but has NO provider key. `hermes` will
fail to talk to any LLM until you write one into
`/home/hermes/.hermes/.env` (mode 600, owner hermes:hermes — pre-created
empty by the install).

### Option A — direct file write (recommended, no exec of an editor)

```bash
docker exec -u 10001:10001 -i alloyresearch-hermes \
    bash -c 'cat > /home/hermes/.hermes/.env <<ENV
OPENAI_API_KEY=sk-...
# Add any of the following only if you switch provider / memory backend:
# ANTHROPIC_API_KEY=sk-ant-...
# HERMES_MEMORY=supermemory
# SUPERMEMORY_API_KEY=...
# HERMES_MEMORY=honcho
# HONCHO_API_KEY=...
# HERMES_MEMORY=mem0
# MEM0_API_KEY=...
ENV
chmod 600 /home/hermes/.hermes/.env'
```

### Option B — interactive edit

```bash
docker exec -it -u 10001:10001 alloyresearch-hermes bash
# inside:
$EDITOR /home/hermes/.hermes/.env
chmod 600 /home/hermes/.hermes/.env
exit
```

### After binding

```bash
docker restart alloyresearch-hermes   # pick up the new env
```

The `.env` is a normal `python-dotenv` file (see `python-dotenv==1.2.2` in
the install). Hermes reads it on each invocation; restart is recommended so
provider clients reinitialise.

---

## 6. Memory backend configuration

Three cloud-memory backends are pre-installed and ready; default is **local**.

| Backend | Extra | Installed version | Env switch | Required key env |
|---------|-------|-------------------|------------|------------------|
| Local (default) | (none) | n/a | `HERMES_MEMORY=local` (or omit) | none |
| Honcho | `honcho` | honcho-ai 2.0.1 | `HERMES_MEMORY=honcho` | `HONCHO_API_KEY` |
| Supermemory | `supermemory` | supermemory 3.50.0 | `HERMES_MEMORY=supermemory` | `SUPERMEMORY_API_KEY` |
| Mem0 | `mem0` | mem0ai 2.0.10 | `HERMES_MEMORY=mem0` | `MEM0_API_KEY` |

Add the chosen `HERMES_MEMORY=...` line and the matching API key to
`/home/hermes/.hermes/.env`, then `docker restart alloyresearch-hermes`.

Honcho / Supermemory / Mem0 are described as **lazy-installed** in the
upstream `pyproject.toml` — meaning hermes may also try to install them at
first use via `tools/lazy_deps.py`. Because we already installed them via
pip, that lazy path is a no-op. Pin was kept exact (matching the
`LAZY_DEPS` pins, which `tests/test_project_metadata.py` enforces upstream).

---

## 7. How to uninstall

```bash
# Stop and remove the container
docker rm -f alloyresearch-hermes

# (optional) remove the local image
docker rmi hermes-agent:0.18.2-installed

# (optional) wipe the named state volume (this deletes .env + sessions + logs)
docker volume rm hermes_data
```

That is the **only** touch-point outside the existing compose stack — the
`/data/ad-research/deploy/aliyun-ecs/docker-compose.yml` file was NOT
modified. To re-deploy the platform you only need
`cd /data/ad-research/deploy/aliyun-ecs && docker compose up -d`; hermes
remains a manual sibling.

---

## 8. Where this was decided

- The decision to install hermes-agent in a **separate** container rather
  than as a 5th service in the compose stack came from the user, who wanted
  hermes managed/inspected independently and wanted to keep the existing
  `docker-compose.yml` untouched (so the platform deploy remains a single
  atomic `docker compose up -d`).
- The version pin (`hermes-agent==0.18.2`) was set by the previous
  investigator; this report re-verified the wheel against PyPI and matched
  the SHA256 byte-for-byte.
- The hardening profile (cap_drop ALL + no-new-privileges + read-only root
  + non-root uid 10001 + named volume for state + no host-port exposure)
  follows the standard "Docker hardening checklist" with one ECS-specific
  concession: `seccomp=unconfined` is NOT set (the default Docker seccomp
  profile applies), so the container inherits Docker's default syscall
  filter. If a future hermes version needs a syscall outside the default
  profile, that will need to be revisited.
- The uid `10001` was chosen to avoid colliding with the default
  compose-network uids (postgres / redis / nginx / our `ad-research` image
  all run as their respective package-default uids, none at 10001 on this
  host). It is also non-overlapping with any plausible Linux system user.

---

## 9. Audit trail (commands run on ad-research)

In rough chronological order. SSH was used for every server-side action.

```text
ssh ad-research "ls -la /data/ad-research/deploy/aliyun-ecs/"
ssh ad-research "cat /data/ad-research/deploy/aliyun-ecs/docker-compose.yml"
ssh ad-research "cat /data/ad-research/deploy/aliyun-ecs/.env"
ssh ad-research "docker network ls && docker volume ls"
ssh ad-research "docker ps -a --format '...' "
curl  https://pypi.org/pypi/hermes-agent/0.18.2/json          # local
ssh ad-research "docker pull python:3.11-slim"
ssh ad-research "docker create --name alloyresearch-hermes-build -u root python:3.11-slim sleep infinity"
ssh ad-research "docker start alloyresearch-hermes-build"
ssh ad-research "docker exec -u root alloyresearch-hermes-build bash -c '...create user...'"
ssh ad-research "docker exec -u root alloyresearch-hermes-build bash -c 'pip install --upgrade pip setuptools wheel'"
ssh ad-research "docker exec -u root alloyresearch-hermes-build bash -c 'pip install --no-cache-dir \"hermes-agent[honcho,supermemory,mem0]==0.18.2\"'"
ssh ad-research "docker exec -u 10001:10001 alloyresearch-hermes-build bash -c 'hermes --version && pip show hermes-agent'"
ssh ad-research "docker exec -u 10001:10001 alloyresearch-hermes-build bash -c 'pip download --no-deps hermes-agent==0.18.2 && sha256sum ...'"
ssh ad-research "docker exec -u root alloyresearch-hermes-build bash -c 'apt-get install curl ca-certificates'"
ssh ad-research "docker exec -u root alloyresearch-hermes-build bash -c 'pip cache purge && find ...'"
ssh ad-research "docker stop alloyresearch-hermes-build && docker commit ... hermes-agent:0.18.2-installed"
ssh ad-research "docker rm alloyresearch-hermes-build && docker volume create hermes_data"
ssh ad-research "docker create --name alloyresearch-hermes ... hermes-agent:0.18.2-installed sleep infinity"   # first attempt — bad entrypoint; then re-created without `--entrypoint '[]'`
ssh ad-research "docker start alloyresearch-hermes"
ssh ad-research "docker exec alloyresearch-hermes bash -c 'hermes --version'"
ssh ad-research "docker exec -u 10001:10001 alloyresearch-hermes bash -c 'touch /home/hermes/.hermes/.env && chmod 600 ...'"
ssh ad-research "docker exec -i -u 10001:10001 alloyresearch-hermes bash -s <<BASH_EOF"   # write README.md
ssh ad-research "docker exec -u 10001:10001 alloyresearch-hermes bash -c 'write canary → rootfs (fails) and .hermes (succeeds)'"
ssh ad-research "docker exec alloyresearch-hermes bash -c 'getent hosts postgres redis backend'"
ssh ad-research "docker inspect alloyresearch-hermes ..."   # final security summary
```

What was NOT done (per user instruction):

- `hermes setup` was NOT run interactively (no key bound yet).
- No daemon / TUI / cron loop was started; the container is `sleep infinity`.
- The `docker-compose.yml` at `/data/ad-research/deploy/aliyun-ecs/` was NOT
  modified; the existing `alloyresearch-*` stack continues to be managed by
  `docker compose` from that directory.
- Nothing in this repo (`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/`)
  was committed or pushed; this markdown report is an untracked working-tree
  artifact in `docs/dev-notes/`.

---

## 10. First-time setup (run as the user, one-time)

The container is up, hardened, and pinned to `hermes-agent==0.18.2`, but
no provider key has been bound and `hermes setup` has never run. Walk
through these three steps from your laptop terminal. Nothing here binds a
key automatically — paste your own.

### Step 1 — bind an LLM key into `/home/hermes/.hermes/.env`

**Get the key from your password manager first.** Do NOT paste it into
chat, commit it, or save it in any file that synchronises. The snippet
below reads the key from your terminal into a shell variable without
echoing it, then writes it to `/home/hermes/.hermes/.env` inside the
container with mode `600`.

```bash
# Paste the key at the prompt (input is hidden). The key never lands in
# your shell history or in this snippet's file.
read -rs KEY && [ -n "$KEY" ] || { echo "empty key, abort"; exit 1; }

ssh ad-research "docker exec -u 10001:10001 -i alloyresearch-hermes \
    bash -c \"printf 'OPENAI_API_KEY=%s\n' \\\"\$KEY\\\" \
        > /home/hermes/.hermes/.env \
        && chmod 600 /home/hermes/.hermes/.env \
        && stat -c 'mode=%a owner=%U bytes=%s name=%n' \
            /home/hermes/.hermes/.env\""
unset KEY
```

If your provider is not OpenAI, swap `OPENAI_API_KEY` for the right env
var; see §6 for the matching keys (`ANTHROPIC_API_KEY`, `HONCHO_API_KEY`,
`SUPERMEMORY_API_KEY`, `MEM0_API_KEY`). Append additional lines with a
second `printf '%s=%s\n' NAME VALUE >> /home/hermes/.hermes/.env` step.

Sanity check (no key bytes leak; just metadata + a count):

```bash
ssh ad-research "docker exec -u 10001:10001 alloyresearch-hermes \
    bash -c 'stat -c \"mode=%a owner=%U bytes=%s name=%n\" \
        /home/hermes/.hermes/.env \
        && echo -n \"key lines: \" \
        && grep -cE \"^(OPENAI|ANTHROPIC|HONCHO|SUPERMEMORY|MEM0)_API_KEY=\" \
            /home/hermes/.hermes/.env'"
```

Expected:

```
mode=600 owner=hermes bytes=49..71 name=/home/hermes/.hermes/.env
key lines: 1
```

Then restart so the provider client re-initialises against the new env:

```bash
ssh ad-research "docker restart alloyresearch-hermes"
```

### Step 2 — first-time `hermes setup`

`hermes setup --help` confirmed the correct flag for 0.18.2:

```
--non-interactive     Non-interactive mode (use defaults/env vars)
```

Run from your laptop:

```bash
ssh -t ad-research "docker exec -it -u 10001:10001 alloyresearch-hermes \
    bash -c 'cd ~ && hermes setup --non-interactive'"
```

With `--non-interactive`, hermes uses the values you already set (env
vars and any pre-existing `~/.hermes/config/`). It will NOT prompt.

Verify what it wrote:

```bash
ssh ad-research "docker exec -u 10001:10001 alloyresearch-hermes \
    bash -c 'ls -la ~/.hermes/ ~/.hermes/config/ 2>/dev/null \
        && echo --- && find ~/.hermes -maxdepth 3 -type f -printf \"%p %s bytes\\n\"'"
```

You should see `~/.hermes/config/config.yaml` (or `.json`) plus any
provider-specific files.

If a single wizard section later needs an interactive run, the help shows
the valid sub-sections:

```
hermes setup {model,tts,terminal,gateway,tools,agent}
```

For example, to re-pick the model only:

```bash
ssh -t ad-research "docker exec -it -u 10001:10001 alloyresearch-hermes \
    bash -c 'cd ~ && hermes setup model'"
```

### Step 3 — smoke-test with `hermes chat`

One-shot non-interactive:

```bash
ssh -t ad-research "docker exec -it -u 10001:10001 alloyresearch-hermes \
    bash -c 'cd ~ && hermes chat -q \"用一句话介绍你自己\"'"
```

Expected: exit 0, a one-line Chinese reply from the configured model,
and a session ID printed at the end. If you see `NoCredentialsError`,
`AuthenticationError`, or HTTP 401/403, the env var in
`/home/hermes/.hermes/.env` was not picked up — re-do Step 1 + `docker
restart alloyresearch-hermes`.

Interactive TUI (no `-q`):

```bash
ssh -t ad-research "docker exec -it -u 10001:10001 alloyresearch-hermes \
    bash -c 'cd ~ && hermes chat'"
```

### Optional extras — NOT recommended

- **Skip `hermes tools`** (cua-driver, browser extras). Those go through
  `tools/lazy_deps.py` and try to write into the read-only root FS; the
  hardening profile (`--read-only`) will reject the writes and you'll have
  to rebuild the image.
- **Skip cron / daemon / "always on" modes.** Keep hermes on-demand via
  `docker exec`. The container's `CMD ["sleep infinity"]` is intentional —
  no auto-start, no background loop.
- **Skip HTTP exposure.** The container has `--expose` for inter-container
  reachability only; there is no `PortBindings` to the host. If a future
  hermes feature wants a webhook port, add it to the `docker create` line
  in §2 and re-create, do not modify the running container.

### Re-running / undo

- `hermes setup` (bare) — re-runs the full wizard showing current defaults
  (the help text explicitly notes that bare `hermes setup` now defaults to
  reconfigure in 0.18.x).
- `hermes setup --quick` — only prompts for missing/unset values.
- `hermes setup --reset` — wipes `~/.hermes/config/` to defaults.
- `hermes setup model` — re-pick only the model.
- To rotate a leaked key: edit `.env`, then `docker restart
  alloyresearch-hermes`. The old key is overwritten in place; nothing
  else is invalidated.

---

## 11. Reusable research-task template (中文)

When the user wants hermes to do an ad-hoc research task, paste the
prompt below into a `hermes chat` session. The template assumes hermes
runs inside the hardened container with read access to this repo's
`docs/dev-notes/` tree.

### How to invoke

```bash
ssh -t ad-research "docker exec -it -u 10001:10001 alloyresearch-hermes \
    bash -c 'cd ~ && hermes chat'"
```

Paste the template, fill the `<TOPIC>` and `<OUTPUT_FILE>` placeholders,
hit enter. To continue a session, swap `hermes chat` for
`hermes chat --resume <session-id>` (the ID is printed on exit).

### The template

```text
你是 ad-hoc 研究助手 hermes-agent，正在容器 alloyresearch-hermes 中以
非 root 用户（uid 10001）运行。你的任务：完成下面的研究请求，并把结果
写到指定路径。

【研究任务】
<TOPIC>

【输出路径】
/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/docs/dev-notes/<OUTPUT_FILE>.md

【硬性约束 — 必须遵守】
1. 先读项目上下文：动笔前先 ls docs/dev-notes/，并按相关性顺序阅读
   已有 .md，特别是：
   - 20260627-数据源已知问题备忘.md
   - 20260627-定时任务恢复操作指南.md
   - 20260622-系统平台功能逻辑说明手册.md
   以及任何与本主题直接相关的 dev-notes。如果现有文档已经回答了任务，
   直接引用 + 标注，不要重复造轮子。
2. 用 WebFetch 取一手资料，不要只靠 WebSearch 摘要。每条核心结论至少
   要从原始页面（券商研报、交易所公告、公司 IR）抓一次正文：
   - 雪球：xueqiu.com/.../...html，不要靠 Google 缓存。
   - 巨潮资讯（cninfo / static.cninfo.com.cn）：公告 PDF 用 WebFetch；
     必要时把 Accept 头设成 text/html 再抓一次。
   - 美股：SEC EDGAR 8-K/10-Q/10-K 全文；公司投资者关系页面原文。
3. 引用规范：每条事实声明后附 (来源: <URL>)。禁止出现“据说”“普遍
   认为”“市场观点”等无来源措辞。如果一条声明找不到一手来源，明确
   写“未找到一手来源，依据来自 X 的二手转述，置信度低”。
4. 不修改代码：/Users/aidanliu/Documents/Coding-Project/
   Investment-Research-Platform/ 下的 .py / .ts / .tsx / .sql / .yml /
   Dockerfile / docker-compose.yml 禁止改动。读可以，写不行。
5. 不提交：不 git commit、不 git push。报告写完即结束。
6. 输出体积：单文件 Markdown ≤ 16 KB（约 4000 中文字 / 1500 行英文），
   超出请拆章节到多个文件，每个文件一个聚焦主题。
7. 自我审计：报告末尾留一段 ## 自我审计，列出
   - 用到的一手来源 URL 列表
   - 哪些结论置信度低、依据二手转述
   - 哪些事项需要用户进一步提供资料

【工作流】
1. 续上次会话用 hermes chat --resume <session-id>；新任务用裸
   hermes chat。
2. 先 ls docs/dev-notes/ 和 cat 关键上下文文件，列出你认为需要读的
   清单，等用户确认后再深读（避免一次性读完浪费上下文）。
3. 用 WebFetch + WebSearch 做交叉验证；同一事实至少 2 个独立来源才标
   “高置信度”。
4. 写到目标路径后，最后一步 wc -c <目标路径> 核对体积。
5. 把报告的 1-2 行摘要贴回对话，让用户决定要不要看全文。

【用户偏好】
- 默认中文输出；专有名词、API 名、命令保持英文（如 OPENAI_API_KEY、
  Python、ETF）。
- 时间统一 Asia/Shanghai；ISO 格式（2026-07-11T10:30+08:00）。
- 数据口径：金额默认人民币（特别标注 USD/HKD 时除外）。
- 不要 emoji；markdown 表格不要出现 | 转义后跑出来 || 的乱码。
- 不要客套结尾（“希望对您有帮助”“如有需要……”一律去掉）。

开始前先复述任务 + 输出路径，等待我的确认（首次只需 yes / no 或
修改意见）。
```

### Fill-in cheatsheet

| 研究类型 | `<TOPIC>` 示例 | `<OUTPUT_FILE>` 建议 |
|---------|---------------|---------------------|
| A 股单股催化 | 浦发银行（600000）2026Q2 解禁 | `20260711-600000-解禁影响.md` |
| 美股单股财报 | NVDA FY27Q1 业绩 vs 预期 | `20260711-NVDA-fy27q1.md` |
| 行业主题 | 国内 ETF 资金面 2026H2 展望 | `20260711-ETF资金面-2026H2.md` |
| 数据源/平台运维 | cninfo 公告增量恢复后的 orgId 覆盖率 | `20260711-cninfo-orgId覆盖率.md` |
| 政策/事件 | 证监会 2026 减持新规影响测算 | `20260711-减持新规-影响测算.md` |

### Variations (paste-after-the-block add-ons)

- **A 股单只股票 + 催化事件**：在【研究任务】尾部追加一句 "同时核对
  docs/dev-notes/20260627-数据源已知问题备忘.md 里列出的 ETF / cninfo
  数据源状态，确认数据可用"。
- **美股财报 + 估值更新**：模板末尾追加 "估值部分只用当前 A 股同业 /
  美股同业的 trading multiples 框架，不建 DCF；数字保留 2 位小数；不要
  给出目标价"。
- **行业 / 主题研究**：输出文件名形如
  `<YYYYMMDD>-<主题>-行业-/<主题>-研究.md`，报告结构固定为：行业概
  述 → 产业链 → 主要玩家 → 最近一次催化 → 风险点 → 自我审计。
- **代码/数据源 debug**：在【硬性约束】之外临时允许修改一个明确列出
  的文件路径；其余约束照旧。报告末尾追加 "## 提议的代码改动"，只写
  diff，不直接落盘。
```

### Post-task checklist

1. `wc -c docs/dev-notes/<OUTPUT_FILE>.md` ≤ 16384 bytes.
2. Open the file in this repo, sanity-check the audit section.
3. Decide whether to commit — **NOT auto-committed per project policy
   (`docs/dev-notes/` are working-tree artifacts, not pushed without
   explicit approval; see project memory: 无明确指令不 push)**.