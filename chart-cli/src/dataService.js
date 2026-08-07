import axios from 'axios';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');
const CACHE_DIR = path.join(ROOT_DIR, '.cache');
const CACHE_FILE = path.join(CACHE_DIR, 'market-cache.json');

const COINGECKO_MIN_INTERVAL_MS = 5000;
const CHART_TTL_MS = 60 * 1000;
const DETAIL_TTL_MS = 30 * 60 * 1000;

const YAHOO_CHART_URL = 'https://query1.finance.yahoo.com/v8/finance/chart';
const YAHOO_QUOTE_URL = 'https://query1.finance.yahoo.com/v7/finance/quote';
const COINGECKO_URL = 'https://api.coingecko.com/api/v3';
const USER_AGENT = 'Mozilla/5.0 (compatible; chart-cli/1.0)';

function rangeFor(days) {
  if (days <= 1) return { range: '1d', interval: '5m' };
  if (days <= 7) return { range: '7d', interval: '1h' };
  if (days <= 30) return { range: '1mo', interval: '1d' };
  if (days <= 90) return { range: '3mo', interval: '1d' };
  if (days <= 180) return { range: '6mo', interval: '1d' };
  if (days <= 365) return { range: '1y', interval: '1d' };
  if (days <= 730) return { range: '2y', interval: '1d' };
  if (days <= 1825) return { range: '5y', interval: '1d' };
  if (days <= 3650) return { range: '10y', interval: '1d' };
  return { range: 'max', interval: '1d' };
}

/**
 * Market data access for crypto (CoinGecko) and equities/ETFs (Yahoo Finance),
 * with a disk-backed cache and conservative rate limiting.
 */
export class DataService {
  /** @param {(level: string, message: string) => void} [logger] */
  constructor(logger = () => {}) {
    this.log = logger;
    this.cache = new Map();
    this.lastCoinGeckoCall = 0;
    this.loadFileCache();
  }

  loadFileCache() {
    try {
      if (!existsSync(CACHE_FILE)) return;
      const data = JSON.parse(readFileSync(CACHE_FILE, 'utf-8'));
      for (const [key, value] of Object.entries(data)) this.cache.set(key, value);
      this.log('info', `cache: loaded ${Object.keys(data).length} entries`);
    } catch (error) {
      this.log('warn', `cache load failed: ${error.message}`);
    }
  }

  saveFileCache() {
    try {
      if (!existsSync(CACHE_DIR)) mkdirSync(CACHE_DIR, { recursive: true });
      writeFileSync(CACHE_FILE, JSON.stringify(Object.fromEntries(this.cache), null, 2));
    } catch (error) {
      this.log('warn', `cache save failed: ${error.message}`);
    }
  }

  isCacheValid(key, ttl = CHART_TTL_MS) {
    const cached = this.cache.get(key);
    return Boolean(cached?.timestamp) && Date.now() - cached.timestamp < ttl;
  }

  async throttleCoinGecko() {
    const elapsed = Date.now() - this.lastCoinGeckoCall;
    if (elapsed < COINGECKO_MIN_INTERVAL_MS) {
      await new Promise((resolve) => setTimeout(resolve, COINGECKO_MIN_INTERVAL_MS - elapsed));
    }
    this.lastCoinGeckoCall = Date.now();
  }

