const nf = (v, d=2) => Number(v || 0).toLocaleString('id-ID', {minimumFractionDigits:d, maximumFractionDigits:d});

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
        const pnl = data.metrics.total_pnl;
        document.getElementById('metric-pnl').textContent = nf(pnl);
        document.getElementById('metric-pnl').className = pnl >= 0 ? 'text-success' : 'text-danger';
        document.getElementById('metric-drawdown').textContent = nf(data.metrics.max_drawdown) + '%';
        document.getElementById('metric-orders').textContent = data.active_orders_count;
        const pfVal = data.metrics.profit_factor;
        document.getElementById('metric-profitfactor').textContent = typeof pfVal === 'string' || pfVal > 0 ? pfVal : '—';

        const pfEl = document.getElementById('portfolio-value');
        if (pfEl) {
            pfEl.textContent = pf.total_idr > 0 ? 'Rp ' + nf(pf.total_idr) : 'Rp 0';
        }
        const btcEl = document.getElementById('btc-price-dash');
        if (btcEl) {
            btcEl.textContent = pf.btc_idr > 0 ? 'Rp ' + nf(pf.btc_idr) : '—';
        }

        const balanceTbody = document.querySelector('#balances-table tbody');
        balanceTbody.innerHTML = '';
        (pf.portfolio || []).filter(b => b.value_idr >= 20000).forEach(b => {
            balanceTbody.innerHTML += `<tr>
                <td><strong>${b.asset}</strong></td>
                <td>${nf(b.free, 6)}</td>
                <td>${nf(b.locked, 6)}</td>
                <td>${nf(b.total, 6)}</td>
                <td class="text-muted small">Rp ${nf(b.value_idr)}</td>
            </tr>`;
        });

        const posTbody = document.querySelector('#positions-table tbody');
        posTbody.innerHTML = '';
        
        const addDustRow = (asset, qty, price, value) => {
            posTbody.innerHTML += `<tr class="table-secondary opacity-50">
                <td>${asset} <span class="badge bg-secondary">dust</span></td>
                <td><span class="badge bg-success">BUY</span></td>
                <td>-</td>
                <td>${nf(price)}</td>
                <td>${nf(qty, 4)}</td>
                <td>-</td>
                <td>-</td>
                <td class="text-muted">${nf(value)} IDR</td>
            </tr>`;
        };
        
        const addPositionRow = (p) => {
            const pnlClass = p.pnl >= 0 ? 'text-success' : 'text-danger';
            posTbody.innerHTML += `<tr>
                <td>${p.symbol}</td>
                <td><span class="badge bg-${p.side === 'BUY' ? 'success' : 'danger'}">${p.side}</span></td>
                <td>${nf(p.entry_price)}</td>
                <td>${nf(p.current_price || 0)}</td>
                <td>${nf(p.quantity, 4)}</td>
                <td class="text-danger">${nf(p.stop_loss)}</td>
                <td class="text-success">${nf(p.take_profit)}</td>
                <td class="${pnlClass}">${nf(p.pnl)} (${nf(p.pnl_pct)}%)</td>
            </tr>`;
        };
        
        data.positions.forEach(p => {
            addPositionRow(p);
        });
        
        if (data.dust_positions) {
            data.dust_positions.forEach(d => {
                addDustRow(d.asset, d.qty, d.price, d.value);
            });
        }
    } catch (e) {
        console.error('Dashboard load error:', e);
    }
}

loadDashboard();
setInterval(loadDashboard, 15000);
