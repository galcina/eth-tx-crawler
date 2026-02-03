# ETH Transaction Crawler

A professional web application for crawling and analyzing Ethereum transactions using the Etherscan API v2. This tool helps you retrieve **ALL** transactions for a wallet address from a specified block to the latest block, handling Etherscan's API limitations through intelligent segmentation.

## Overview

The Etherscan API has a limitation: account endpoints return a maximum of ~10,000 records per query. For active addresses with many transactions, this cap prevents retrieving complete transaction history in a single request. This application solves this problem by:

- **Segmented Crawling**: Automatically splits large block ranges into smaller windows to stay within API limits
- **Deduplication**: Ensures no duplicate transactions are included, even when ranges overlap
- **Coverage Proof**: Guarantees complete coverage from your start block to the latest block
- **Background Processing**: Long-running crawls run in the background with real-time progress updates

## Features

### Normal Mode (Fast Pagination)
- **Server-side pagination**: Browse transactions page by page with `page` and `token_page` parameters
- **Fast single-page queries**: Perfect for quick lookups and exploration
- **Separate pagination**: ETH transactions and ERC-20 token transfers have independent pagination

### Crawl ALL Mode (Complete Coverage)
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
eth-tx-crawler/
├── app/
│   ├── __init__.py          # Package initialization
│   ├── main.py              # Main FastAPI application with all routes and logic
│   ├── etherscan.py         # Etherscan API client with retry logic and error handling
│   └── templates/
│       ├── index.html       # Main UI with forms for crawling and balance lookup
│       └── progress.html    # Progress page for background crawl jobs
├── requirements.txt         # Python dependencies
├── .env.example            # Example environment variables (template)
└── README.md               # This file
```

### Key Files

- **`app/main.py`**: Contains all FastAPI routes, background job management, segmentation logic, and CSV export functionality
- **`app/etherscan.py`**: Etherscan API client with automatic retry logic, rate limit handling, and timeout management
- **`app/templates/index.html`**: User interface with forms for address input, block range selection, and results display
- **`requirements.txt`**: Lists all Python package dependencies with versions
- **`.env.example`**: Template for environment variables (copy to `.env` and fill in your API key)

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- Mac or Linux (Windows users may need to adjust commands)
- Etherscan API key ([Get one here](https://etherscan.io/apis))

### Installation Steps

1. **Clone the repository** (if applicable):
   ```bash
   cd eth-tx-crawler
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Create environment file**:
   ```bash
   cp .env.example .env
   ```

6. **Edit `.env` file** and add your configuration:
   ```
   ETHERSCAN_API_KEY=your_api_key_here
   CHAIN_ID=1
   ```
   
   **Important**: Never commit your `.env` file to version control. It contains sensitive API keys.

## Running the Application

1. **Start the development server**:
   ```bash
   python -m uvicorn app.main:app --reload --reload-exclude .venv
   ```

2. **Open your browser**:
   ```
   http://127.0.0.1:8000
   ```

The application will be available at `http://127.0.0.1:8000` with auto-reload enabled (code changes will restart the server automatically).

## Usage Examples

### Basic Transaction Lookup

**Address**: `0xaa7a9ca87d3694b5755f213b5d04094b8d0f0a6f`  
**Start Block**: `9000000`

This is a good test case for basic functionality. Use Normal Mode to browse transactions page by page.

### Heavy Transaction History (with Tokens)

**Address**: `0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045`  
**Start Block**: `10000000`

This address has extensive transaction history and token transfers. Use Crawl ALL mode with "Include Tokens" enabled to retrieve complete history.

### Balance on Date

Enter any Ethereum address and a date in `YYYY-MM-DD` format to get the ETH balance at 00:00 UTC on that date.

## UI Controls Explained

### Include Tokens
- **Checkbox**: When enabled, also fetches ERC-20 token transfers
- **Normal Mode**: Adds token transfer pagination alongside ETH transactions
- **Crawl ALL Mode**: Segmented crawling includes both ETH and token transactions

### Crawl ALL
- **Checkbox**: Enables segmented crawling mode
- **When enabled**: Redirects to background job system with progress tracking
- **Use for**: Complete transaction history retrieval when you need ALL transactions

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

### Best Practices
- **Start with Normal Mode**: Use pagination to explore before committing to a full crawl
- **Use Max Pages**: Set a reasonable limit for testing to avoid excessive API usage
- **Monitor Progress**: Watch the progress page for long-running crawls
- **Export Early**: Download partial results if you need data before a crawl completes

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
