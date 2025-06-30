let customThresholds = null;
let defaultThresholds = {
    throughput: 0.8,
    memory: 0.8,
    cpu: 0.6,
    latency: 3
};

function formatBytes(bytes) {
    if (bytes === null || bytes === undefined) return 'N/A';
    const gb = bytes / (1024 * 1024 * 1024);
    return gb.toFixed(2) + ' GB';
}

function formatThroughput(value, limit) {
    if (value === null || value === undefined) return 'N/A';
    return `${value.toFixed(2)} / ${limit}`;
}

function formatCPU(value, threshold) {
    if (value === null || value === undefined) return 'N/A';
    return `${value.toFixed(2)}% / ${(threshold * 100).toFixed(0)}%`;
}

function formatLatency(value, limit) {
    if (value === null || value === undefined) return 'N/A';
    return `${(value * 1000).toFixed(2)}ms / ${limit}ms`;
}

function getThresholds(db) {
    if (!customThresholds) return db.thresholds;
    // Use custom thresholds if set
    return {
        throughput_threshold: customThresholds.throughput,
        memory_threshold: customThresholds.memory,
        cpu_threshold: customThresholds.cpu,
        latency_threshold_ms: customThresholds.latency
    };
}

function setThresholdInputs(thresh) {
    document.getElementById('thresh-throughput').value = (thresh.throughput * 100).toFixed(0);
    document.getElementById('thresh-memory').value = (thresh.memory * 100).toFixed(0);
    document.getElementById('thresh-cpu').value = (thresh.cpu * 100).toFixed(0);
    document.getElementById('thresh-latency').value = thresh.latency;
}

function getStatusSummary(throughput_ok, memory_ok, cpu_ok, latency_ok, m) {
    // If both throughput and memory are N/A, show No Data
    if ((m.throughput === null || m.throughput === undefined) && (m.memory === null || m.memory === undefined)) {
        return '<span class="badge badge-gray">No Data</span>';
    }
    // If throughput or memory is red (and not N/A), show candidate for upscale
    if ((m.throughput !== null && m.throughput !== undefined && throughput_ok === false) ||
        (m.memory !== null && m.memory !== undefined && memory_ok === false)) {
        return '<span class="badge badge-red">Candidate for upscale</span>';
    }
    // All metrics N/A
    if ([m.throughput, m.memory, m.cpu, m.latency_ms].every(v => v === null || v === undefined)) {
        return '<span class="badge badge-gray">No Data</span>';
    }
    // N/A logic (some metrics N/A)
    if ([m.throughput, m.memory, m.cpu, m.latency_ms].some(v => v === null || v === undefined)) {
        return '';
    }
    // All green
    if (throughput_ok && memory_ok && cpu_ok && latency_ok) {
        return '<span class="badge badge-green">Candidate for downscale</span>';
    }
    // All red
    if (!throughput_ok && !memory_ok && !cpu_ok && !latency_ok) {
        return '<span class="badge badge-red">Candidate for upscale</span>';
    }
    // (throughput is red OR memory is red) AND (CPU and latency are green)
    if ((!throughput_ok || !memory_ok) && cpu_ok && latency_ok) {
        return '<span class="badge badge-red">Candidate for upscale</span>';
    }
    // Only CPU and/or latency red (not throughput or memory)
    if ((cpu_ok === false || latency_ok === false) && throughput_ok && memory_ok && (cpu_ok === false || latency_ok === false) && !(throughput_ok === false || memory_ok === false)) {
        return '<span class="badge badge-yellow">Review usage</span>';
    }
    // Only CPU red
    if (!cpu_ok && throughput_ok && memory_ok && latency_ok) {
        return '<span class="badge badge-yellow">Review usage</span>';
    }
    // Only latency red
    if (!latency_ok && throughput_ok && memory_ok && cpu_ok) {
        return '<span class="badge badge-yellow">Review usage</span>';
    }
    // Only CPU and latency red
    if (!cpu_ok && !latency_ok && throughput_ok && memory_ok) {
        return '<span class="badge badge-yellow">Review usage</span>';
    }
    return '';
}

