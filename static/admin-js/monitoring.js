// admin-js/monitoring.js: раздел «Мониторинг»: проблемы, настройки порогов, журнал инцидентов.

let monitoringState = null;

function monEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function loadMonitoring() {
  try {
    monitoringState = await apiGet('/api/admin/monitoring');
    renderMonitoring();
  } catch(e) {
    if (String(e.message) !== '401') showToast('Не удалось загрузить мониторинг: ' + e.message, 'err');
  }
}

function renderMonitoring() {
  if (!monitoringState) return;
  const st = monitoringState, s = st.settings, open = st.open || [];
  const banner = document.getElementById('monBanner');
  if (!s.enabled) {
    banner.style.color = 'var(--text-muted)';
    banner.textContent = 'Мониторинг выключен: проверки не выполняются и письма не приходят.';
  } else if (open.length) {
    banner.style.color = '#e57373';
    banner.textContent = 'Есть проблемы: ' + open.length;
  } else {
    banner.style.color = '#7bc67e';
    banner.textContent = 'Всё в порядке: проблем не найдено.';
  }
  document.getElementById('monOpen').innerHTML = open.map(i => `
    <div style="padding:12px 16px;border:1px solid var(--black-border);background:var(--black-card);margin-bottom:10px">
      <div style="font-size:13px;color:var(--text-primary)">${monEsc(i.title)}</div>
      <div style="font-size:12px;color:var(--text-secondary);margin-top:4px;line-height:1.6">${monEsc(i.detail)}</div>
      <div style="font-size:11px;color:var(--text-muted);margin-top:4px">Началось: ${monEsc(i.since)}</div>
    </div>`).join('');
  document.getElementById('monRecipient').textContent = st.recipient || '(почта не указана)';
  document.getElementById('monLastRun').textContent = st.last_run || 'ещё не было';
  document.getElementById('monEnabled').checked = !!s.enabled;
  document.getElementById('monIcal').value = s.ical_hours;
  document.getElementById('monBackup').value = s.backup_hours;
  document.getElementById('monDisk').value = s.disk_free_percent;
  document.getElementById('monRemind').value = s.remind_hours;
  document.getElementById('monDeepUrl').textContent = location.origin + '/health/deep';
  const h = st.history || [];
  document.getElementById('monHistory').innerHTML = h.length ? h.map(i => `
    <div style="padding:10px 0;border-top:1px solid var(--black-border);font-size:12px">
      <div style="color:var(--text-primary)">${monEsc(i.title)}</div>
      <div style="color:var(--text-muted);font-size:11px;margin-top:2px">${monEsc(i.since)} → ${monEsc(i.resolved)}</div>
    </div>`).join('') : '<div style="color:var(--text-muted);font-size:12px">Сбоев пока не было</div>';
}

async function saveMonitoring() {
  const num = id => parseInt(document.getElementById(id).value, 10);
  const payload = {
    enabled: document.getElementById('monEnabled').checked,
    ical_hours: num('monIcal'), backup_hours: num('monBackup'),
    disk_free_percent: num('monDisk'), remind_hours: num('monRemind')
  };
  Object.keys(payload).forEach(k => { if (Number.isNaN(payload[k])) delete payload[k]; });
  try {
    monitoringState = await apiRequest('POST', '/api/admin/monitoring', payload);
    renderMonitoring();
    showToast('Настройки мониторинга сохранены', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

async function runMonitoringNow() {
  try {
    monitoringState = await apiRequest('POST', '/api/admin/monitoring/run', {});
    renderMonitoring();
    showToast('Проверка выполнена', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

async function testMonitoringMail() {
  try {
    const r = await apiRequest('POST', '/api/admin/monitoring/test', {});
    if (r.ok) showToast('Тестовое письмо отправлено на ' + r.to, 'gold');
    else showToast('Письмо не отправилось: ' + (r.error || 'неизвестная ошибка'), 'err');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

// Раздел «Мониторинг»: данные загружаются при каждом открытии
(function() {
  const menuItem = document.getElementById('sbMonitoring');
  if (menuItem) menuItem.addEventListener('click', () => {
    const title = document.getElementById('topbarTitle');
    if (title) title.textContent = 'Мониторинг';
    loadMonitoring();
  });
})();
