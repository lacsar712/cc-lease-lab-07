async function 填池下拉(sel) {
  const rows = await 租约台.getJSON('/api/资源池');
  sel.innerHTML = '';
  for (const r of rows) {
    if (!r.启用) continue;
    const o = document.createElement('option');
    o.value = r.池键;
    o.textContent = r.名称 + ' (' + r.池键 + ')';
    sel.appendChild(o);
  }
}

async function 刷新租约() {
  const st = document.getElementById('状态筛').value;
  const url = st ? '/api/租约?状态=' + encodeURIComponent(st) : '/api/租约';
  const [rows, 缺口] = await Promise.all([
    租约台.getJSON(url),
    租约台.getJSON('/api/缺口'),
  ]);
  const 按租约 = {};
  for (const g of 缺口) {
    if (!按租约[g.租约号]) 按租约[g.租约号] = { 待补: 0, 超限: 0, 已补: 0, 闭合: 0 };
    if (g.处置态 === '缺口已记') 按租约[g.租约号].待补 += 1;
    else if (g.处置态 === '超限拒延') 按租约[g.租约号].超限 += 1;
    else if (g.处置态 === '已补偿') 按租约[g.租约号].已补 += 1;
    else if (g.处置态 === '成功闭合') 按租约[g.租约号].闭合 += 1;
  }
  const tb = document.getElementById('租约表');
  tb.innerHTML = '';
  for (const r of rows) {
    const tr = document.createElement('tr');
    const act = r.状态 === '待生效'
      ? '<button class="按钮" data-id="' + 租约台.安全文本(r.租约号) + '">激活</button>'
      : '';
    const g = 按租约[r.租约号] || { 待补: 0, 超限: 0, 已补: 0, 闭合: 0 };
    const 连续 = g.待补 + g.超限;
    const 连续文 = 连续 ? ('第 ' + 连续 + ' 次' + (g.超限 ? '（超限拒延）' : '（缺口已记）')) : '0';
    const 处置文 = '已补 ' + g.已补 + ' / 闭合 ' + g.闭合 +
      (g.超限 ? ' / 超限拒延 ' + g.超限 : '');
    tr.innerHTML =
      '<td>' + 租约台.安全文本(r.租约号) + '</td>' +
      '<td>' + 租约台.安全文本(r.租户) + '</td>' +
      '<td>' + 租约台.安全文本(r.池键) + '</td>' +
      '<td>' + 租约台.状态徽章(r.状态) + '</td>' +
      '<td>' + 租约台.安全文本(租约台.格式化时刻(r.到期时刻)) + '</td>' +
      '<td>' + 租约台.安全文本(连续文) + '</td>' +
      '<td>' + 租约台.安全文本(处置文) + '</td>' +
      '<td>' + act + '</td>';
    tb.appendChild(tr);
  }
  tb.querySelectorAll('button').forEach((b) => {
    b.onclick = async () => {
      await 租约台.postJSON('/api/租约/激活', { 租约号: b.dataset.id });
      await 刷新租约();
    };
  });
}

document.getElementById('申领钮').onclick = async () => {
  const msg = document.getElementById('申领消息');
  try {
    const row = await 租约台.postJSON('/api/租约/申领', {
      池键: document.getElementById('申领池').value,
      租户: document.getElementById('申领租户').value,
      租期分钟: Number(document.getElementById('申领分钟').value),
      立即生效: document.getElementById('申领立即').value === '1',
    });
    msg.textContent = '已申领 ' + row.租约号 + ' 状态 ' + row.状态;
    await 刷新租约();
  } catch (e) {
    msg.textContent = e.message;
  }
};

document.getElementById('刷新钮').onclick = () => 刷新租约();
document.getElementById('状态筛').onchange = () => 刷新租约();

填池下拉(document.getElementById('申领池'));
刷新租约();