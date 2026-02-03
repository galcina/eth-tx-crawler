from dotenv import load_dotenv
import os
import requests

load_dotenv()

key = os.getenv("ETHERSCAN_API_KEY")
assert key, "Missing ETHERSCAN_API_KEY"

url = "https://api.etherscan.io/v2/api"
params = {
    "chainid": 1,
    "module": "account",
    "action": "txlist",
    "address": "0xaa7a9ca87d3694b5755f213b5d04094b8d0f0a6f",
    "startblock": 9000000,
    "endblock": 99999999,
    "sort": "asc",
    "apikey": key,
}

r = requests.get(url, params=params, timeout=30)
data = r.json()

print("status:", data.get("status"), "message:", data.get("message"))
print("tx count:", len(data.get("result", [])))
if data.get("result"):
    first_block = data["result"][0].get("blockNumber")
    last_block = data["result"][-1].get("blockNumber")
    print("first blockNumber:", first_block)
    print("last blockNumber:", last_block)
