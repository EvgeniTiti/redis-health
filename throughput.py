import os
import time
import requests
import yaml
import json
from dotenv import load_dotenv
import re
from datetime import datetime, timedelta

load_dotenv()

API_KEY = os.getenv("REDIS_CLOUD_API_KEY")
API_SECRET = os.getenv("REDIS_CLOUD_API_SECRET")
SUBSCRIPTION_ID = os.getenv("REDIS_CLOUD_SUBSCRIPTION_ID")
API_URL = "https://api.redislabs.com/v1"

with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

THROUGHPUT_THRESHOLD = config.get('throughput_threshold', 0.8)
MEMORY_THRESHOLD = config.get('memory_threshold', 0.8)
CPU_THRESHOLD = config.get('cpu_threshold', 0.6)
LATENCY_THRESHOLD_MS = config.get('latency_threshold_ms', 3)
PROM_SERVER_URL = config.get('prometheus_server_url', 'http://localhost:9090')
PROM_QUERY_PERIOD = config.get('prometheus_query_period', '1h')

# --- Caching for Redis API ---
_redis_cache = {
    'subscriptions': None,
    'databases': {},
    'last_fetch': None
}
_CACHE_TTL = timedelta(hours=1)

def get_subscriptions_cached():
    now = datetime.utcnow()
    if _redis_cache['subscriptions'] is not None and _redis_cache['last_fetch'] and now - _redis_cache['last_fetch'] < _CACHE_TTL:
        return _redis_cache['subscriptions']
    subs = get_subscriptions()
    _redis_cache['subscriptions'] = subs
    _redis_cache['databases'] = {}  # clear DB cache on new subs fetch
    _redis_cache['last_fetch'] = now
    return subs

def get_databases_for_subscription_cached(subscription_id):
    now = datetime.utcnow()
    if (subscription_id in _redis_cache['databases'] and _redis_cache['last_fetch'] and now - _redis_cache['last_fetch'] < _CACHE_TTL):
        return _redis_cache['databases'][subscription_id]
    dbs = get_databases_for_subscription(subscription_id)
    _redis_cache['databases'][subscription_id] = dbs
    return dbs

