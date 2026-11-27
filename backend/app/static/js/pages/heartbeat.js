async function 填租约下拉() {
  const rows = await 租约台.getJSON('/api/租约');
  const sel = document.getElementById('心跳租约');
  const 旧值 = sel.value;
  sel.innerHTML = '';
  for (const r of rows) {
    if (!['生效中', '已续约'].includes(r.状态)) continue;
    const o = document.createElement('option');
    o.value = r.租约号;
    o.textContent = r.租约号 + ' · ' + r.状态;
    sel.appendChild(o);
  }
  if (旧值) sel.value = 旧值;
}

function 当前租约号() {
  return document.getElementById('心跳租约').value;
}

async function 刷新心跳() {
  const rows = await 租约台.getJSON('/api/心跳');
  const tb = document.getElementById('心跳表');
  tb.innerHTML = '';
  for (const r of rows.slice(0, 40)) {
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + 租约台.安全文本(r.心跳号) + '</td>' +
      '<td>' + 租约台.安全文本(r.租约号) + '</td>' +
      '<td>' + 租约台.安全文本(租约台.格式化时刻(r.时刻)) + '</td>' +
      '<td>' + 租约台.安全文本(r.结果) + '</td>' +
      '<td>' + 租约台.安全文本(r.延迟毫秒) + '</td>' +
      '<td>' + 租约台.安全文本(r.说明) + '</td>';
    tb.appendChild(tr);
  }
}

async function 刷新缺口() {
  const [缺口, 影子, 规] = await Promise.all([
    租约台.getJSON('/api/缺口'),
    租约台.getJSON('/api/缺口/影子'),
    租约台.getJSON('/api/租账规'),
  ]);
  const 上限 = 规['连续丢包上限'] || '3';

  const 缺口体 = document.getElementById('缺口表');
  缺口体.innerHTML = '';
  for (const r of 缺口.slice().reverse()) {
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + 租约台.安全文本(r.租约号) + '</td>' +
      '<td>' + 租约台.安全文本(r.缺口序号) + '</td>' +
      '<td>' + 租约台.安全文本(租约台.格式化时刻(r.时刻)) + '</td>' +
      '<td>' + 租约台.安全文本(r.处置态) + '</td>' +
      '<td>' + (r.是否超限 ? '是' : '否') + '</td>' +
      '<td>' + (r.第几次拒延 ? '第' + 租约台.安全文本(r.第几次拒延) + '次拒延' : '—') + '</td>' +
      '<td>' + 租约台.安全文本(r.补偿心跳号 || '—') + '</td>';
    缺口体.appendChild(tr);
  }

  const 影子体 = document.getElementById('影子表');
  影子体.innerHTML = '';
  for (const r of 影子.slice().reverse()) {
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + 租约台.安全文本(r.租约号) + '</td>' +
      '<td>' + 租约台.安全文本(r.缺口序号) + '</td>' +
      '<td>' + 租约台.安全文本(r.处置态) + '</td>' +
      '<td>' + (r.第几次拒延 ? '第' + 租约台.安全文本(r.第几次拒延) + '次拒延' : '—') + '</td>' +
      '<td>' + 租约台.安全文本(租约台.格式化时刻(r.时刻归档)) + '</td>';
    影子体.appendChild(tr);
  }

  const lid = 当前租约号();
  const 本租缺口 = 缺口.filter((r) => r.租约号 === lid);
  const 待补 = 本租缺口.filter((r) => r.处置态 === '缺口已记');
  const 超限 = 本租缺口.some((r) => r.处置态 === '超限拒延');
  const 概 = document.getElementById('缺口概览');
  if (超限) {
    const 行 = 本租缺口.filter((r) => r.处置态 === '超限拒延').pop();
    概.textContent = '连续丢包已超上限 ' + 上限 + '：第 ' + 行.第几次拒延 +
      ' 次丢包拒延时，缺口已记，补偿已拒（候审影子已归档）。';
  } else if (待补.length) {
    概.textContent = '当前有 ' + 待补.length + ' 个心跳缺口待补发（未超上限 ' + 上限 + '），补发成功将记“已补偿”并延时。';
  } else {
    概.textContent = '连续丢包上限 ' + 上限 + '：允许连续丢包不超过三次，第四次必须拒延时。当前无待补缺口。';
  }
}

async function 发(失败) {
  const msg = document.getElementById('心跳消息');
  try {
    const rep = await 租约台.postJSON('/api/心跳', {
      租约号: 当前租约号(),
      延长分钟: Number(document.getElementById('延长分').value),
      模拟失败: 失败,
    });
    let 文 = '结果 ' + rep.结果;
    if (rep.新到期时刻) 文 += ' 新到期 ' + 租约台.格式化时刻(rep.新到期时刻);
    if (rep.结果 === '失败') {
      文 += ' · 连续丢包第 ' + rep.连续丢包数 + ' 次' +
        (rep.是否超限 ? '（已超限：缺口已记，补发拒延时）' : '（缺口已记）');
    }
    msg.textContent = 文;
    await 全刷新();
  } catch (e) {
    msg.textContent = e.message;
  }
}

async function 补发() {
  const msg = document.getElementById('心跳消息');
  try {
    const rep = await 租约台.postJSON('/api/心跳/补发', {
      租约号: 当前租约号(),
      延长分钟: Number(document.getElementById('延长分').value),
    });
    msg.textContent = '补发成功：补偿 ' + rep.补偿缺口数 + ' 个缺口，新到期 ' +
      租约台.格式化时刻(rep.新到期时刻);
    await 全刷新();
  } catch (e) {
    msg.textContent = '补偿已拒：' + e.message;
    await 全刷新();
  }
}

async function 全刷新() {
  await 刷新心跳();
  await 刷新缺口();
  await 填租约下拉();
}

document.getElementById('心跳钮').onclick = () => 发(false);
document.getElementById('失败钮').onclick = () => 发(true);
document.getElementById('补发钮').onclick = () => 补发();
document.getElementById('心跳租约').onchange = () => 刷新缺口();

填租约下拉().then(全刷新);
