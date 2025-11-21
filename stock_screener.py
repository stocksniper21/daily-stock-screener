import yfinance as yf
import pandas as pd
import time
import requests
import io
import datetime
import concurrent.futures
import json
import os

# --- CONFIGURATION ---
BATCH_SIZE = 50         # Batch size to prevent rate limits
LOOKBACK_DAYS = 5       # Days to look back for a cross event
SLEEP_TIME = 2          # Sleep between batches
MAX_WORKERS = 5         # Threads for fundamental analysis
MAX_RETRIES = 3         # Retry attempts for downloads
OUTPUT_FILENAME = "index.html" # Standard name for web hosting

# --- HTML TEMPLATE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Market Scan</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        .scrollbar-hide::-webkit-scrollbar { display: none; }
        .scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }
    </style>
</head>
<body class="bg-slate-900 text-slate-200 font-sans min-h-screen p-6">
    <div class="max-w-7xl mx-auto">
        <header class="flex justify-between items-center mb-8 border-b border-slate-700 pb-4">
            <div>
                <h1 class="text-3xl font-bold text-blue-400 flex items-center gap-2">
                    <i data-lucide="radar" class="w-8 h-8"></i> Market Scanner
                </h1>
                <p class="text-slate-400 text-sm mt-1">Automated Technical & Fundamental Screen</p>
            </div>
            <div class="text-right">
                <div class="text-sm text-slate-500 italic">Updated: <span id="gen-date" class="text-slate-300"></span></div>
                <div class="text-xs text-slate-600 mt-1">Click tickers to open TradingView</div>
            </div>
        </header>

        <!-- Stats Cards -->
        <div id="stats-container" class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div class="bg-slate-800 p-4 rounded-lg border-l-4 border-blue-500 shadow-lg">
                <div class="text-slate-400 text-xs uppercase font-bold">Total Matches</div>
                <div class="text-2xl font-bold text-white" id="stat-total">0</div>
            </div>
            <div class="bg-slate-800 p-4 rounded-lg border-l-4 border-emerald-500 shadow-lg">
                <div class="text-slate-400 text-xs uppercase font-bold">Bullish Confirmed</div>
                <div class="text-2xl font-bold text-emerald-400" id="stat-bull">0</div>
            </div>
            <div class="bg-slate-800 p-4 rounded-lg border-l-4 border-red-500 shadow-lg">
                <div class="text-slate-400 text-xs uppercase font-bold">Bearish Confirmed</div>
                <div class="text-2xl font-bold text-red-400" id="stat-bear">0</div>
            </div>
            <div class="bg-slate-800 p-4 rounded-lg border-l-4 border-yellow-500 shadow-lg">
                <div class="text-slate-400 text-xs uppercase font-bold">Speculative</div>
                <div class="text-2xl font-bold text-yellow-400" id="stat-spec">0</div>
            </div>
        </div>

        <!-- Filters -->
        <div id="filters-container" class="flex flex-wrap gap-4 mb-6">
            <input type="text" id="search-input" placeholder="Search Ticker..." class="bg-slate-800 border border-slate-700 rounded px-4 py-2 focus:outline-none focus:border-blue-500 text-sm transition-colors">
            <select id="category-filter" class="bg-slate-800 border border-slate-700 rounded px-4 py-2 text-sm focus:outline-none hover:bg-slate-700 transition-colors">
                <option value="all">All Categories</option>
                <option value="Bullish (Confirmed)">🚀 Bullish Confirmed</option>
                <option value="Bearish (Confirmed)">📉 Bearish Confirmed</option>
                <option value="Speculative">⚠️ Speculative (Tech Only)</option>
            </select>
        </div>

        <!-- Data Table -->
        <div class="overflow-x-auto bg-slate-800 rounded-lg shadow-xl" id="table-container">
            <table class="w-full text-left border-collapse">
                <thead>
                    <tr class="bg-slate-900 text-slate-400 text-xs uppercase tracking-wider border-b border-slate-700">
                        <th class="p-4 font-medium">Ticker</th>
                        <th class="p-4 font-medium">Category</th>
                        <th class="p-4 font-medium">Signal</th>
                        <th class="p-4 font-medium">Price</th>
                        <th class="p-4 font-medium">1Y %</th>
                        <th class="p-4 font-medium">Fundamentals</th>
                        <th class="p-4 font-medium">Liquidity</th>
                        <th class="p-4 font-medium">Date</th>
                    </tr>
                </thead>
                <tbody id="table-body" class="text-sm divide-y divide-slate-700">
                    <!-- Rows injected via JS -->
                </tbody>
            </table>
        </div>
        
        <footer class="mt-10 text-center text-slate-600 text-xs">
            Generated by Python Market Scanner
        </footer>
    </div>

    <script>
        // --- DATA INJECTION ---
        const embeddedData = /* DATA_PLACEHOLDER */;
        const generatedDate = "/* DATE_PLACEHOLDER */";

        // --- APP LOGIC ---
        if (typeof lucide !== 'undefined') lucide.createIcons();
        document.getElementById('gen-date').textContent = generatedDate;

        const tableBody = document.getElementById('table-body');
        const searchInput = document.getElementById('search-input');
        const categoryFilter = document.getElementById('category-filter');

        // Init
        renderStats();
        renderTable();

        // Listeners
        searchInput.addEventListener('input', renderTable);
        categoryFilter.addEventListener('change', renderTable);

        function renderStats() {
            document.getElementById('stat-total').textContent = embeddedData.length;
            const bull = embeddedData.filter(r => r.Category === 'Bullish (Confirmed)').length;
            const bear = embeddedData.filter(r => r.Category === 'Bearish (Confirmed)').length;
            const spec = embeddedData.length - (bull + bear);

            document.getElementById('stat-bull').textContent = bull;
            document.getElementById('stat-bear').textContent = bear;
            document.getElementById('stat-spec').textContent = spec;
        }

        function renderTable() {
            const searchTerm = searchInput.value.toLowerCase();
            const catFilter = categoryFilter.value;

            const filtered = embeddedData.filter(row => {
                const matchesSearch = row.Ticker.toLowerCase().includes(searchTerm);
                let matchesCat = true;
                if (catFilter === 'Speculative') matchesCat = row.Category.includes('Speculative');
                else if (catFilter !== 'all') matchesCat = row.Category === catFilter;
                return matchesSearch && matchesCat;
            });

            if (filtered.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="8" class="p-8 text-center text-slate-500 italic">No matches found for these filters.</td></tr>';
                return;
            }

            tableBody.innerHTML = filtered.map(row => {
                let badgeClass = "bg-slate-700 text-slate-300";
                if (row.Category === 'Bullish (Confirmed)') badgeClass = "bg-emerald-900/50 text-emerald-400 border border-emerald-700";
                if (row.Category === 'Bearish (Confirmed)') badgeClass = "bg-red-900/50 text-red-400 border border-red-700";
                if (row.Category.includes('Speculative')) badgeClass = "bg-yellow-900/30 text-yellow-500 border border-yellow-800";

                const cleanPct = parseFloat(row['1Y %'].replace('%', ''));
                const pctClass = cleanPct >= 0 ? 'text-emerald-400' : 'text-red-400';

                // TradingView Link Logic
                const tvLink = `https://www.tradingview.com/chart/?symbol=${row.Ticker}`;

                return `
                    <tr class="hover:bg-slate-700/50 transition-colors group">
                        <td class="p-4 font-bold text-white">
                            <a href="${tvLink}" target="_blank" class="hover:text-blue-400 flex items-center gap-2 transition-colors">
                                ${row.Ticker} 
                                <i data-lucide="external-link" class="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity"></i>
                            </a>
                        </td>
                        <td class="p-4"><span class="px-2 py-1 rounded text-xs font-medium ${badgeClass}">${row.Category}</span></td>
                        <td class="p-4 font-mono text-slate-300">${row.Signal}</td>
                        <td class="p-4 font-mono text-white">$${row.Price}</td>
                        <td class="p-4 ${pctClass}">${row['1Y %']}</td>
                        <td class="p-4 text-slate-400 text-xs max-w-xs truncate" title="${row.Fundamentals}">${row.Fundamentals}</td>
                        <td class="p-4 text-slate-400">${row.Liquidity}</td>
                        <td class="p-4 text-slate-500">${row.Date}</td>
                    </tr>
                `;
            }).join('');
            
            if (typeof lucide !== 'undefined') lucide.createIcons();
        }
    </script>