async function loadData() {
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
    const data = await res.json();
    const tbody = document.querySelector('#metricsTable tbody');
    tbody.innerHTML = '';
    
    // Group data by subscription
    const groupedData = {};
    data.forEach(db => {
        const subName = db.subscription_name;
        if (!groupedData[subName]) {
            groupedData[subName] = [];
        }
        groupedData[subName].push(db);
    });
    
    // Render grouped data
    Object.keys(groupedData).forEach(subName => {
        const databases = groupedData[subName];
        databases.forEach((db, index) => {
            const m = db.metrics;
            const t = getThresholds(db);
            const isFirstRow = index === 0;
            const rowspan = isFirstRow ? databases.length : 0;
            // Calculate OK status with custom thresholds if set
            const throughput_ok = m.throughput !== null && m.throughput < t.throughput_threshold * m.throughput_limit;
            const memory_ok = m.memory !== null && m.memory < t.memory_threshold * m.memory_limit_bytes;
            const cpu_ok = m.cpu !== null && m.cpu < t.cpu_threshold * 100;
            const latency_ok = m.latency_ms !== null && (m.latency_ms * 1000) < t.latency_threshold_ms;
            const summary = getStatusSummary(throughput_ok, memory_ok, cpu_ok, latency_ok, m);
            tbody.innerHTML += `
                <tr>
                    ${isFirstRow ? `<td rowspan="${rowspan}" class="subscription-header">${subName}</td>` : ''}
                    <td>${db.database_name}</td>
                    <td class="${m.throughput === null || m.throughput === undefined ? 'na' : (throughput_ok ? 'ok' : 'fail')}">
                        <div class="value">${formatThroughput(m.throughput, m.throughput_limit)}</div>
                    </td>
                    <td class="${m.memory === null || m.memory === undefined ? 'na' : (memory_ok ? 'ok' : 'fail')}">
                        <div class="value">${formatBytes(m.memory)} / ${formatBytes(m.memory_limit_bytes)}</div>
                    </td>
                    <td class="${m.cpu === null || m.cpu === undefined ? 'na' : (cpu_ok ? 'ok' : 'fail')}">
                        <div class="value">${formatCPU(m.cpu, t.cpu_threshold)}</div>
                    </td>
                    <td class="${m.latency_ms === null || m.latency_ms === undefined ? 'na' : (latency_ok ? 'ok' : 'fail')}">
                        <div class="value">${formatLatency(m.latency_ms, t.latency_threshold_ms)}</div>
                    </td>
                    <td>${summary}</td>
                </tr>
            `;
        });
    });
}

function setupThresholdControls() {
    const controls = document.getElementById('threshold-controls');
    controls.innerHTML = `
        <div class="threshold-panel">
            <div class="threshold-title">Limits Configuration</div>
            <div class="threshold-fields">
                <label>Throughput (%): <input id="thresh-throughput" type="number" min="0" max="100" step="1" value="80"></label>
                <label>Memory (%): <input id="thresh-memory" type="number" min="0" max="100" step="1" value="80"></label>
                <label>CPU (%): <input id="thresh-cpu" type="number" min="0" max="100" step="1" value="60"></label>
                <label>Latency (ms): <input id="thresh-latency" type="number" min="0" step="1" value="3"></label>
                <button id="apply-thresholds">Apply</button>
                <button id="reset-thresholds">Reset</button>
            </div>
        </div>
    `;
    document.getElementById('apply-thresholds').onclick = () => {
        customThresholds = {
            throughput: parseFloat(document.getElementById('thresh-throughput').value) / 100,
            memory: parseFloat(document.getElementById('thresh-memory').value) / 100,
            cpu: parseFloat(document.getElementById('thresh-cpu').value) / 100,
            latency: parseFloat(document.getElementById('thresh-latency').value)
        };
        loadData();
    };
    document.getElementById('reset-thresholds').onclick = () => {
        customThresholds = { ...defaultThresholds };
        setThresholdInputs(defaultThresholds);
        loadData();
    };
    // Set initial values to defaults
    setThresholdInputs(defaultThresholds);
}

// Initialize dashboard
setupThresholdControls();
loadData();
setInterval(loadData, 60000); // auto-refresh every 60s 