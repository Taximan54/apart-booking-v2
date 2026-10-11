// admin-js/integrations.js: Интеграции: синхронизация календарей с площадками (Авито, Яндекс Путешествия, Суточно.ру и другие).
// Часть админки (ранее единого admin.js). Файлы подключаются подряд, в порядке из admin.html.

let calState = { platforms: [], presets: [], max_platforms: 30 };

// Запросы PUT и DELETE с понятным текстом ошибки от сервера (например, «Ссылка должна начинаться с http://»)
async function calRequest(method, path, data) {
  const r = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {})
    },
    body: data === undefined ? undefined : JSON.stringify(data),
    signal: AbortSignal.timeout(15000)
  });
  if (r.status === 401) { forceRelogin(); throw new Error('401'); }
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json()).detail; } catch(e) {}
    throw new Error(detail || r.status);
  }
  return r.json();
}

function calEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function calSyncText(sync, hasUrl) {
  if (!hasUrl) return 'Ссылка на календарь площадки не указана: даты с неё не забираются.';
  if (!sync) return 'Синхронизация ещё не запускалась.';
  if (!sync.ok) return `Последняя попытка ${sync.at}: ошибка — ${sync.error || 'неизвестно'}`;
  return `Последняя синхронизация ${sync.at}: новых блокировок ${sync.created}, обновлено ${sync.updated}, снято ${sync.cancelled}, пропущено (уже заняты) ${sync.skipped}.`;
}

function renderCalendars() {
  const box = document.getElementById('calPlatforms');
  if (!box) return;
  if (!calState.platforms.length) {
    box.innerHTML = '<div style="color:var(--text-muted);padding:8px 0 4px;font-size:12px">Площадки пока не добавлены. Выберите площадку ниже и нажмите «Добавить».</div>';
  } else {
    box.innerHTML = calState.platforms.map(p => {
      const s = calEsc(p.source);
      const failed = p.url && p.last_sync && !p.last_sync.ok;
      const badge = !p.url ? ['только отдаём даты', 'rgba(90,74,48,.3)', 'var(--text-muted)']
        : failed ? ['ошибка', 'rgba(248,113,113,.15)', '#f87171']
        : !p.enabled ? ['получение выключено', 'rgba(90,74,48,.3)', 'var(--text-muted)']
        : ['синхронизация включена', 'rgba(74,222,128,.12)', '#4ade80'];
      return `
      <div style="padding:16px;border:1px solid var(--black-border);background:var(--black-card);margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px">
          <div style="font-size:14px;color:var(--text-primary)">${calEsc(p.name)}</div>
          <span style="font-size:10px;padding:2px 10px;background:${badge[1]};color:${badge[2]}">${badge[0]}</span>
        </div>
        <div class="info-field" style="margin-bottom:14px">
          <div class="info-label">Наша ссылка (вставьте в кабинете площадки)</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <input type="text" class="info-input" id="calExport_${s}" readonly value="${calEsc(p.export_url)}" style="flex:1;min-width:200px">
            <button class="btn btn-ghost btn-sm" onclick="copyCalUrl('${s}')">Копировать</button>
            <button class="btn btn-ghost btn-sm" onclick="regenCalToken('${s}')">Сменить</button>
          </div>
        </div>
        <div class="info-field" style="margin-bottom:12px">
          <div class="info-label">Ссылка на календарь площадки (скопируйте в её кабинете)</div>
          <input type="text" class="info-input" id="calUrl_${s}" maxlength="600" placeholder="https://..." value="${calEsc(p.url)}">
        </div>
        <label style="display:flex;gap:8px;align-items:center;font-size:12px;color:var(--text-secondary);margin-bottom:14px;cursor:pointer">
          <input type="checkbox" id="calEnabled_${s}" ${p.enabled ? 'checked' : ''}> Забирать календарь площадки автоматически
        </label>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px">
          <button class="btn btn-primary btn-sm" onclick="saveCalPlatform('${s}')">Сохранить</button>
          <button class="btn btn-ghost btn-sm" onclick="syncCalPlatform('${s}')">Синхронизировать</button>
          <button class="btn btn-danger btn-sm" onclick="deleteCalPlatform('${s}')">Удалить площадку</button>
        </div>
        <div style="font-size:11px;color:${failed ? '#f87171' : 'var(--text-muted)'};line-height:1.7" id="calStatus_${s}">${calEsc(calSyncText(p.last_sync, !!p.url))}</div>
      </div>`;
    }).join('');
  }
  // список «Добавить площадку»: готовые варианты (кроме уже добавленных) и своя
  const used = new Set(calState.platforms.map(p => p.source));
  const sel = document.getElementById('calPreset');
  const prev = sel.value;
  sel.innerHTML = calState.presets.filter(x => !used.has(x.source))
      .map(x => `<option value="${calEsc(x.source)}">${calEsc(x.name)}</option>`).join('')
    + '<option value="__custom__">Другая площадка (своё название)…</option>';
  if ([...sel.options].some(o => o.value === prev)) sel.value = prev;
  onCalPresetChange();
}

function onCalPresetChange() {
  const custom = document.getElementById('calPreset').value === '__custom__';
  document.getElementById('calCustomName').style.display = custom ? '' : 'none';
}

