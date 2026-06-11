async function loadTrades() {
    const symbol = document.getElementById('filter-symbol').value;
    const strategy = document.getElementById('filter-strategy').value;
    const side = document.getElementById('filter-side').value;

    let url = '/api/trades?limit=200';
    if (symbol) url += `&symbol=${symbol}`;
    if (strategy) url += `&strategy=${strategy}`;
    if (side) url += `&side=${side}`;

    try {
        const res = await fetch(url);
        const data = await res.json();
        const tbody = document.querySelector('#trades-table tbody');
        tbody.innerHTML = '';

        data.trades.forEach(t => {
            const sideClass = t.side === 'BUY' ? 'success' : 'danger';
            const pnlClass = t.pnl >= 0 ? 'text-success' : 'text-danger';
            const pnlIcon = t.pnl >= 0 ? 'bi-arrow-up' : 'bi-arrow-down';

            tbody.innerHTML += `<tr>
                <td class="text-muted small">${t.trade_time_str || ''}</td>
                <td><strong>${t.symbol}</strong></td>
                <td><span class="badge bg-${sideClass}">${t.side}</span></td>
                <td>${parseFloat(t.price).toFixed(4)}</td>
                <td>${parseFloat(t.qty).toFixed(4)}</td>
                <td>${parseFloat(t.quote_qty).toFixed(2)}</td>
                <td class="${pnlClass}"><i class="bi ${pnlIcon}"></i> ${parseFloat(t.pnl).toFixed(2)}</td>
                <td><span class="badge bg-secondary">${t.strategy || '-'}</span></td>
            </tr>`;
        });

        if (data.trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No trades found</td></tr>';
        }
    } catch (e) {
        console.error('Trades load error:', e);
    }
}

document.getElementById('filter-symbol').addEventListener('change', loadTrades);
document.getElementById('filter-strategy').addEventListener('change', loadTrades);
document.getElementById('filter-side').addEventListener('change', loadTrades);

loadTrades();
setInterval(loadTrades, 15000);
