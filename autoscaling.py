import requests
import os
from dotenv import load_dotenv
import threading
import time
import throughput  # Import to access scaling configuration

load_dotenv()

API_KEY = os.getenv("REDIS_CLOUD_API_KEY")
API_SECRET = os.getenv("REDIS_CLOUD_API_SECRET")
API_URL = "https://api.redislabs.com/v1"

# Get scaling percentages from configuration
MEMORY_SCALING_PERCENTAGE = throughput.MEMORY_SCALING_PERCENTAGE
THROUGHPUT_SCALING_PERCENTAGE = throughput.THROUGHPUT_SCALING_PERCENTAGE

# In-memory lock to prevent parallel autoscaling per subscription
_autoscale_locks = {}

# In-memory status for UI indication
_autoscale_status = {}  # {database_id: 'in_progress'|'done'}

# In-memory tracking of autoscaling-enabled databases
_autoscale_enabled = set()  # set of (subscription_id, database_id) tuples

# Track recent autoscaling actions to prevent duplicates
_recent_autoscale_actions = {}  # {database_id: {'values': dict, 'timestamp': float, 'task_id': str}}

def is_autoscale_needed(db_metrics, thresholds, max_scaling):
    """
    Returns dict with scaling needs: {"memory": bool, "throughput": bool}
    """
    m = db_metrics
    t = thresholds
    result = {"memory": False, "throughput": False}
    
    # Check if throughput needs scaling
    throughput_limit = m.get("throughput_limit", 0)
    throughput = m.get("throughput", 0)
    if throughput_limit and throughput is not None and throughput >= t["throughput_threshold"] * throughput_limit:
        if throughput_limit < max_scaling["throughput_ops"]:
            result["throughput"] = True
    
    # Check if memory needs scaling
    memory_limit_bytes = m.get("memory_limit_bytes", 0)
    memory = m.get("memory", 0)
    if memory_limit_bytes and memory is not None and memory >= t["memory_threshold"] * memory_limit_bytes:
        if (memory_limit_bytes / (1024*1024*1024)) < max_scaling["memory_gb"]:
            result["memory"] = True
    
    return result

def calculate_new_scaling(db, db_metrics, max_scaling):
    """
    Scale up by at least 20% or to maximum allowed.
    Returns dict: {"datasetSizeInGb": float, "throughputMeasurement": {"value": int, ...}}
    Only includes parameters that need scaling.
    """
    m = db_metrics
    replication = db.get("replication", False)
    result = {}
    
    # Check if memory needs scaling
    current_memory_gb = m.get("memory_limit_bytes", 0) / (1024*1024*1024)
    used_memory_gb = m.get("memory", 0) / (1024*1024*1024)
    memory_threshold = 0.8  # 80% threshold
    
    if used_memory_gb >= memory_threshold * current_memory_gb and current_memory_gb < max_scaling["memory_gb"]:
        # Calculate new total memory (in GB) - increase by configured percentage or to max
        scaling_factor = 1 + (MEMORY_SCALING_PERCENTAGE / 100)
        min_increase = current_memory_gb * scaling_factor
        new_total_memory_gb = min(max_scaling["memory_gb"], min_increase)
        # Round to nearest 100MB
        new_total_memory_gb = round(new_total_memory_gb * 10) / 10  # Round to 0.1 GB (100MB)
        new_total_memory_gb = max(0.1, new_total_memory_gb)
        # Calculate datasetSizeInGb based on replication
        if replication:
            new_dataset_size_gb = new_total_memory_gb / 2
        else:
            new_dataset_size_gb = new_total_memory_gb
        # Round to nearest 100MB
        new_dataset_size_gb = round(new_dataset_size_gb * 10) / 10  # Round to 0.1 GB (100MB)
        new_dataset_size_gb = max(0.1, new_dataset_size_gb)
        result["datasetSizeInGb"] = new_dataset_size_gb
    
    # Check if throughput needs scaling
    current_throughput = m.get("throughput_limit", 0)
    used_throughput = m.get("throughput", 0)
    throughput_threshold = 0.8  # 80% threshold
    if used_throughput >= throughput_threshold * current_throughput and current_throughput < max_scaling["throughput_ops"]:
        # Calculate new throughput - use the higher of:
        # 1. Current usage + configured percentage
        # 2. Current configuration + configured percentage
        scaling_factor = 1 + (THROUGHPUT_SCALING_PERCENTAGE / 100)
        usage_based = int(used_throughput * scaling_factor) if used_throughput else 0
        config_based = int(current_throughput * scaling_factor)
        new_throughput = max(usage_based, config_based)
        
        # Cap at maximum allowed
        new_throughput = min(max_scaling["throughput_ops"], new_throughput)
        
        # Round to nearest 100 ops
        new_throughput = int(round(new_throughput / 100.0) * 100)
        result["throughputMeasurement"] = {
            "by": "operations-per-second",
            "value": new_throughput
        }
    
    return result

