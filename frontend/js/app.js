/**
 * OmniFeed Frontend Application
 *
 * Main application logic for the financial intelligence dashboard.
 */

// API endpoints
const API_BASE = window.OMNIFEED_API_BASE || '/api';
const FEEDS_BASE = window.OMNIFEED_FEEDS_BASE || '';
const FEEDS_URL = `${FEEDS_BASE}/feeds/latest_feeds.json`;
const SYMBOLS_URL = `${FEEDS_BASE}/symbols/`;

// Application state
const state = {
    feeds: [],
    filteredFeeds: [],
    tickers: [],
    activeTicker: null,
    activeView: 'timeline',
    isLoading: true,
};

// DOM elements
const elements = {};

/**
 * Escape HTML to prevent XSS injection
 */
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Initialize the application
 */
document.addEventListener('DOMContentLoaded', async () => {
    initializeElements();
    setupEventListeners();
    await loadData();
});

/**
 * Cache DOM elements
 */
function initializeElements() {
    elements.tickerGrid = document.getElementById('tickerGrid');
    elements.feedList = document.getElementById('feedList');
    elements.feedTitle = document.getElementById('feedTitle');
    elements.feedStats = document.getElementById('feedStats');
    elements.loading = document.getElementById('loading');
    elements.tickerInput = document.getElementById('tickerInput');
    elements.submitForm = document.getElementById('submitForm');
    elements.submitMessage = document.getElementById('submitMessage');
    elements.rawJsonModal = document.getElementById('rawJsonModal');
    elements.jsonContent = document.getElementById('jsonContent');
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Navigation buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.activeView = btn.dataset.view;
            filterAndRenderFeeds();
            updateFeedTitle();
        });
    });

    // Add ticker button
    document.getElementById('btnAddTicker').addEventListener('click', () => {
        elements.submitForm.classList.toggle('hidden');
        elements.tickerInput.focus();
    });

    // Submit ticker
    document.getElementById('btnSubmit').addEventListener('click', submitTicker);

    // Cancel ticker
    document.getElementById('btnCancel').addEventListener('click', () => {
        elements.submitForm.classList.add('hidden');
        elements.tickerInput.value = '';
        elements.submitMessage.textContent = '';
    });

    // Ticker input validation
    elements.tickerInput.addEventListener('input', (e) => {
        e.target.value = e.target.value.toUpperCase().replace(/[^A-Z]/g, '');
    });

    // Enter key to submit
    elements.tickerInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') submitTicker();
    });

    // Filter button
    document.querySelector('.btn-filter').addEventListener('click', () => {
        state.activeTicker = null;
        filterAndRenderFeeds();
        updateTickerCards();
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (!elements.rawJsonModal.classList.contains('hidden')) {
                toggleRawJSON();
            }
        }
    });
}

/**
 * Load data from R2 storage
 */
async function loadData() {
    try {
        showLoading(true);

        // Load feeds and default tickers in parallel
        const [feedsResponse] = await Promise.all([
            fetch(FEEDS_URL).catch(() => null),
        ]);

        if (feedsResponse && feedsResponse.ok) {
            state.feeds = await feedsResponse.json();
        }

        // Extract unique tickers from feeds
        const tickerSet = new Set(state.feeds.map(f => f.ticker));
        state.tickers = Array.from(tickerSet).sort();

        // If no tickers from feeds, use defaults
        if (state.tickers.length === 0) {
            state.tickers = [
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA',
                'AMD', 'COIN', 'PLTR', 'SOFI', 'MARA', 'RIOT'
            ];
        }

        renderTickerGrid();
        filterAndRenderFeeds();
        showLoading(false);
    } catch (error) {
        console.error('Failed to load data:', error);
        showError('Failed to load data. Please try again later.');
        showLoading(false);
    }
}

/**
 * Render ticker grid
 */