</body>
</html>
"""

def get_sma(series, window):
    return series.rolling(window=window).mean()

def get_sp500_tickers():
    print("Fetching S&P 500 tickers...")
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        tables = pd.read_html(io.StringIO(response.text))
        target_df = next((t for t in tables if 'Symbol' in t.columns), None)
        if target_df is None: return []
        return [str(t).replace('.', '-') for t in target_df['Symbol'].tolist()]
    except Exception: return []

def get_nasdaq_100_tickers():
    print("Fetching NASDAQ 100 tickers...")
    url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        tables = pd.read_html(io.StringIO(response.text))
        target_df = next((t for t in tables if 'Ticker' in t.columns or 'Symbol' in t.columns), None)
        if target_df is None: return []
        col = 'Ticker' if 'Ticker' in target_df.columns else 'Symbol'
        return [str(t).replace('.', '-') for t in target_df[col].tolist()]
    except Exception: return []

def get_nasdaq_composite_tickers():
    print("Fetching NASDAQ Composite list...")
    url = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
    try:
        response = requests.get(url, timeout=30)
        df = pd.read_csv(io.StringIO(response.text), sep='|')
        if 'Test Issue' in df.columns: df = df[df['Test Issue'] == 'N']
        df = df.dropna(subset=['Symbol'])
        df = df[~df['Symbol'].astype(str).str.contains('File Creation')]
        return [str(t).replace('.', '-') for t in df['Symbol'].tolist()]
    except Exception: return []

def check_fundamentals(ticker, mode):
    try:
        time.sleep(0.5) 
        stock = yf.Ticker(ticker)
        fin = stock.quarterly_financials
        
        if fin.empty: return False, "No Financial Data"
            
        fin = fin.T 
        fin.sort_index(ascending=False, inplace=True)
        fin = fin[~fin.index.duplicated(keep='first')]
        
        if len(fin) < 3: return False, "Insufficient Quarters"

        try:
            rev_curr   = fin['Total Revenue'].iloc[0]
            rev_1q_ago = fin['Total Revenue'].iloc[1]
            rev_2q_ago = fin['Total Revenue'].iloc[2]
        except KeyError:
            return False, "Revenue Data Missing"
        
        if mode == 'bullish':
            if not (rev_curr > rev_1q_ago and rev_1q_ago > rev_2q_ago):
                return False, f"Rev Not Growing"
        else:
            if not (rev_curr < rev_1q_ago and rev_1q_ago < rev_2q_ago):
                return False, f"Rev Not Declining"

        eps_keys = [c for c in fin.columns if 'Basic EPS' in str(c) or 'Diluted EPS' in str(c)]
        if not eps_keys: return False, "EPS Key Missing"
        eps_key = eps_keys[0]
        
        eps_curr   = fin[eps_key].iloc[0]
        eps_1q_ago = fin[eps_key].iloc[1]
        eps_2q_ago = fin[eps_key].iloc[2]

        if mode == 'bullish':
            if not (eps_curr > eps_1q_ago and eps_1q_ago > eps_2q_ago):
                return False, f"EPS Not Growing"
        else:
            if not (eps_curr < eps_1q_ago and eps_1q_ago < eps_2q_ago):
                return False, f"EPS Not Declining"
        
        return True, "Passed"

    except Exception as e:
        return False, f"Error: {str(e)}"

def download_data_with_retry(tickers):
    for attempt in range(MAX_RETRIES):
        try:
            data = yf.download(tickers, period="1y", group_by='ticker', progress=False, threads=True, auto_adjust=True)
            return data
        except Exception as e:
            if "Rate limited" in str(e) or "Too Many Requests" in str(e):
                wait = 60 * (attempt + 1)
                print(f"\n   [!] Rate Limit Hit. Cooling down for {wait}s...")
                time.sleep(wait)
            else:
                print(f"\n   [!] Download Error: {e}")
                return pd.DataFrame()
    return pd.DataFrame()

def analyze_batch(tickers):
    results_list = []
    technical_matches = []
    stats = {"liquid_fail": 0, "bull_cross": 0, "bear_cross": 0, "no_cross": 0}

    try:
        data = download_data_with_retry(tickers)
        if data.empty: return []

        for ticker in tickers:
            print(f"   [Technicals] Processing: {ticker:<10}", end='\r', flush=True)
            try:
                if len(tickers) > 1:
                    if ticker not in data.columns.levels[0]: continue
                    df = data[ticker].copy()
                else:
                    df = data.copy()

                if df.empty or len(df) < 200: continue
                df.dropna(how='all', inplace=True)
                
                current_price = df['Close'].iloc[-1]
                if current_price <= 10: continue
                    
                df['SMA50'] = get_sma(df['Close'], 50)
                df['SMA200'] = get_sma(df['Close'], 200)
                df['VolSMA50'] = get_sma(df['Volume'], 50)
                
                sma50 = df['SMA50'].iloc[-1]
                vol_sma = df['VolSMA50'].iloc[-1]
                
                if pd.isna(sma50) or pd.isna(vol_sma) or (sma50 * vol_sma) < 20000000:
                    stats["liquid_fail"] += 1
                    continue

                subset = df.iloc[-(LOOKBACK_DAYS+1):]
                if len(subset) < 2: continue
                
                detected_mode = None
                cross_date = ""
                
                sma50_vals = subset['SMA50'].values
                sma200_vals = subset['SMA200'].values
                dates = subset.index

                for i in range(1, len(sma50_vals)):
                    prev_50 = sma50_vals[i-1]
                    prev_200 = sma200_vals[i-1]
                    curr_50 = sma50_vals[i]
                    curr_200 = sma200_vals[i]

                    if prev_50 <= prev_200 and curr_50 > curr_200:
                        detected_mode = 'bullish'
                        cross_date = str(dates[i].date())
                        stats["bull_cross"] += 1
                        break
                    elif prev_50 >= prev_200 and curr_50 < curr_200:
                        detected_mode = 'bearish'
                        cross_date = str(dates[i].date())
                        stats["bear_cross"] += 1
                        break
                
                if detected_mode:
                    start_price = df['Close'].iloc[0]
                    yoy = ((current_price - start_price) / start_price) * 100
                    
                    technical_matches.append({
                        'Ticker': ticker,
                        'Mode': detected_mode,
                        'Price': current_price,
                        '1Y %': yoy,
                        'Date': cross_date,
                        'Liquidity': sma50 * vol_sma
                    })
                else:
                    stats["no_cross"] += 1

            except Exception: continue
        
        print(f"   [Batch Stats] Liquid: {len(tickers)-stats['liquid_fail']} | Bull: {stats['bull_cross']} | Bear: {stats['bear_cross']} | None: {stats['no_cross']}   ")

        if technical_matches:
            print(f"   [Fundamentals] Analyzing {len(technical_matches)} technical matches...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_stock = {executor.submit(check_fundamentals, item['Ticker'], item['Mode']): item for item in technical_matches}
                
                for future in concurrent.futures.as_completed(future_to_stock):
                    item = future_to_stock[future]
                    try:
                        passed_fund, reason = future.result()
                        
                        if item['Mode'] == 'bullish':
                            category = "Bullish (Confirmed)" if passed_fund else "Bullish (Speculative)"
                        else:
                            category = "Bearish (Confirmed)" if passed_fund else "Bearish (Speculative)"
                        
                        results_list.append({
                            'Ticker': item['Ticker'],
                            'Category': category,
                            'Signal': "GOLDEN" if item['Mode'] == 'bullish' else "DEATH",
                            'Fundamentals': "PASSED" if passed_fund else f"FAIL ({reason})",
                            'Price': round(item['Price'], 2),
                            '1Y %': f"{item['1Y %']:+.2f}%",
                            'Liquidity': f"${item['Liquidity']/1000000:.1f}M",
                            'Date': item['Date']
                        })
                    except Exception as e:
                        print(f"   [!] Error analyzing {item['Ticker']}: {e}")

    except Exception as e: print(f"Batch Error: {e}")
    return results_list

def generate_dashboard_file(df):
    """Generates a self-contained HTML dashboard."""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Convert DF to JSON string
    json_data = df.to_json(orient='records')
    
    # Inject data into template
    html_content = HTML_TEMPLATE.replace("/* DATA_PLACEHOLDER */", json_data)
    html_content = html_content.replace("/* DATE_PLACEHOLDER */", timestamp)
    
    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"\n[SUCCESS] Dashboard generated: {OUTPUT_FILENAME}")
    print(f"Open this file in your browser to view results.")

def run_auto_screener():
    # AUTOMATIC MODE for NASDAQ Composite
    tickers = get_nasdaq_composite_tickers()
    if not tickers: return

    print(f"\n--- Auto-Running Scan on {len(tickers)} tickers ---")
    
    all_results = []
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        print(f"\n[Batch {i}-{min(i+BATCH_SIZE, len(tickers))}] Downloading...")
        results = analyze_batch(batch)
        all_results.extend(results)
        if i + BATCH_SIZE < len(tickers): time.sleep(SLEEP_TIME)

    if all_results:
        df = pd.DataFrame(all_results)
        generate_dashboard_file(df)
    else:
        print("No stocks met criteria today.")

def main():
    print("1. S&P 500\n2. NASDAQ 100\n3. NASDAQ Composite (Auto-Mode)\n4. Test List")
    c = input("Select Index: ").strip()
    if c=='1': t=get_sp500_tickers()
    elif c=='2': t=get_nasdaq_100_tickers()
    elif c=='3': 
        run_auto_screener()
        return
    else: t=["AAPL", "MSFT", "NVDA", "AMD", "INTC", "TSLA", "GOOGL", "AMZN"]
    
    if not t: return

    print(f"\n--- Starting Scan on {len(t)} tickers ---")
    all_results = []
    for i in range(0, len(t), BATCH_SIZE):
        batch = t[i : i + BATCH_SIZE]
        print(f"\n[Batch {i}-{min(i+BATCH_SIZE, len(t))}] Downloading...")
        results = analyze_batch(batch)
        all_results.extend(results)
        if i + BATCH_SIZE < len(t): time.sleep(SLEEP_TIME)

    if all_results:
        df = pd.DataFrame(all_results)
        generate_dashboard_file(df)
    else:
        print("No stocks met criteria.")

if __name__ == "__main__":
    main()
