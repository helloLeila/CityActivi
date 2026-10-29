(function (root) {
  'use strict';
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const safeUrl = (value) => {
    try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : ''; }
    catch { return ''; }
  };
  const row = (label, value) => value ? `<p><strong>${escape(label)}：</strong>${escape(value)}</p>` : '';
  const link = (url, label) => safeUrl(url) ? `<a class="calendar-detail-link" href="${escape(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${escape(label)} ↗</a>` : '';
  function render(item) {
    const d = item.details || {};
    const sources = Array.isArray(item.sources) ? item.sources : [];
    if (!Object.keys(d).length && !sources.length) return '';
    const highlights = Array.isArray(d.highlights) ? d.highlights : [];
    const transport = d.transport || {};
    return `<section class="calendar-detail-section imported-event-details" aria-label="详细活动信息">
      <h4>详细活动信息</h4>
      ${row('中文解释', d.chinese_explanation)}
      ${highlights.length ? `<h4>内容看点</h4><ul>${highlights.map((x) => `<li>${escape(x)}</li>`).join('')}</ul>` : ''}
      ${row('活动时长', d.duration_text)}${row('费用', d.price_text)}
      ${row('参与条件与旁听', d.participation)}${row('报名状态', ({ open: '报名开放', closed: '报名关闭', unknown: '未核实', cancelled: '活动取消' })[d.registration_status])}
      ${row('是否值得专程前往', d.recommendation)}${row('推荐理由', d.recommendation_reason)}
      ${Object.keys(transport).length ? `<h4>深大地铁站出发交通${transport.estimated === false ? '' : '（估算）'}</h4>${row('方案', transport.plan)}${row('单程时间', transport.one_way_time)}${row('单程费用', transport.one_way_cost)}${row('往返交通耗时', transport.round_trip_time)}` : ''}
      ${link(d.registration_url, '报名入口')}
      ${sources.length ? `<h4>原始来源与核验</h4><ul>${sources.map((s) => `<li>${link(s.url, s.name || '活动来源')}${row('核验时间', s.verified_at)}<details><summary>字段证据</summary>${Object.entries(s.evidence || {}).map(([field, proof]) => row(field, proof.excerpt || '采集器抓取记录')).join('')}</details></li>`).join('')}</ul>` : ''}
      ${item.conflicts?.length ? `<p role="note">${item.conflicts.length} 项来源信息存在冲突，当前保留主来源事实，请核对原文。</p>` : ''}
    </section>`;
  }
  function dateKeys(item, firstDay, days) {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: item.facts.timezone || 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' });
    const keyOf = (value) => { const p = parts.formatToParts(new Date(value)); return ['year', 'month', 'day'].map((k) => p.find((x) => x.type === k).value).join('-'); };
    const start = keyOf(item.facts.start_at);
    const end = item.details?.end_date || (item.facts.end_at ? keyOf(new Date(new Date(item.facts.end_at).getTime() - 1)) : start);
    const keys = [];
    for (let index = 0; index < days; index++) {
      const key = new Date(firstDay.getTime() + index * 86400000).toISOString().slice(0, 10);
      if (key >= start && key <= end) keys.push(key);
    }
    return keys;
  }
  function decorate(target, items) {
    for (const item of items) {
      const detail = target.ownerDocument.getElementById(`detail-${item.id}`);
      const content = detail?.querySelector('.calendar-detail-content');
      if (!content) continue;
      content.insertAdjacentHTML('beforeend', render(item));
      for (const span of content.querySelectorAll('.calendar-meta-primary')) {
        if (span.querySelector('strong')?.textContent === '通勤' && item.enrichment.commute_minutes == null) {
          span.innerHTML = '<strong>通勤</strong>官方未公开';
        }
      }
      if (item.details?.time_precision === 'date') {
        const time = detail.querySelector('.calendar-detail-type');
        if (time) time.textContent = `具体时刻未公开 · ${item.facts.timezone} · ${item.enrichment.kind}`;
      }
    }
  }
  root.CityActiviDetails = { render, decorate, dateKeys, safeUrl };
})(typeof window === 'undefined' ? globalThis : window);
