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
CLOUD_API_QUERY_INTERVAL_SECONDS = config.get('cloud_api_query_interval_seconds', 3600)
CLOUD_API_QUERY_INTERVAL_SECONDS_AUTOSCALE = config.get('cloud_api_query_interval_seconds_autoscale', 60)

# Autoscaling configuration
MEMORY_SCALING_PERCENTAGE = config.get('memory_scaling_percentage', 20)
THROUGHPUT_SCALING_PERCENTAGE = config.get('throughput_scaling_percentage', 20)

# --- Caching for Redis API ---
_redis_cache = {
    'subscriptions': None,
    'databases': {},
    'last_fetch': None
}

AUTOSCALE_QUERY_PERIOD = config.get('autoscale_query_period', '5m')

def is_any_autoscale_enabled():
    # Import here to avoid circular import
    try:
        import autoscaling
        enabled = autoscaling.get_all_autoscale_enabled()
        return bool(enabled)
    except Exception as e:
        return False

def get_subscriptions_cached():
    now = datetime.utcnow()
    # Use shorter TTL if any DB has autoscaling enabled
    if is_any_autoscale_enabled():
        cache_ttl = timedelta(seconds=CLOUD_API_QUERY_INTERVAL_SECONDS_AUTOSCALE)
    else:
        cache_ttl = timedelta(seconds=CLOUD_API_QUERY_INTERVAL_SECONDS)
    if _redis_cache['subscriptions'] is not None and _redis_cache['last_fetch'] and now - _redis_cache['last_fetch'] < cache_ttl:
        return _redis_cache['subscriptions']
    subs = get_subscriptions()
    _redis_cache['subscriptions'] = subs
    _redis_cache['databases'] = {}  # clear DB cache on new subs fetch
    _redis_cache['last_fetch'] = now
    return subs

def get_databases_for_subscription_cached(subscription_id):
    now = datetime.utcnow()
    # Use shorter TTL if any DB has autoscaling enabled
    if is_any_autoscale_enabled():
        cache_ttl = timedelta(seconds=CLOUD_API_QUERY_INTERVAL_SECONDS_AUTOSCALE)
    else:
        cache_ttl = timedelta(seconds=CLOUD_API_QUERY_INTERVAL_SECONDS)
    if (subscription_id in _redis_cache['databases'] and _redis_cache['last_fetch'] and now - _redis_cache['last_fetch'] < cache_ttl):
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

