from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import os
import uuid
import csv
import io
import threading
import time
import math
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any, Callable
from app.etherscan import EtherscanClient

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

# Initialize Etherscan client
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
CHAIN_ID = int(os.getenv("CHAIN_ID", "1"))
client = EtherscanClient(ETHERSCAN_API_KEY, CHAIN_ID) if ETHERSCAN_API_KEY else None

# In-memory cache for crawl_all results (for CSV export)
RESULTS_CACHE: Dict[str, Dict[str, Any]] = {}
RESULT_IDS: List[str] = []  # FIFO list for cache size management
CACHE_SIZE_LIMIT = 10  # Keep last 10 results

# Job management for background crawl_all operations
JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()  # Thread-safe access to JOBS
JOBS_SIZE_LIMIT = 20  # Keep last 20 jobs (FIFO)
JOB_IDS: List[str] = []  # FIFO list for job cleanup

# Render limits to prevent browser memory crashes
RENDER_LIMIT_ETH = 2000
RENDER_LIMIT_TOKENS = 2000

# Preview limit for live progress display (keep small to avoid memory issues)
PREVIEW_LIMIT = 200

# Etherscan API cap: account endpoints limit to ~10,000 records per query
MAX_RECORDS_PER_QUERY = 10000

# Segmentation constants
MIN_WINDOW_BLOCKS = 1  # Minimum window size (can go down to 1 block)
MAX_WINDOW_BLOCKS = 200_000  # Maximum window size
SAFETY_MAX_SEGMENTS = 5000  # Safety limit to prevent infinite loops


def wei_to_eth(wei_str: str) -> float:
    """Convert wei (as string) to ETH."""
    try:
        return int(wei_str) / 1e18
    except (ValueError, TypeError):
        return 0.0


