let balanceChart, equityChart;
const nf = (v, d=2) => Number(v || 0).toLocaleString('id-ID', {minimumFractionDigits:d, maximumFractionDigits:d});

async function loadCharts() {
    try {
        const [dashRes, perfRes, pfRes] = await Promise.all([
            fetch('/api/dashboard'),
            fetch('/api/performance'),
            fetch('/api/portfolio')
        ]);
        const dash = await dashRes.json();
        const perf = await perfRes.json();
        const pf = await pfRes.json();

        // Balance pie chart (by IDR value)
        const items = (pf.portfolio || []).filter(i => i.value_idr > 0);
        if (items.length > 0) {
            const labels = items.map(i => i.asset);
            const values = items.map(i => i.value_idr);
            const colors = ['#0d6efd', '#22c55e', '#eab308', '#ef4444', '#a855f7', '#ec4899', '#14b8a6', '#f97316'];

            if (balanceChart) balanceChart.destroy();
            balanceChart = new Chart(document.getElementById('balanceChart'), {
                type: 'doughnut',
                data: {
                    labels,
                    datasets: [{
                        data: values,
                        backgroundColor: colors.slice(0, labels.length),
                        borderWidth: 0,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: { color: '#94a3b8', boxWidth: 12 }
                        },
                        tooltip: {
                            callbacks: {
                                label: ctx => {
                                    const pct = nf(ctx.parsed / pf.total_idr * 100);
                                    return `${ctx.label}: Rp ${nf(ctx.parsed)} (${pct}%)`;
                                }
                            }
                        }
                    }
                }
            });
        }

        const equityData = pf.equity && pf.equity.length > 1 ? pf.equity : perf.equity;
        if (equityData && equityData.length > 1) {
            const labels = equityData.map(e => new Date(e.timestamp).toLocaleString('id-ID'));
            const values = equityData.map(e => e.equity);

            if (equityChart) equityChart.destroy();
            equityChart = new Chart(document.getElementById('equityChart'), {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label: 'Equity',
                        data: values,
                        borderColor: '#22c55e',
                        backgroundColor: 'rgba(34,197,94,0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#94a3b8', maxTicksLimit: 10 }, grid: { color: '#1e293b' } },
                        y: { ticks: { color: '#94a3b8', callback: v => nf(v) }, grid: { color: '#1e293b' } }
                    }
                }
            });
        }
    } catch (e) {
        console.error('Chart load error:', e);
    }
}

loadCharts();
setInterval(loadCharts, 30000);