def query_prometheus(prom_url, promql, bdb=None, cluster=None):
    try:
        resp = requests.get(f"{prom_url}/api/v1/query", params={"query": promql}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data["status"] == "success" and data["data"]["result"]:
            for result in data["data"]["result"]:
                metric = result.get("metric", {})
                if (bdb is None or metric.get("bdb") == bdb) and (cluster is None or metric.get("cluster") == cluster):
                    return float(result["value"][1])
            return None  # No matching result found
        else:
            return None
    except Exception as e:
        return None

def get_metric_from_metrics_text(metrics_text, metric_name, labels):
    # Match the metric line and capture the label block and value
    pattern = rf'{re.escape(metric_name)}\{{([^}}]+)\}}\s+([0-9.eE+-]+)'
    regex = re.compile(pattern)
    for match in regex.finditer(metrics_text):
        label_block = match.group(1)
        value = match.group(2)
        # Check if all required labels are present in the label block
        if all(f'{k}="{v}"' in label_block for k, v in labels.items()):
            return float(value)
    return None

def check_database_metrics_prometheus(cluster_label, db, thresholds):
    bdb = str(db.get("databaseId"))
    cluster = db.get("subscriptionId")
    mem_limit_gb = db.get("memoryLimitInGb", 0)
    throughput_limit = db.get("throughputMeasurement", {}).get("value", 0)
    # Query Prometheus for each metric
    period = PROM_QUERY_PERIOD
    prom_url = PROM_SERVER_URL
    labels = f'cluster="{cluster_label}",bdb="{bdb}"'
    throughput = query_prometheus(prom_url, f'max_over_time(bdb_total_req_max{{{labels}}}[{period}])', bdb=bdb, cluster=cluster_label)
    memory = query_prometheus(prom_url, f'max_over_time(bdb_used_memory{{{labels}}}[{period}])', bdb=bdb, cluster=cluster_label)
    cpu = query_prometheus(prom_url, f'max_over_time(bdb_shard_cpu_user_max{{{labels}}}[{period}])', bdb=bdb, cluster=cluster_label)
    latency = query_prometheus(prom_url, f'max_over_time(bdb_avg_latency_max{{{labels}}}[{period}])', bdb=bdb, cluster=cluster_label)

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
    return result

def get_metrics_for_db(cluster_label, db, thresholds, subscription_name, period):
    bdb = str(db.get("databaseId"))
    cluster = db.get("subscriptionId")
    mem_limit_gb = db.get("memoryLimitInGb", 0)
    throughput_limit = db.get("throughputMeasurement", {}).get("value", 0)
    # Only set static/config data, no Prometheus queries
    metrics = {
        "throughput": None,
        "throughput_limit": throughput_limit,
        "memory": None,
        "memory_limit_bytes": mem_limit_gb * 1024 * 1024 * 1024,
        "cpu": None,
        "latency_ms": None
    }
    # Calculate status (all will be None, so all will be False)
    throughput_ok = False
    memory_ok = False
    cpu_ok = False
    latency_ok = False
    # Calculate max scaling limits based on number of shards
    clustering = db.get("clustering", {})
    num_shards = clustering.get("numberOfShards", 1)
    replication = db.get("replication", False)
    max_throughput = num_shards * 25000  # 25K ops/sec per shard
    max_memory_gb = num_shards * 25 * (2 if replication else 1)  # 25GB per shard, doubled if replication
    result = {
        "subscription_id": cluster,
        "subscription_name": subscription_name,
        "database_id": bdb,
        "database_name": db.get("name"),
        "metrics": metrics,
        "thresholds": thresholds,
        "status": {
            "throughput_ok": throughput_ok,
            "memory_ok": memory_ok,
            "cpu_ok": cpu_ok,
            "latency_ok": latency_ok
        },
        "max_scaling": {
            "memory_gb": max_memory_gb,
            "throughput_ops": max_throughput
        }
    }
    return result

def get_all_metrics(period=None):
    prom_period = period if period else '5m'
    autoscale_period = AUTOSCALE_QUERY_PERIOD
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
            if db.get("activeActiveRedis") and db.get("crdbDatabases"):
                continue
            db0 = db
            cluster_label = db0.get("cluster", None)
            if not cluster_label:
                private_endpoint = db0.get("privateEndpoint", "")
                if ".internal." in private_endpoint:
                    cluster_label = private_endpoint.split(".internal.", 1)[1].split(":")[0]
                else:
                    cluster_label = ""
            import copy
            metrics_result = {}
            try:
                bdb = str(db.get("databaseId"))
                cluster = db.get("subscriptionId")
                mem_limit_gb = db.get("memoryLimitInGb", 0)
                throughput_limit = db.get("throughputMeasurement", {}).get("value", 0)
                # Use prom_period for UI metrics, autoscale_period for autoscaling
                period_for_metrics = prom_period
                period_for_autoscale = autoscale_period
                labels = f'cluster="{cluster_label}",bdb="{bdb}"'
                # Metrics for UI (period_for_metrics)
                throughput = query_prometheus(PROM_SERVER_URL, f'max_over_time(bdb_total_req_max{{{labels}}}[{period_for_metrics}])', bdb=bdb, cluster=cluster_label)
                memory = query_prometheus(PROM_SERVER_URL, f'max_over_time(bdb_used_memory{{{labels}}}[{period_for_metrics}])', bdb=bdb, cluster=cluster_label)
                cpu = query_prometheus(PROM_SERVER_URL, f'max_over_time(bdb_shard_cpu_user_max{{{labels}}}[{period_for_metrics}])', bdb=bdb, cluster=cluster_label)
                latency = query_prometheus(PROM_SERVER_URL, f'max_over_time(bdb_avg_latency_max{{{labels}}}[{period_for_metrics}])', bdb=bdb, cluster=cluster_label)
                # Metrics for autoscaling (period_for_autoscale)
                throughput_autoscale = query_prometheus(PROM_SERVER_URL, f'max_over_time(bdb_total_req_max{{{labels}}}[{period_for_autoscale}])', bdb=bdb, cluster=cluster_label)
                memory_autoscale = query_prometheus(PROM_SERVER_URL, f'max_over_time(bdb_used_memory{{{labels}}}[{period_for_autoscale}])', bdb=bdb, cluster=cluster_label)
                cpu_autoscale = query_prometheus(PROM_SERVER_URL, f'max_over_time(bdb_shard_cpu_user_max{{{labels}}}[{period_for_autoscale}])', bdb=bdb, cluster=cluster_label)
                latency_autoscale = query_prometheus(PROM_SERVER_URL, f'max_over_time(bdb_avg_latency_max{{{labels}}}[{period_for_autoscale}])', bdb=bdb, cluster=cluster_label)
                metrics_result = {
                    "subscription_id": cluster,
                    "subscription_name": sub_name,
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
                    "metrics_autoscale": {
                        "throughput": throughput_autoscale,
                        "throughput_limit": throughput_limit,
                        "memory": memory_autoscale,
                        "memory_limit_bytes": mem_limit_gb * 1024 * 1024 * 1024,
                        "cpu": cpu_autoscale,
                        "latency_ms": latency_autoscale
                    },
                    "thresholds": thresholds,
                    "status": {
                        "throughput_ok": throughput is not None and throughput < thresholds["throughput_threshold"] * throughput_limit,
                        "memory_ok": memory is not None and memory < thresholds["memory_threshold"] * mem_limit_gb * 1024 * 1024 * 1024,
                        "cpu_ok": cpu is not None and cpu < thresholds["cpu_threshold"] * 100,
                        "latency_ok": latency is None or latency < thresholds["latency_threshold_ms"]
                    }
                }
                # Add max_scaling calculation
                clustering = db.get("clustering", {})
                num_shards = clustering.get("numberOfShards", 1)
                replication = db.get("replication", False)
                max_throughput = num_shards * 25000  # 25K ops/sec per shard
                max_memory_gb = num_shards * 25 * (2 if replication else 1)  # 25GB per shard, doubled if replication
                metrics_result["max_scaling"] = {
                    "memory_gb": max_memory_gb,
                    "throughput_ops": max_throughput
                }
            except Exception as e:
                metrics_result = get_metrics_for_db(cluster_label, db, thresholds, sub_name, prom_period)
            result = metrics_result
            result["region"] = db.get("region")
            result["active_active"] = False
            result["subscription_id"] = sub_id
            result["db_status"] = db.get("status")
            results.append(result)
    return {"databases": results}

if __name__ == '__main__':
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
        databases = get_databases_for_subscription(sub_id)
        if not databases:
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
        for db in databases:
            db_id = db.get("databaseId")
            db_name = db.get("name")
            check_database_metrics_prometheus(cluster_label, db, thresholds)
