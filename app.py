from flask import Flask, jsonify, render_template, request
import throughput

app = Flask(__name__)

@app.route('/api/metrics')
def metrics():
    period = request.args.get('period', None)
    data = throughput.get_all_metrics(period=period)
    return jsonify(data)

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) 