def get_database_config(subscription_id, database_id):
    """
    Get the current database configuration from Redis Cloud API.
    """
    url = f"{API_URL}/subscriptions/{subscription_id}/databases/{database_id}"
    headers = {
        "accept": "application/json",
        "x-api-key": API_KEY,
        "x-api-secret-key": API_SECRET
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to get database config: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error getting database config: {e}")
        return None

def filter_allowed_update_fields(config):
    """
    Filter the database configuration to only include fields that are allowed for updates.
    Based on the Redis Cloud API error message, we need to exclude read-only fields.
    """
    # Only include fields that are typically allowed for database updates
    # Excluding alerts and backup as they contain read-only fields like 'id'
    allowed_fields = {
        'datasetSizeInGb',
        'throughputMeasurement',
        'memoryLimitInGb',
        'dataPersistence',
        'dataEvictionPolicy',
        'replication'
    }
    
    filtered_config = {}
    for key, value in config.items():
        if key in allowed_fields:
            filtered_config[key] = value
    
    return filtered_config

def check_task_status(task_id):
    """
    Check the status of a Redis Cloud API task.
    """
    url = f"{API_URL}/tasks/{task_id}"
    headers = {
        "accept": "application/json",
        "x-api-key": API_KEY,
        "x-api-secret-key": API_SECRET
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            task_data = response.json()
            status = task_data.get('status', 'unknown')
            print(f"Task {task_id} status: {status}")
            return status
        else:
            print(f"Failed to check task status: {response.status_code} - {response.text}")
            return 'unknown'
    except Exception as e:
        print(f"Error checking task status: {e}")
        return 'unknown'

def is_duplicate_request(database_id, new_values):
    """
    Check if this is a duplicate autoscaling request.
    """
    current_time = time.time()
    
    if database_id in _recent_autoscale_actions:
        last_action = _recent_autoscale_actions[database_id]
        # Check if it's the same values and within 5 minutes
        if (last_action['values'] == new_values and 
            current_time - last_action['timestamp'] < 300):  # 5 minutes
            return True
    
    return False

def update_recent_action(database_id, new_values, task_id=None):
    """
    Update the tracking of recent autoscaling actions.
    """
    _recent_autoscale_actions[database_id] = {
        'values': new_values,
        'timestamp': time.time(),
        'task_id': task_id
    }

def is_duplicate_task_check(database_id, task_id):
    """
    Check if we've already checked this task status.
    """
    if database_id in _recent_autoscale_actions:
        last_action = _recent_autoscale_actions[database_id]
        if last_action.get('task_id') == task_id:
            return True
    return False

def update_database_scaling(subscription_id, database_id, new_values):
    """
    Call the Redis Cloud API to update the database scaling values.
    Only sends the specific fields that need updating.
    """
    # Check for duplicate request
    if is_duplicate_request(database_id, new_values):
        print(f"Skipping duplicate autoscaling request for DB {database_id}")
        return None
    
    # Get current database configuration
    current_config = get_database_config(subscription_id, database_id)
    if not current_config:
        print(f"Could not get current configuration for DB {database_id}, trying direct update...")
        # Fallback to direct update with only the new values
        url = f"{API_URL}/subscriptions/{subscription_id}/databases/{database_id}"
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "x-api-key": API_KEY,
            "x-api-secret-key": API_SECRET
        }
        print(f"Updating database scaling: {url}")
        print(f"Request body: {new_values}")
        
        try:
            response = requests.put(url, headers=headers, json=new_values)
            print(f"API Response Status: {response.status_code}")
            print(f"API Response Body: {response.text}")
            
            if response.status_code not in (200, 202):
                print(f"API Error Response: {response.status_code} - {response.text}")
                raise Exception(f"Failed to update database scaling: {response.status_code} {response.text}")
            
            # If it's a 202 response, check the task status
            if response.status_code == 202:
                response_data = response.json()
                task_id = response_data.get('taskId')
                if task_id:
                    print(f"Task created: {task_id}")
                    # Update tracking with task ID
                    update_recent_action(database_id, new_values, task_id)
                    # Wait a bit and check task status
                    time.sleep(2)
                    task_status = check_task_status(task_id)
                    if task_status in ['completed', 'success']:
                        print(f"Successfully updated database scaling for DB {database_id}")
                        return response_data
                    elif task_status in ['failed', 'error']:
                        raise Exception(f"Task failed with status: {task_status}")
                    else:
                        print(f"Task status: {task_status} - will check again later")
                        return response_data
            else:
                print(f"Successfully updated database scaling for DB {database_id}")
                return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Request exception: {e}")
            raise Exception(f"Network error updating database scaling: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise
    else:
        # Only send the specific fields that need updating
        # Don't include current config, just send the new values
        url = f"{API_URL}/subscriptions/{subscription_id}/databases/{database_id}"
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "x-api-key": API_KEY,
            "x-api-secret-key": API_SECRET
        }
        print(f"Updating database scaling: {url}")
        print(f"Request body: {new_values}")
        
        try:
            response = requests.put(url, headers=headers, json=new_values)
            print(f"API Response Status: {response.status_code}")
            print(f"API Response Body: {response.text}")
            
            if response.status_code not in (200, 202):
                print(f"API Error Response: {response.status_code} - {response.text}")
                raise Exception(f"Failed to update database scaling: {response.status_code} {response.text}")
            
            # If it's a 202 response, check the task status
            if response.status_code == 202:
                response_data = response.json()
                task_id = response_data.get('taskId')
                if task_id:
                    print(f"Task created: {task_id}")
                    # Update tracking with task ID
                    update_recent_action(database_id, new_values, task_id)
                    # Wait a bit and check task status
                    time.sleep(2)
                    task_status = check_task_status(task_id)
                    if task_status in ['completed', 'success']:
                        print(f"Successfully updated database scaling for DB {database_id}")
                        return response_data
                    elif task_status in ['failed', 'error']:
                        raise Exception(f"Task failed with status: {task_status}")
                    else:
                        print(f"Task status: {task_status} - will check again later")
                        return response_data
            else:
                print(f"Successfully updated database scaling for DB {database_id}")
                return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Request exception: {e}")
            raise Exception(f"Network error updating database scaling: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

def set_autoscale_status(database_id, status):
    _autoscale_status[database_id] = status

def get_autoscale_status():
    return _autoscale_status.copy()

def are_all_databases_active(subscription_id, all_databases):
    """
    Check if all databases in the subscription are in active state.
    """
    subscription_databases = [db for db in all_databases if str(db.get('subscription_id')) == str(subscription_id)]
    if not subscription_databases:
        return False
    
    for db in subscription_databases:
        db_status = db.get('db_status', '').lower() or db.get('status', '').lower()
        if db_status != 'active':
            print(f"DB {db.get('database_id')} is not active (status: {db_status})")
            return False
    
    return True

def autoscale_database(subscription_id, db, db_metrics, thresholds, max_scaling, all_databases=None):
    """
    Main entry point: checks if autoscaling is needed and performs it if allowed.
    Ensures only one autoscale per subscription at a time.
    Only scales if all databases in the subscription are active.
    """
    lock = _autoscale_locks.setdefault(subscription_id, threading.Lock())
    db_id = db.get('databaseId') or db.get('database_id')
    
    # Check if all databases in the subscription are active
    if all_databases and not are_all_databases_active(subscription_id, all_databases):
        print(f"Not all databases in subscription {subscription_id} are active, skipping autoscale.")
        return False
    
    # Check for db_status in the db object or in the metrics data
    db_status = db.get('db_status', '').lower() or db.get('status', '').lower()
    if db_status != 'active':
        print(f"DB {db_id} is not active (status: {db_status}), skipping autoscale.")
        return False
    if not lock.acquire(blocking=False):
        print(f"Autoscale already in progress for subscription {subscription_id}, skipping.")
        return False
    try:
        scaling_needs = is_autoscale_needed(db_metrics, thresholds, max_scaling)
        if not any(scaling_needs.values()):
            return False
        
        set_autoscale_status(db_id, 'in_progress')
        new_values = calculate_new_scaling(db, db_metrics, max_scaling)
        
        if not new_values:
            return False
            
        print(f"Autoscaling DB {db_id} with values: {new_values}")
        update_database_scaling(subscription_id, db_id, new_values)
        print(f"Autoscale performed for DB {db_id}")
        set_autoscale_status(db_id, 'done')
        return True
    finally:
        lock.release()

def enable_autoscale(subscription_id, database_id):
    _autoscale_enabled.add((str(subscription_id), str(database_id)))

def disable_autoscale(subscription_id, database_id):
    _autoscale_enabled.discard((str(subscription_id), str(database_id)))

def is_autoscale_enabled(subscription_id, database_id):
    return (str(subscription_id), str(database_id)) in _autoscale_enabled

def get_all_autoscale_enabled():
    return list(_autoscale_enabled) 