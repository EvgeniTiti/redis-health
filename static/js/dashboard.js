// Global variables
let isLoading = false;
let autoscaleEnabled = {};
let autoscaleStatus = {};
let customThresholds = null;
let defaultThresholds = {
    throughput: 0.8,
    memory: 0.8,
    cpu: 0.6,
    latency: 3,
    payload_size_kb: 3
};

// Utility functions
function formatBytes(bytes) {
    if (bytes === null || bytes === undefined) return 'N/A';
    const gb = bytes / (1024 * 1024 * 1024);
    if (gb < 1) {
        const mb = bytes / (1024 * 1024);
        return mb.toFixed(2) + ' MB';
    }
    return gb.toFixed(2) + ' GB';
}

function formatThroughput(value, limit) {
    const actual = (value === null || value === undefined) ? 'N/A' : value.toFixed(2);
    const lim = (limit === null || limit === undefined) ? 'N/A' : limit;
    return `${actual} / ${lim}`;
}

function formatCPU(value, threshold) {
    if (value === null || value === undefined) return 'N/A';
    return `${value.toFixed(2)}% / ${(threshold * 100).toFixed(0)}%`;
}

function formatLatency(value, limit) {
    if (value === null || value === undefined) return 'N/A';
    return `${(value * 1000).toFixed(2)}ms / ${limit}ms`;
}

function formatMaxScaling(memory_gb, throughput_ops) {
    if (memory_gb === null || memory_gb === undefined || throughput_ops === null || throughput_ops === undefined) return 'N/A';
    const throughput_k = throughput_ops / 1000;
    return `${memory_gb}GB / ${throughput_k}K ops/sec`;
}

function formatPriceHourly(price) {
    if (price === null || price === undefined) return 'N/A';
    return `$${price.toFixed(3)}/hr`;
}

function formatMinSubscriptionPrice(price) {
    if (price === null || price === undefined) return 'N/A';
    return `$${price.toFixed(3)}/hr`;
}

function formatPayloadSize(bytes) {
    if (bytes === null || bytes === undefined) return 'N/A';
    return (bytes / 1024).toFixed(1) + ' KB';
}

function getThresholds(db) {
    if (!customThresholds) return db.thresholds;
    // Use custom thresholds if set
    return {
        throughput_threshold: customThresholds.throughput,
        memory_threshold: customThresholds.memory,
        cpu_threshold: customThresholds.cpu,
        latency_threshold_ms: customThresholds.latency,
        payload_size_threshold_kb: customThresholds.payload_size_kb
    };
}

function setThresholdInputs(thresh) {
    document.getElementById('thresh-throughput').value = (thresh.throughput * 100).toFixed(0);
    document.getElementById('thresh-memory').value = (thresh.memory * 100).toFixed(0);
    document.getElementById('thresh-cpu').value = (thresh.cpu * 100).toFixed(0);
    document.getElementById('thresh-latency').value = thresh.latency;
    document.getElementById('thresh-payload-size').value = thresh.payload_size_kb || 1024;
}

