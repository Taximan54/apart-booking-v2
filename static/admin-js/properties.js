// admin-js/properties.js: Объекты (квартиры): переключатель в меню и раздел «Объекты».
// Часть админки (ранее единого admin.js). Файлы подключаются подряд, в порядке из admin.html.

let propState = { properties: [], default_id: 1 };

function propEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// Переключатель объектов в левом меню: виден, когда объектов больше одного
async function loadPropertySwitch() {
  try {
    propState = await apiGet('/api/admin/properties', { 'X-Property-Id': '1' });
  } catch(e) {
    if (String(e.message) !== '401') showToast('Не удалось загрузить список объектов: ' + e.message, 'err');
    return;
  }
  renderPropertySwitch();
}

function renderPropertySwitch() {
  const items = propState.properties;
  propCacheWrite(items);
  renderPropertyBadge(items);   // плавающий переключатель: не зависит от бокового меню
  const box = document.getElementById('sbPropertyBox');
  const sel = document.getElementById('propertySwitch');
  if (!box || !sel) return;
  // выбранного объекта больше нет (например, удалён): возвращаемся к основному
  if (!items.some(p => String(p.id) === ADMIN_PROPERTY_ID)) {
    try { localStorage.setItem('adminPropertyId', '1'); } catch(e) {}
    if (ADMIN_PROPERTY_ID !== '1') { location.reload(); return; }
  }
  box.style.display = items.length > 1 ? '' : 'none';
  sel.innerHTML = items.map(p => `<option value="${p.id}">${propEsc(p.name)}${p.active ? '' : ' (отключён)'}</option>`).join('');
  sel.value = ADMIN_PROPERTY_ID;
}

// Плавающий переключатель объектов в углу экрана: виден всегда, пока объектов больше одного,
// и не зависит от бокового меню. Список объектов запоминается в браузере, поэтому переключатель
// появляется сразу при открытии админки, даже если сервер ответит не сразу.
const PROP_CACHE_KEY = 'adminPropertyList';

function propCacheRead() {
  try {
    const list = JSON.parse(localStorage.getItem(PROP_CACHE_KEY) || '[]');
    return Array.isArray(list) ? list : [];
  } catch(e) { return []; }
}

function propCacheWrite(items) {
  try {
    localStorage.setItem(PROP_CACHE_KEY, JSON.stringify(items.map(p => ({ id: p.id, name: p.name, active: p.active }))));
  } catch(e) {}
}

function renderPropertyBadge(items) {
  let box = document.getElementById('propertyFloat');
  if (!box) {
    box = document.createElement('div');
    box.id = 'propertyFloat';
    box.style.cssText = 'position:fixed;left:12px;bottom:12px;z-index:9500;align-items:center;gap:8px;padding:6px 10px;background:var(--black-card);border:1px solid var(--gold);font-size:11px;letter-spacing:.05em;color:var(--gold)';
    const label = document.createElement('span');
    label.textContent = 'Объект:';
    const sel = document.createElement('select');
    sel.id = 'propertyFloatSelect';
    sel.className = 'info-input';
    sel.style.cssText = 'min-width:140px;padding:4px 8px;font-size:12px';
    sel.onchange = () => switchProperty(sel.value);
    box.append(label, sel);
    document.body.appendChild(box);
  }
  const old = document.getElementById('propertyBadge');
  if (old) old.remove();
  const sel = document.getElementById('propertyFloatSelect');
  const show = items.length > 1;
  box.style.setProperty('display', show ? 'flex' : 'none', 'important');
  sel.innerHTML = '';
  items.forEach(p => {
    const o = document.createElement('option');
    o.value = p.id;
    o.textContent = p.name + (p.active === false ? ' (отключён)' : '');
    sel.appendChild(o);
  });
  sel.value = ADMIN_PROPERTY_ID;
  // название выбранного объекта во вкладке браузера
  const cur = items.find(p => String(p.id) === ADMIN_PROPERTY_ID);
  if (!window.__adminBaseTitle) window.__adminBaseTitle = document.title;
  document.title = (show && cur) ? cur.name + ' · ' + window.__adminBaseTitle : window.__adminBaseTitle;
}

function switchProperty(id) {
  try { localStorage.setItem('adminPropertyId', String(id)); } catch(e) {}
  location.reload();   // самый надёжный способ: все экраны заново загружают данные выбранного объекта
}

// Раздел «Объекты»
async function loadProperties() {
  try {
    propState = await apiGet('/api/admin/properties', { 'X-Property-Id': '1' });
    renderProperties();
    renderPropertySwitch();
  } catch(e) {}
}