def date_to_timestamp_utc_midnight(date_str: str) -> int:
    """
    Convert date string (YYYY-MM-DD) to Unix timestamp for 00:00:00 UTC.
    Example: "2024-01-15" -> timestamp for 2024-01-15 00:00:00 UTC
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        dt_utc = dt.replace(tzinfo=timezone.utc)
        return int(dt_utc.timestamp())
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid date format. Use YYYY-MM-DD. Error: {e}")


def format_transaction(tx: dict, address: str) -> dict:
    """Format a transaction for display."""
    tx_from = tx.get("from", "").lower()
    tx_to = tx.get("to", "").lower()
    address_lower = address.lower()
    
    # Determine direction
    if tx_from == address_lower:
        direction = "OUT"
    elif tx_to == address_lower:
        direction = "IN"
    else:
        direction = "UNKNOWN"
    
    # Format timestamp
    timestamp = tx.get("timeStamp", "0")
    try:
        dt = datetime.utcfromtimestamp(int(timestamp))
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError):
        time_str = "N/A"
    
    value_eth = wei_to_eth(tx.get("value", "0"))
    
    # Calculate transaction fee if available
    tx_fee_eth = None
    gas_used = tx.get("gasUsed")
    gas_price = tx.get("gasPrice")
    if gas_used and gas_price:
        try:
            gas_used_int = int(gas_used) if isinstance(gas_used, str) else gas_used
            gas_price_int = int(gas_price) if isinstance(gas_price, str) else gas_price
            fee_wei = gas_used_int * gas_price_int
            tx_fee_eth = wei_to_eth(str(fee_wei))
        except (ValueError, TypeError):
            pass
    
    # Shorten hash for display (first 8 + last 6 chars)
    tx_hash = tx.get("hash", "N/A")
    hash_short = tx_hash
    if tx_hash != "N/A" and len(tx_hash) > 14:
        hash_short = f"{tx_hash[:8]}...{tx_hash[-6:]}"
    
    # Etherscan link
    etherscan_link = None
    if tx_hash != "N/A" and tx_hash.startswith("0x"):
        etherscan_link = f"https://etherscan.io/tx/{tx_hash}"
    
    return {
        "time": time_str,
        "block": tx.get("blockNumber", "N/A"),
        "direction": direction,
        "from": tx.get("from", "N/A"),
        "to": tx.get("to", "N/A"),
        "value_eth": f"{value_eth:.6f}",
        "hash": tx_hash,
        "hash_short": hash_short,
        "etherscan_link": etherscan_link,
        "tx_fee_eth": f"{tx_fee_eth:.6f}" if tx_fee_eth is not None else None
    }


def get_coverage_status(coverage_start: Optional[int], coverage_end: Optional[int], latest_block: Optional[int], done: bool) -> dict:
    """Generate coverage status information for display."""
    if coverage_start is None or coverage_end is None or latest_block is None:
        return {"text": "N/A", "status": "unknown", "icon": "❓"}
    
    if done and coverage_end >= latest_block:
        return {
            "text": f"{coverage_start:,} → {coverage_end:,} (latest: {latest_block:,})",
            "status": "complete",
            "icon": "✅"
        }
    elif done:
        return {
            "text": f"{coverage_start:,} → {coverage_end:,} (latest: {latest_block:,})",
            "status": "stopped_early",
            "icon": "⚠️"
        }
    else:
        return {
            "text": f"{coverage_start:,} → {coverage_end:,} (latest: {latest_block:,})",
            "status": "in_progress",
            "icon": "🔄"
        }


def format_token_transfer(tx: dict, address: str) -> dict:
    """Format an ERC-20 token transfer for display."""
    tx_from = tx.get("from", "").lower()
    tx_to = tx.get("to", "").lower()
    address_lower = address.lower()
    
    # Determine direction
    if tx_from == address_lower:
        direction = "OUT"
    elif tx_to == address_lower:
        direction = "IN"
    else:
        direction = "UNKNOWN"
    
    # Format timestamp
    timestamp = tx.get("timeStamp", "0")
    try:
        dt = datetime.utcfromtimestamp(int(timestamp))
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError):
        time_str = "N/A"
    
    # Calculate token amount using tokenDecimal
    token_decimal = int(tx.get("tokenDecimal", "18"))
    value_raw = tx.get("value", "0")
    try:
        value_int = int(value_raw)
        amount = value_int / (10 ** token_decimal)
        amount_str = f"{amount:.6f}"
    except (ValueError, TypeError):
        amount_str = "N/A"
    
    return {
        "time": time_str,
        "block": tx.get("blockNumber", "N/A"),
        "direction": direction,
        "token_symbol": tx.get("tokenSymbol", "N/A"),
        "token_name": tx.get("tokenName", "N/A"),
        "amount": amount_str,
        "from": tx.get("from", "N/A"),
        "to": tx.get("to", "N/A"),
        "contract_address": tx.get("contractAddress", "N/A"),
        "hash": tx.get("hash", "N/A")
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/crawl_all_start", response_class=HTMLResponse)
def crawl_all_start(
    request: Request,
    address: str = Query(...),
    start_block: int = Query(...),
    include_tokens: bool = Query(False),
    max_pages: Optional[str] = Query(None),
    page_size: int = Query(200)
):
    """Start a background crawl_all job."""
    error = None
    
    # Validate inputs (same as /crawl)
    if not address or not address.startswith("0x"):
        error = "Invalid Ethereum address. Must start with 0x."
    elif start_block < 0:
        error = "Start block must be non-negative."
    elif not client:
        error = "Etherscan API key not configured. Please check .env file."
    else:
        # Parse max_pages
        max_pages_int = None
        if max_pages is not None and max_pages.strip() != "":
            try:
                max_pages_int = int(max_pages.strip())
                if max_pages_int < 1:
                    error = "max_pages must be >= 1"
            except ValueError:
                error = "max_pages must be a valid number"
        
        if not error:
            # Validate and clamp page_size
            page_size = max(50, min(500, page_size))
            
            # Create job
            job_id = uuid.uuid4().hex[:12]
            
            with JOBS_LOCK:
                # Clean up old jobs if over limit (FIFO)
                JOB_IDS.append(job_id)
                if len(JOB_IDS) > JOBS_SIZE_LIMIT:
                    oldest_job_id = JOB_IDS.pop(0)
                    if oldest_job_id in JOBS:
                        del JOBS[oldest_job_id]
                
                JOBS[job_id] = {
                    "address": address,
                    "start_block": start_block,
                    "include_tokens": include_tokens,
                    "page_size": page_size,
                    "max_pages_int": max_pages_int,
                    "latest_block": None,
                    "seg_start": start_block,
                    "window_blocks": MAX_WINDOW_BLOCKS,
                    "pages_total": 0,
                    "segments_done": 0,
                    "eth_total_unique": 0,
                    "current_segment_start": None,
                    "current_segment_end": None,
                    "coverage_start": start_block,
                    "coverage_end": start_block - 1,  # Will be updated as segments complete
                    "stop_requested": False,
                    "running": False,
                    "done": False,
                    "paused": False,
                    "error": None,
                    "rid": None,
                    "seen_hashes": {},  # Deduplication dict: hash -> raw tx dict
                    "segments": [],  # List of segment metadata
                    "partial_preview_eth": [],  # Raw tx dicts (up to RENDER_LIMIT_ETH)
                    "eth_preview": [],  # Formatted preview (last PREVIEW_LIMIT rows) - for backward compat
                    "token_seen_hashes": {},  # For token transfers if include_tokens
                    "token_preview": []  # Live token preview (last 200 formatted rows)
                }
            
            # Start background thread
            thread = threading.Thread(target=run_job, args=(job_id,), daemon=True)
            thread.start()
            
            return RedirectResponse(url=f"/progress?job_id={job_id}", status_code=303)
    
    # If error, show it
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error,
            "results": None
        }
    )


@app.get("/progress", response_class=HTMLResponse)
def progress(request: Request, job_id: str = Query(...)):
    """Display progress page for a crawl_all job."""
    print(f"[PROGRESS] Rendering progress page for job_id={job_id}", flush=True)
    if not job_id or job_id == "":
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": "Invalid job_id",
                "results": None
            }
        )
    return templates.TemplateResponse("progress.html", {"request": request, "job_id": job_id})


# Throttle status logging to reduce noise
_last_status_log_time: Dict[str, float] = {}
_STATUS_LOG_INTERVAL = 30.0  # Log status at most once per 30 seconds per job

@app.get("/crawl_status")
def crawl_status(job_id: str = Query(...)):
    """Return JSON status of a crawl_all job."""
    # Throttle logging to reduce noise
    current_time = time.time()
    should_log = False
    if job_id not in _last_status_log_time:
        should_log = True
        _last_status_log_time[job_id] = current_time
    elif current_time - _last_status_log_time[job_id] >= _STATUS_LOG_INTERVAL:
        should_log = True
        _last_status_log_time[job_id] = current_time
    
    if should_log:
        print(f"[STATUS] job {job_id} requested", flush=True)
    
    with JOBS_LOCK:
        if job_id not in JOBS:
            if should_log:
                print(f"[STATUS] job {job_id} not found", flush=True)
            return JSONResponse({"error": "Job not found"}, status_code=404)
        
        job = JOBS[job_id]
        
        eth_total_unique = job.get("eth_total_unique", 0)
        status = {
            "running": job.get("running", False),
            "done": job.get("done", False),
            "paused": job.get("paused", False),
            "error": job.get("error"),
            "latest_block": job.get("latest_block"),
            "current_segment_start": job.get("current_segment_start"),
            "current_segment_end": job.get("current_segment_end"),
            "segments_done": job.get("segments_done", 0),
            "pages_total": job.get("pages_total", 0),
            "eth_total_unique": eth_total_unique,
            "stop_requested": job.get("stop_requested", False),
            "rid": None,
            "eth_preview": job.get("eth_preview", []),  # Last 200 formatted rows for live preview
            "token_preview": job.get("token_preview", []),  # Last 200 formatted token rows
            "high_activity": job.get("high_activity", False),  # High activity warning flag
            "high_activity_reason": job.get("high_activity_reason", ""),  # Explanation string
            "window_blocks": job.get("window_blocks", MAX_WINDOW_BLOCKS),  # Current window size
            "coverage_start": job.get("coverage_start", job.get("start_block", 0)),
            "coverage_end": job.get("coverage_end", job.get("start_block", 0) - 1),
            "has_partial": eth_total_unique > 0  # Flag indicating partial results available
        }
        
        if job.get("done") and job.get("rid"):
            status["rid"] = job["rid"]
        
        if should_log:
            print(f"[STATUS] job {job_id} response: running={status['running']}, done={status['done']}, paused={status['paused']}, segments={status['segments_done']}", flush=True)
        return JSONResponse(status)


@app.get("/crawl_stop")
def crawl_stop(job_id: str = Query(...)):
    """Stop a running crawl_all job."""
    with JOBS_LOCK:
        if job_id not in JOBS:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        
        JOBS[job_id]["stop_requested"] = True
        return JSONResponse({"status": "stop_requested"})


@app.get("/crawl_resume")
def crawl_resume(job_id: str = Query(...)):
    """Resume a stopped crawl_all job."""
    with JOBS_LOCK:
        if job_id not in JOBS:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        
        job = JOBS[job_id]
        
        # Check if job can be resumed (paused, not running, not done)
        if not job.get("paused", False):
            return JSONResponse({"error": "Job is not paused"}, status_code=400)
        if job.get("running", False):
            return JSONResponse({"error": "Job is already running"}, status_code=400)
        if job.get("done", False):
            return JSONResponse({"error": "Job is already done"}, status_code=400)
        
        # Reset pause state and start new thread
        job["paused"] = False
        job["stop_requested"] = False
        job["running"] = True
        job["error"] = None
        
        # Ensure seg_start is set correctly (should be coverage_end + 1, or use saved seg_start)
        if job.get("coverage_end") is not None:
            # Resume from after the last completed segment
            job["seg_start"] = job["coverage_end"] + 1
        # Otherwise use saved seg_start
        
        thread = threading.Thread(target=run_job, args=(job_id,), daemon=True)
        thread.start()
        
        return JSONResponse({"status": "resumed"})


@app.get("/results/download")
def download_results(rid: str = Query(...)):
    """
    Download crawl_all results as CSV.
    Streams all collected transactions (not just preview).
    """
    if rid not in RESULTS_CACHE:
        return HTMLResponse(
            content="<h1>Error</h1><p>Result not found. It may have expired.</p>",
            status_code=404
        )
    
    cache_entry = RESULTS_CACHE[rid]
    # Normalize to always be a list (never None)
    eth_txs = cache_entry.get("eth_txs") or []
    address = cache_entry.get("address", "unknown")
    start_block = cache_entry.get("start_block", 0)
    
    # Handle empty list
    if not eth_txs:
        return HTMLResponse(
            content="<h1>Error</h1><p>No ETH transactions found in this result.</p>",
            status_code=404
        )
    
    # Generate filename
    filename = f"eth_txs_{address}_{start_block}_to_latest.csv"
    
    # Create CSV generator
    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(["time", "block", "direction", "from", "to", "value", "hash"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        
        # Write rows
        for tx in eth_txs:
            # Determine direction
            tx_from = tx.get("from", "").lower()
            tx_to = tx.get("to", "").lower()
            address_lower = address.lower()
            
            if tx_from == address_lower:
                direction = "OUT"
            elif tx_to == address_lower:
                direction = "IN"
            else:
                direction = "UNKNOWN"
            
            # Format timestamp
            timestamp = tx.get("timeStamp", "0")
            try:
                dt = datetime.utcfromtimestamp(int(timestamp))
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except (ValueError, TypeError):
                time_str = "N/A"
            
            # Format value (in ETH)
            value_wei = tx.get("value", "0")
            value_eth = wei_to_eth(value_wei)
            
            # Write row
            writer.writerow([
                time_str,
                tx.get("blockNumber", "N/A"),
                direction,
                tx.get("from", "N/A"),
                tx.get("to", "N/A"),
                f"{value_eth:.6f}",
                tx.get("hash", "N/A")
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
    
    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/results/download_tokens")
def download_token_results(rid: str = Query(...)):
    """
    Download crawl_all token transfer results as CSV.
    Streams all collected token transfers (not just preview).
    """
    if rid not in RESULTS_CACHE:
        return HTMLResponse(
            content="<h1>Error</h1><p>Result not found. It may have expired.</p>",
            status_code=404
        )
    
    cache_entry = RESULTS_CACHE[rid]
    
    # Normalize to always be a list (never None)
    token_txs = cache_entry.get("token_txs") or []
    address = cache_entry.get("address", "unknown")
    start_block = cache_entry.get("start_block", 0)
    
    # Handle empty list with friendly message
    if not token_txs:
        return HTMLResponse(
            content="<h1>Error</h1><p>No token transfers found in this result.</p>",
            status_code=404
        )
    
    # Generate filename
    filename = f"token_txs_{address}_{start_block}_to_latest.csv"
    
    # Create CSV generator
    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(["time", "block", "direction", "token_symbol", "token_name", "amount", "from", "to", "contract_address", "hash"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        
        # Write rows
        for tx in token_txs:
            # Determine direction
            tx_from = tx.get("from", "").lower()
            tx_to = tx.get("to", "").lower()
            address_lower = address.lower()
            
            if tx_from == address_lower:
                direction = "OUT"
            elif tx_to == address_lower:
                direction = "IN"
            else:
                direction = "UNKNOWN"
            
            # Format timestamp
            timestamp = tx.get("timeStamp", "0")
            try:
                dt = datetime.utcfromtimestamp(int(timestamp))
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except (ValueError, TypeError):
                time_str = "N/A"
            
            # Format token amount using tokenDecimal (fallback to 18)
            token_decimal = int(tx.get("tokenDecimal", "18"))
            value_raw = tx.get("value", "0")
            try:
                value_int = int(value_raw)
                amount = value_int / (10 ** token_decimal)
                amount_str = f"{amount:.6f}"
            except (ValueError, TypeError):
                amount_str = "0"
            
            # Write row
            writer.writerow([
                time_str,
                tx.get("blockNumber", "N/A"),
                direction,
                tx.get("tokenSymbol", "N/A"),
                tx.get("tokenName", "N/A"),
                amount_str,
                tx.get("from", "N/A"),
                tx.get("to", "N/A"),
                tx.get("contractAddress", "N/A"),
                tx.get("hash", "N/A")
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
    
    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


def run_job(job_id: str):
    """
    Background job function that performs segmented crawling.
    Updates JOBS[job_id] with progress and final results.
    """
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["running"] = True
        job["paused"] = False
        job["done"] = False
        job["error"] = None
    
    try:
        address = job["address"]
        start_block = job["start_block"]
        include_tokens = job["include_tokens"]
        page_size = job["page_size"]
        max_pages_int = job["max_pages_int"]
        
        # Get latest block once
        latest_block = client.get_latest_block()
        with JOBS_LOCK:
            job["latest_block"] = latest_block
        
        # Initialize state (restore from saved state if resuming)
        # Use job state as source of truth - work with reference but persist frequently
        with JOBS_LOCK:
            if "seen_hashes" not in job:
                job["seen_hashes"] = {}
            if "segments" not in job:
                job["segments"] = []
            if "partial_preview_eth" not in job:
                job["partial_preview_eth"] = []
        
        # Get references to job state (will persist after each segment)
        all_txs_raw_dict = job["seen_hashes"]  # Work directly with job state
        pages_total = job.get("pages_total", 0)
        segments = job["segments"]  # Work directly with job state
        window_blocks = job.get("window_blocks", MAX_WINDOW_BLOCKS)
        seg_start = job.get("seg_start", start_block)
        segment_num = job.get("segments_done", 0)
        coverage_start = job.get("coverage_start", start_block)
        
        while seg_start <= latest_block:
            # Check stop request
            with JOBS_LOCK:
                if job.get("stop_requested", False):
                    job["running"] = False
                    job["done"] = False  # Not done, just paused
                    job["paused"] = True
                    job["stop_requested"] = False  # Reset stop flag
                    job["error"] = None  # No error, just paused
                    job["seg_start"] = seg_start  # Save state for resume
                    job["window_blocks"] = window_blocks  # Save window size
                    job["pages_total"] = pages_total  # Save pages total
                    job["segments_done"] = segment_num  # Save segment count
                    # seen_hashes and segments are already in job state (we work with references)
                    # Update coverage_end from last completed segment
                    if segments:
                        job["coverage_end"] = segments[-1]["end"]
                    print(f"[JOB {job_id}] Paused by user at segment {segment_num}, seg_start={seg_start}, collected={len(all_txs_raw_dict)}", flush=True)
                    return
            
            seg_end = min(seg_start + window_blocks - 1, latest_block)
            segment_num += 1
            
            print(f"[JOB {job_id}] ETH segment {segment_num}: {seg_start}-{seg_end} (window={window_blocks})", flush=True)
            
            # Create should_stop callback that checks job state
            def should_stop_check():
                with JOBS_LOCK:
                    return job.get("stop_requested", False)
            
            # Safety check: prevent infinite loops
            if segment_num > SAFETY_MAX_SEGMENTS:
                with JOBS_LOCK:
                    job["running"] = False
                    job["done"] = True
                    job["error"] = f"Safety limit reached: {SAFETY_MAX_SEGMENTS} segments. Address may be too active for this range."
                return
            
            # Fetch this window
            window_txs, pages_used, cap_hit, window_truncated, paused_hit, cap_unresolvable = fetch_txlist_window(
                client, address, seg_start, seg_end, page_size, pages_total, max_pages_int, should_stop_check, MIN_WINDOW_BLOCKS
            )
            
            pages_total += pages_used
            
            # Check if paused (stop requested during fetch)
            if paused_hit:
                with JOBS_LOCK:
                    job["running"] = False
                    job["done"] = False  # Not done, just paused
                    job["paused"] = True
                    job["stop_requested"] = False  # Reset stop flag
                    job["error"] = None  # No error, just paused
                    job["seg_start"] = seg_start  # Save state for resume
                    job["window_blocks"] = window_blocks  # Save window size
                    job["pages_total"] = pages_total  # Save pages total
                    job["segments_done"] = segment_num  # Save segment count
                    # seen_hashes and segments are already in job state (we work with references)
                    # Update coverage_end from last completed segment
                    if segments:
                        job["coverage_end"] = segments[-1]["end"]
                print(f"[JOB {job_id}] Paused by user at segment {segment_num}, seg_start={seg_start}, collected={len(all_txs_raw_dict)}", flush=True)
                return
            
            # Check max_pages limit
            if window_truncated:
                with JOBS_LOCK:
                    job["running"] = False
                    job["done"] = True
                    job["error"] = "Stopped due to max_pages limit"
                break
            
            # If cap hit, reduce window size and retry
            if cap_hit:
                if cap_unresolvable:
                    # Even at minimum window (1 block), we hit the cap
                    with JOBS_LOCK:
                        job["running"] = False
                        job["done"] = True
                        job["error"] = f"Even a window of {window_blocks} block(s) exceeds Etherscan cap (~10,000 records). Cannot guarantee ALL results via Etherscan for this address in this range. Consider using a smaller start_block or switching to a node-based approach."
                    return
                
                # Reduce window size and retry
                if window_blocks > MIN_WINDOW_BLOCKS:
                    window_blocks = max(window_blocks // 2, MIN_WINDOW_BLOCKS)
                    segment_num -= 1  # Don't count this as a completed segment
                    print(f"[JOB {job_id}] Cap hit at window={window_blocks*2}, reducing to {window_blocks} and retrying", flush=True)
                    
                    # Check for high activity condition
                    with JOBS_LOCK:
                        if window_blocks <= 1000 and not job.get("high_activity", False):
                            job["high_activity"] = True
                            job["high_activity_reason"] = f"Window reduced to {window_blocks} blocks due to Etherscan cap"
                            print(f"[JOB {job_id}] High activity detected: window={window_blocks}", flush=True)
                    
                    continue
                else:
                    # Should not happen (cap_unresolvable should be set), but safety check
                    with JOBS_LOCK:
                        job["running"] = False
                        job["done"] = True
                        job["error"] = f"Cap hit at minimum window size ({MIN_WINDOW_BLOCKS} blocks). Cannot proceed."
                    return
            
            # Add transactions (deduplicate)
            for tx in window_txs:
                tx_hash = tx.get("hash")
                if tx_hash:
                    # Add to deduplication dict (already a reference to job state)
                    all_txs_raw_dict[tx_hash] = tx
            
            # Add segment metadata
            segments.append({
                "start": seg_start,
                "end": seg_end,
                "pages": pages_used,
                "tx_count": len(window_txs),
                "cap_hit": False
            })
            
            # Update partial preview with raw tx dicts (up to RENDER_LIMIT_ETH)
            with JOBS_LOCK:
                partial_preview = job.get("partial_preview_eth", [])
                # Add new transactions to preview (raw dicts, not formatted)
                for tx in window_txs:
                    if len(partial_preview) < RENDER_LIMIT_ETH:
                        partial_preview.append(tx)
                    else:
                        break  # Already at limit
                job["partial_preview_eth"] = partial_preview
                
                # Also maintain formatted preview for backward compatibility (last PREVIEW_LIMIT)
                formatted_preview = job.get("eth_preview", [])
                for tx in window_txs:
                    formatted = format_transaction(tx, address)
                    formatted_preview.append(formatted)
                    if len(formatted_preview) > PREVIEW_LIMIT:
                        formatted_preview.pop(0)  # Remove oldest
                job["eth_preview"] = formatted_preview
            
            # Update progress state after segment completion
            with JOBS_LOCK:
                job["seg_start"] = seg_end + 1
                job["segments_done"] = segment_num
                job["pages_total"] = pages_total
                job["eth_total_unique"] = len(all_txs_raw_dict)
                job["current_segment_start"] = seg_start
                job["current_segment_end"] = seg_end
                job["window_blocks"] = window_blocks
                job["coverage_end"] = seg_end  # Update coverage_end after successful segment
                # Store last 10 segments metadata to avoid memory blow
                job["segments_tail"] = segments[-10:] if len(segments) > 10 else segments
                
                # Check for high activity condition (segment count)
                if segment_num >= 2000 and not job.get("high_activity", False):
                    job["high_activity"] = True
                    job["high_activity_reason"] = f"Segments exceeded 2000 (currently {segment_num})"
                    print(f"[JOB {job_id}] High activity detected: {segment_num} segments", flush=True)
                
                # Also check window size (in case it was reduced earlier)
                if window_blocks <= 1000 and not job.get("high_activity", False):
                    job["high_activity"] = True
                    job["high_activity_reason"] = f"Window reduced to {window_blocks} blocks due to Etherscan cap"
                    print(f"[JOB {job_id}] High activity detected: window={window_blocks}", flush=True)
            
            print(f"[JOB {job_id}] ETH segment {segment_num} done: txs={len(window_txs)} pages={pages_used} total_unique={len(all_txs_raw_dict)}", flush=True)
            
            # Move to next segment
            seg_start = seg_end + 1
            
            # Gradually increase window size if reduced (but don't exceed MAX_WINDOW_BLOCKS)
            if window_blocks < MAX_WINDOW_BLOCKS:
                window_blocks = min(window_blocks * 2, MAX_WINDOW_BLOCKS)
        
        # Job completed successfully
        # Build final sorted list from job state (all_txs_raw_dict is a reference to job["seen_hashes"])
        all_txs_raw = sorted(
            all_txs_raw_dict.values(),
            key=lambda x: (int(x.get("blockNumber", 0)), int(x.get("timeStamp", 0)))
        )
        
        # Compute coverage from segments
        coverage_start = segments[0]["start"] if segments else start_block
        coverage_end = segments[-1]["end"] if segments else latest_block
        
        # Update job state with final coverage
        with JOBS_LOCK:
            job["coverage_end"] = coverage_end
        
        # Create result_id and store in cache
        result_id = str(uuid.uuid4())
        
        # Collect token transactions if include_tokens is True
        token_txs_data = None
        if include_tokens:
            # Token transactions should be collected in a similar segmented way
            # For now, we'll check if they exist in the job state
            with JOBS_LOCK:
                token_seen_hashes = job.get("token_seen_hashes", {})
                if token_seen_hashes:
                    token_txs_data = sorted(
                        token_seen_hashes.values(),
                        key=lambda x: (int(x.get("blockNumber", 0)), int(x.get("timeStamp", 0)))
                    )
        
        RESULTS_CACHE[result_id] = {
            "eth_txs": all_txs_raw,
            "address": address,
            "start_block": start_block,
            "latest_block": latest_block,
            "eth_total": len(all_txs_raw),
            "coverage_start": coverage_start,
            "coverage_end": coverage_end,
            "segments": segments,
            "include_tokens": include_tokens,
            "token_txs": token_txs_data  # Will be populated if tokens were collected
        }
        
        # Manage cache size
        RESULT_IDS.append(result_id)
        if len(RESULT_IDS) > CACHE_SIZE_LIMIT:
            oldest_rid = RESULT_IDS.pop(0)
            if oldest_rid in RESULTS_CACHE:
                del RESULTS_CACHE[oldest_rid]
        
        # Update job status
        with JOBS_LOCK:
            job["running"] = False
            job["done"] = True
            job["rid"] = result_id
            job["eth_total_unique"] = len(all_txs_raw)
            
            # Store token_txs in cache if available
            if include_tokens:
                # Note: token_txs should be stored in RESULTS_CACHE by the job runner
                # This is just for reference
                pass
        
        print(f"[JOB {job_id}] Completed: {len(all_txs_raw)} unique transactions, rid={result_id}", flush=True)
        
        # Clean up job after completion (optional: keep for a while, or delete immediately)
        # For now, keep jobs in memory until they're pushed out by FIFO limit
        
    except Exception as e:
        with JOBS_LOCK:
            job["running"] = False
            job["done"] = True
            job["error"] = f"Error: {str(e)}"
        print(f"[JOB {job_id}] Error: {str(e)}", flush=True)


def fetch_txlist_window(
    client: EtherscanClient,
    address: str,
    start_blk: int,
    end_blk: int,
    page_size: int,
    pages_total: int,
    max_pages_int: Optional[int],
    should_stop: Optional[Callable[[], bool]] = None,
    min_window_blocks: int = MIN_WINDOW_BLOCKS
) -> Tuple[List[dict], int, bool, bool, bool, bool]:
    """
    Fetch ALL pages for a block window [start_blk, end_blk].
    Returns: (txs_list, pages_used, cap_hit, truncated, paused_hit, cap_unresolvable)
    
    Cap detection: Etherscan limits account endpoints to ~10,000 records per query.
    We calculate max_pages_for_offset based on page_size to detect when we hit the cap.
    
    cap_unresolvable: True if cap was hit even at min_window_blocks (cannot split further).
    
    should_stop: Optional callback that returns True if job should pause.
    min_window_blocks: Minimum window size before marking cap as unresolvable.
    """
    collected = []
    current_page = 1
    cap_hit = False
    truncated = False
    paused_hit = False
    cap_unresolvable = False  # Initialize to False
    
    # Calculate max pages for this page_size before hitting the cap
    max_pages_for_offset = math.ceil(MAX_RECORDS_PER_QUERY / page_size)
    
    while True:
        # Check stop request before each page fetch
        if should_stop and should_stop():
            paused_hit = True
            break
        
        # Check global max_pages limit (across all segments)
        if max_pages_int is not None and pages_total + current_page > max_pages_int:
            truncated = True
            break
        
        # Fetch page
        chunk = client.txlist_page(
            address,
            start_blk,
            end_blk,
            page=current_page,
            offset=page_size
        )
        
        collected.extend(chunk)
        
        # Check stop request after each page fetch
        if should_stop and should_stop():
            paused_hit = True
            break
        
        # Stop if we got less than a full page (end of results)
        if len(chunk) < page_size:
            break
        
        current_page += 1
        
        # Cap detection: if we hit max_pages_for_offset with full results, likely cap hit
        # OR if total collected >= MAX_RECORDS_PER_QUERY
        if (current_page > max_pages_for_offset and len(chunk) == page_size) \
           or len(collected) >= MAX_RECORDS_PER_QUERY:
            cap_hit = True
            # Check if we're at minimum window size - if so, cap is unresolvable
            window_size = end_blk - start_blk + 1
            if window_size <= min_window_blocks:
                cap_unresolvable = True
            break
    
    return collected, current_page, cap_hit, truncated, paused_hit, cap_unresolvable


def fetch_tokentx_window(
    client: EtherscanClient,
    address: str,
    start_blk: int,
    end_blk: int,
    page_size: int,
    pages_total: int,
    max_pages_int: Optional[int],
    should_stop: Optional[Callable[[], bool]] = None,
    min_window_blocks: int = MIN_WINDOW_BLOCKS
) -> Tuple[List[dict], int, bool, bool, bool, bool]:
    """
    Fetch ALL token transfer pages for a block window [start_blk, end_blk].
    Same cap detection logic as fetch_txlist_window.
    Returns: (txs_list, pages_used, cap_hit, truncated, paused_hit, cap_unresolvable)
    
    cap_unresolvable: True if cap was hit even at min_window_blocks (cannot split further).
    
    should_stop: Optional callback that returns True if job should pause.
    min_window_blocks: Minimum window size before marking cap as unresolvable.
    """
    collected = []
    current_page = 1
    cap_hit = False
    truncated = False
    paused_hit = False
    cap_unresolvable = False
    
    # Calculate max pages for this page_size before hitting the cap
    max_pages_for_offset = math.ceil(MAX_RECORDS_PER_QUERY / page_size)
    
    # Check if this is a single block window that still hits cap
    window_size = end_blk - start_blk + 1
    if window_size <= min_window_blocks:
        # If we're already at minimum window, we'll mark as unresolvable if cap is hit
        pass
    
    while True:
        # Check stop request before each page fetch
        if should_stop and should_stop():
            paused_hit = True
            break
        
        # Check global max_pages limit
        if max_pages_int is not None and pages_total + current_page > max_pages_int:
            truncated = True
            break
        
        # Fetch page
        chunk = client.tokentx_page(
            address,
            start_blk,
            end_blk,
            page=current_page,
            offset=page_size
        )
        
        collected.extend(chunk)
        
        # Check stop request after each page fetch
        if should_stop and should_stop():
            paused_hit = True
            break
        
        # Stop if we got less than a full page
        if len(chunk) < page_size:
            break
        
        current_page += 1
        
        # Cap detection: if we hit max_pages_for_offset with full results, likely cap hit
        # OR if total collected >= MAX_RECORDS_PER_QUERY
        if (current_page > max_pages_for_offset and len(chunk) == page_size) \
           or len(collected) >= MAX_RECORDS_PER_QUERY:
            cap_hit = True
            # Check if we're at minimum window size - if so, cap is unresolvable
            window_size = end_blk - start_blk + 1
            if window_size <= min_window_blocks:
                cap_unresolvable = True
            break
    
    return collected, current_page, cap_hit, truncated, paused_hit, cap_unresolvable


@app.get("/crawl", response_class=HTMLResponse)
def crawl(
    request: Request,
    address: str,
    start_block: int,
    include_tokens: bool = False,
    mode: Optional[str] = Query(None),
    crawl_all: bool = Query(False),  # Backward compatibility
    max_pages: Optional[str] = Query(None),
    page: int = 1,
    token_page: int = 1,
    page_size: int = 200
):
    error = None
    latest_block = None
    txs_page = []
    token_transfers = []
    token_count = 0
    has_next = False
    has_prev = False
    token_has_next = False
    token_has_prev = False
    all_mode_pages = 0
    all_mode_truncated = False
    token_all_mode_pages = 0
    token_all_mode_truncated = False
    segments = []
    token_segments = []
    result_id = None  # For CSV export in crawl_all mode
    coverage_start = None
    coverage_end = None
    # Render limits are defined at module level (RENDER_LIMIT_ETH, RENDER_LIMIT_TOKENS)
    eth_total = None
    eth_rendered = None
    token_total = None
    token_rendered = None
    
    # Parse mode parameter: convert to crawl_all boolean
    # Priority: mode parameter > crawl_all parameter (for backward compatibility)
    if mode is not None and mode.strip() != "":
        mode_lower = mode.lower().strip()
        if mode_lower == "all":
            crawl_all = True
        elif mode_lower == "browse":
            crawl_all = False
        else:
            # Invalid mode value, default to True (Crawl ALL)
            crawl_all = True
    # If mode not provided, use crawl_all parameter as-is (backward compatibility with existing URLs)
    # crawl_all defaults to False in Query(), but form will send mode=all by default
    
    # Parse max_pages: handle empty string from form submission
    # Browser sends max_pages="" when field is empty, which FastAPI can't parse as Optional[int]
    # So we accept str and parse it manually
    max_pages_int = None
    if max_pages is not None and max_pages.strip() != "":
        try:
            max_pages_int = int(max_pages.strip())
            if max_pages_int < 1:
                error = "max_pages must be >= 1"
        except ValueError:
            error = "max_pages must be a valid number"
    
    # Validate and clamp page_size
    page_size = max(50, min(500, page_size))
    page = max(1, page)
    token_page = max(1, token_page)
    
    # Validate inputs
    if not address or not address.startswith("0x"):
        error = "Invalid Ethereum address. Must start with 0x."
    elif start_block < 0:
        error = "Start block must be non-negative."
    elif not client:
        error = "Etherscan API key not configured. Please check .env file."
    else:
        try:
            # Get latest block
            latest_block = client.get_latest_block()
            
            if crawl_all:
                # CRAWL ALL MODE: Redirect to background job system
                from urllib.parse import urlencode
                params = {
                    "address": address,
                    "start_block": start_block,
                    "page_size": page_size
                }
                if include_tokens:
                    params["include_tokens"] = "true"
                if max_pages_int:
                    params["max_pages"] = str(max_pages_int)
                
                return RedirectResponse(url=f"/crawl_all_start?{urlencode(params)}", status_code=303)
            
            # NORMAL MODE: Fetch single page (existing logic)
            # Fetch single page from API (fast - one API call)
            txs_raw = client.txlist_page(
                address,
                start_block,
                latest_block,
                page=page,
                offset=page_size
            )
            
            # Format transactions
            txs_page = [format_transaction(tx, address) for tx in txs_raw]
            
            # Determine pagination state for ETH transactions
            has_prev = page > 1
            has_next = len(txs_raw) == page_size  # If we got a full page, there might be more
            
            # Fetch token transfers if requested
            if include_tokens:
                    token_txs_raw = client.tokentx_page(
                        address,
                        start_block,
                        latest_block,
                        page=token_page,
                        offset=page_size
                    )
                    
                    # Format token transfers
                    token_transfers = [format_token_transfer(tx, address) for tx in token_txs_raw]
                    
                    # Determine pagination state for token transfers
                    token_count = len(token_transfers)
                    token_has_prev = token_page > 1
                    token_has_next = len(token_txs_raw) == page_size
            
        except Exception as e:
            error = f"Error fetching transactions: {str(e)}"
    
    # Build results object for template
    results = None
    if address and not error:
        results = {
            "address": address,
            "start_block": start_block,
            "latest_block": latest_block,
            "include_tokens": include_tokens,
            "crawl_all": crawl_all,
            "max_pages": max_pages_int,
            "eth_count": len(txs_page),
            "txs_page": txs_page,
            "page": page if not crawl_all else 1,
            "has_prev": has_prev,
            "has_next": has_next,
            "token_count": token_count,
            "token_transfers": token_transfers,
            "token_page": token_page if not crawl_all else 1,
            "token_has_prev": token_has_prev,
            "token_has_next": token_has_next,
            "page_size": page_size,
            "all_mode_pages": all_mode_pages,
            "all_mode_truncated": all_mode_truncated,
            "segments": segments,
            "eth_total": eth_total if crawl_all else None,
            "eth_rendered": eth_rendered if crawl_all else None,
            "eth_render_limit": RENDER_LIMIT_ETH if crawl_all else None,
            "token_all_mode_pages": token_all_mode_pages if include_tokens else 0,
            "token_all_mode_truncated": token_all_mode_truncated if include_tokens else False,
            "token_segments": token_segments if include_tokens else [],
            "token_total": token_total if (include_tokens and crawl_all) else None,
            "token_rendered": token_rendered if (include_tokens and crawl_all) else None,
            "token_render_limit": RENDER_LIMIT_TOKENS if (include_tokens and crawl_all) else None,
            "result_id": result_id if crawl_all else None,
            "coverage_start": coverage_start if crawl_all else None,
            "coverage_end": coverage_end if crawl_all else None
        }
    
    # Redirect to /results for crawl_all mode to prevent refresh re-running crawl
    if crawl_all and result_id and not error:
        return RedirectResponse(url=f"/results?rid={result_id}", status_code=303)
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error,
            "results": results
        }
    )


@app.get("/results", response_class=HTMLResponse)
def show_results(request: Request, rid: str = Query(None)):
    """
    Display cached crawl_all results without re-running crawl.
    Prevents refresh from re-running expensive crawl operations.
    """
    # Guard: if rid is missing, show friendly error
    if not rid:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": "Result ID is missing. Please run a new crawl.",
                "results": None
            }
        )
    
    if rid not in RESULTS_CACHE:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": "Result not found or expired. Please run a new crawl.",
                "results": None
            }
        )
    
    cache_entry = RESULTS_CACHE[rid]
    
    # Extract cached data
    address = cache_entry["address"]
    start_block = cache_entry["start_block"]
    latest_block = cache_entry["latest_block"]
    coverage_start = cache_entry.get("coverage_start", start_block)
    coverage_end = cache_entry.get("coverage_end", latest_block)
    segments = cache_entry.get("segments", [])
    include_tokens = cache_entry.get("include_tokens", False)
    
    # Normalize cached lists to always be lists (never None)
    all_txs_raw = cache_entry.get("eth_txs") or []
    token_txs = cache_entry.get("token_txs") or []
    
    # Compute eth_total and render limits
    eth_total = cache_entry.get("eth_total")
    if eth_total is None:
        eth_total = len(all_txs_raw)
    eth_rendered = min(RENDER_LIMIT_ETH, eth_total)
    
    # Format preview rows
    txs_page = [format_transaction(tx, address) for tx in all_txs_raw[:eth_rendered]]
    
    # Token data - rely ONLY on cache_entry, normalize None to empty list
    token_total = cache_entry.get("token_total")
    if token_total is None:
        token_total = len(token_txs)
    token_rendered = min(RENDER_LIMIT_TOKENS, token_total) if token_total > 0 else 0
    token_transfers = []
    token_count = 0
    token_segments = []
    token_all_mode_pages = 0
    token_all_mode_truncated = False
    
    if include_tokens and token_txs:
        # Format only the preview rows
        token_transfers = [format_token_transfer(tx, address) for tx in token_txs[:token_rendered]]
        token_count = len(token_transfers)
        token_segments = cache_entry.get("token_segments", [])
        # Estimate pages (not stored, but not critical for display)
        token_all_mode_pages = len(token_segments)  # Rough estimate
    
    # Build results dict for template
    # Generate coverage status
    coverage_status = get_coverage_status(coverage_start, coverage_end, latest_block, done=True)
    
    results = {
        "address": address,
        "start_block": start_block,
        "latest_block": latest_block,
        "include_tokens": include_tokens,
        "crawl_all": True,
        "done": True,
        "paused": False,
        "max_pages": None,
        "eth_count": len(txs_page),
        "txs_page": txs_page,
        "page": 1,
        "has_prev": False,
        "has_next": False,
        "token_count": token_count,
        "token_transfers": token_transfers,
        "token_page": 1,
        "token_has_prev": False,
        "token_has_next": False,
        "page_size": 200,
        "all_mode_pages": len(segments),  # Rough estimate
        "all_mode_truncated": False,
        "segments": segments,
        "eth_total": eth_total,
        "eth_rendered": eth_rendered,
        "eth_render_limit": RENDER_LIMIT_ETH,
        "token_all_mode_pages": token_all_mode_pages,
        "token_all_mode_truncated": token_all_mode_truncated,
        "token_segments": token_segments,
        "token_total": token_total if include_tokens else None,
        "token_rendered": token_rendered if include_tokens else None,
        "token_render_limit": RENDER_LIMIT_TOKENS if include_tokens else None,
        "result_id": rid,
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "coverage_status": coverage_status
    }
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": None,
            "results": results
        }
    )


@app.get("/results_partial", response_class=HTMLResponse)
def results_partial(request: Request, job_id: str = Query(...)):
    """
    Display partial results from a paused or running crawl_all job.
    Shows preview of data collected so far.
    """
    with JOBS_LOCK:
        if job_id not in JOBS:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "error": "Job not found or expired.",
                    "results": None
                }
            )
        
        job = JOBS[job_id]
    
    # Build results dict for template (partial results)
    address = job["address"]
    start_block = job["start_block"]
    latest_block = job.get("latest_block")
    include_tokens = job.get("include_tokens", False)
    
    # Get all collected transactions so far from raw dict (for up to 2000 display)
    all_txs_raw_dict = job.get("seen_hashes", {})  # This is the dedupe dict
    eth_total_so_far = len(all_txs_raw_dict)
    
    # Use partial_preview_eth if available (raw dicts), otherwise sort all
    if job.get("partial_preview_eth") and len(job["partial_preview_eth"]) > 0:
        # Use preview (already limited to RENDER_LIMIT_ETH)
        preview_raw = job["partial_preview_eth"]
        # Sort preview by block and timestamp
        preview_sorted = sorted(
            preview_raw,
            key=lambda x: (int(x.get("blockNumber", 0)), int(x.get("timeStamp", 0)))
        )
        eth_rendered = len(preview_sorted)
        txs_page = [format_transaction(tx, address) for tx in preview_sorted]
    else:
        # Fallback: sort all and take first RENDER_LIMIT_ETH
        all_txs_raw = sorted(
            all_txs_raw_dict.values(),
            key=lambda x: (int(x.get("blockNumber", 0)), int(x.get("timeStamp", 0)))
        )
        eth_rendered = min(RENDER_LIMIT_ETH, eth_total_so_far)
        txs_page = [format_transaction(tx, address) for tx in all_txs_raw[:eth_rendered]]
    
    # Token data
    token_transfers = []
    token_count = 0
    token_total = 0
    token_rendered = 0
    
    if include_tokens:
        token_raw_dict = job.get("token_seen_hashes", {})
        if token_raw_dict:
            all_token_txs_raw = sorted(
                token_raw_dict.values(),
                key=lambda x: (int(x.get("blockNumber", 0)), int(x.get("timeStamp", 0)))
            )
            token_total = len(all_token_txs_raw)
            token_rendered = min(RENDER_LIMIT_TOKENS, token_total)
            token_transfers = [format_token_transfer(tx, address) for tx in all_token_txs_raw[:token_rendered]]
            token_count = len(token_transfers)
    
    # Generate coverage status for partial results
    partial_coverage_start = job.get("coverage_start", start_block)
    partial_coverage_end = job.get("coverage_end", job.get("current_segment_end", start_block - 1))
    partial_done = job.get("done", False)
    partial_paused = job.get("paused", False)
    coverage_status = get_coverage_status(partial_coverage_start, partial_coverage_end, latest_block, partial_done)
    
    results = {
        "address": address,
        "start_block": start_block,
        "latest_block": latest_block,
        "include_tokens": include_tokens,
        "crawl_all": True,
        "partial": True,  # Flag to show this is partial results
        "done": partial_done,
        "paused": partial_paused,
        "max_pages": None,
        "eth_count": len(txs_page),
        "txs_page": txs_page,
        "page": 1,
        "has_prev": False,
        "has_next": False,
        "token_count": token_count,
        "token_transfers": token_transfers,
        "token_page": 1,
        "token_has_prev": False,
        "token_has_next": False,
        "page_size": 200,
        "all_mode_pages": job.get("segments_done", 0),
        "all_mode_truncated": False,
        "segments": job.get("segments", []),
        "segments_done": job.get("segments_done", 0),
        "pages_total": job.get("pages_total", 0),
        "current_segment_start": job.get("current_segment_start"),
        "current_segment_end": job.get("current_segment_end"),
        "eth_total": eth_total_so_far,
        "eth_rendered": eth_rendered,
        "eth_render_limit": RENDER_LIMIT_ETH,
        "token_all_mode_pages": 0,
        "token_all_mode_truncated": False,
        "token_segments": [],
        "token_total": token_total if include_tokens else None,
        "token_rendered": token_rendered if include_tokens else None,
        "token_render_limit": RENDER_LIMIT_TOKENS if include_tokens else None,
        "result_id": None,  # No rid for partial results
        "result_source": "job",  # Flag for partial download
        "job_id": job_id,  # Store job_id for partial download
        "coverage_start": partial_coverage_start,
        "coverage_end": partial_coverage_end,
        "coverage_status": coverage_status
    }
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": None,
            "results": results
        }
    )


@app.get("/results_partial/download")
def download_partial_results(job_id: str = Query(...)):
    """
    Download partial crawl_all results as CSV.
    Streams all collected transactions so far from a paused/running job.
    """
    with JOBS_LOCK:
        if job_id not in JOBS:
            return HTMLResponse(
                content="<h1>Error</h1><p>Job not found or expired.</p>",
                status_code=404
            )
        
        job = JOBS[job_id]
    
    # Get all collected transactions from raw dict (authoritative source)
    all_txs_raw_dict = job.get("seen_hashes", {})
    
    if not all_txs_raw_dict:
        return HTMLResponse(
            content="<h1>Error</h1><p>No transactions collected yet.</p>",
            status_code=404
        )
    
    # Sort all transactions by block and timestamp
    all_txs_raw = sorted(
        all_txs_raw_dict.values(),
        key=lambda x: (int(x.get("blockNumber", 0)), int(x.get("timeStamp", 0)))
    )
    
    address = job.get("address", "unknown")
    start_block = job.get("start_block", 0)
    
    # Generate filename
    filename = f"eth_txs_partial_{address}_{start_block}.csv"
    
    # Create CSV generator
    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(["time", "block", "direction", "from", "to", "value", "hash"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        
        # Write rows
        for tx in all_txs_raw:
            # Determine direction
            tx_from = tx.get("from", "").lower()
            tx_to = tx.get("to", "").lower()
            address_lower = address.lower()
            
            if tx_from == address_lower:
                direction = "OUT"
            elif tx_to == address_lower:
                direction = "IN"
            else:
                direction = "UNKNOWN"
            
            # Format timestamp
            timestamp = tx.get("timeStamp", "0")
            try:
                dt = datetime.utcfromtimestamp(int(timestamp))
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except (ValueError, TypeError):
                time_str = "N/A"
            
            # Format value (in ETH)
            value_wei = tx.get("value", "0")
            value_eth = wei_to_eth(value_wei)
            
            # Write row
            writer.writerow([
                time_str,
                tx.get("blockNumber", "N/A"),
                direction,
                tx.get("from", "N/A"),
                tx.get("to", "N/A"),
                f"{value_eth:.6f}",
                tx.get("hash", "N/A")
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
    
    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/balance", response_class=HTMLResponse)
def balance(request: Request, address: str = "", date: str = ""):
    """
    Get ETH balance for an address at 00:00 UTC on a given date.
    """
    error = None
    balance_result = None
    
    # Validate inputs
    if not address or not address.startswith("0x"):
        error = "Invalid Ethereum address. Must start with 0x."
    elif not date:
        error = "Please provide a date (YYYY-MM-DD format)."
    elif not client:
        error = "Etherscan API key not configured. Please check .env file."
    else:
        try:
            # Korak A: Pretvori datum v timestamp za 00:00 UTC
            timestamp = date_to_timestamp_utc_midnight(date)
            
            # Korak B: Pridobi block number za ta timestamp
            block_no = client.get_block_by_timestamp(timestamp)
            
            if block_no == 0:
                error = f"Could not find block for date {date} 00:00 UTC."
            else:
                # Korak C: Pridobi balance na tem bloku
                balance_wei = client.get_balance_at_block(address, block_no)
                balance_eth = wei_to_eth(balance_wei)
                
                balance_result = {
                    "address": address,
                    "date": date,
                    "timestamp": timestamp,
                    "block_no": block_no,
                    "balance_wei": balance_wei,
                    "balance_eth": f"{balance_eth:.6f}"
                }
        
        except ValueError as e:
            error = str(e)
        except Exception as e:
            error = f"Error fetching balance: {str(e)}"
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error,
            "balance_result": balance_result
        }
    )