function getStatusSummary(throughput_ok, memory_ok, cpu_ok, latency_ok, payload_size_ok, m) {
    // If both throughput and memory are N/A, show No Data
    if ((m.throughput === null || m.throughput === undefined) && (m.memory === null || m.memory === undefined)) {
        return '<span class="badge badge-gray"><i class="fas fa-question-circle"></i> No Data</span>';
    }
    // If throughput or memory is red (and not N/A), show candidate for upscale
    if ((m.throughput !== null && m.throughput !== undefined && throughput_ok === false) ||
        (m.memory !== null && m.memory !== undefined && memory_ok === false)) {
        return '<span class="badge badge-red"><i class="fas fa-arrow-up"></i> Scale Up</span>';
    }
    // All metrics N/A
    if ([m.throughput, m.memory, m.cpu, m.latency_ms, m.payload_size_bytes].every(v => v === null || v === undefined)) {
        return '<span class="badge badge-gray"><i class="fas fa-question-circle"></i> No Data</span>';
    }
    // N/A logic (some metrics N/A)
    if ([m.throughput, m.memory, m.cpu, m.latency_ms, m.payload_size_bytes].some(v => v === null || v === undefined)) {
        return '';
    }
    // All green - no action needed
    if (throughput_ok && memory_ok && cpu_ok && latency_ok && payload_size_ok) {
        return '<span class="badge badge-green"><i class="fas fa-check"></i> Healthy</span>';
    }
    // All red
    if (!throughput_ok && !memory_ok && !cpu_ok && !latency_ok && !payload_size_ok) {
        return '<span class="badge badge-red"><i class="fas fa-arrow-up"></i> Scale Up</span>';
    }
    // (throughput is red OR memory is red) AND (CPU, latency, and payload size are green)
    if ((!throughput_ok || !memory_ok) && cpu_ok && latency_ok && payload_size_ok) {
        return '<span class="badge badge-red"><i class="fas fa-arrow-up"></i> Scale Up</span>';
    }
    // Only CPU, latency, or payload size red (not throughput or memory)
    if ((cpu_ok === false || latency_ok === false || payload_size_ok === false) && throughput_ok && memory_ok) {
        return '<span class="badge badge-yellow"><i class="fas fa-exclamation-triangle"></i> Review</span>';
    }
    // Only CPU red
    if (!cpu_ok && throughput_ok && memory_ok && latency_ok && payload_size_ok) {
        return '<span class="badge badge-yellow"><i class="fas fa-exclamation-triangle"></i> Review</span>';
    }
    // Only latency red
    if (!latency_ok && throughput_ok && memory_ok && cpu_ok && payload_size_ok) {
        return '<span class="badge badge-yellow"><i class="fas fa-exclamation-triangle"></i> Review</span>';
    }
    // Only payload size red
    if (!payload_size_ok && throughput_ok && memory_ok && cpu_ok && latency_ok) {
        return '<span class="badge badge-yellow"><i class="fas fa-exclamation-triangle"></i> Review</span>';
    }
    // Only CPU and latency red
    if (!cpu_ok && !latency_ok && throughput_ok && memory_ok && payload_size_ok) {
        return '<span class="badge badge-yellow"><i class="fas fa-exclamation-triangle"></i> Review</span>';
    }
    // Only CPU and payload size red
    if (!cpu_ok && !payload_size_ok && throughput_ok && memory_ok && latency_ok) {
        return '<span class="badge badge-yellow"><i class="fas fa-exclamation-triangle"></i> Review</span>';
    }
    // Only latency and payload size red
    if (!latency_ok && !payload_size_ok && throughput_ok && memory_ok && cpu_ok) {
        return '<span class="badge badge-yellow"><i class="fas fa-exclamation-triangle"></i> Review</span>';
    }
    return '';
}

// Autoscaling functions
async function fetchAutoscaleStatus() {
    try {
        const res = await fetch('/api/autoscaling-status');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        autoscaleStatus = await res.json();
    } catch (error) {
        console.error('Failed to fetch autoscaling status:', error);
        autoscaleStatus = {};
    }
}

async function fetchAutoscaleEnabled() {
    try {
        const res = await fetch('/api/autoscale/enabled');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const enabledList = await res.json();
        autoscaleEnabled = {};
        enabledList.forEach(([subId, dbId]) => {
            autoscaleEnabled[`${subId}_${dbId}`] = true;
        });
    } catch (error) {
        console.error('Failed to fetch autoscaling enabled status:', error);
        autoscaleEnabled = {};
    }
}

