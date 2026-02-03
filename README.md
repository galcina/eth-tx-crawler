# ETH Transaction Crawler

A professional web application for crawling and analyzing Ethereum transactions using the Etherscan API v2. This tool helps you retrieve **ALL** transactions for a wallet address from a specified block to the latest block, handling Etherscan's API limitations through intelligent segmentation.

> **⚠️ First Time Setup Required**: Before running this application, you **must** create a `.env` file with your Etherscan API key. See [Quick Start](#quick-start) below for step-by-step instructions.

## Overview

The Etherscan API has a limitation: account endpoints return a maximum of ~10,000 records per query. For active addresses with many transactions, this cap prevents retrieving complete transaction history in a single request. This application solves this problem by:

- **Segmented Crawling**: Automatically splits large block ranges into smaller windows to stay within API limits
- **Deduplication**: Ensures no duplicate transactions are included, even when ranges overlap
- **Coverage Proof**: Guarantees complete coverage from your start block to the latest block
- **Background Processing**: Long-running crawls run in the background with real-time progress updates

## Features

### Two Modes Available

#### Browse Mode (Fast) - Quick Inspection Only
- **Server-side pagination**: Browse transactions page by page with `page` and `token_page` parameters
- **Fast single-page queries**: Perfect for quick lookups and exploration
- **Separate pagination**: ETH transactions and ERC-20 token transfers have independent pagination
- **⚠️ Important**: Browse mode does **NOT** guarantee ALL transactions. It shows one page at a time (default 200 results).
- **⚠️ No CSV export**: Browse mode is for exploration only, not for complete data collection.

**Use Browse mode when**: You want to quickly check a few transactions or explore an address before committing to a full crawl.

#### Crawl ALL Mode (Complete) - Required for Assignment
**This is the mode that satisfies the assignment requirement: "collect ALL ETH transactions from block B to latest"**

- **Complete coverage**: Guarantees ALL transactions from start block to latest block
- **Segmented crawling**: Automatically handles Etherscan's ~10,000 record cap by splitting block ranges
- **Deduplication by hash**: Ensures each transaction appears only once, even across segment boundaries
- **Coverage proof**: Shows clear status (✅ covered to latest, ⚠️ stopped early, 🔄 in progress)
- **Progress tracking**: Real-time progress page with segment-by-segment status
- **Stop/Resume**: Pause long-running crawls and resume later without losing progress
- **Partial results**: View and download results even while a crawl is in progress
- **CSV export**: Download complete transaction history as CSV

**Use Crawl ALL mode when**: You need complete transaction history, CSV export, or are completing the assignment.

### Crawl ALL Mode Details
- **Segmented crawling**: Automatically handles Etherscan's ~10,000 record cap by splitting block ranges
- **Deduplication by hash**: Ensures each transaction appears only once, even across segment boundaries
- **Coverage proof**: Guarantees all transactions from start block to latest block are captured
- **Progress tracking**: Real-time progress page with segment-by-segment status
- **Stop/Resume**: Pause long-running crawls and resume later without losing progress
- **Partial results**: View and download results even while a crawl is in progress

### CSV Export
- **Full results download**: Export complete transaction history as CSV
- **Separate exports**: ETH transactions and ERC-20 token transfers exported separately
- **Partial export**: Download results from paused or running crawls

### Balance on Date (Bonus Feature)
- **Historical balance lookup**: Get ETH balance for any address at 00:00 UTC on any date
- **Uses `getblocknobytime`**: Converts date to block number
- **Uses `balancehistory`**: Retrieves balance at that specific block

## Tech Stack

- **FastAPI**: Modern, fast web framework for building APIs
- **Jinja2**: Template engine for server-side HTML rendering
- **Etherscan API v2**: Official Ethereum blockchain explorer API
- **Python 3.x**: Core programming language
- **Uvicorn**: ASGI server for running FastAPI applications

## Repository Structure

```
eth-tx-crawler/              # ← Run commands from HERE (project root)
├── app/
│   ├── __init__.py          # Package initialization
│   ├── main.py              # Main FastAPI application with all routes and logic
│   ├── etherscan.py         # Etherscan API client with retry logic and error handling
│   └── templates/
│       ├── index.html       # Main UI with forms for crawling and balance lookup
│       └── progress.html    # Progress page for background crawl jobs
├── requirements.txt         # Python dependencies
├── .env.example            # Example environment variables (template)
├── .env                    # Your API key goes here (create this file - not in git)
├── .venv/                  # Virtual environment (created during setup - not in git)
└── README.md               # This file
```

**Important**: Always run `uvicorn` from the **project root** (where `app/` folder and `requirements.txt` are), not from inside the `app/` folder.

### Key Files

- **`app/main.py`**: Contains all FastAPI routes, background job management, segmentation logic, and CSV export functionality
- **`app/etherscan.py`**: Etherscan API client with automatic retry logic, rate limit handling, and timeout management
- **`app/templates/index.html`**: User interface with forms for address input, block range selection, and results display
- **`requirements.txt`**: Lists all Python package dependencies with versions
- **`.env.example`**: Template for environment variables (copy to `.env` and fill in your API key)

## Quick Start

**First time setup?** Follow these steps in order:

```bash
# 1. Navigate to project directory
cd eth-tx-crawler

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file (REQUIRED - app won't work without this!)
cp .env.example .env

# 5. Edit .env and add your Etherscan API key
# Open .env in a text editor and replace 'your_api_key_here' with your actual key

# 6. Run the application
python -m uvicorn app.main:app --reload --reload-exclude .venv
```

**⚠️ Critical**: You **MUST** create a `.env` file with your Etherscan API key before running the app. See [Setup Instructions](#setup-instructions) below for details.

## Setup Instructions

### Prerequisites
- **Python 3.8 or higher** (check with `python --version`)
- **Mac or Linux** (Windows users: use `python` instead of `python3`, and `.venv\Scripts\activate` instead of `source .venv/bin/activate`)
- **Etherscan API key** - [Get one free here](https://etherscan.io/apis) (takes 2 minutes)

### Step-by-Step Installation

#### 1. Navigate to Project Directory

Make sure you're in the repository root directory (where `requirements.txt` and `app/` folder are located):

```bash
cd eth-tx-crawler  # or wherever you cloned/extracted the project
pwd  # Verify you're in the right directory - should show path ending in 'eth-tx-crawler'
ls   # Should show: app/, requirements.txt, README.md, .env.example
```

#### 2. Create Virtual Environment

```bash
python -m venv .venv
```

**Verify**: Check that `.venv` directory was created:
```bash
ls -la | grep .venv
```

#### 3. Activate Virtual Environment

**Mac/Linux:**
```bash
source .venv/bin/activate
```

**Windows:**
```bash
.venv\Scripts\activate
```

**Verify**: Your terminal prompt should now show `(.venv)` at the beginning:
```bash
(.venv) user@computer:~/eth-tx-crawler$
```

**⚠️ Important**: You must activate the virtual environment **every time** you open a new terminal. If you see `(.venv)` in your prompt, you're good to go.

#### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

**Verify**: Check that packages installed successfully:
```bash
pip list | grep -E "(fastapi|uvicorn|jinja2)"
```

You should see `fastapi`, `uvicorn`, and `jinja2` in the output.

#### 5. Create `.env` File (REQUIRED)

**This step is critical - the application will not work without a `.env` file!**

```bash
# Check if .env.example exists
ls -la .env.example

# Copy it to create .env
cp .env.example .env
```

**If `.env.example` is missing** (older repository clones), create `.env` manually:
```bash
cat > .env << EOF
ETHERSCAN_API_KEY=your_api_key_here
CHAIN_ID=1
EOF
```

**Note**: If you're cloning from GitHub and `.env.example` is missing, you can create it yourself or check if it exists in the latest version of the repository.

**Verify**: Check that `.env` file exists:
```bash
ls -la .env
```

#### 6. Add Your Etherscan API Key

**Open `.env` in a text editor** and replace `your_api_key_here` with your actual Etherscan API key:

```bash
# Using nano (Mac/Linux)
nano .env

# Or using vim
vim .env

# Or using VS Code
code .env
```

**Edit the file to look like this:**
```
ETHERSCAN_API_KEY=YourActualAPIKeyHere123456789
CHAIN_ID=1
```

**Verify**: Check that your API key is set (don't worry, this won't expose your key):
```bash
grep -q "your_api_key_here" .env && echo "⚠️ WARNING: You still need to replace 'your_api_key_here' with your actual API key!" || echo "✅ API key appears to be set"
```

**🔒 Security**: Never commit your `.env` file to version control. It contains sensitive API keys. The `.gitignore` file should already exclude it.

#### 7. Get Your Etherscan API Key (if you don't have one)

1. Go to [https://etherscan.io/apis](https://etherscan.io/apis)
2. Click "Sign Up" or "Login" (free account)
3. Go to "API-KEYs" section
4. Click "Add" to create a new API key
5. Copy the API key and paste it into your `.env` file

## Running the Application

**Make sure you're in the project root directory and virtual environment is activated:**

```bash
# Verify you're in the right directory
pwd  # Should show path ending in 'eth-tx-crawler'

# Verify virtual environment is activated
which python  # Should show path containing '.venv'

# Start the server
python -m uvicorn app.main:app --reload --reload-exclude .venv
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**Open your browser:**
```
http://127.0.0.1:8000
```

The application will be available at `http://127.0.0.1:8000` with auto-reload enabled (code changes will restart the server automatically).

### Troubleshooting Common Issues

#### ❌ "Etherscan API key not configured"

**Problem**: You see this error when trying to use the app.

**Solutions**:
1. ✅ Verify `.env` file exists: `ls -la .env`
2. ✅ Check that API key is set: `grep ETHERSCAN_API_KEY .env`
3. ✅ Make sure `.env` is in the **project root** (same directory as `app/` folder)
4. ✅ Restart the server after creating/editing `.env`

#### ❌ "ModuleNotFoundError: No module named 'fastapi'"

**Problem**: Python can't find installed packages.

**Solutions**:
1. ✅ Make sure virtual environment is activated (you should see `(.venv)` in prompt)
2. ✅ Reinstall dependencies: `pip install -r requirements.txt`
3. ✅ Verify activation: `which python` should show `.venv` in path

#### ❌ "No such file or directory: app/main.py"

**Problem**: You're running uvicorn from the wrong directory.

**Solutions**:
1. ✅ Navigate to project root: `cd eth-tx-crawler` (or wherever the project is)
2. ✅ Verify you're in the right place: `ls` should show `app/` folder and `requirements.txt`
3. ✅ Run uvicorn from project root, not from inside `app/` folder

#### ❌ "Command not found: python"

**Problem**: `python` command doesn't exist on your system.

**Solutions**:
1. ✅ Try `python3` instead: `python3 -m venv .venv`
2. ✅ On some systems, you may need to install Python first
3. ✅ Check Python version: `python3 --version` (should be 3.8+)

#### ❌ Server starts but shows "Etherscan API key not configured" error

**Problem**: `.env` file exists but app can't read it.

**Solutions**:
1. ✅ Verify `.env` is in project root (same level as `app/` folder)
2. ✅ Check file permissions: `ls -la .env` (should be readable)
3. ✅ Verify `.env` format (no spaces around `=`):
   ```
   ETHERSCAN_API_KEY=YourKeyHere
   CHAIN_ID=1
   ```
4. ✅ Restart the server completely (Ctrl+C and start again)

## Demo Steps (Assignment Completion)

Follow these steps to demonstrate the assignment requirements:

### Step 1: Start Crawl ALL
1. Open `http://127.0.0.1:8000` in your browser
2. In the "Transaction Crawler" form:
   - Select **"Crawl ALL (Complete)"** mode (default, recommended)
   - Enter an Ethereum address (e.g., `0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045`)
   - Enter a start block (e.g., `10000000`)
   - Optionally check "Include ERC-20 Token Transfers" for bonus feature
   - Click "Start Crawl"

### Step 2: Monitor Progress
- You'll be redirected to a progress page showing:
  - Current segment being processed
  - Total unique transactions collected so far
  - Coverage progress (start block → current block → latest block)
  - Segment count and pages processed

### Step 3: View Results
- When complete, you'll see:
  - **Total unique ETH transaction count**
  - **Coverage proof**: Shows `start_block → coverage_end (latest: latest_block)` with status:
    - ✅ **Covered to latest** if `coverage_end >= latest_block` and done
    - ⚠️ **Stopped early** if paused/stopped before latest
    - 🔄 **In progress** if still running
  - Preview of transactions (first 2000 rows for performance)
  - Download buttons for CSV export

### Step 4: Download CSV
- Click "Download full ETH CSV" to export all collected transactions
- If tokens were included, click "Download Token CSV" for ERC-20 transfers

### Optional: Pause/Resume Demo
- Click "Stop" during a crawl to pause
- View partial results and download partial CSV
- Click "Resume" to continue from where it stopped

### Bonus: Balance on Date
- Use the "ETH Balance on Date" form
- Enter address and date (YYYY-MM-DD format)
- Get balance at 00:00 UTC on that date

## Usage Examples

### Complete Transaction History (Assignment Requirement)

**Address**: `0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045`  
**Start Block**: `10000000`  
**Mode**: **Crawl ALL (Complete)**

This demonstrates the assignment requirement: collecting ALL transactions from start block to latest. The results will show:
- Total unique transaction count
- Coverage proof (start → end → latest)
- CSV export for complete data

### Quick Exploration (Browse Mode)

**Address**: `0xaa7a9ca87d3694b5755f213b5d04094b8d0f0a6f`  
**Start Block**: `9000000`  
**Mode**: Browse (Fast)

Use Browse mode to quickly check a few pages of transactions. Note: This does NOT collect all transactions and has no CSV export.

### Balance on Date (Bonus Feature)

Enter any Ethereum address and a date in `YYYY-MM-DD` format to get the ETH balance at 00:00 UTC on that date.

## UI Controls Explained

### Mode Selection

**Crawl ALL (Complete)** - Default, Recommended
- **Radio button**: Selected by default
- **Purpose**: Collects ALL transactions from start block to latest (satisfies assignment)
- **Features**: Complete coverage, CSV export, progress tracking, pause/resume
- **Use when**: Completing assignment, need full history, need CSV export

**Browse (Fast)**
- **Radio button**: Alternative mode
- **Purpose**: Quick page-by-page exploration (one page = ~200 results)
- **Limitations**: Does NOT guarantee all transactions, no CSV export
- **Use when**: Quick inspection before full crawl

### Include Tokens
- **Checkbox**: When enabled, also fetches ERC-20 token transfers
- **Browse Mode**: Adds token transfer pagination alongside ETH transactions
- **Crawl ALL Mode**: Segmented crawling includes both ETH and token transactions

### Max Pages (Optional Safety Limit)
- **Purpose**: Safety limit to prevent runaway API usage
- **Format**: Integer (e.g., `1000`)
- **Behavior**: Stops crawling when total pages across all segments reaches this limit
- **Leave empty**: No limit (crawl until complete)

### Page Size
- **Default**: 200 transactions per page
- **Range**: 50-500 (automatically clamped)
- **Impact**: Larger page sizes = fewer API calls but more data per call
- **Recommendation**: 200 is optimal for most use cases

## Notes and Limitations

### Etherscan API Limitations
- **Rate Limits**: Etherscan enforces rate limits. The application includes automatic retry logic with exponential backoff, but very aggressive crawling may still hit HTTP 429 errors
- **Timeouts**: Long-running segmented crawls may encounter timeouts. The client automatically retries failed requests
- **10,000 Record Cap**: Account endpoints return a maximum of ~10,000 records per query. The segmentation system handles this automatically

### Performance Considerations
- **Crawl ALL Duration**: For very active addresses, complete crawls may take several minutes to hours
- **Memory Usage**: Large result sets are cached in memory. Very large crawls (100,000+ transactions) may consume significant memory
- **Browser Rendering**: Results are limited to 2,000 rows in the browser for performance. Full results are always available via CSV export

**Adaptive Window Behavior (Dense Addresses)**

For very active wallets (exchanges, routers, whales), block windows may shrink to a few thousand blocks due to repeated 10k-cap hits. This is expected behavior and ensures correctness at the cost of speed. The system automatically halves the window size when it detects a cap hit, then gradually increases it back up as segments complete successfully. This adaptive behavior is typical when using free-tier blockchain APIs that enforce per-query record limits.

Example log output showing adaptive window reduction:

```
[JOB 9a5989e1018e] ETH segment 2: 19012500-19024999 (window=12500)  
[JOB 9a5989e1018e] Cap hit at window=12500, reducing to 6250 and retrying  
[JOB 9a5989e1018e] ETH segment 2: 19012500-19018749 (window=6250)  
[JOB 9a5989e1018e] ETH segment 2 done: txs=6346 pages=32 total_unique=15391  
[JOB 9a5989e1018e] ETH segment 3: 19018750-19031249 (window=12500)
```

### Best Practices
- **Start with Normal Mode**: Use pagination to explore before committing to a full crawl
- **Use Max Pages**: Set a reasonable limit for testing to avoid excessive API usage
- **Monitor Progress**: Watch the progress page for long-running crawls
- **Export Early**: Download partial results if you need data before a crawl completes

**Demo Strategy for Reviewers**
- Use a light address for full Crawl ALL demos (fast completion, CSV export, coverage proof).
- Use dense addresses only with short ranges (e.g. start block close to latest, such as latest − 50,000).
- Demonstrate ERC-20 token transfers in Normal/Browse mode on dense contracts (e.g. Uniswap router).
- Use Pause/Resume and Partial CSV to safely inspect long-running crawls.

## Pre-Flight Checklist

**Before running the app for the first time, verify:**

- ✅ You're in the project root directory (`cd eth-tx-crawler`)
- ✅ Virtual environment is created (`.venv` folder exists)
- ✅ Virtual environment is activated (see `(.venv)` in terminal prompt)
- ✅ Dependencies are installed (`pip list` shows fastapi, uvicorn, jinja2)
- ✅ `.env` file exists in project root (`ls -la .env`)
- ✅ `.env` contains your actual Etherscan API key (not `your_api_key_here`)
- ✅ You're running uvicorn from project root (not from `app/` folder)

**Quick verification command:**
```bash
# Run this from project root to check everything
[ -f .env ] && [ -d .venv ] && [ -d app ] && echo "✅ Setup looks good!" || echo "❌ Something is missing - check the setup steps above"
```

## Delivery Checklist

Before deploying or sharing this repository, ensure:

- ✅ `.env` file is in `.gitignore` (not committed)
- ✅ `.venv` directory is in `.gitignore` (not committed)
- ✅ `.env.example` exists with template values (no real secrets)
- ✅ `requirements.txt` exists with all dependencies
- ✅ Application runs locally with `uvicorn` command
- ✅ All features tested: Normal mode, Crawl ALL, CSV export, Balance lookup

## Security Notes

- **Never commit `.env`**: Your Etherscan API key is sensitive. Always use `.env.example` as a template
- **API Key Security**: Treat your Etherscan API key like a password. Rotate it if exposed
- **Rate Limits**: Be mindful of Etherscan's rate limits to avoid temporary API key restrictions

## License

This project is provided as-is for educational and development purposes.

## Support

For issues related to:
- **Etherscan API**: Check [Etherscan API Documentation](https://docs.etherscan.io/)
- **Application Bugs**: Review error messages in the browser and server logs
- **Rate Limits**: Wait a few minutes and retry, or check your API key status on Etherscan

---

**Happy Crawling!** 🚀
