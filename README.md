# Redis Health Dashboard

A modern, Redis.io-inspired dashboard for monitoring Redis Cloud databases with intelligent autoscaling capabilities and cost optimization features.

## Features

### 🎨 Modern UI Design
- **Redis.io-inspired design** with clean, professional aesthetics
- **Responsive layout** that works on desktop and mobile devices
- **Collapsible subscriptions** for better organization of multiple databases
- **Real-time status indicators** with color-coded badges
- **Interactive controls** with hover effects and smooth transitions

### 📊 Dashboard Features
- **Real-time metrics monitoring** for throughput, memory, CPU, latency, and payload size
- **Customizable thresholds** for different metrics
- **Auto-refresh capability** with configurable intervals
- **Summary statistics** showing total databases, healthy count, and attention needed
- **Time range selection** from 5 minutes to 2 days, plus absolute time ranges
- **Payload size monitoring** with average KB per request calculation

### 💰 Cost Optimization
- **Intelligent downscale suggestions** with proper headroom calculations
- **Price recommendations** for downscale configurations
- **Cost savings display** showing hourly pricing for suggested configurations
- **Shard type optimization** to find the most cost-effective configuration
- **HA (High Availability) pricing** consideration

### 🤖 Autoscaling Intelligence
- **Smart scaling recommendations** based on usage patterns
- **Per-database autoscaling control** with toggle switches
- **Maximum scaling limits** display for each database
- **Automatic upscaling** when thresholds are exceeded
- **API integration** with Redis Cloud for seamless scaling

### 🔧 Configuration
- **Threshold Configuration Panel** for customizing alert levels:
  - Throughput: 80% of limit (default)
  - Memory: 80% of limit (default)
  - CPU: 60% of limit (default)
  - Latency: 3ms (default)
  - Payload Size: 3KB (default)

### 📱 User Experience
- **Collapsible subscriptions** - Click the chevron icon to expand/collapse database groups
- **Status indicators**:
  - 🟢 **Healthy** - Database is performing well
  - 🔴 **Scale Up** - Database needs more resources
  - 🟡 **Review** - Some metrics need attention
  - ⚪ **No Data** - No metrics available
- **Help modal** with comprehensive documentation
- **Notifications** for user actions and system events
- **Price suggestions** displayed below hourly pricing

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd Redis-Health
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your Redis Cloud API credentials
```

4. Run the application:
```bash
python app.py
```

5. Open your browser and navigate to `http://localhost:5000`

## Configuration

Copy `config.yaml.example` to `config.yaml` and edit with your values:

```bash
cp config.yaml.example config.yaml
```