function renderTickerGrid() {
    elements.tickerGrid.innerHTML = '';

    state.tickers.forEach(ticker => {
        const card = document.createElement('div');
        card.className = 'ticker-card';
        card.dataset.ticker = ticker;

        if (state.activeTicker === ticker) {
            card.classList.add('active');
        }

        const tickerFeeds = state.feeds.filter(f => f.ticker === ticker);
        const eventCount = tickerFeeds.length;

        // Calculate resonance index (placeholder logic)
        const resonance = calculateResonance(tickerFeeds);

        card.innerHTML = `
            <div class="ticker-header">
                <span class="ticker-symbol">${escapeHtml(ticker)}.US</span>
                <span class="resonance-index ${getResonanceClass(resonance)}">
                    ${getResonanceEmoji(resonance)} ${resonance}
                </span>
            </div>
            <div class="ticker-stats">
                <span>事件: ${eventCount}</span>
                <span>最新: ${getLatestTime(tickerFeeds)}</span>
            </div>
        `;

        card.addEventListener('click', () => {
            state.activeTicker = ticker;
            filterAndRenderFeeds();
            updateTickerCards();
        });

        elements.tickerGrid.appendChild(card);
    });
}

/**
 * Update ticker card active states
 */
function updateTickerCards() {
    document.querySelectorAll('.ticker-card').forEach(card => {
        card.classList.toggle('active', card.dataset.ticker === state.activeTicker);
    });
}

/**
 * Calculate resonance index for a ticker
 */
function calculateResonance(feeds) {
    if (feeds.length === 0) return 0;

    // Simple resonance calculation based on event diversity
    const sources = new Set(feeds.map(f => f.source));
    const recentEvents = feeds.filter(f => {
        const time = new Date(f.eventTimestamp);
        const dayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
        return time > dayAgo;
    });

    // Base score from event count
    let score = Math.min(feeds.length * 2, 10);

    // Bonus for multiple sources (cross-source resonance)
    if (sources.size > 1) score += sources.size * 2;

    // Bonus for recent events
    score += recentEvents.length;

    // Cap at -10 to 10
    return Math.max(-10, Math.min(10, score));
}

/**
 * Get resonance CSS class
 */
function getResonanceClass(value) {
    if (value >= 5) return 'resonance-hot';
    if (value <= -5) return 'resonance-cold';
    return 'resonance-neutral';
}

/**
 * Get resonance emoji
 */
function getResonanceEmoji(value) {
    if (value >= 7) return '🔥';
    if (value >= 5) return '🌡️';
    if (value <= -5) return '❄️';
    if (value <= -7) return '🧊';
    return '⚖️';
}

/**
 * Get latest event time string
 */
function getLatestTime(feeds) {
    if (feeds.length === 0) return '无数据';

    const latest = feeds.reduce((max, f) =>
        new Date(f.eventTimestamp) > new Date(max.eventTimestamp) ? f : max
    );

    return formatTimeAgo(new Date(latest.eventTimestamp));
}

/**
 * Filter and render feeds based on current view and ticker
 */
function filterAndRenderFeeds() {
    let filtered = [...state.feeds];

    // Filter by source
    if (state.activeView !== 'timeline') {
        const sourceMap = {
            'congress': 'CONGRESS',
            'insider': 'INSIDER',
            'articles': 'ARTICLE',
        };
        filtered = filtered.filter(f => f.source === sourceMap[state.activeView]);
    }

    // Filter by ticker
    if (state.activeTicker) {
        filtered = filtered.filter(f => f.ticker === state.activeTicker);
    }

    // Sort by timestamp (most recent first)
    filtered.sort((a, b) => new Date(b.eventTimestamp) - new Date(a.eventTimestamp));

    state.filteredFeeds = filtered;
    renderFeeds();
    updateFeedStats();
}

/**
 * Render feed list
 */
