# Redis Health Dashboard

A modern, Redis.io-inspired dashboard for monitoring Redis Cloud databases with intelligent autoscaling capabilities.

## Features

### 🎨 Modern UI Design
- **Redis.io-inspired design** with clean, professional aesthetics
- **Responsive layout** that works on desktop and mobile devices
- **Collapsible subscriptions** for better organization of multiple databases
- **Real-time status indicators** with color-coded badges
- **Interactive controls** with hover effects and smooth transitions

### 📊 Dashboard Features
- **Real-time metrics monitoring** for throughput, memory, CPU, and latency
- **Customizable thresholds** for different metrics
- **Auto-refresh capability** with configurable intervals
- **Summary statistics** showing total databases, healthy count, and attention needed
- **Time range selection** from 5 minutes to 2 days, plus absolute time ranges

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

### 📱 User Experience
- **Collapsible subscriptions** - Click the chevron icon to expand/collapse database groups
- **Status indicators**:
  - 🟢 **Healthy** - Database is performing well
  - 🔴 **Scale Up** - Database needs more resources
  - 🟡 **Review** - Some metrics need attention
  - ⚪ **No Data** - No metrics available
- **Help modal** with comprehensive documentation
- **Notifications** for user actions and system events

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

### Environment Variables
- `REDIS_CLOUD_API_KEY`: Your Redis Cloud API key
- `REDIS_CLOUD_API_SECRET`: Your Redis Cloud API secret
- `REDIS_CLOUD_ACCOUNT_ID`: Your Redis Cloud account ID

### Threshold Configuration
The dashboard allows you to customize alert thresholds for different metrics:
- **Throughput**: Percentage of throughput limit before alerting
- **Memory**: Percentage of memory limit before alerting  
- **CPU**: Percentage of CPU usage before alerting
- **Latency**: Maximum acceptable latency in milliseconds

## Usage

### Basic Monitoring
1. The dashboard automatically loads and displays all your Redis Cloud databases
2. Metrics are refreshed every 30 seconds by default
3. Use the time range selector to view different time periods
4. Click the "Auto Refresh" button to enable/disable automatic updates

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

## API Endpoints

- `GET /` - Main dashboard page
- `GET /api/metrics` - Get database metrics
- `GET /api/autoscaling-status` - Get autoscaling status
- `GET /api/autoscale/enabled` - Get enabled autoscaling databases
- `POST /api/autoscale/enable` - Enable autoscaling for a database
- `POST /api/autoscale/disable` - Disable autoscaling for a database

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 