async function loadDashboard() {
    try {
        const [dashRes, pfRes] = await Promise.all([
            fetch('/api/dashboard'),
            fetch('/api/portfolio')
        ]);
        const data = await dashRes.json();
        const pf = await pfRes.json();

        document.getElementById('metric-trades').textContent = data.metrics.total_trades;
        document.getElementById('metric-winrate').textContent = data.metrics.win_rate + '%';
        document.getElementById('metric-pnl').textContent = data.metrics.total_pnl.toLocaleString();
        document.getElementById('metric-pnl').className = data.metrics.total_pnl >= 0 ? 'text-success' : 'text-danger';
        document.getElementById('metric-drawdown').textContent = data.metrics.max_drawdown + '%';
        document.getElementById('metric-orders').textContent = data.active_orders_count;
        document.getElementById('metric-profitfactor').textContent = data.metrics.profit_factor;

        const pfEl = document.getElementById('portfolio-value');
        if (pfEl) {
            pfEl.textContent = pf.total_idr > 0
                ? 'Rp ' + pf.total_idr.toLocaleString('id-ID', {minimumFractionDigits:2})
                : 'Rp 0';
        }
        const btcEl = document.getElementById('btc-price-dash');
        if (btcEl) {
            btcEl.textContent = pf.btc_idr > 0
                ? 'Rp ' + Number(pf.btc_idr).toLocaleString('id-ID')
                : '—';
        }

        const balanceTbody = document.querySelector('#balances-table tbody');
        balanceTbody.innerHTML = '';
        (pf.portfolio || []).forEach(b => {
            balanceTbody.innerHTML += `<tr>
                <td><strong>${b.asset}</strong></td>
                <td>${b.free.toFixed(6)}</td>
                <td>${b.locked.toFixed(6)}</td>
                <td>${b.total.toFixed(6)}</td>
                <td class="text-muted small">Rp ${Number(b.value_idr).toLocaleString('id-ID', {minimumFractionDigits:0})}</td>
            </tr>`;
        });

        const posTbody = document.querySelector('#positions-table tbody');
        posTbody.innerHTML = '';
        data.positions.forEach(p => {
            const pnlClass = p.pnl >= 0 ? 'text-success' : 'text-danger';
            posTbody.innerHTML += `<tr>
                <td>${p.symbol}</td>
                <td><span class="badge bg-${p.side === 'BUY' ? 'success' : 'danger'}">${p.side}</span></td>
                <td>${p.entry_price.toFixed(4)}</td>
                <td>${p.quantity.toFixed(4)}</td>
                <td class="${pnlClass}">${p.pnl.toFixed(2)} (${p.pnl_pct.toFixed(2)}%)</td>
            </tr>`;
        });
    } catch (e) {
        console.error('Dashboard load error:', e);
    }
}

loadDashboard();
setInterval(loadDashboard, 15000);
