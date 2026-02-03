# ETH Transaction Crawler

A FastAPI web application that collects and displays **ALL** Ethereum transactions for a wallet address from a specified start block to the latest block. Handles Etherscan API limitations through intelligent segmentation to guarantee complete coverage.

## Key Features

- **Crawl ALL Mode**: Collects all transactions from start block to latest with deduplication and coverage proof
- **Browse Mode**: Fast page-by-page exploration (does not guarantee all transactions)
- **CSV Export**: Download complete transaction history
- **Progress Tracking**: Real-time progress with pause/resume for long-running crawls
- **Balance on Date**: Get ETH balance at 00:00 UTC on any date (bonus feature)
- **ERC-20 Token Transfers**: Optional inclusion of token transfers

## Quick Start

### Prerequisites
- Python 3.8+
- Etherscan API key ([Get one free](https://etherscan.io/apis))

### Setup

```bash
# 1. Navigate to project directory
cd eth-tx-crawler

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
cp .env.example .env

# 5. Edit .env and add your Etherscan API key:
#    ETHERSCAN_API_KEY=your_api_key_here
#    CHAIN_ID=1

# 6. Run the application
python -m uvicorn app.main:app --reload --reload-exclude .venv
```

Open `http://127.0.0.1:8000` in your browser.

## How to Use

### Two Modes

**Crawl ALL (Complete)** - Default, Required for Assignment
- Collects **ALL** transactions from start block to latest
- Shows coverage proof (start → end → latest)
- CSV export available
- Use this mode to satisfy the assignment requirement

**Browse (Fast)** - Quick Inspection Only
- Shows one page at a time (~200 results)
- Does NOT guarantee all transactions
- No CSV export
- Use for quick exploration before full crawl

### Basic Usage

1. Enter Ethereum address and start block
2. Select **Crawl ALL (Complete)** mode (default)
3. Optionally check "Include ERC-20 Token Transfers"
4. Click "Start Crawl"
5. Monitor progress and download CSV when complete

## Demo for Reviewers

Follow these steps to demonstrate the assignment:

### Step 1: Start the Application
```bash
# Make sure virtual environment is activated
source .venv/bin/activate

# Run the server
python -m uvicorn app.main:app --reload --reload-exclude .venv
```

### Step 2: Run Crawl ALL
1. Open `http://127.0.0.1:8000`
2. In "Transaction Crawler" form:
   - **Address**: `0xaa7a9ca87d3694b5755f213b5d04094b8d0f0a6f`
   - **Start Block**: `9000000`
   - **Mode**: Crawl ALL (Complete) - already selected by default
   - Click "Start Crawl"

### Step 3: View Results
- Progress page shows real-time segment processing
- When complete, results display:
  - Total unique ETH transaction count
  - Coverage proof: `start_block → coverage_end (latest: latest_block)` with ✅ status
  - Preview of transactions (first 2000 rows)
  - "Download full ETH CSV" button

### Step 4: Download CSV
- Click "Download full ETH CSV" to export all collected transactions

### Optional: Test Bonus Features
- **Balance on Date**: Use the "ETH Balance on Date" form with any address and date (YYYY-MM-DD)
- **Token Transfers**: Re-run crawl with "Include ERC-20 Token Transfers" checked

## Notes

- **Etherscan Rate Limits**: The application includes automatic retry logic, but very aggressive crawling may hit rate limits. Wait a few minutes and retry if needed.
- **Active Addresses**: Very active wallets (exchanges, routers) may process slower due to Etherscan's 10,000 record per-query cap. The system automatically adjusts window sizes to ensure correctness.
- **Memory**: Large result sets are cached in memory. Very large crawls (100,000+ transactions) may consume significant memory.
- **Browser Display**: Results are limited to 2,000 rows in the browser for performance. Full results are always available via CSV export.

## Troubleshooting

**"Etherscan API key not configured"**
- Verify `.env` file exists in project root
- Check that `ETHERSCAN_API_KEY` is set in `.env`
- Restart the server after creating/editing `.env`

**"ModuleNotFoundError: No module named 'fastapi'"**
- Activate virtual environment: `source .venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`

**"No such file or directory: app/main.py"**
- Run uvicorn from project root (where `app/` folder is located), not from inside `app/`

## License

MIT License - Copyright (c) 2026 Gal

---

**Happy Crawling!** 🚀
