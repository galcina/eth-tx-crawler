import requests
import time
from typing import Callable, List, Dict, Any
from requests import exceptions as req_exc

ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"


class EtherscanClient:
    def __init__(self, api_key: str, chain_id: int = 1):
        self.api_key = api_key
        self.chain_id = chain_id

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a GET request to Etherscan API with retries and exponential backoff.
        Retries are needed because Etherscan can timeout during long segmented crawls,
        especially when fetching many pages across large block ranges.
        """
        full_params = {
            "chainid": self.chain_id,
            "apikey": self.api_key,
            **params
        }
        
        max_attempts = 3  # Reduced from 5 to 3 for faster failure on persistent errors
        backoff_times = [1, 2, 4]  # Exponential backoff in seconds (1s, 2s, 4s)
        
        last_exception = None
        last_response_content = None
        
        for attempt in range(max_attempts):
            try:
                r = requests.get(ETHERSCAN_V2_URL, params=full_params, timeout=60)
                r.raise_for_status()
                
                # Parse JSON to check for rate limit or error messages
                last_response_content = r.text[:200]  # Store for error reporting
                try:
                    json_data = r.json()
                except ValueError:
                    # Invalid JSON - treat as transient error
                    if attempt < max_attempts - 1:
                        backoff = backoff_times[attempt]
                        print(f"[Etherscan] Invalid JSON response, retrying in {backoff}s (attempt {attempt + 1}/{max_attempts})", flush=True)
                        time.sleep(backoff)
                        continue
                    else:
                        raise RuntimeError(f"Etherscan API returned invalid JSON after {max_attempts} attempts. Last response: {last_response_content}")
                
                # Check for rate limit or error messages in response
                status = json_data.get("status")
                message = json_data.get("message", "").lower()
                result = json_data.get("result", "")
                
                # Check for rate limit indicators
                is_rate_limit = (
                    status == "0" and (
                        "rate limit" in message or
                        "max rate limit reached" in message or
                        "busy" in message or
                        (isinstance(result, str) and ("rate limit" in result.lower() or "busy" in result.lower()))
                    )
                )
                
                # Check for NOTOK status (but allow "1" which is success)
                is_notok = status == "0" and not is_rate_limit
                
                # If rate limit or transient error, retry
                if is_rate_limit and attempt < max_attempts - 1:
                    backoff = backoff_times[attempt]
                    print(f"[Etherscan] Rate limit detected, retrying in {backoff}s (attempt {attempt + 1}/{max_attempts})", flush=True)
                    time.sleep(backoff)
                    continue
                
                # If NOTOK but not rate limit, check if it's a transient error we should retry
                # (Some NOTOK responses are permanent errors, but we'll retry for safety)
                if is_notok and attempt < max_attempts - 1:
                    backoff = backoff_times[attempt]
                    print(f"[Etherscan] API returned NOTOK, retrying in {backoff}s (attempt {attempt + 1}/{max_attempts}): {message[:100]}", flush=True)
                    time.sleep(backoff)
                    continue
                
                # Success - return the JSON data
                return json_data
                
            except req_exc.Timeout as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    backoff = backoff_times[attempt]
                    print(f"[Etherscan] Request timeout, retrying in {backoff}s (attempt {attempt + 1}/{max_attempts})", flush=True)
                    time.sleep(backoff)
                    continue
                else:
                    raise RuntimeError(f"Etherscan API request timed out after {max_attempts} attempts. Last error: {str(e)}")
                    
            except req_exc.ConnectionError as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    backoff = backoff_times[attempt]
                    print(f"[Etherscan] Connection error, retrying in {backoff}s (attempt {attempt + 1}/{max_attempts})", flush=True)
                    time.sleep(backoff)
                    continue
                else:
                    raise RuntimeError(f"Etherscan API connection failed after {max_attempts} attempts. Last error: {str(e)}")
                    
            except requests.exceptions.HTTPError as e:
                # Check for HTTP 429 (Too Many Requests)
                if e.response is not None and e.response.status_code == 429:
                    if attempt < max_attempts - 1:
                        backoff = backoff_times[attempt]
                        print(f"[Etherscan] HTTP 429 (Too Many Requests), retrying in {backoff}s (attempt {attempt + 1}/{max_attempts})", flush=True)
                        time.sleep(backoff)
                        continue
                    else:
                        raise RuntimeError(f"Etherscan API returned HTTP 429 after {max_attempts} attempts. Last response: {e.response.text[:200]}")
                else:
                    # Other HTTP errors - don't retry
                    raise
                    
            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    backoff = backoff_times[attempt]
                    print(f"[Etherscan] Unexpected error, retrying in {backoff}s (attempt {attempt + 1}/{max_attempts}): {str(e)[:100]}", flush=True)
                    time.sleep(backoff)
                    continue
                else:
                    raise RuntimeError(f"Etherscan API request failed after {max_attempts} attempts. Last error: {str(e)}")
        
        # Should not reach here, but just in case
        error_msg = f"Etherscan API request failed after {max_attempts} attempts."
        if last_exception:
            error_msg += f" Last exception: {str(last_exception)}"
        if last_response_content:
            error_msg += f" Last response: {last_response_content[:200]}"
        raise RuntimeError(error_msg)

    def get_latest_block(self) -> int:
        """Get the latest block number."""
        data = self._get({
            "module": "proxy",
            "action": "eth_blockNumber"
        })
        hex_block = data.get("result", "0x0")
        return int(hex_block, 16)

    def txlist_range(
        self,
        address: str,
        start_block: int,
        end_block: int,
        page: int = 1,
        offset: int = 10000
    ) -> Dict[str, Any]:
        """Get transaction list for an address in a block range."""
        return self._get({
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": "asc"
        })

    def txlist_page(
        self,
        address: str,
        start_block: int,
        end_block: int,
        page: int = 1,
        offset: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Get a single page of transactions for an address in a block range.
        Returns list of transactions (not the full API response dict).
        Does NOT do splitting or crawl-all - just one API call.
        """
        data = self.txlist_range(address, start_block, end_block, page, offset)
        if data.get("status") == "1":
            return data.get("result", [])
        return []

    def tokentx_page(
        self,
        address: str,
        start_block: int,
        end_block: int,
        page: int = 1,
        offset: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Get a single page of ERC-20 token transfers for an address in a block range.
        Returns list of token transfers (not the full API response dict).
        Does NOT do splitting or crawl-all - just one API call.
        """
        data = self._get({
            "module": "account",
            "action": "tokentx",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": "asc"
        })
        if data.get("status") == "1":
            return data.get("result", [])
        return []

    def get_block_by_timestamp(self, timestamp: int) -> int:
        """
        Get block number for a given timestamp (closest before).
        module=block, action=getblocknobytime
        """
        data = self._get({
            "module": "block",
            "action": "getblocknobytime",
            "timestamp": timestamp,
            "closest": "before"
        })
        if data.get("status") == "1":
            return int(data.get("result", 0))
        return 0

    def get_balance_at_block(self, address: str, block_no: int) -> str:
        """
        Get ETH balance for an address at a specific block.
        module=account, action=balancehistory
        Returns balance as string in wei.
        """
        data = self._get({
            "module": "account",
            "action": "balancehistory",
            "address": address,
            "blockno": block_no
        })
        if data.get("status") == "1":
            result = data.get("result", {})
            return result.get("balance", "0")
        return "0"


def crawl_all_by_block_splitting(
    fetch_fn: Callable[[str, int, int, int, int], Dict[str, Any]],
    address: str,
    start_block: int,
    end_block: int,
    offset: int = 10000
) -> List[Dict[str, Any]]:
    """
    Fetch all transactions by splitting block ranges recursively if needed.
    Deduplicates by transaction hash.
    """
    all_txs = {}
    
    def fetch_range(sb: int, eb: int, page: int = 1):
        """Recursively fetch transactions, splitting ranges if needed."""
        data = fetch_fn(address, sb, eb, page, offset)
        
        if data.get("status") != "1":
            # API error or no results
            return
        
        results = data.get("result", [])
        if not results:
            return
        
        # Add transactions, deduplicating by hash
        for tx in results:
            tx_hash = tx.get("hash")
            if tx_hash:
                all_txs[tx_hash] = tx
        
        # Check if we hit the offset limit
        if len(results) == offset:
            # Need to split the range
            if eb - sb > 1:
                # Split in half
                mid = (sb + eb) // 2
                fetch_range(sb, mid)
                fetch_range(mid + 1, eb)
            else:
                # Range is too small to split, try next page
                fetch_range(sb, eb, page + 1)
    
    fetch_range(start_block, end_block)
    
    # Return as list sorted by block number
    return sorted(all_txs.values(), key=lambda x: int(x.get("blockNumber", 0)))
