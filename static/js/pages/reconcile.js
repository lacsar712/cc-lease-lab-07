async function 刷新报告() {
  const rows = await 租约台.getJSON('/api/互证');
  const tb = document.getElementById('报告表');
  tb.innerHTML = '';
  for (const r of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + 租约台.安全文本(r.报告号) + '</td>' +
      '<td>' + 租约台.安全文本(租约台.格式化时刻(r.时刻)) + '</td>' +
      '<td>' + 租约台.安全文本(r.结论) + '</td>' +
      '<td>' + (r.是否对齐 ? '对齐' : '有差异') + '</td>' +
      '<td>' + 租约台.安全文本(r.差异摘要) + '</td>';
    tb.appendChild(tr);
  }
}

async function 刷新留痕() {
  const rows = await 租约台.getJSON('/api/留痕');
  const tb = document.getElementById('留痕表');
  tb.innerHTML = '';
  for (const r of rows.slice(0, 30)) {
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + 租约台.安全文本(租约台.格式化时刻(r.时刻)) + '</td>' +
      '<td>' + 租约台.安全文本(r.操作) + '</td>' +
      '<td>' + 租约台.安全文本(r.租约号) + '</td>' +
      '<td>' + 租约台.安全文本(r.详情) + '</td>';
    tb.appendChild(tr);
  }
}

document.getElementById('跑互证').onclick = async () => {
  const rep = await 租约台.postJSON('/api/互证/跑', {});
  const 双轨 = {
    候审缺口数: rep.候审缺口数,
    超限拒延缺口数: rep.超限拒延缺口数,
    合法补偿缺口数: rep.合法补偿缺口数,
    是否全部对齐: rep.是否全部对齐,
    口径: '候审影子只读归档，不算合法补偿；超限拒延缺口单列差异',
  };
  document.getElementById('互证详情').textContent =
    JSON.stringify(双轨, null, 2) + '\n\n' + JSON.stringify(rep, null, 2);
  await 刷新报告();
  await 刷新留痕();
};

刷新报告();
刷新留痕();