function renderFeeds() {
    elements.feedList.innerHTML = '';

    if (state.filteredFeeds.length === 0) {
        elements.feedList.innerHTML = `
            <div class="loading">
                <p>暂无情报数据</p>
                <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.5rem;">
                    数据将每2小时自动更新
                </p>
            </div>
        `;
        return;
    }

    state.filteredFeeds.forEach(feed => {
        const card = createFeedCard(feed);
        elements.feedList.appendChild(card);
    });
}

/**
 * Create a feed card element
 */
function createFeedCard(feed) {
    const card = document.createElement('article');
    card.className = 'feed-card';

    const sourceClass = {
        'CONGRESS': 'source-congress',
        'INSIDER': 'source-insider',
        'ARTICLE': 'source-article',
    }[feed.source] || '';

    const sourceLabel = {
        'CONGRESS': '🏛️国会山',
        'INSIDER': '💼管理层',
        'ARTICLE': '📰舆情',
    }[feed.source] || feed.source;

    const timeAgo = formatTimeAgo(new Date(feed.eventTimestamp));

    let financialsHtml = '';
    if (feed.financials) {
        const actionClass = feed.financials.action === 'BUY' ? 'action-buy' : 'action-sell';
        const actionLabel = feed.financials.action === 'BUY' ? '买入' : '卖出';

        financialsHtml = `
            <div class="feed-financials">
                <span class="${actionClass}">● ${actionLabel}</span>
                ${feed.financials.valueRange ?
                    `<span class="feed-value-range">${escapeHtml(feed.financials.valueRange)}</span>` :
                    ''
                }
                ${feed.financials.volume ?
                    `<span>${Number(feed.financials.volume).toLocaleString()}股</span>` :
                    ''
                }
                ${feed.financials.price ?
                    `<span>@ $${Number(feed.financials.price).toFixed(2)}</span>` :
                    ''
                }
            </div>
        `;
    }

    // Highlight AI insight
    const bodyZh = feed.content.bodyZh || '';
    const insightMatch = bodyZh.match(/(🤖.*?(?:。|$))/);
    const insightHtml = insightMatch ?
        bodyZh.replace(insightMatch[0], `<span class="feed-insight">${insightMatch[0]}</span>`) :
        bodyZh;

    card.innerHTML = `
        <div class="feed-card-header">
            <div>
                <span class="feed-source ${sourceClass}">${sourceLabel}</span>
                <span class="feed-ticker">${escapeHtml(feed.ticker)}.US</span>
            </div>
            <span class="feed-time">${escapeHtml(timeAgo)}</span>
        </div>

        <div class="feed-actor">
            <strong>${escapeHtml(feed.actor.nameZh)}</strong>
            ${feed.actor.nameEn !== feed.actor.nameZh ?
                `<span style="color: var(--text-muted); font-size: 0.8rem;"> (${escapeHtml(feed.actor.nameEn)})</span>` :
                ''
            }
        </div>
        <div class="feed-actor-identity">${escapeHtml(feed.actor.identityZh)}</div>

        ${financialsHtml}

        <div class="feed-content">
            <div class="feed-title-zh">${escapeHtml(feed.content.titleZh)}</div>
            <div class="feed-body-zh">${escapeHtml(feed.content.bodyZh)}</div>
        </div>

        <div class="feed-footer">
            <a href="${escapeHtml(feed.sourceUrl)}" target="_blank" rel="noopener noreferrer" class="feed-source-link">
                查看原始来源 →
            </a>
            <span style="color: var(--text-muted); font-family: var(--font-mono); font-size: 0.7rem;">
                ${escapeHtml(feed.eventId.substring(0, 8))}...
            </span>
        </div>
    `;

    return card;
}

/**
 * Update feed statistics
 */