### config.yaml fields
- `redis_cloud_api_key`: Your Redis Cloud API key
- `redis_cloud_email`: Your Redis Cloud account email
- `throughput_threshold`: Percentage of throughput limit before alerting (default: 0.8)
- `memory_threshold`: Percentage of memory limit before alerting (default: 0.8)
- `cpu_threshold`: Percentage of CPU usage before alerting (default: 0.6)
- `latency_threshold_ms`: Maximum acceptable latency in milliseconds (default: 3)
- `payload_size_threshold_kb`: Maximum average payload size in KB (default: 3)
- `prometheus_server_url`: The URL of your Prometheus server (e.g., http://localhost:9090 or your remote address)
- `prometheus_query_period`: Default lookback window for Prometheus queries (default: 1h, but UI selection usually overrides this)
- `prometheus_query_interval_seconds`: How often to fetch live metrics from Prometheus (default: 30)
- `memory_scaling_percentage`: Percentage increase for memory scaling (default: 20)
- `throughput_scaling_percentage`: Percentage increase for throughput scaling (default: 20)
- `autoscale_query_period`: Time window for autoscaling decisions (default: 5m). **Autoscaling always uses this period, regardless of the UI selection.**
- `cloud_api_query_interval_seconds`: How often to fetch static data from the Redis Cloud API (default: 3600)
- `cloud_api_query_interval_seconds_autoscale`: How often to fetch static data if any DB has autoscaling enabled (default: 60)

### Environment Variables
- `REDIS_CLOUD_API_KEY`: Your Redis Cloud API key
- `REDIS_CLOUD_API_SECRET`: Your Redis Cloud API secret

### Threshold Configuration
The dashboard allows you to customize alert thresholds for different metrics:
- **Throughput**: Percentage of throughput limit before alerting
- **Memory**: Percentage of memory limit before alerting  
- **CPU**: Percentage of CPU usage before alerting
- **Latency**: Maximum acceptable latency in milliseconds
- **Payload Size**: Maximum average payload size in KB

## Usage

### Basic Monitoring
1. The dashboard automatically loads and displays all your Redis Cloud databases
2. Metrics are refreshed every 30 seconds by default
3. Use the time range selector to view different time periods
4. Click the "Auto Refresh" button to enable/disable automatic updates

### Cost Optimization
1. **Downscale Suggestions**: When all metrics are healthy, the system suggests smaller configurations
2. **Headroom Logic**: Suggestions ensure current usage stays below 80% of the new limit
3. **Price Calculations**: See cost savings for suggested configurations
4. **Step Sizes**: Predictable increments (100, 500, 1K for throughput; 100MB, 500MB, 1GB for memory)

### Autoscaling Management
1. Toggle autoscaling for individual databases using the checkboxes
2. Monitor the "Max Autoscaling" column to see scaling limits
3. The system will automatically scale up databases when thresholds are exceeded

### Subscription Organization
1. Click the chevron icon (▶️/🔽) next to subscription names to collapse/expand
2. This helps organize large numbers of databases by subscription
3. The subscription header shows the number of databases in each group

### Custom Thresholds
1. Use the "Threshold Configuration" panel to adjust alert levels
2. Click "Apply" to save changes (only reloads if thresholds actually changed)
3. Click "Reset" to return to default values

### Payload Size Monitoring
1. Monitor average payload size per request in KB
2. Set custom thresholds for payload size alerts
3. Helps identify inefficient data patterns

## Downscale Logic

The system provides intelligent downscale suggestions with the following logic:

### Throughput Steps
- **Current Usage**: 999 ops/sec
- **Suggested**: 2,000 ops/sec (ensuring 999/2000 = 50% usage)
- **Step Sizes**: 100 → 500 → 1,000 → 2,000 → 3,000... (minimum 1K jumps after 1K)

### Memory Steps  
- **Current Usage**: 800 MB
- **Suggested**: 2,048 MB (ensuring 800/2048 = 39% usage)
- **Step Sizes**: 100MB → 500MB → 1GB → 2GB → 3GB... (minimum 1GB jumps after 1GB)

### Headroom Requirements
- All suggestions ensure usage stays below 80% threshold
- Provides buffer for traffic spikes and growth
- Uses `max_over_time` aggregation for safety

## API Endpoints

- `GET /` - Main dashboard page
- `GET /api/metrics` - Get database metrics
- `GET /api/config` - Get configuration settings
- `GET /api/autoscaling-status` - Get autoscaling status
- `GET /api/autoscale/enabled` - Get enabled autoscaling databases
- `POST /api/autoscale/enable` - Enable autoscaling for a database
- `POST /api/autoscale/disable` - Disable autoscaling for a database
- `POST /api/refresh-cloud` - Refresh cloud data from Redis Cloud API

## Metrics Calculation

### Payload Size
```
Average Payload Size = (Ingress Bytes + Egress Bytes) / Total Requests
```

### Downscale Suggestions
- Only shown when all metrics are healthy
- Uses `max_over_time` aggregation for safety
- Ensures proper headroom below thresholds
- Calculates optimal pricing for suggested configurations

### Status Logic
- **Healthy**: All metrics below thresholds
- **Scale Up**: Throughput or memory above thresholds
- **Review**: CPU, latency, or payload size issues
- **No Data**: No metrics available

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 