# OmniFeed

**AI驱动型金融另类数据情报站 · 全量生产级落地规格白皮书**

打破金融核心内幕与政策数据的信息非对称，用AI提炼降噪，为独立投资者及自动化量化客群提供即拿即用的高价值情报。

## 核心功能

- **全局上帝时间轴** - 跨所有数据源按时间倒序混排的情报河流
- **单标的自选看板网格** - 预制20-50个高热度美股核心标的
- **用户提报心愿单** - 动态添加监控标的，下次轮询自动生效
- **跨源异动信号共振** - 国会交易 + 内幕交易 + 独家舆情的Alpha信号捕捉

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                    全 Serverless 架构                        │
├─────────────────────────────────────────────────────────────┤
│  GitHub Actions (每2小时)  ──>  FMP API 数据抽取              │
│           ↓                                                 │
│  LLM 智能网关  ──>  AI翻译 & 洞察生成                        │
│           ↓                                                 │
│  Cloudflare R2  ──>  数据湖存储                              │
│           ↓                                                 │
│  Cloudflare Pages  ──>  全球边缘分发                         │
└─────────────────────────────────────────────────────────────┘
```

## 项目结构

```
OmniFeed/
├── src/                          # Python ETL 后端
│   ├── main.py                   # 入口点
│   ├── models/                   # 数据模型
│   │   └── feed.py               # FeedEvent, Actor, Content 等
│   ├── etl/                      # ETL 管道
│   │   └── pipeline.py           # 主要编排逻辑
│   ├── services/                 # 外部服务客户端
│   │   ├── fmp_client.py         # FMP API 客户端
│   │   ├── llm_gateway.py        # LLM 网关 (支持SDK/HTTP模式)
│   │   ├── r2_client.py          # Cloudflare R2 客户端
│   │   └── rss_generator.py      # RSS 订阅源生成器
│   └── utils/                    # 工具模块
│       ├── config.py             # 配置管理
│       └── fingerprint.py        # MD5 指纹去重引擎
│
├── frontend/                     # 前端静态页面
│   ├── index.html                # 主页面
│   ├── css/style.css             # 暗黑金融风格样式
│   └── js/app.js                 # 前端逻辑
│
├── worker/                       # Cloudflare Worker
│   ├── worker.js                 # 股票代码提交端点
│   └── wrangler.toml             # Worker 配置
│
├── tests/                        # 单元测试
│   ├── test_fingerprint.py       # 指纹引擎测试
│   ├── test_models.py            # 数据模型测试
│   └── test_rss.py               # RSS 生成测试
│
├── .github/workflows/            # GitHub Actions
│   ├── etl-pipeline.yml          # ETL 定时任务
│   ├── deploy-frontend.yml       # 前端部署
│   ├── deploy-worker.yml         # Worker 部署
│   └── test.yml                  # 测试工作流
│
└── spec/                         # 规格文档
    └── omnifeed_specification.pdf
```

## 快速开始

### 1. 环境配置

复制环境变量模板:
```bash
cp .env.example .env
```

编辑 `.env` 填入你的 API 密钥:
- `FMP_API_KEY` - Financial Modeling Prep API 密钥
- `LLM_API_KEY` - LLM 服务 API 密钥 (DeepSeek/OpenAI)
- `R2_*` - Cloudflare R2 存储配置

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 运行 ETL 管道

```bash
python -m src.main
```

### 4. 本地前端开发

```bash
cd frontend
npx http-server . -p 3000
```

### 5. 部署 Cloudflare Worker

```bash
cd worker
npm install
npx wrangler deploy
```

## GitHub Actions 配置

在仓库 Settings > Secrets 中配置:

| Secret | 说明 |
|--------|------|
| `FMP_API_KEY` | FMP API 密钥 |
| `LLM_API_KEY` | LLM 服务密钥 |
| `LLM_BASE_URL` | LLM API 端点 |
| `R2_ACCOUNT_ID` | Cloudflare 账户 ID |
| `R2_ACCESS_KEY_ID` | R2 访问密钥 ID |
| `R2_SECRET_ACCESS_KEY` | R2 密钥 |
| `R2_BUCKET_NAME` | R2 存储桶名称 |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API 令牌 |

## 数据源

| 数据源 | 说明 | 更新频率 |
|--------|------|----------|
| 国会交易 | 美国参众议员及其配偶的股票交易披露 | 2小时 |
| 内幕交易 | 上市公司高管的持股变动 | 2小时 |
| 独家舆情 | FMP 提供的金融新闻分析 | 2小时 |

## 核心技术特性

### MD5 指纹去重引擎
- 国会交易: `MD5(stockTicker + lastName + disclosureDate + amount + type)`
- 内幕交易: `MD5(symbol + insiderName + filingDate + securitiesTransacted + transactionType)`
- 新闻文章: `MD5(title + pubDate)`
- 滑动窗口: 90天自动过期裁剪

### 分布式并发锁 (ETag 乐观锁)
Cloudflare Worker 使用 HTTP ETag 机制防止并发写入冲突:
1. GET `whitelist.json` 并捕获 ETag
2. 内存中追加新标的
3. PUT 时注入 `If-Match: ETag`
4. 412 冲突时自动重试 (100-300ms 随机延迟)

### LLM 故障优雅降级
- 熔断器机制: 连续3次失败后自动降级
- 降级策略: 跳过AI翻译，使用原始英文元数据
- 确保 R2 数据和 RSS 源 100% 可用

## 许可证

MIT License - Copyright (c) 2026 liu-kaining