# --- Existing API functions ---
def get_subscriptions():
    url = f"{API_URL}/subscriptions"
    headers = {
        "accept": "application/json",
        "x-api-key": API_KEY,
        "x-api-secret-key": API_SECRET
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    return data.get("subscriptions", [])

def get_databases_for_subscription(subscription_id):
    url = f"{API_URL}/subscriptions/{subscription_id}/databases?offset=0&limit=100"
    headers = {
        "accept": "application/json",
        "x-api-key": API_KEY,
        "x-api-secret-key": API_SECRET
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    return data.get("subscription", [])[0].get("databases", [])

def query_prometheus(prom_url, promql):
    try:
        resp = requests.get(f"{prom_url}/api/v1/query", params={"query": promql}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data["status"] == "success" and data["data"]["result"]:
            return float(data["data"]["result"][0]["value"][1])
        else:
            return None
    except Exception as e:
        print(f"      ⚠️ Prometheus API query failed: {e}")
        return None

def get_metric_from_metrics_text(metrics_text, metric_name, labels):
    # Match the metric line and capture the label block and value
    pattern = rf'{re.escape(metric_name)}\{{([^}}]+)\}}\s+([0-9.eE+-]+)'
    regex = re.compile(pattern)
    print(f"[DEBUG] Searching for metric: {metric_name}, labels: {labels}, regex: {pattern}")
    for match in regex.finditer(metrics_text):
        label_block = match.group(1)
        value = match.group(2)
        # Check if all required labels are present in the label block
        if all(f'{k}="{v}"' in label_block for k, v in labels.items()):
            print(f"[DEBUG] Found value: {value} for metric: {metric_name}")
            return float(value)
    print(f"[DEBUG] No match for metric: {metric_name} with labels: {labels}")
    return None

# def print_metrics_for_bdb_cluster(metrics_text, bdb, cluster_label):
#     print(f"[DEBUG] All metrics for bdb={bdb}, cluster={cluster_label}:")
#     for line in metrics_text.splitlines():
#         if f'bdb="{bdb}"' in line and f'cluster="{cluster_label}"' in line:
#             print(line)

def check_database_metrics_prometheus(cluster_label, db, thresholds):
    bdb = str(db.get("databaseId"))
    cluster = db.get("subscriptionId")
    mem_limit_gb = db.get("memoryLimitInGb", 0)
    throughput_limit = db.get("throughputMeasurement", {}).get("value", 0)
    # Query Prometheus for each metric
    period = PROM_QUERY_PERIOD
    prom_url = PROM_SERVER_URL
    labels = f'cluster="{cluster_label}",bdb="{bdb}"'
    throughput = query_prometheus(prom_url, f'max_over_time(bdb_total_req_max{{{labels}}}[{period}])')
    memory = query_prometheus(prom_url, f'max_over_time(bdb_used_memory{{{labels}}}[{period}])')
    cpu = query_prometheus(prom_url, f'max_over_time(bdb_shard_cpu_user_max{{{labels}}}[{period}])')
    latency = query_prometheus(prom_url, f'max_over_time(bdb_avg_latency_max{{{labels}}}[{period}])')

    throughput_ok = throughput is not None and throughput < thresholds["throughput_threshold"] * throughput_limit
    memory_ok = memory is not None and memory < thresholds["memory_threshold"] * mem_limit_gb * 1024 * 1024 * 1024  # bytes
    cpu_ok = cpu is not None and cpu < thresholds["cpu_threshold"] * 100
    latency_ok = latency is None or latency < thresholds["latency_threshold_ms"]

    result = {
        "subscription_id": cluster,
        "database_id": bdb,
        "database_name": db.get("name"),
        "metrics": {
            "throughput": throughput,
            "throughput_limit": throughput_limit,
            "memory": memory,
            "memory_limit_bytes": mem_limit_gb * 1024 * 1024 * 1024,
            "cpu": cpu,
            "latency_ms": latency
        },
        "thresholds": thresholds,
        "status": {
            "throughput_ok": throughput_ok,
            "memory_ok": memory_ok,
            "cpu_ok": cpu_ok,
            "latency_ok": latency_ok
        }
    }
    print(json.dumps(result))

def get_metrics_for_db(cluster_label, db, thresholds, subscription_name, period):
    bdb = str(db.get("databaseId"))
    cluster = db.get("subscriptionId")
    mem_limit_gb = db.get("memoryLimitInGb", 0)
    throughput_limit = db.get("throughputMeasurement", {}).get("value", 0)
    prom_url = PROM_SERVER_URL
    labels = f'cluster="{cluster_label}",bdb="{bdb}"'
    prom_period = period if period else PROM_QUERY_PERIOD
    throughput = query_prometheus(prom_url, f'max_over_time(bdb_total_req_max{{{labels}}}[{prom_period}])')
    memory = query_prometheus(prom_url, f'max_over_time(bdb_used_memory{{{labels}}}[{prom_period}])')
    cpu = query_prometheus(prom_url, f'max_over_time(bdb_shard_cpu_user_max{{{labels}}}[{prom_period}])')
    latency = query_prometheus(prom_url, f'max_over_time(bdb_avg_latency_max{{{labels}}}[{prom_period}])')
    throughput_ok = throughput is not None and throughput < thresholds["throughput_threshold"] * throughput_limit
    memory_ok = memory is not None and memory < thresholds["memory_threshold"] * mem_limit_gb * 1024 * 1024 * 1024
    cpu_ok = cpu is not None and cpu < thresholds["cpu_threshold"] * 100
    latency_ok = latency is not None and latency < thresholds["latency_threshold_ms"]
    return {
        "subscription_id": cluster,
        "subscription_name": subscription_name,
        "database_id": bdb,
        "database_name": db.get("name"),
        "metrics": {
            "throughput": throughput,
            "throughput_limit": throughput_limit,
            "memory": memory,
            "memory_limit_bytes": mem_limit_gb * 1024 * 1024 * 1024,
            "cpu": cpu,
            "latency_ms": latency
        },
        "thresholds": thresholds,
        "status": {
            "throughput_ok": throughput_ok,
            "memory_ok": memory_ok,
            "cpu_ok": cpu_ok,
            "latency_ok": latency_ok
        }
    }

def get_all_metrics(period=None):
    subscriptions = get_subscriptions_cached()
    thresholds = {
        "throughput_threshold": THROUGHPUT_THRESHOLD,
        "memory_threshold": MEMORY_THRESHOLD,
        "cpu_threshold": CPU_THRESHOLD,
        "latency_threshold_ms": LATENCY_THRESHOLD_MS
    }
    results = []
    for sub in subscriptions:
        sub_id = sub.get("id")
        sub_name = sub.get("name")
        deployment_type = sub.get("deploymentType", "")
        databases = get_databases_for_subscription_cached(sub_id)
        if not databases:
            continue
        for db in databases:
            # Handle active-active (multi-region) databases
            if db.get("activeActiveRedis") and db.get("crdbDatabases"):
                for region_info in db["crdbDatabases"]:
                    region = region_info.get("region")
                    provider = region_info.get("provider")
                    memory_limit_gb = region_info.get("memoryLimitInGb")
                    dataset_size_gb = region_info.get("datasetSizeInGb")
                    memory_used_mb = region_info.get("memoryUsedInMb")
                    public_endpoint = region_info.get("publicEndpoint")
                    # Throughput info (if available)
                    read_ops = region_info.get("readOperationsPerSecond")
                    write_ops = region_info.get("writeOperationsPerSecond")
                    # Compose metrics dict
                    results.append({
                        "subscription_name": sub_name,
                        "database_name": db.get("name"),
                        "region": region,
                        "provider": provider,
                        "public_endpoint": public_endpoint,
                        "memory_limit_gb": memory_limit_gb,
                        "dataset_size_gb": dataset_size_gb,
                        "memory_used_mb": memory_used_mb,
                        "read_ops_per_sec": read_ops,
                        "write_ops_per_sec": write_ops,
                        # For compatibility with dashboard, add metrics as a dict
                        "metrics": {
                            "memory_limit_gb": memory_limit_gb,
                            "dataset_size_gb": dataset_size_gb,
                            "memory_used_mb": memory_used_mb,
                            "read_ops_per_sec": read_ops,
                            "write_ops_per_sec": write_ops
                        },
                        "thresholds": thresholds,
                        "active_active": True
                    })
            else:
                # Non-active-active: keep existing logic
                db0 = db
                cluster_label = db0.get("cluster", None)
                if not cluster_label:
                    private_endpoint = db0.get("privateEndpoint", "")
                    if ".internal." in private_endpoint:
                        cluster_label = private_endpoint.split(".internal.", 1)[1].split(":")[0]
                    else:
                        cluster_label = ""
                result = get_metrics_for_db(cluster_label, db, thresholds, sub_name, period)
                result["region"] = db.get("region")
                result["active_active"] = False
                results.append(result)
    return results

if __name__ == '__main__':
    print("🔄 Starting Redis Cloud Prometheus metrics checker (via Prometheus server) ...")
    subscriptions = get_subscriptions()
    thresholds = {
        "throughput_threshold": THROUGHPUT_THRESHOLD,
        "memory_threshold": MEMORY_THRESHOLD,
        "cpu_threshold": CPU_THRESHOLD,
        "latency_threshold_ms": LATENCY_THRESHOLD_MS
    }
    for sub in subscriptions:
        sub_id = sub.get("id")
        sub_name = sub.get("name")
        print(f"\n📦 Subscription: {sub_name} (ID: {sub_id})")
        databases = get_databases_for_subscription(sub_id)
        if not databases:
            print("  No databases found.")
            continue
        # Use the first database to get the cluster label
        db0 = databases[0]
        cluster_label = db0.get("cluster", None)
        if not cluster_label:
            private_endpoint = db0.get("privateEndpoint", "")
            if ".internal." in private_endpoint:
                cluster_label = private_endpoint.split(".internal.", 1)[1].split(":")[0]
            else:
                cluster_label = ""
        print(f"  Using cluster_label: {cluster_label}")
        for db in databases:
            db_id = db.get("databaseId")
            db_name = db.get("name")
            print(f"    - Database: {db_name} (ID: {db_id})")
            check_database_metrics_prometheus(cluster_label, db, thresholds)