function propPageUrl(p) {
  return p.is_default ? '/' : '/o/' + encodeURIComponent(p.slug);
}

function renderProperties() {
  const box = document.getElementById('propList');
  if (!box) return;
  box.innerHTML = propState.properties.map(p => `
    <div style="padding:16px;border:1px solid var(--black-border);background:var(--black-card);margin-bottom:14px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px">
        <div style="font-size:12px;color:var(--text-muted)">Объект № ${p.id}${p.is_default ? ' · основной' : ''} · броней и блокировок: ${p.bookings}</div>
        <a href="${propPageUrl(p)}" target="_blank" style="font-size:11px;color:var(--gold)">Открыть страницу сайта ↗</a>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">
        <div class="info-field" style="flex:2;min-width:200px"><div class="info-label">Название</div>
          <input type="text" class="info-input" id="propName_${p.id}" maxlength="80" value="${propEsc(p.name)}"></div>
        <div class="info-field" style="flex:2;min-width:200px"><div class="info-label">Адрес (для договора)</div>
          <input type="text" class="info-input" id="propAddress_${p.id}" maxlength="200" value="${propEsc(p.address)}" placeholder="${p.is_default ? 'Берётся из «Данных арендодателя»' : ''}"></div>
        <div class="info-field" style="flex:2;min-width:200px"><div class="info-label">Адрес страницы</div>
          <input type="text" class="info-input" id="propSlug_${p.id}" maxlength="40" value="${propEsc(p.slug)}" ${p.is_default ? 'disabled placeholder="главная страница"' : ''}></div>
      </div>
      ${p.is_default ? '' : `<label style="display:flex;gap:8px;align-items:center;font-size:12px;color:var(--text-secondary);margin-bottom:12px;cursor:pointer">
        <input type="checkbox" id="propActive_${p.id}" ${p.active ? 'checked' : ''}> Объект включён (виден гостям на сайте)</label>`}
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn btn-primary btn-sm" onclick="saveProperty(${p.id})">Сохранить</button>
        ${p.is_default ? '' : `<button class="btn btn-danger btn-sm" onclick="deleteProperty(${p.id})">Удалить</button>`}
      </div>
    </div>`).join('');
}

async function addProperty() {
  const name = document.getElementById('propNewName').value.trim();
  if (!name) { showToast('Введите название объекта', 'err'); return; }
  try {
    const d = await apiPost('/api/admin/properties', {
      name,
      address: document.getElementById('propNewAddress').value.trim(),
      slug: document.getElementById('propNewSlug').value.trim(),
      copy_settings: !!(document.getElementById('propNewCopy') || {}).checked
    }, { 'X-Property-Id': '1' });
    propState = d;
    ['propNewName', 'propNewAddress', 'propNewSlug'].forEach(id => { document.getElementById(id).value = ''; });
    const copyBox = document.getElementById('propNewCopy');
    if (copyBox) copyBox.checked = false;
    renderProperties();
    renderPropertySwitch();
    showToast(d.copied
      ? 'Объект создан, настройки скопированы. Выберите его в левом меню: проверьте описание, места и «Расположение», добавьте фото.'
      : 'Объект создан. Выберите его в левом меню, чтобы заполнить цены, фото и описание.', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

async function saveProperty(id) {
  const body = {
    name: document.getElementById('propName_' + id).value.trim(),
    address: document.getElementById('propAddress_' + id).value.trim()
  };
  const slugEl = document.getElementById('propSlug_' + id);
  if (slugEl && !slugEl.disabled) body.slug = slugEl.value.trim();
  const activeEl = document.getElementById('propActive_' + id);
  if (activeEl) body.active = activeEl.checked;
  try {
    propState = await apiRequest('PUT', '/api/admin/properties/' + id, body);
    renderProperties();
    renderPropertySwitch();
    showToast('Сохранено', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

async function deleteProperty(id) {
  const p = propState.properties.find(x => x.id === id);
  if (!confirm(`Удалить объект «${p ? p.name : id}» вместе с его настройками (цены, описание, акции, места, правила)? Объект с бронями удалить нельзя, его можно только отключить.`)) return;
  try {
    propState = await apiRequest('DELETE', '/api/admin/properties/' + id);
    renderProperties();
    renderPropertySwitch();
    showToast('Объект удалён', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

// Сразу при открытии админки показываем переключатель по запомненному списку (потом он обновится с сервера)
try { renderPropertyBadge(propCacheRead()); } catch(e) {}