async function setAutoscaleEnabled(subscriptionId, databaseId, enabled) {
    try {
        const res = await fetch(`/api/autoscale/${enabled ? 'enable' : 'disable'}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subscription_id: subscriptionId, database_id: databaseId })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        // Show success feedback
        showNotification(`${enabled ? 'Enabled' : 'Disabled'} autoscaling for database`, 'success');
    } catch (error) {
        console.error('Failed to update autoscaling status:', error);
        showNotification(`Failed to ${enabled ? 'enable' : 'disable'} autoscaling`, 'error');
    }
}

function calculateSummaryStats(data) {
    let total = 0;
    let healthy = 0;
    let attention = 0;
    let autoscaleCount = 0;
    
    data.forEach(db => {
        total++;
        const m = db.metrics;
        const t = getThresholds(db);
        
        // Check if autoscaling is enabled
        const enabledKey = `${db.subscription_id}_${db.database_id}`;
        if (autoscaleEnabled[enabledKey]) {
            autoscaleCount++;
        }

        // Calculate health status
        const throughput_ok = m.throughput !== null && m.throughput < t.throughput_threshold * m.throughput_limit;
        const memory_ok = m.memory !== null && m.memory < t.memory_threshold * m.memory_limit_bytes;
        const cpu_ok = m.cpu !== null && m.cpu < t.cpu_threshold * 100;
        const latency_ok = m.latency_ms !== null && (m.latency_ms * 1000) < t.latency_threshold_ms;

        // Determine if needs attention
        if ((m.throughput !== null && m.throughput !== undefined && !throughput_ok) ||
            (m.memory !== null && m.memory !== undefined && !memory_ok) ||
            (m.cpu !== null && m.cpu !== undefined && !cpu_ok) ||
            (m.latency_ms !== null && m.latency_ms !== undefined && !latency_ok)) {
            attention++;
        } else if (m.throughput !== null && m.memory !== null) {
            healthy++;
        }
    });
    
    return { total, healthy, attention, autoscaleCount };
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
        ${message}
    `;
    
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => notification.classList.add('show'), 100);
    
    // Remove after 3 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

function setLoadingState(loading) {
    isLoading = loading;
    const container = document.querySelector('.metrics-container');
    const refreshBtn = document.getElementById('refresh-btn'); // Use ID, not class!
    
    if (loading) {
        container.classList.add('loading');
        if (refreshBtn) {
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
            refreshBtn.disabled = true;
        }
    } else {
        container.classList.remove('loading');
        if (refreshBtn) {
            refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
            refreshBtn.disabled = false;
        }
    }
}

// Main data loading function
async function loadData() {
    if (isLoading) return;
    setLoadingState(true);
    try {
        // Get time range selection
        let period = document.getElementById('time-range-select')?.value || '5m';
        let params = [];
        if (period === 'absolute') {
            const absFrom = document.getElementById('abs-from').value;
            const absTo = document.getElementById('abs-to').value;
            if (absFrom && absTo) {
                params.push('abs_from=' + encodeURIComponent(absFrom));
                params.push('abs_to=' + encodeURIComponent(absTo));
            }
        } else {
            params.push('period=' + encodeURIComponent(period));
        }
        const res = await fetch('/api/metrics' + (params.length ? ('?' + params.join('&')) : ''));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setLoadingState(false); // Hide spinner as soon as data is fetched
        const dbs = data.databases || data;
        
        await fetchAutoscaleEnabled();
        await fetchAutoscaleStatus();
        
        // Show/hide warning banner
        let banner = document.getElementById('prometheus-warning');
        if (!banner && data.prometheus_available === false) {
            banner = document.createElement('div');
            banner.id = 'prometheus-warning';
            banner.className = 'notification notification-info show';
            banner.innerHTML = '<i class="fas fa-info-circle"></i> Live metrics unavailable. Showing configuration data only.';
            document.body.prepend(banner);
        } else if (banner && data.prometheus_available !== false) {
            banner.remove();
        }
        
        const tbody = document.querySelector('#metricsTable tbody');
        tbody.innerHTML = '';
        
        // Calculate and display summary stats
        const stats = calculateSummaryStats(dbs);
        document.getElementById('total-dbs').textContent = stats.total;
        document.getElementById('healthy-dbs').textContent = stats.healthy;
        document.getElementById('attention-dbs').textContent = stats.attention;
        document.getElementById('autoscale-enabled').textContent = stats.autoscaleCount;
        document.getElementById('summary-stats').style.display = 'block';
        
        // Group data by subscription
        const groupedData = {};
        dbs.forEach(db => {
            const subName = db.subscription_name;
            if (!groupedData[subName]) {
                groupedData[subName] = [];
            }
            groupedData[subName].push(db);
        });
        
        // Render grouped data
        Object.keys(groupedData).forEach(subName => {
            const databases = groupedData[subName];
            const subId = databases[0].subscription_id;
            const collapseId = `collapse-${subId}`;
            
            // Add subscription header with collapse button
            tbody.innerHTML += `
                <tr class="subscription-row" data-subscription="${subId}">
                    <td class="subscription-header" colspan="10">
                        <div class="subscription-header-content">
                            <button class="collapse-btn" onclick="toggleSubscription('${collapseId}')" title="Toggle subscription">
                                <i class="fas fa-chevron-down"></i>
                            </button>
                            <span class="subscription-name">${subName}</span>
                            <span class="subscription-count">(${databases.length} database${databases.length > 1 ? 's' : ''})</span>
                        </div>
                    </td>
                </tr>
            `;
            
            // Add database rows
            databases.forEach((db, index) => {
                const m = db.metrics;
                const t = getThresholds(db);
                // Debug: log throughput_limit
                console.log('DB', db.database_name, 'throughput_limit:', m.throughput_limit);
                // Calculate OK status with custom thresholds if set
                const throughput_ok = m.throughput !== null && m.throughput < t.throughput_threshold * m.throughput_limit;
                const memory_ok = m.memory !== null && m.memory < t.memory_threshold * m.memory_limit_bytes;
                const cpu_ok = m.cpu !== null && m.cpu < t.cpu_threshold * 100;
                const latency_ok = m.latency_ms !== null && (m.latency_ms * 1000) < t.latency_threshold_ms;
                const payload_size_ok = m.payload_size_bytes !== null && m.payload_size_bytes < (t.payload_size_threshold_kb || 1024) * 1024;
                const summary = getStatusSummary(throughput_ok, memory_ok, cpu_ok, latency_ok, payload_size_ok, m);
                
                const dbId = db.database_id;
                const enabledKey = `${subId}_${dbId}`;
                let checked = autoscaleEnabled[enabledKey] ? 'checked' : '';
                let autoscaleCell = `<input type="checkbox" class="autoscale-checkbox" data-db="${dbId}" data-sub="${subId}" ${checked} />`;
                
                // Build table row with conditional autoscaling cell
                let rowHTML = `
                    <tr class="database-row ${collapseId}" data-subscription="${subId}">
                        <td></td>
                        <td>${db.database_name}</td>
                        <td class="${m.throughput === null || m.throughput === undefined ? 'na' : (throughput_ok ? 'ok' : 'fail')}">
                            <div class="value">${formatThroughput(m.throughput, m.throughput_limit)}</div>
                            ${db.downscale_throughput_ops ? `<div class='downscale-suggestion'>↓ Suggest: ${db.downscale_throughput_ops.toLocaleString()} ops</div>` : ''}
                        </td>
                        <td class="${m.memory === null || m.memory === undefined ? 'na' : (memory_ok ? 'ok' : 'fail')}">
                            <div class="value">${formatBytes(m.memory)} / ${formatBytes(m.memory_limit_bytes)}</div>
                            ${db.downscale_memory_mb ? `<div class='downscale-suggestion'>↓ Suggest: ${db.downscale_memory_mb} MB</div>` : ''}
                        </td>
                        <td class="${m.cpu === null || m.cpu === undefined ? 'na' : (cpu_ok ? 'ok' : 'fail')}">
                            <div class="value">${formatCPU(m.cpu, t.cpu_threshold)}</div>
                        </td>
                        <td class="${m.latency_ms === null || m.latency_ms === undefined ? 'na' : (latency_ok ? 'ok' : 'fail')}">
                            <div class="value">${formatLatency(m.latency_ms, t.latency_threshold_ms)}</div>
                        </td>
                        <td class="${m.payload_size_bytes === null || m.payload_size_bytes === undefined ? 'na' : (payload_size_ok ? 'ok' : 'fail')}">
                            <div class="value">${formatPayloadSize(m.payload_size_bytes)}</div>
                        </td>
                        <td>${summary}`;
                
                // Add autoscaling cells
                rowHTML += `<td>${autoscaleCell}</td>`;
                rowHTML += `<td><div class="value">${formatMaxScaling(db.max_scaling?.memory_gb, db.max_scaling?.throughput_ops)}</div></td>`;
                
                rowHTML += `
                        <td><div class="value">${formatPriceHourly(db.price_hourly)}</div>
                            ${db.downscale_price_suggestion ? `<div class='price-suggestion'>💲 $${db.downscale_price_suggestion.price}/hr (${db.downscale_price_suggestion.unit_type}${db.downscale_price_suggestion.units_needed > 1 ? ' x' + db.downscale_price_suggestion.units_needed : ''})</div>` : ''}
                        </td>
                        <td><div class="value">${formatMinSubscriptionPrice(db.min_subscription_price)}</div></td>
                    </tr>
                `;
                
                tbody.innerHTML += rowHTML;
            });
        });
        
        // Update last updated timestamp
        updateLastUpdated();
        
        // Add event listeners to autoscale checkboxes
        document.querySelectorAll('.autoscale-checkbox').forEach(cb => {
            cb.addEventListener('change', async function() {
                await setAutoscaleEnabled(this.getAttribute('data-sub'), this.getAttribute('data-db'), this.checked);
            });
        });
        
    } catch (error) {
        setLoadingState(false);
        console.error('Failed to load data:', error);
        showNotification('Failed to load metrics data', 'error');
        const errorColspan = 10;
        document.querySelector('#metricsTable tbody').innerHTML = `
            <tr>
                <td colspan="${errorColspan}" style="text-align: center; padding: 40px; color: #6c757d;">
                    <i class="fas fa-exclamation-triangle" style="font-size: 2em; margin-bottom: 10px;"></i><br>
                    Failed to load data. Please try again.
                </td>
            </tr>
        `;
    }
}

function setupThresholdControls() {
    const controls = document.getElementById('threshold-controls');
    controls.innerHTML = `
        <div class="threshold-panel">
            <div class="threshold-title">Threshold Configuration</div>
            <div class="threshold-fields">
                <label>Throughput (%): <input id="thresh-throughput" type="number" min="0" max="100" step="1" value="80"></label>
                <label>Memory (%): <input id="thresh-memory" type="number" min="0" max="100" step="1" value="80"></label>
                <label>CPU (%): <input id="thresh-cpu" type="number" min="0" max="100" step="1" value="60"></label>
                <label>Latency (ms): <input id="thresh-latency" type="number" min="0" step="1" value="3"></label>
                <label>Payload Size (KB): <input id="thresh-payload-size" type="number" min="0" step="1" value="1024"></label>
                <button id="apply-thresholds" class="btn btn-primary">Apply</button>
                <button id="reset-thresholds" class="btn btn-secondary">Reset</button>
            </div>
        </div>
    `;
    
    document.getElementById('apply-thresholds').onclick = () => {
        const newThresholds = {
            throughput: parseFloat(document.getElementById('thresh-throughput').value) / 100,
            memory: parseFloat(document.getElementById('thresh-memory').value) / 100,
            cpu: parseFloat(document.getElementById('thresh-cpu').value) / 100,
            latency: parseFloat(document.getElementById('thresh-latency').value),
            payload_size_kb: parseFloat(document.getElementById('thresh-payload-size').value)
        };
        
        // Only reload if thresholds actually changed
        const thresholdsChanged = !customThresholds || 
            customThresholds.throughput !== newThresholds.throughput ||
            customThresholds.memory !== newThresholds.memory ||
            customThresholds.cpu !== newThresholds.cpu ||
            customThresholds.latency !== newThresholds.latency ||
            customThresholds.payload_size_kb !== newThresholds.payload_size_kb;
        
        if (thresholdsChanged) {
            customThresholds = newThresholds;
            showNotification('Threshold configuration applied successfully', 'success');
            loadData();
        } else {
            showNotification('No changes to apply', 'info');
        }
    };
    
    document.getElementById('reset-thresholds').onclick = () => {
        if (customThresholds !== null) {
            customThresholds = null;
            setThresholdInputs(defaultThresholds);
            showNotification('Threshold configuration reset to defaults', 'info');
            loadData();
        } else {
            showNotification('Already using default thresholds', 'info');
        }
    };
    
    // Set initial values to defaults
    setThresholdInputs(defaultThresholds);
}

// Add this function to handle manual cloud refresh
async function refreshCloudData() {
    try {
        const res = await fetch('/api/refresh-cloud', { method: 'POST' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        showNotification('Cloud data refreshed successfully', 'success');
        await loadData();
    } catch (error) {
        showNotification('Failed to refresh cloud data', 'error');
    }
}

function updateLastUpdated() {
    const now = new Date();
    const timeString = now.toLocaleTimeString();
    const dateString = now.toLocaleDateString();
    document.getElementById('last-updated').textContent = `Last updated: ${dateString} ${timeString}`;
}

// Initialize dashboard
document.addEventListener('DOMContentLoaded', async function() {
    setupThresholdControls(); // Only once on page load
    
    // Fetch config for Prometheus interval
    let prometheusInterval = 30000;
    try {
        const res = await fetch('/api/config');
        if (res.ok) {
            const config = await res.json();
            if (config.prometheus_query_interval_seconds) {
                prometheusInterval = config.prometheus_query_interval_seconds * 1000;
            }
        }
    } catch (e) { /* fallback to default */ }
    
    // Load initial data
    loadData();
    
    // Auto-refresh using config interval
    window.autoRefreshInterval = setInterval(loadData, prometheusInterval);
    
    // Add manual cloud refresh button
    const controlPanel = document.querySelector('.control-panel');
    if (controlPanel) {
        const refreshCloudBtn = document.createElement('button');
        refreshCloudBtn.className = 'btn btn-warning';
        refreshCloudBtn.innerHTML = '<i class="fas fa-cloud"></i> Refresh Cloud Data';
        refreshCloudBtn.onclick = refreshCloudData;
        // Insert after the regular refresh button
        const refreshBtn = controlPanel.querySelector('.btn-primary');
        if (refreshBtn && refreshBtn.parentNode) {
            refreshBtn.parentNode.insertBefore(refreshCloudBtn, refreshBtn.nextSibling);
        } else {
            controlPanel.appendChild(refreshCloudBtn);
        }
        // Add id to the main Refresh button for targeting
        if (refreshBtn) {
            refreshBtn.id = 'refresh-btn';
        }
    }
    
    // Add event handler for main Refresh button
    const mainRefreshBtn = document.getElementById('refresh-btn');
    if (mainRefreshBtn) {
        mainRefreshBtn.onclick = () => {
            setupThresholdControls(); // Reload threshold controls
            loadData();               // Reload data
        };
    }
    
    // Time frame change only reloads data
    const timeRangeSelect = document.getElementById('time-range-select');
    if (timeRangeSelect) {
        timeRangeSelect.onchange = () => {
            loadData();
        };
    }
});

// Toggle subscription collapse/expand
function toggleSubscription(collapseId) {
    const databaseRows = document.querySelectorAll(`.${collapseId}`);
    const subscriptionRow = document.querySelector(`[data-subscription="${collapseId.replace('collapse-', '')}"]`);
    const collapseBtn = subscriptionRow.querySelector('.collapse-btn i');
    
    const isCollapsed = databaseRows[0].style.display === 'none';
    
    databaseRows.forEach(row => {
        row.style.display = isCollapsed ? 'table-row' : 'none';
    });
    
    // Update button icon
    collapseBtn.className = isCollapsed ? 'fas fa-chevron-down' : 'fas fa-chevron-right';
    
    // Update button title
    const btn = subscriptionRow.querySelector('.collapse-btn');
    btn.title = isCollapsed ? 'Collapse subscription' : 'Expand subscription';
} 