  async getCoinGecko(url, options, retries = 2, baseDelay = 1200) {
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        await this.throttleCoinGecko();
        return await axios.get(url, options);
      } catch (error) {
        const status = error.response?.status;
        const retryable = status === 429 || status >= 500 || !status;
        if (attempt === retries || !retryable) throw error;
        const delay = baseDelay * 2 ** attempt + Math.floor(Math.random() * 300);
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
    }
    throw new Error('unreachable');
  }

  async fetchCrypto(symbol, coinId, days) {
    const chartKey = `crypto:${symbol}:${days}`;
    const detailKey = `detail:${coinId}`;
    if (this.isCacheValid(chartKey)) return { ...this.cache.get(chartKey), fromCache: true };

    try {
      const chart = await this.getCoinGecko(`${COINGECKO_URL}/coins/${coinId}/market_chart`, {
        params: { vs_currency: 'usd', days: days >= Number.MAX_SAFE_INTEGER ? 'max' : days },
        headers: { 'User-Agent': USER_AGENT },
        timeout: 10000
      });

      const timestamps = [];
      const history = [];
      for (const point of chart.data.prices ?? []) {
        const [ts, value] = point ?? [];
        if (Number.isFinite(value)) {
          timestamps.push(Number.isFinite(ts) ? ts : Date.now());
          history.push(value);
        }
      }
      if (history.length === 0) throw new Error('empty price series');

      let detail = this.isCacheValid(detailKey, DETAIL_TTL_MS) ? this.cache.get(detailKey) : null;
      if (!detail) {
        try {
          const response = await this.getCoinGecko(`${COINGECKO_URL}/coins/${coinId}`, {
            params: {
              localization: false,
              tickers: false,
              community_data: false,
              developer_data: false
            },
            headers: { 'User-Agent': USER_AGENT },
            timeout: 10000
          });
          const market = response.data.market_data ?? {};
          detail = {
            currentPrice: market.current_price?.usd ?? null,
            change24h: market.price_change_percentage_24h ?? 0,
            high24h: market.high_24h?.usd ?? null,
            low24h: market.low_24h?.usd ?? null,
            ath: market.ath?.usd ?? null,
            atl: market.atl?.usd ?? null,
            marketCap: market.market_cap?.usd ?? 0,
            volume24h: market.total_volume?.usd ?? 0,
            circulatingSupply: market.circulating_supply ?? 0,
            rank: response.data.market_cap_rank ?? 0,
            timestamp: Date.now()
          };
          this.cache.set(detailKey, detail);
        } catch (error) {
          this.log('warn', `${symbol} detail unavailable: ${error.message}`);
        }
      }

      const price = detail?.currentPrice ?? history[history.length - 1];
      const first = history[0] || price;
      const asset = {
        symbol,
        category: 'crypto',
        price,
        change: first > 0 ? ((price - first) / first) * 100 : 0,
        change24h: detail?.change24h ?? 0,
        history,
        timestamps,
        open: history[0],
        previousClose: history[0],
        high: detail?.high24h ?? Math.max(...history),
        low: detail?.low24h ?? Math.min(...history),
        high52w: detail?.ath ?? 0,
        low52w: detail?.atl ?? 0,
        marketCap: detail?.marketCap ?? 0,
        volume: detail?.volume24h ?? 0,
        circulatingSupply: detail?.circulatingSupply ?? 0,
        rank: detail?.rank ?? 0,
        pe: 0,
        avgVolume: 0,
        timestamp: Date.now(),
        error: false
      };
      this.cache.set(chartKey, asset);
      this.saveFileCache();
      return asset;
    } catch (error) {
      this.log('error', `${symbol}: ${error.message}`);
      if (this.cache.has(chartKey)) {
        return { ...this.cache.get(chartKey), error: true, fromCache: true };
      }
      return this.emptyAsset(symbol, 'crypto');
    }
  }

  async fetchEquity(symbol, days) {
    const cacheKey = `equity:${symbol}:${days}`;
    if (this.isCacheValid(cacheKey)) return { ...this.cache.get(cacheKey), fromCache: true };

    const { range, interval } = rangeFor(days);
    try {
      const response = await axios.get(`${YAHOO_CHART_URL}/${encodeURIComponent(symbol)}`, {
        params: { interval, range },
        headers: { 'User-Agent': USER_AGENT },
        timeout: 10000
      });

      const result = response.data.chart?.result?.[0];
      if (!result) throw new Error('no chart payload');
      const quote = result.indicators?.quote?.[0] ?? {};
      const meta = result.meta ?? {};

      const history = [];
      const timestamps = [];
      const closes = quote.close ?? [];
      const stamps = result.timestamp ?? [];
      for (let i = 0; i < closes.length; i++) {
        if (Number.isFinite(closes[i])) {
          history.push(closes[i]);
          timestamps.push(Number.isFinite(stamps[i]) ? stamps[i] * 1000 : Date.now());
        }
      }
      if (history.length === 0) throw new Error('empty price series');

      const price = meta.regularMarketPrice ?? history[history.length - 1];
      const previousClose = meta.chartPreviousClose ?? history[0] ?? price;
      const opens = (quote.open ?? []).filter((value) => Number.isFinite(value));

      const asset = {
        symbol,
        category: meta.instrumentType === 'ETF' ? 'etf' : 'stock',
        price,
        change: previousClose > 0 ? ((price - previousClose) / previousClose) * 100 : 0,
        change24h: previousClose > 0 ? ((price - previousClose) / previousClose) * 100 : 0,
        history,
        timestamps,
        open: meta.regularMarketOpen ?? opens[opens.length - 1] ?? previousClose,
        previousClose,
        high: meta.regularMarketDayHigh ?? Math.max(...history),
        low: meta.regularMarketDayLow ?? Math.min(...history),
        high52w: meta.fiftyTwoWeekHigh ?? 0,
        low52w: meta.fiftyTwoWeekLow ?? 0,
        marketCap: 0,
        volume: meta.regularMarketVolume ?? 0,
        avgVolume: 0,
        circulatingSupply: 0,
        rank: 0,
        pe: 0,
        timestamp: Date.now(),
        error: false
      };

      try {
        const quoteResponse = await axios.get(YAHOO_QUOTE_URL, {
          params: { symbols: symbol },
          headers: { 'User-Agent': USER_AGENT },
          timeout: 5000
        });
        const data = quoteResponse.data.quoteResponse?.result?.[0];
        if (data) {
          asset.marketCap = data.marketCap ?? 0;
          asset.pe = data.trailingPE ?? data.forwardPE ?? 0;
          asset.avgVolume = data.averageDailyVolume3Month ?? data.averageDailyVolume10Day ?? 0;
          asset.high52w = data.fiftyTwoWeekHigh ?? asset.high52w;
          asset.low52w = data.fiftyTwoWeekLow ?? asset.low52w;
          asset.open = data.regularMarketOpen ?? asset.open;
        }
      } catch {
        // Supplemental quote fields are optional.
      }

      this.cache.set(cacheKey, asset);
      this.saveFileCache();
      return asset;
    } catch (error) {
      this.log('error', `${symbol}: ${error.message}`);
      if (this.cache.has(cacheKey)) {
        return { ...this.cache.get(cacheKey), error: true, fromCache: true };
      }
      return this.emptyAsset(symbol, 'stock');
    }
  }

  emptyAsset(symbol, category) {
    return {
      symbol,
      category,
      price: 0,
      change: 0,
      change24h: 0,
      history: [0],
      timestamps: [Date.now()],
      open: 0,
      previousClose: 0,
      high: 0,
      low: 0,
      high52w: 0,
      low52w: 0,
      marketCap: 0,
      volume: 0,
      avgVolume: 0,
      circulatingSupply: 0,
      rank: 0,
      pe: 0,
      timestamp: Date.now(),
      error: true
    };
  }

  /** Fetch every configured ticker sequentially so upstream rate limits are respected. */
  async fetchAll(tickers, cryptoIds, days) {
    const assets = [];
    for (const ticker of tickers) {
      const coinId = cryptoIds[ticker];
      assets.push(
        coinId ? await this.fetchCrypto(ticker, coinId, days) : await this.fetchEquity(ticker, days)
      );
    }
    return assets;
  }

  /** Load a longer daily series than the chart shows, for a backtest. */
  async fetchBacktestHistory(symbol, cryptoIds, days = 730) {
    const coinId = cryptoIds[symbol];
    return coinId ? this.fetchCrypto(symbol, coinId, days) : this.fetchEquity(symbol, days);
  }
}