async function loadIntegrations() {
  try {
    calState = await apiGet('/api/admin/integrations/calendars');
    renderCalendars();
  } catch(e) {}
}

async function addCalPlatform() {
  const sel = document.getElementById('calPreset');
  let body;
  if (sel.value === '__custom__') {
    const name = document.getElementById('calCustomName').value.trim();
    if (!name) { showToast('Введите название площадки', 'err'); return; }
    body = { name };
  } else {
    const preset = calState.presets.find(x => x.source === sel.value);
    body = { name: preset ? preset.name : sel.value, source: sel.value };
  }
  try {
    calState = await apiPost('/api/admin/integrations/calendars', body);
    document.getElementById('calCustomName').value = '';
    renderCalendars();
    showToast('Площадка добавлена', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

async function saveCalPlatform(source) {
  try {
    calState = await calRequest('PUT', '/api/admin/integrations/calendars/' + encodeURIComponent(source), {
      url: document.getElementById('calUrl_' + source).value.trim(),
      enabled: document.getElementById('calEnabled_' + source).checked
    });
    renderCalendars();
    showToast('Сохранено', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

async function syncCalPlatform(source) {
  try {
    // сначала сохраняем ссылку из поля, чтобы синхронизировать именно с ней
    await calRequest('PUT', '/api/admin/integrations/calendars/' + encodeURIComponent(source), {
      url: document.getElementById('calUrl_' + source).value.trim(),
      enabled: document.getElementById('calEnabled_' + source).checked
    });
    const d = await apiPost('/api/admin/integrations/calendars/' + encodeURIComponent(source) + '/sync', {});
    calState = d;
    renderCalendars();
    if (d.report && d.report.ok) {
      showToast('Календарь синхронизирован', 'gold');
      if (typeof loadAll === 'function') loadAll();
    } else {
      showToast('Ошибка: ' + ((d.report && d.report.error) || 'не удалось синхронизировать'), 'err');
    }
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

async function syncAllCalendars() {
  const btn = document.getElementById('calSyncAllBtn');
  btn.disabled = true;
  try {
    const d = await apiPost('/api/admin/integrations/calendars/sync-all', {});
    calState = d;
    renderCalendars();
    const reports = Object.values(d.reports || {});
    const failed = reports.filter(r => !r.ok).length;
    document.getElementById('calGlobalStatus').textContent = reports.length
      ? `Синхронизировано площадок: ${reports.length - failed} из ${reports.length}.` + (failed ? ' Ошибки смотрите в карточках площадок.' : '')
      : 'Нет площадок со ссылкой на календарь.';
    if (typeof loadAll === 'function') loadAll();
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  } finally {
    btn.disabled = false;
  }
}

async function deleteCalPlatform(source) {
  const p = calState.platforms.find(x => x.source === source);
  if (!confirm(`Удалить площадку «${p ? p.name : source}»? Блокировки дат, пришедшие из её календаря, будут сняты, а ссылка на наш календарь перестанет работать.`)) return;
  try {
    const d = await calRequest('DELETE', '/api/admin/integrations/calendars/' + encodeURIComponent(source));
    calState = d;
    renderCalendars();
    showToast(`Площадка удалена (снято блокировок: ${d.removed_blocks || 0})`, 'gold');
    if (typeof loadAll === 'function') loadAll();
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

async function regenCalToken(source) {
  if (!confirm('Сменить ссылку нашего календаря для этой площадки? Старая перестанет работать, новую нужно будет заново вставить в кабинете площадки.')) return;
  try {
    calState = await apiPost('/api/admin/integrations/calendars/' + encodeURIComponent(source) + '/regenerate-token', {});
    renderCalendars();
    showToast('Ссылка изменена. Вставьте новую в кабинете площадки.', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

function copyCalUrl(source) {
  const input = document.getElementById('calExport_' + source);
  input.select();
  try {
    navigator.clipboard.writeText(input.value);
  } catch(e) {
    document.execCommand('copy');
  }
  showToast('Ссылка скопирована', 'gold');
}

// Ручная бронь: список источников = привычные (Авито, Яндекс, Суточно) + площадки из «Интеграций» + Телефон + Другое
async function loadManualSources() {
  const sel = document.getElementById('mbSource');
  if (!sel) return;
  let platforms = [];
  try {
    platforms = (await apiGet('/api/admin/integrations/calendars')).platforms || [];
  } catch(e) { return; }
  const base = [['avito', 'Avito'], ['yandex', 'Яндекс.Путешествия'], ['sutochno', 'Суточно.ру']];
  const names = {};
  platforms.forEach(p => { names[p.source] = p.name; });
  const options = base.map(([v, label]) => [v, names[v] || label]);
  platforms.filter(p => !base.some(([v]) => v === p.source)).forEach(p => options.push([p.source, p.name]));
  options.push(['phone', 'Телефон'], ['other', 'Другое']);
  const current = sel.value;
  sel.innerHTML = options.map(([v, label]) => `<option value="${calEsc(v)}">${calEsc(label)}</option>`).join('');
  if (options.some(([v]) => v === current)) sel.value = current;
}
