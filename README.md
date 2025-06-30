# redis-health

**Note:** This project is only relevant for Redis Cloud users. You must have a Redis Cloud API key and access to a Prometheus server to use this dashboard.

A web-based dashboard for monitoring Redis health and throughput.

## Features
- Visualize Redis throughput and health metrics
- Customizable dashboard
- Easy setup and configuration

## Requirements
- Redis Cloud account with API key and secret
- Prometheus server with access to Redis metrics

## Setup

1. **Clone the repository:**
   ```sh
   git clone https://github.com/EvgeniTiti/redis-health.git
   cd redis-health
   ```
2. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
3. **Configure:**
   - Edit `config.yaml` to set your Prometheus server endpoint.
   - Create a `.env` file with your Redis Cloud API key and secret (see `.env.example`).
4. **Run the app:**
   ```sh
   python app.py
   ```

## Usage
- Access the dashboard at `http://localhost:5000` (or the port specified in your config).
- View real-time Redis metrics and throughput.

## Project Structure
- `app.py` - Main Flask application
- `throughput.py` - Throughput monitoring logic
- `config.yaml` - Configuration file
- `static/` - CSS and JS assets
- `templates/` - HTML templates

## License
MIT 