function updateFeedStats() {
    const total = state.filteredFeeds.length;
    const congress = state.filteredFeeds.filter(f => f.source === 'CONGRESS').length;
    const insider = state.filteredFeeds.filter(f => f.source === 'INSIDER').length;
    const article = state.filteredFeeds.filter(f => f.source === 'ARTICLE').length;

    elements.feedStats.innerHTML = `
        <span class="stat-item">总计: <span class="stat-value">${total}</span></span>
        <span class="stat-item">🏛️ <span class="stat-value">${congress}</span></span>
        <span class="stat-item">💼 <span class="stat-value">${insider}</span></span>
        <span class="stat-item">📰 <span class="stat-value">${article}</span></span>
    `;
}

/**
 * Update feed title based on active view
 */
function updateFeedTitle() {
    const titles = {
        'timeline': '⏱️ 另类情报全量流',
        'congress': '🏛️ 参议院交易',
        'insider': '💼 内幕交易',
        'articles': '📰 独家舆情',
    };
    elements.feedTitle.textContent = titles[state.activeView] || '';

    if (state.activeTicker) {
        elements.feedTitle.textContent += ` | ${state.activeTicker}.US`;
    }
}

/**
 * Submit new ticker
 */
async function submitTicker() {
    const ticker = elements.tickerInput.value.trim().toUpperCase();

    if (!ticker) {
        showMessage('请输入股票代码', 'error');
        return;
    }

    if (!/^[A-Z]{1,5}$/.test(ticker)) {
        showMessage('股票代码格式无效 (1-5个字母)', 'error');
        return;
    }

    if (state.tickers.includes(ticker)) {
        showMessage(`${ticker} 已在监控列表中`, 'error');
        return;
    }

    try {
        showMessage('提交中...', '');

        const response = await fetch(`${API_BASE}/submit-ticker`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker,
                turnstileToken: getTurnstileToken(),
            }),
        });

        const data = await response.json();

        if (response.ok) {
            showMessage(`${ticker} 已成功添加到监控列表`, 'success');
            state.tickers.push(ticker);
            state.tickers.sort();
            renderTickerGrid();
            elements.tickerInput.value = '';

            // Hide form after success
            setTimeout(() => {
                elements.submitForm.classList.add('hidden');
                elements.submitMessage.textContent = '';
            }, 2000);
        } else {
            showMessage(data.error || '提交失败，请重试', 'error');
        }
    } catch (error) {
        console.error('Submit ticker error:', error);
        showMessage('网络错误，请重试', 'error');
    }
}

/**
 * Get Turnstile token (placeholder)
 */
function getTurnstileToken() {
    // In production, this would get the token from Cloudflare Turnstile widget
    return '';
}

/**
 * Show message in submit form
 */
function showMessage(text, type) {
    elements.submitMessage.textContent = text;
    elements.submitMessage.className = 'submit-message ' + (type || '');
}

/**
 * Toggle raw JSON modal
 */
function toggleRawJSON() {
    const modal = elements.rawJsonModal;
    modal.classList.toggle('hidden');

    if (!modal.classList.contains('hidden')) {
        elements.jsonContent.textContent = JSON.stringify(
            state.filteredFeeds.length > 0 ? state.filteredFeeds : state.feeds,
            null,
            2
        );
    }
}

/**
 * Show/hide loading indicator
 */
function showLoading(show) {
    state.isLoading = show;
    if (elements.loading) {
        elements.loading.style.display = show ? 'block' : 'none';
    }
}

/**
 * Show error message
 */
function showError(message) {
    elements.feedList.innerHTML = `
        <div class="loading">
            <p style="color: var(--accent-red);">⚠️ ${message}</p>
        </div>
    `;
}

/**
 * Format time ago string
 */
function formatTimeAgo(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMins < 1) return '刚刚';
    if (diffMins < 60) return `${diffMins}分钟前`;
    if (diffHours < 24) return `${diffHours}小时前`;
    if (diffDays < 7) return `${diffDays}天前`;

    return date.toLocaleDateString('zh-CN', {
        month: 'short',
        day: 'numeric',
    });
}

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        calculateResonance,
        formatTimeAgo,
        getResonanceClass,
        getResonanceEmoji,
    };
}
