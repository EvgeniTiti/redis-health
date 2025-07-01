from flask import Flask, jsonify, render_template, request
import throughput
import autoscaling
import yaml

app = Flask(__name__)

@app.route('/api/metrics')
def metrics():
    period = request.args.get('period', None)
    data = throughput.get_all_metrics(period=period)
    # For each enabled database, check and trigger autoscale if needed
    enabled = autoscaling.get_all_autoscale_enabled()
    for entry in data["databases"]:
        sub_id = str(entry.get('subscription_id'))
        db_id = str(entry.get('database_id'))
        if (sub_id, db_id) in enabled:
            autoscaling.autoscale_database(
                sub_id,
                entry,
                entry['metrics_autoscale'],
                entry.get('thresholds', {}),
                entry.get('max_scaling', {}),
                data["databases"]  # Pass all databases to check if all are active
            )
    return jsonify(data)

@app.route('/api/autoscale/enable', methods=['POST'])
def enable_autoscale():
    req = request.get_json()
    subscription_id = req.get('subscription_id')
    database_id = req.get('database_id')
    autoscaling.enable_autoscale(subscription_id, database_id)
    return jsonify({'success': True})

@app.route('/api/autoscale/disable', methods=['POST'])
def disable_autoscale():
    req = request.get_json()
    subscription_id = req.get('subscription_id')
    database_id = req.get('database_id')
    autoscaling.disable_autoscale(subscription_id, database_id)
    return jsonify({'success': True})

@app.route('/api/autoscale/enabled', methods=['GET'])
def get_enabled_autoscale():
    return jsonify(autoscaling.get_all_autoscale_enabled())

@app.route('/api/autoscaling-status')
def autoscaling_status():
    return jsonify(autoscaling.get_autoscale_status())

@app.route('/api/refresh-cloud', methods=['POST'])
def refresh_cloud():
    # Clear the cache and force a fresh fetch from the Cloud API
    throughput._redis_cache['subscriptions'] = None
    throughput._redis_cache['databases'] = {}
    throughput._redis_cache['last_fetch'] = None
    # Fetch fresh data
    throughput.get_subscriptions_cached()
    return jsonify({'success': True})

@app.route('/api/config')
def get_config():
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    return jsonify({
        'prometheus_query_interval_seconds': config.get('prometheus_query_interval_seconds', 30)
    })

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) 