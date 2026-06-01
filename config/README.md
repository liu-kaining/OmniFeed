# OmniFeed 配置指南

所有环境变量定义在 **[omnifeed.env.example](./omnifeed.env.example)**，Python 运行时统一由 `src/utils/config.py` 加载。

---

## 快速开始（本地）

```bash
# 1. 复制配置模板
cp config/omnifeed.env.example .env

# 2. 编辑 .env，填入 API Key 等（见下方说明）

# 3. 生成前端 config.js
python scripts/generate_frontend_config.py

# 4. 运行 ETL（dry run 不写 R2）
DRY_RUN=true python -m src.main
```

---

## GitHub Secrets 配置

进入仓库：**Settings → Secrets and variables → Actions → New repository secret**

### 必填 Secrets（ETL 管道）

| Secret 名称 | 说明 | 获取方式 |
|------------|------|---------|
| `FMP_API_KEY` | Financial Modeling Prep API 密钥 | [FMP 注册](https://site.financialmodelingprep.com/register) → Dashboard → API Key |
| `LLM_API_KEY` | LLM 服务密钥 | DeepSeek / OpenAI 等兼容接口的 API Key |
| `R2_ACCOUNT_ID` | Cloudflare 账户 ID | Cloudflare Dashboard → 右侧 Account ID |
| `R2_ACCESS_KEY_ID` | R2 API Token Access Key | R2 → Manage R2 API Tokens → Create |
| `R2_SECRET_ACCESS_KEY` | R2 API Token Secret Key | 创建 Token 时一次性显示 |
| `CLOUDFLARE_API_TOKEN` | Cloudflare 部署令牌 | My Profile → API Tokens → 创建 Pages + Workers + R2 权限 |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 账户 ID | 同 `R2_ACCOUNT_ID` |

### 必填 Secrets（前端 + Worker）

| Secret 名称 | 说明 | 示例值 |
|------------|------|--------|
| `OMNIFEED_API_BASE` | Worker API 根路径 | `https://omnifeed-worker.xxx.workers.dev/api` |
| `OMNIFEED_FEEDS_BASE` | R2 公开访问 URL | `https://pub-xxx.r2.dev` |
| `TURNSTILE_SITE_KEY` | Turnstile 站点公钥 | Cloudflare Dashboard → Turnstile → Site Key |
| `TURNSTILE_SECRET_KEY` | Turnstile 服务端密钥 | 同上 → Secret Key（同时注入 Worker） |

> **R2 公开访问**：R2 控制台 → 你的 bucket → Settings → Public Access → 开启并复制 Public URL。

### 可选 Secrets

| Secret 名称 | 默认值 | 说明 |
|------------|--------|------|
| `QUIVER_API_KEY` | （空） | Quiver 国会交易 API；不配则自动用 Capitol Trades 免费源 |
| `R2_BUCKET_NAME` | `omnifeed-bucket` | R2 存储桶名称，需与 `worker/wrangler.toml` 一致 |
| `LLM_MODE` | `SDK_MODE` | `SDK_MODE` 或 `DIRECT_HTTP_MODE` |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | LLM API 端点 |
| `LLM_MODEL` | `deepseek-chat` | 模型名称 |
| `LLM_CHUNK_SIZE` | `10` | 每批 LLM 处理条数 |
| `LLM_MAX_FAILURES` | `3` | 熔断阈值 |
| `ETL_DAYS_BACK` | `7` | 数据回溯天数 |
| `ETL_MAX_FEED_ITEMS` | `500` | latest_feeds.json 最大保留条数 |
| `FMP_BASE_URL` | stable API | 一般无需修改 |
| `FMP_INSIDER_LIMIT` | `100` | 单次内幕交易拉取上限 |
| `FMP_NEWS_LIMIT` | `100` | 单次新闻拉取上限 |

---

## 各组件使用的 Secrets

### 1. ETL 管道（`.github/workflows/etl-pipeline.yml`）

每 2 小时自动运行，使用以下 Secrets：

```
FMP_API_KEY
QUIVER_API_KEY          # 可选
LLM_MODE                # 可选
LLM_API_KEY
LLM_BASE_URL            # 可选
LLM_MODEL               # 可选
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME          # 可选
```

手动触发时可勾选 **Dry run**，等效于 `DRY_RUN=true`。

### 2. 前端部署（`.github/workflows/deploy-frontend.yml`）

部署前自动生成 `frontend/config.js`：

```
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
OMNIFEED_API_BASE
OMNIFEED_FEEDS_BASE
TURNSTILE_SITE_KEY
```

### 3. Worker 部署（`.github/workflows/deploy-worker.yml`）

```
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
```

部署后还需手动注入 Worker secrets（**不在 GitHub Secrets 中自动注入**）：

```bash
cd worker
npx wrangler secret put TURNSTILE_SECRET_KEY   # 与 GitHub Secret 同名同值
npx wrangler secret put ALLOWED_ORIGIN         # 可选，如: https://your-domain.com
```

---

## 配置检查清单

部署前确认：

- [ ] 所有必填 GitHub Secrets 已配置
- [ ] R2 bucket 已创建且名称与 `R2_BUCKET_NAME` / `wrangler.toml` 一致
- [ ] R2 公开访问已开启，`OMNIFEED_FEEDS_BASE` 指向正确 URL
- [ ] Worker 已部署且 `TURNSTILE_SECRET_KEY` 已通过 wrangler 注入
- [ ] `OMNIFEED_API_BASE` 指向 Worker 的 `/api` 路径
- [ ] 手动触发一次 ETL（可先 dry run）验证日志无报错
- [ ] 前端页面能加载 feed 数据且提报标的功能正常

---

## 环境变量 → 代码映射

| 变量 | 读取位置 |
|------|---------|
| ETL / FMP / LLM / R2 / Quiver / Turnstile | `src/utils/config.py` |
| 前端 apiBase / feedsBase / turnstileSiteKey | `scripts/generate_frontend_config.py` → `frontend/config.js` |
| Worker TURNSTILE_SECRET_KEY / ALLOWED_ORIGIN | `worker/worker.js` via wrangler secrets |
| Cloudflare 部署 | GitHub Actions workflows |

完整变量列表见 [omnifeed.env.example](./omnifeed.env.example)。
