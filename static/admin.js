// ============================================================
// CONFIG — same API base as index.html
// ============================================================
let API_BASE = localStorage.getItem('gorodskaya-pauza_api_base') || 'https://citypause.ru';
let ADMIN_TOKEN = localStorage.getItem('gorodskaya-pauza_token') || null;

// ============================================================
// AUTH
// ============================================================
function togglePasswordVisibility(inputId, btn) {
  const input = document.getElementById(inputId);
  if (input.type === 'password') {
    input.type = 'text';
    btn.textContent = '🙈';
    btn.title = 'Скрыть пароль';
  } else {
    input.type = 'password';
    btn.textContent = '👁';
    btn.title = 'Показать пароль';
  }
}

async function doLogin() {
  const pwd = document.getElementById('loginPwd').value;
  const btn = document.querySelector('#loginScreen button');
  if (btn) { btn.disabled = true; btn.textContent = '...'; }
  try {
    const r = await fetch(`${API_BASE}/api/admin/login`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({password: pwd}),
      signal: AbortSignal.timeout(6000)
    });
    if (!r.ok) throw new Error('bad credentials');
    const data = await r.json();
    ADMIN_TOKEN = data.token;
    localStorage.setItem('gorodskaya-pauza_token', ADMIN_TOKEN);
    document.getElementById('loginScreen').style.display = 'none';
    initAdmin();
  } catch(e) {
    document.getElementById('loginErr').style.display = 'block';
    setTimeout(() => document.getElementById('loginErr').style.display = 'none', 2500);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Войти'; }
  }
}

function logout() {
  ADMIN_TOKEN = null;
  localStorage.removeItem('gorodskaya-pauza_token');
  location.reload();
}

// Если уже есть сохранённый токен — пробуем зайти сразу.
// Если он окажется просрочен/невалиден, первый же запрос к API вернёт 401
// и forceRelogin() сам вернёт на экран входа.
if (ADMIN_TOKEN) {
  document.getElementById('loginScreen').style.display = 'none';
  // init after DOM ready
  document.addEventListener('DOMContentLoaded', initAdmin);
}

// ============================================================
// DATA STATE
// ============================================================
let allBookings = [];
let config = { weekday: 3500, weekend: 4500, cleaning: 1500, included_guests: 1, extra_guest_price: 100, deposit: 6000, stay_discounts: [{min_nights:5,percent:5},{min_nights:10,percent:10},{min_nights:14,percent:20},{min_nights:0,percent:0}], holiday_periods: [{start:'',end:'',price:'',label:''},{start:'',end:'',price:'',label:''}], door_code: '0000' };
let adminCalYear, adminCalMonth;
let adminSelStart = null, adminSelEnd = null;
let selectedBookingId = null;

// Demo bookings (used when API unavailable)
const DEMO_BOOKINGS = [
  { id:'AUR-A1B2C3', guest_name:'Анна Петрова', guest_phone:'+7 901 234-56-78', guest_email:'anna@mail.ru', check_in:'2026-06-10', check_out:'2026-06-13', nights:3, total_price:12000, payment_method:'card', status:'confirmed', guests_count:2, notes:'' },
  { id:'AUR-D4E5F6', guest_name:'Михаил Иванов', guest_phone:'+7 902 345-67-89', guest_email:'misha@gmail.com', check_in:'2026-06-18', check_out:'2026-06-20', nights:2, total_price:9000, payment_method:'sbp', status:'confirmed', guests_count:2, notes:'Поздний заезд' },
  { id:'AUR-G7H8I9', guest_name:'Елена Смирнова', guest_phone:'+7 903 456-78-90', guest_email:'elena@yandex.ru', check_in:'2026-06-25', check_out:'2026-06-28', nights:3, total_price:15000, payment_method:'card', status:'pending', guests_count:3, notes:'Есть кошка' },
  { id:'AUR-J0K1L2', guest_name:'Дмитрий Козлов', guest_phone:'+7 904 567-89-01', guest_email:'dmitry@mail.ru', check_in:'2026-07-04', check_out:'2026-07-07', nights:3, total_price:13500, payment_method:'cash', status:'confirmed', guests_count:1, notes:'' },
  { id:'AUR-M3N4O5', guest_name:'Ольга Новикова', guest_phone:'+7 905 678-90-12', guest_email:'olga@gmail.com', check_in:'2026-05-20', check_out:'2026-05-23', nights:3, total_price:10500, payment_method:'card', status:'confirmed', guests_count:2, notes:'' },
];

// Заблокированные администратором даты — теперь считаются из реального
// списка броней (allBookings, status === 'blocked'), а не из localStorage
// браузера. См. blockedRealSet().
function blockedRealSet() {
  const s = new Set();
  (allBookings || []).filter(b => b.status === 'blocked').forEach(b => {
    const start = new Date(b.check_in), end = new Date(b.check_out);
    for (let d = new Date(start); d < end; d.setDate(d.getDate() + 1)) s.add(fmtDate(d));
  });
  return s;
}

// ============================================================
// INIT
// ============================================================
async function initAdmin() {
  // Update topbar date
  document.getElementById('topbarDate').textContent = new Date().toLocaleDateString('ru-RU', {weekday:'long', day:'numeric', month:'long', year:'numeric'});

  // Load api base setting
  const saved = localStorage.getItem('gorodskaya-pauza_api_base');
  if (saved) {
    document.getElementById('apiBaseInput').value = saved;
    document.getElementById('apiBaseDisplay').textContent = saved;
  }

  // Check API
  checkApi();

  // Load data
  await loadAll();

  // Init admin calendar
  const now = new Date();
  adminCalYear = now.getFullYear();
  adminCalMonth = now.getMonth();
  renderAdminCal();

  // Calendar nav
  document.getElementById('adminPrevM').onclick = () => { adminCalMonth--; if(adminCalMonth<0){adminCalMonth=11;adminCalYear--;} renderAdminCal(); };
  document.getElementById('adminNextM').onclick = () => { adminCalMonth++; if(adminCalMonth>11){adminCalMonth=0;adminCalYear++;} renderAdminCal(); };

  startAutoRefresh();
}

// Автообновление броней/дашборда в фоне — чтобы новые брони с сайта появлялись
// без ручного обновления страницы. Не трогает открытые модалки/формы, просто
// обновляет список и статистику. Пропускает тик, если вкладка неактивна.
let _autoRefreshTimer = null;
function startAutoRefresh() {
  if (_autoRefreshTimer) return;
  _autoRefreshTimer = setInterval(async () => {
    if (document.hidden) return;
    try {
      await loadBookings();
      updateDashboard();
      if (typeof renderAdminCal === 'function') renderAdminCal();
    } catch(e) { /* тихо игнорируем, не мешаем работе админа */ }
  }, 25000);
}

async function checkApi() {
  try {
    const r = await fetch(`${API_BASE}/api/prices`, {signal: AbortSignal.timeout(3000)});
    if (r.ok) {
      setApiStatus(true);
      return true;
    }
  } catch(e) {}
  setApiStatus(false);
  return false;
}

function setApiStatus(online) {
  const dot = document.getElementById('apiDot');
  const txt = document.getElementById('apiStatus');
  const txtS = document.getElementById('apiStatusText');
  if (online) {
    dot.className = 'status-dot';
    txt.textContent = 'API онлайн';
    if(txtS) txtS.textContent = 'Активен';
    if(txtS) txtS.style.color = '#4ade80';
  } else {
    dot.className = 'status-dot offline';
    txt.textContent = 'Демо-режим';
    if(txtS) txtS.textContent = 'Демо-режим';
    if(txtS) txtS.style.color = 'var(--gold)';
  }
}

async function loadAll() {
  await Promise.all([loadBookings(), loadPrices(), loadDoorCode(), loadPromoCodes()]);
  updateDashboard();
}

// ============================================================
// API CALLS with demo fallback
// ============================================================
function forceRelogin() {
  ADMIN_TOKEN = null;
  localStorage.removeItem('gorodskaya-pauza_token');
  showToast('Сессия истекла — войдите снова', 'err');
  document.getElementById('loginScreen').style.display = 'flex';
}

async function apiGet(path) {
  const r = await fetch(`${API_BASE}${path}`, {
    headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {},
    signal: AbortSignal.timeout(4000)
  });
  if (r.status === 401) { forceRelogin(); throw new Error('401'); }
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

async function apiPost(path, data) {
  const r = await fetch(`${API_BASE}${path}`, {
    method:'POST',
    headers:{
      'Content-Type':'application/json',
      ...(ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {})
    },
    body:JSON.stringify(data),
    signal: AbortSignal.timeout(4000)
  });
  if (r.status === 401) { forceRelogin(); throw new Error('401'); }
  if (!r.ok) {
    let message = String(r.status);
    try {
      const errBody = await r.json();
      if (errBody && errBody.detail) message = errBody.detail;
    } catch(e) {}
    throw new Error(message);
  }
  return r.json();
}

async function apiDelete(path) {
  const r = await fetch(`${API_BASE}${path}`, {
    method:'DELETE',
    headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {},
    signal: AbortSignal.timeout(4000)
  });
  if (r.status === 401) { forceRelogin(); throw new Error('401'); }
  if (!r.ok) {
    let message = String(r.status);
    try {
      const errBody = await r.json();
      if (errBody && errBody.detail) message = errBody.detail;
    } catch(e) {}
    throw new Error(message);
  }
  return r.json();
}

async function apiPut(path, data) {
  const r = await fetch(`${API_BASE}${path}`, {
    method:'PUT',
    headers:{
      'Content-Type':'application/json',
      ...(ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {})
    },
    body:JSON.stringify(data),
    signal: AbortSignal.timeout(4000)
  });
  if (r.status === 401) { forceRelogin(); throw new Error('401'); }
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

// BOOKINGS
async function loadBookings() {
  try {
    const data = await apiGet('/api/bookings?admin=1');
    allBookings = Array.isArray(data) ? data : (data.bookings || data);
  } catch(e) {
    allBookings = [...DEMO_BOOKINGS];
  }
  renderBookingsTable(allBookings);
  renderAlerts();
}

// АЛЕРТЫ ДАШБОРДА — то, что требует ручного внимания
function renderAlerts() {
  const card = document.getElementById('alertsCard');
  const list = document.getElementById('alertsList');
  const countEl = document.getElementById('alertsCount');
  if (!card || !list) return;

  const now = new Date();
  const todayStr = now.toISOString().slice(0, 10);
  const msHour = 60 * 60 * 1000;
  const msDay = 24 * msHour;

  const alerts = [];

  (allBookings || []).forEach(b => {
    if (b.status === 'cancelled') return;

    // 1. Оплата не подтверждена больше 2 часов
    if (['waiting_payment', 'payment_pending'].includes(b.status) && b.created_at) {
      const created = new Date(b.created_at);
      if (!isNaN(created) && (now - created) > 2 * msHour) {
        const hoursAgo = Math.floor((now - created) / msHour);
        alerts.push({
          type: 'payment', booking: b, severity: 'high',
          text: `Оплата не подтверждена уже ${hoursAgo} ч — бронь ${b.username || b.id}`,
        });
      }
    }

    // 2. Нет фото паспорта — по любой предстоящей/идущей брони (не только заезд завтра).
    // Защита от ложных срабатываний: не показываем, пока оплата ещё не подтверждена
    // (b.status waiting_payment/payment_pending), и не показываем для уже завершившихся
    // (check_out в прошлом) или отменённых/заблокированных дат.
    const isBlockedEntry = b.source === 'admin_block' || b.status === 'blocked';
    if (!isBlockedEntry && !['waiting_payment', 'payment_pending'].includes(b.status)
        && !b.has_passport_photo && b.check_out && b.check_out >= todayStr) {
      alerts.push({
        type: 'passport', booking: b, severity: 'high',
        text: `Нет фото паспорта — бронь ${b.username || b.id} (${b.guest_name || 'без имени'}), заезд ${fmtDateRu(b.check_in)}`,
      });
    }

    // 3. Депозит не возвращён — подсвечиваем сразу после выезда
    if (['confirmed', 'fully_paid'].includes(b.status) && b.check_out && !b.deposit_returned && (b.deposit || 0) > 0) {
      if (b.check_out < todayStr) {
        const daysAgo = Math.floor((now - new Date(b.check_out)) / msDay);
        alerts.push({
          type: 'deposit', booking: b, severity: 'medium',
          text: `Депозит не возвращён — выезд был ${daysAgo === 0 ? 'сегодня' : daysAgo + ' дн. назад'} — бронь ${b.username || b.id}`,
        });
      }
    }
  });

  if (alerts.length === 0) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'block';
  countEl.textContent = `${alerts.length}`;
  alerts.sort((a, b) => (a.severity === 'high' ? 0 : 1) - (b.severity === 'high' ? 0 : 1));

  list.innerHTML = alerts.map(a => `
    <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 14px;
                background:${a.severity === 'high' ? 'rgba(192,57,43,.08)' : 'rgba(201,168,76,.06)'};
                border-left:2px solid ${a.severity === 'high' ? '#c0392b' : 'var(--gold)'};cursor:pointer"
         onclick="openBookingModal(${encodeBooking(a.booking)})">
      <span style="font-size:12px;color:var(--text-secondary)">${a.text}</span>
      ${a.type === 'deposit'
        ? `<button class="btn btn-ghost btn-sm" onclick="event.stopPropagation();markDepositReturned('${a.booking.username || a.booking.id}')">Депозит возвращён</button>`
        : `<span style="font-size:11px;color:var(--text-muted);white-space:nowrap">›</span>`}
    </div>
  `).join('');
}

async function markDepositReturned(ref) {
  try {
    await apiPost(`/api/admin/bookings/${ref}/deposit-returned`, {});
    showToast('Депозит отмечен как возвращённый', 'gold');
    await loadBookings();
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

// PRICES
async function loadPrices() {
  try {
    const data = await apiGet('/api/prices');
    config.weekday  = data.weekday  || data.weekday_price  || config.weekday;
    config.weekend  = data.weekend  || data.weekend_price  || config.weekend;
    config.cleaning = data.cleaning || data.cleaning_price || config.cleaning;
    config.included_guests   = data.included_guests   ?? config.included_guests   ?? 1;
    config.extra_guest_price = data.extra_guest_price ?? config.extra_guest_price ?? 100;
    config.deposit = data.deposit ?? config.deposit ?? 6000;
    config.stay_discounts = Array.isArray(data.stay_discounts) ? data.stay_discounts : config.stay_discounts;
    config.holiday_periods = Array.isArray(data.holiday_periods) && data.holiday_periods.length
      ? data.holiday_periods
      : [{start:'',end:'',price:'',label:''},{start:'',end:'',price:'',label:''}];
  } catch(e) {}
  document.getElementById('pWeekday').value  = config.weekday;
  document.getElementById('pWeekend').value  = config.weekend;
  document.getElementById('pCleaning').value = config.cleaning;
  document.getElementById('pIncludedGuests').value   = config.included_guests;
  document.getElementById('pExtraGuestPrice').value  = config.extra_guest_price;
  document.getElementById('pDeposit').value = config.deposit;
  const mbDeposit = document.getElementById('mbDeposit');
  if (mbDeposit && !mbDeposit.value) mbDeposit.placeholder = config.deposit;

  const sd = config.stay_discounts || [];
  for (let i = 0; i < 4; i++) {
    document.getElementById(`sd${i}Nights`).value  = sd[i]?.min_nights ?? 0;
    document.getElementById(`sd${i}Percent`).value = sd[i]?.percent ?? 0;
  }

  renderHolidayPeriodsEditor();
}

// ПРАЗДНИЧНЫЕ ДНИ — динамический список периодов с фиксированной ценой
function renderHolidayPeriodsEditor() {
  const el = document.getElementById('holidayPeriodsEditor');
  if (!el) return;
  el.innerHTML = config.holiday_periods.map((h, i) => `
    <div class="holiday-row">
      <div class="price-input-box">
        <div class="pib-label">Начало</div>
        <input type="date" class="pib-input holiday-start" data-idx="${i}" value="${h.start || ''}">
      </div>
      <div class="price-input-box">
        <div class="pib-label">Конец</div>
        <input type="date" class="pib-input holiday-end" data-idx="${i}" value="${h.end || ''}">
      </div>
      <div class="price-input-box">
        <div class="pib-label" style="white-space:nowrap">Цена, ₽</div>
        <input type="number" class="pib-input holiday-price" data-idx="${i}" value="${h.price || ''}" placeholder="7600" min="0">
      </div>
      <button class="btn btn-ghost btn-sm" onclick="removeHolidayPeriod(${i})" title="Удалить период" style="margin-bottom:2px;padding:6px 12px">✕</button>
    </div>
    <input type="text" class="info-input holiday-label" data-idx="${i}" value="${h.label || ''}"
           placeholder="Название периода (например: Новогодние каникулы) — необязательно"
           style="margin-bottom:14px">
  `).join('');
}

function addHolidayPeriod() {
  config.holiday_periods.push({start:'',end:'',price:'',label:''});
  renderHolidayPeriodsEditor();
}

async function removeHolidayPeriod(idx) {
  collectHolidayPeriodsFromForm();
  config.holiday_periods.splice(idx, 1);
  if (config.holiday_periods.length === 0) config.holiday_periods.push({start:'',end:'',price:'',label:''});
  renderHolidayPeriodsEditor();

  // Сразу сохраняем на сервере — иначе визуально период исчез, а цены
  // на сайте остаются старыми, пока не нажать "Сохранить" вручную
  const payload = buildFullPricesPayload();
  try {
    await apiPost('/api/prices', payload);
    Object.assign(config, payload);
    showToast('Период удалён и сохранён', 'gold');
  } catch(e) {
    showToast('Период удалён локально, но не сохранился на сервере: ' + e.message, 'err');
  }
}

function collectHolidayPeriodsFromForm() {
  const starts = document.querySelectorAll('.holiday-start');
  const ends   = document.querySelectorAll('.holiday-end');
  const prices = document.querySelectorAll('.holiday-price');
  const labels = document.querySelectorAll('.holiday-label');
  const collected = [];
  starts.forEach((s, i) => {
    collected.push({
      start: s.value || '',
      end:   ends[i]?.value || '',
      price: prices[i]?.value || '',
      label: labels[i]?.value.trim() || '',
    });
  });
  config.holiday_periods = collected;
  return collected;
}

// Собирает ПОЛНЫЙ набор цен (включая пороги скидок и праздничные периоды) —
// нужно отправлять целиком при любом сохранении, т.к. /api/prices каждый раз
// перезаписывает файл целиком, а не сливает частично
function buildFullPricesPayload() {
  const stay_discounts = [];
  for (let i = 0; i < 4; i++) {
    stay_discounts.push({
      min_nights: parseInt(document.getElementById(`sd${i}Nights`).value) || 0,
      percent:    parseInt(document.getElementById(`sd${i}Percent`).value) || 0,
    });
  }
  return {
    weekday:   parseInt(document.getElementById('pWeekday').value),
    weekend:   parseInt(document.getElementById('pWeekend').value),
    cleaning:  parseInt(document.getElementById('pCleaning').value),
    included_guests:   parseInt(document.getElementById('pIncludedGuests').value),
    extra_guest_price: parseInt(document.getElementById('pExtraGuestPrice').value),
    deposit: parseInt(document.getElementById('pDeposit').value),
    stay_discounts,
    holiday_periods: collectHolidayPeriodsFromForm(),
  };
}

async function saveHolidayPeriods() {
  const payload = buildFullPricesPayload();
  try {
    await apiPost('/api/prices', payload);
    Object.assign(config, payload);
    showToast('Праздничные дни сохранены', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения', 'err');
  }
}

async function savePrices() {
  const payload = buildFullPricesPayload();
  try {
    await apiPost('/api/prices', payload);
    Object.assign(config, payload);
    showToast('Цены сохранены', 'gold');
  } catch(e) {
    Object.assign(config, payload);
    showToast('Сохранено локально (API недоступен)', 'gold');
  }
}

// PROMO CODES
async function loadPromoCodes() {
  let codes = {};
  try {
    codes = await apiGet('/api/promo-codes');
  } catch(e) {}
  renderPromoTable(codes);
}

function renderPromoTable(codes) {
  const tbody = document.getElementById('promoTableBody');
  tbody.innerHTML = '';
  const entries = Object.entries(codes || {});
  if (entries.length === 0) {
    addPromoRow();
  } else {
    entries.forEach(([code, percent]) => addPromoRow(code, percent));
  }
}

function addPromoRow(code = '', percent = '') {
  const tbody = document.getElementById('promoTableBody');
  const tr = document.createElement('tr');
  tr.innerHTML =
    '<td data-label="Код"><input type="text" class="pib-input promo-code-input" ' +
    'style="font-size:14px;padding:8px 10px;text-transform:uppercase" ' +
    'value="' + code + '" placeholder="SUMMER10"></td>' +
    '<td data-label="Скидка, %"><input type="number" class="pib-input promo-percent-input" ' +
    'style="font-size:14px;padding:8px 10px;width:90px" ' +
    'value="' + percent + '" placeholder="10"></td>' +
    '<td data-label=""><button class="btn btn-danger btn-sm" onclick="this.closest(\'tr\').remove()">✕</button></td>';
  tbody.appendChild(tr);
}

async function savePromoCodes() {
  const rows = document.querySelectorAll('#promoTableBody tr');
  const codes = {};
  rows.forEach(tr => {
    const codeInput    = tr.querySelector('.promo-code-input');
    const percentInput = tr.querySelector('.promo-percent-input');
    const code    = codeInput.value.trim().toUpperCase();
    const percent = parseInt(percentInput.value);
    if (code && !isNaN(percent)) codes[code] = percent;
  });
  try {
    await apiPost('/api/promo-codes', {codes});
    showToast('Промокоды сохранены', 'gold');
    renderPromoTable(codes);
  } catch(e) {
    showToast('Не удалось сохранить промокоды — проверьте соединение с API', 'err');
  }
}

// DOOR CODE
async function loadDoorCode() {
  try {
    const data = await apiGet('/api/door-code');
    config.door_code = data.code || data.door_code || config.door_code;
  } catch(e) {}
  document.getElementById('doorCodeAdmin').textContent = config.door_code;
  document.getElementById('dashDoorCode').textContent = config.door_code;
}

async function saveCode() {
  const code = document.getElementById('newCode').value.trim();
  if (!code) return showToast('Введите код', 'err');
  try {
    await apiPost('/api/door-code', { code });
  } catch(e) {}
  config.door_code = code;
  document.getElementById('doorCodeAdmin').textContent = code;
  document.getElementById('dashDoorCode').textContent = code;
  document.getElementById('newCode').value = '';
  showToast('Код замка обновлён', 'gold');
}

let codeRevealed = false;
function toggleCode() {
  codeRevealed = !codeRevealed;
  document.getElementById('doorCodeAdmin').classList.toggle('revealed', codeRevealed);
}

// TIMEZONE
async function loadTimezone() {
  try {
    const s = await apiGet('/api/site-settings');
    document.getElementById('timezoneOffset').value = String(s.timezone_offset ?? 7);
    document.getElementById('notifyChecklistTime').value = s.notify_checklist_time || '10:00';
    document.getElementById('notifyReviewTime').value = s.notify_review_time || '14:00';
    document.getElementById('notifyOwnerTime').value = s.notify_owner_time || '09:00';
  } catch(e) {}
}

async function saveTimezone() {
  const offset = parseInt(document.getElementById('timezoneOffset').value, 10);
  const checklistTime = document.getElementById('notifyChecklistTime').value || '10:00';
  const reviewTime = document.getElementById('notifyReviewTime').value || '14:00';
  const ownerTime = document.getElementById('notifyOwnerTime').value || '09:00';
  try {
    const current = await apiGet('/api/site-settings');
    await apiPost('/api/site-settings', {
      ...current,
      timezone_offset: offset,
      notify_checklist_time: checklistTime,
      notify_review_time: reviewTime,
      notify_owner_time: ownerTime,
    });
    showToast('Часовой пояс и расписание сохранены', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения', 'err');
  }
}

// DESCRIPTION
async function loadDesc() {
  try {
    const r = await fetch(`${API_BASE}/api/description`);
    const t = await r.text();
    document.getElementById('aptDesc').value = t;
  } catch(e) {}
}

async function saveDesc() {
  const desc = document.getElementById('aptDesc').value;
  try {
    await apiPost('/api/description', { text: desc });
    showToast('Описание сохранено', 'gold');
  } catch(e) {
    showToast('Сохранено (API недоступен)', 'gold');
  }
}

// BLOCKED DATES — реальные записи в БД (см. /api/blocked-dates, /api/unblock-dates)
async function blockDates() {
  if (!adminSelStart) return showToast('Выберите даты', 'err');
  const end = adminSelEnd || adminSelStart;
  const dates = [];
  const s = new Date(adminSelStart), e = new Date(end);
  for (let d = new Date(s); d <= e; d.setDate(d.getDate()+1)) dates.push(fmtDate(d));

  try {
    await apiPost('/api/blocked-dates', { dates, reason: document.getElementById('blockReason').value });
  } catch(e) {
    showToast(e.message || 'Не удалось заблокировать даты', 'err');
    return;
  }
  adminSelStart = null; adminSelEnd = null;
  await loadBookings();
  renderAdminCal();
  showToast(`Заблокировано ${dates.length} дней`, 'gold');
}

async function unblockDates() {
  if (!adminSelStart) return showToast('Выберите даты', 'err');
  const end = adminSelEnd || adminSelStart;

  try {
    await apiPost('/api/unblock-dates', { start: adminSelStart, end: end });
  } catch(e) {
    showToast(e.message || 'Не удалось разблокировать даты', 'err');
    return;
  }
  adminSelStart = null; adminSelEnd = null;
  await loadBookings();
  renderAdminCal();
  showToast('Даты разблокированы', 'gold');
}

// ============================================================
// DASHBOARD STATS
// ============================================================
function updateDashboard() {
  const now = new Date();
  const thisMonth = now.getMonth();
  const thisYear = now.getFullYear();

  const monthBookings = allBookings.filter(b => {
    const d = new Date(b.check_in);
    return d.getMonth() === thisMonth && d.getFullYear() === thisYear;
  });

  const revenue = monthBookings.reduce((sum,b) => sum + (b.total_price||0), 0);

  // Count booked nights this month
  const daysInMonth = new Date(thisYear, thisMonth+1, 0).getDate();
  let bookedDays = 0;
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = `${thisYear}-${String(thisMonth+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    if (allBookings.some(b => b.check_in <= ds && b.check_out > ds && b.status !== 'cancelled')) bookedDays++;
  }

  document.getElementById('sTotal').textContent = allBookings.length;
  document.getElementById('sMonth').textContent = monthBookings.length;
  document.getElementById('sRevenue').textContent = (revenue/1000).toFixed(0) + 'K';
  document.getElementById('sOccupancy').textContent = Math.round(bookedDays/daysInMonth*100) + '%';

  if(typeof renderDashStrip === 'function') renderDashStrip();
  if(typeof renderCheckoutSchedule === 'function') renderCheckoutSchedule();

  // Upcoming bookings
  const upcoming = allBookings
    .filter(b => new Date(b.check_in) >= now && b.status !== 'cancelled')
    .sort((a,b) => new Date(a.check_in)-new Date(b.check_in))
    .slice(0, 5);

  const tbody = document.getElementById('upcomingBody');
  if (upcoming.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:32px;color:var(--text-muted)">Нет предстоящих броней</td></tr>';
  } else {
    tbody.innerHTML = upcoming.map(b => `
      <tr onclick="openBookingModal(${JSON.stringify(b).split('"').join("'").replace(/'/g,"&#39;")})" style="cursor:pointer">
        <td data-label="Гость"><strong style="color:var(--text-primary)">${b.guest_name}</strong></td>
        <td data-label="Заезд">${fmtDateRu(b.check_in)}</td>
        <td data-label="Ночей">${b.nights}</td>
        <td data-label="Сумма" style="color:var(--gold)">₽${(b.total_price||0).toLocaleString('ru')}</td>
        <td data-label="Статус">${statusBadge(b.status)}</td>
      </tr>
    `).join('');
  }

  // Today status
  const todayDs = fmtDate(now);
  const todayBook = allBookings.find(b => b.check_in <= todayDs && b.check_out > todayDs && b.status !== 'cancelled');
  const tsEl = document.getElementById('todayStatus');
  if (todayBook) {
    tsEl.innerHTML = `<span style="color:#4ade80">● Занято</span><br>Гость: ${todayBook.guest_name}<br>Выезд: ${fmtDateRu(todayBook.check_out)}`;
  } else {
    tsEl.innerHTML = `<span style="color:var(--gold)">○ Свободно</span><br>Нет активных заездов`;
  }

  // Badge
  const pending = allBookings.filter(b=>b.status==='pending').length;
  const badge = document.getElementById('newBookBadge');
  badge.textContent = pending;
  badge.style.display = pending > 0 ? 'inline-block' : 'none';
}

// ============================================================
// BOOKINGS TABLE
// ============================================================
let currentFilter = 'all';

function filterBookings(f) {
  currentFilter = f;
  document.querySelectorAll('.btn-sm').forEach(btn => btn.className = 'btn btn-ghost btn-sm');
  const btnMap = {
    'all': 'fAll', 'confirmed': 'fConf',
    'waiting_payment': 'fPend', 'payment_pending': 'fPay', 'cancelled': 'fCanc'
  };
  const activeBtn = document.getElementById(btnMap[f] || 'fAll');
  if(activeBtn) activeBtn.className = 'btn btn-primary btn-sm';
  const filtered = f === 'all' ? allBookings : allBookings.filter(b => b.status === f);
  renderBookingsTable(filtered);
}

function renderBookingsTable(list) {
  const tbody = document.getElementById('bookingsBody');
  if (!list || list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:48px;color:var(--text-muted)">Нет бронирований</td></tr>';
    return;
  }
  const sorted = [...list].sort((a,b) => new Date(b.check_in)-new Date(a.check_in));
  tbody.innerHTML = sorted.map((b,i) => `
    <tr onclick="openBookingModal(${encodeBooking(b)})" style="cursor:pointer">
      <td data-label="#" style="color:var(--gold-muted);font-size:10px">${b.id||i+1}</td>
      <td data-label="Гость"><strong style="color:var(--text-primary)">${b.guest_name}</strong></td>
      <td data-label="Телефон">${b.guest_phone||'—'}</td>
      <td data-label="Даты" class="mob-only-cell">${fmtDateRu(b.check_in)} → ${fmtDateRu(b.check_out)}</td>
      <td data-label="Заезд" class="desk-only-cell">${fmtDateRu(b.check_in)}</td>
      <td data-label="Выезд" class="desk-only-cell">${fmtDateRu(b.check_out)}</td>
      <td data-label="Ночей">${b.nights}</td>
      <td data-label="Сумма" style="color:var(--gold)">₽${(b.total_price||0).toLocaleString('ru')}</td>
      <td data-label="Оплата">${payBadge(b.payment_method)}</td>
      <td data-label="Статус">${statusBadge(b.status)}</td>
      <td data-label="" style="white-space:nowrap">
        <button class="btn btn-ghost btn-icon" onclick="event.stopPropagation();openBookingModal(${encodeBooking(b)})">›</button>
        <button class="btn btn-ghost btn-icon" title="Удалить" onclick="event.stopPropagation();deleteBookingRow('${b.username || b.id}','${(b.guest_name||'').replace(/'/g,"\\'")}')">🗑</button>
      </td>
    </tr>
  `).join('');
}

async function deleteBookingRow(ref, guestName) {
  if (!confirm(`Удалить бронь «${guestName}» (${ref}) безвозвратно?\n\nБудут удалены сама бронь, договор, фото паспорта — восстановить будет нельзя.`)) return;
  try {
    await apiDelete(`/api/bookings/${ref}`);
    allBookings = allBookings.filter(x => (x.username || x.id) != ref);
    filterBookings(currentFilter);
    updateDashboard();
    showToast('Бронь удалена', 'gold');
  } catch(e) {
    showToast('Ошибка удаления: ' + e.message, 'err');
  }
}

function encodeBooking(b) {
  return "'"+btoa(encodeURIComponent(JSON.stringify(b)))+"'";
}

function openBookingModal(encoded) {
  let b;
  try { b = JSON.parse(decodeURIComponent(atob(encoded))); }
  catch(e) { return; }
  selectedBookingId = b.id;
  document.getElementById('modalGuestName').textContent = b.guest_name;
  const detailRows = [
    ['ID брони', b.id||'—'],
    ['Email', b.guest_email||'—'],
    ['Телефон', b.guest_phone||'—'],
    ['Заезд', fmtDateRu(b.check_in)],
    ['Выезд', fmtDateRu(b.check_out)],
    ['Ночей', b.nights],
    ['Гостей', b.guests_count||'—'],
    ['Сумма', '₽'+(b.total_price||0).toLocaleString('ru')],
  ];
  if (b.promo_code) {
    detailRows.push(['Промокод', b.promo_code + ' (−' + (b.discount_percent||0) + '%)']);
  }
  const SLOT_LABELS = {main: '📄 Главная страница', reg1: '🏠 Прописка'};
  const photoSlots = b.passport_photo_slots || [];
  detailRows.push(
    ['Оплата', b.payment_method||'—'],
    ['Статус', statusBadge(b.status)],
    ['Пожелания', b.notes||'—'],
    ['Фото паспорта', photoSlots.length
      ? photoSlots.map(slot => `<button class="btn btn-ghost btn-sm" onclick="viewPassportPhoto('${b.username||b.id}','${slot}')">${SLOT_LABELS[slot]}</button>`).join(' ')
      : '—'],
  );
  document.getElementById('modalDetails').innerHTML = detailRows
    .map(([l,v]) => `<div class="mbd-box"><div class="mbd-label">${l}</div><div class="mbd-val">${v}</div></div>`).join('');

  // Показываем кнопки в зависимости от статуса
  const s = b.status;
  const btnConfirm = document.getElementById('btnConfirm');
  const btnFullPay = document.getElementById('btnFullPay');
  btnConfirm.style.display = (s === 'waiting_payment' || s === 'payment_pending') ? '' : 'none';
  btnFullPay.style.display = (s === 'confirmed') ? '' : 'none';

  // Кнопки подписанных документов — только если договор реально подписан
  const signed = !!b.signed_at;
  document.getElementById('btnContractPdf').style.display = signed ? '' : 'none';
  document.getElementById('btnConsentPdf').style.display = signed ? '' : 'none';

  document.getElementById('bookingModal').classList.add('open');
}

async function downloadSignedPdf(docType) {
  if (!selectedBookingId) return;
  const b = allBookings.find(x => x.id == selectedBookingId || x.username == selectedBookingId);
  const ref = b ? (b.username || b.id) : selectedBookingId;
  try {
    const resp = await fetch(`${API_BASE}/api/admin/contract-pdf/${ref}/${docType}`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    if (!resp.ok) throw new Error('Документ не найден');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  } catch(e) {
    showToast('Не удалось открыть документ: ' + e.message, 'err');
  }
}

async function deleteBookingConfirm() {
  if (!selectedBookingId) return;
  const b = allBookings.find(x => x.id == selectedBookingId || x.username == selectedBookingId);
  const ref = b ? (b.username || b.id) : selectedBookingId;
  const name = b ? b.guest_name : ref;
  if (!confirm(`Удалить бронь «${name}» (${ref}) безвозвратно?\n\nБудут удалены сама бронь, договор, фото паспорта — восстановить будет нельзя.`)) return;
  try {
    await apiDelete(`/api/bookings/${ref}`);
    allBookings = allBookings.filter(x => x !== b);
    closeModal();
    filterBookings(currentFilter);
    updateDashboard();
    showToast('Бронь удалена', 'gold');
  } catch(e) {
    showToast('Ошибка удаления: ' + e.message, 'err');
  }
}

async function viewPassportPhoto(ref, slot) {
  try {
    const resp = await fetch(`${API_BASE}/api/admin/passport-photo/${ref}/${slot}`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    if(!resp.ok) throw new Error('not found');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  } catch(e) {
    showToast('Фото не найдено', 'err');
  }
}

async function copySignLinkForSelected() {
  if (!selectedBookingId) return;
  const b = allBookings.find(x => x.id == selectedBookingId || x.username == selectedBookingId);
  const ref = b ? (b.username || b.id) : selectedBookingId;
  try {
    const data = await apiGet(`/api/admin/bookings/${ref}/sign-link`);
    try {
      await navigator.clipboard.writeText(data.sign_link);
    } catch(e) {
      const tmp = document.createElement('input');
      document.body.appendChild(tmp);
      tmp.value = data.sign_link;
      tmp.select();
      document.execCommand('copy');
      document.body.removeChild(tmp);
    }
    showToast(data.already_signed ? 'Ссылка скопирована (договор уже подписан)' : 'Ссылка скопирована', 'gold');
  } catch(e) {
    showToast('Не удалось получить ссылку: ' + e.message, 'err');
  }
}

async function confirmBooking() {
  if (!selectedBookingId) return;
  const btn = document.getElementById('btnConfirm');
  if(btn) { btn.textContent = 'Подтверждаем...'; btn.disabled = true; }
  try {
    const b = allBookings.find(x => x.id == selectedBookingId || x.username == selectedBookingId);
    const ref = b ? (b.username || b.id) : selectedBookingId;
    const result = await apiPost('/api/bookings/' + ref + '/confirm', {});
    if (b) b.status = 'confirmed';
    closeModal();
    renderBookingsTable(allBookings);
    updateDashboard();
    showToast('Предоплата подтверждена — договор отправлен гостю', 'gold');
  } catch(e) {
    showToast('Ошибка подтверждения: ' + e.message, 'err');
  } finally {
    if(btn) { btn.textContent = '✓ Подтвердить'; btn.disabled = false; }
  }
}

async function fullPaymentBooking() {
  if (!selectedBookingId) return;
  const btn = document.getElementById('btnFullPay');
  if(btn) { btn.textContent = 'Отправляем...'; btn.disabled = true; }
  try {
    const b = allBookings.find(x => x.id == selectedBookingId || x.username == selectedBookingId);
    const ref = b ? (b.username || b.id) : selectedBookingId;
    await apiPost('/api/bookings/' + ref + '/full-payment', {});
    if (b) b.status = 'fully_paid';
    closeModal();
    renderBookingsTable(allBookings);
    updateDashboard();
    showToast('Полная оплата подтверждена — памятка с кодом замка отправлена гостю', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  } finally {
    if(btn) { btn.textContent = '✓ Полная оплата получена'; btn.disabled = false; }
  }
}

async function cancelBooking() {
  if (!selectedBookingId) return;
  try {
    const b = allBookings.find(x => x.id == selectedBookingId || x.username == selectedBookingId);
    const ref = b ? (b.username || b.id) : selectedBookingId;
    await apiPost('/api/bookings/' + ref + '/cancel', {});
    if (b) b.status = 'cancelled';
    closeModal();
    renderBookingsTable(allBookings);
    updateDashboard();
    showToast('Бронь отменена', 'err');
  } catch(e) {
    showToast('Ошибка отмены', 'err');
  }
}
function closeModal() { document.getElementById('bookingModal').classList.remove('open'); }

// ============================================================
// ADMIN CALENDAR
// ============================================================
const MONTHS_RU = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];

function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function fmtDateRu(ds) {
  if (!ds) return '—';
  const d = new Date(ds+'T00:00:00');
  return d.toLocaleDateString('ru-RU', {day:'numeric', month:'short', year:'2-digit'});
}

function renderAdminCal() {
  document.getElementById('adminCalLabel').textContent = `${MONTHS_RU[adminCalMonth]} ${adminCalYear}`;
  const grid = document.getElementById('adminCalGrid');
  grid.innerHTML = '';

  const firstDow = new Date(adminCalYear, adminCalMonth, 1).getDay();
  const offset = firstDow === 0 ? 6 : firstDow - 1;
  const dim = new Date(adminCalYear, adminCalMonth+1, 0).getDate();
  const today = new Date(); today.setHours(0,0,0,0);
  const todayS = fmtDate(today);

  // Collect client-booked dates (реальные брони гостей, без блокировок)
  const clientBooked = new Set();
  allBookings.filter(b=>b.status!=='cancelled' && b.status!=='blocked').forEach(b=>{
    const s=new Date(b.check_in), e=new Date(b.check_out);
    for(let d=new Date(s);d<e;d.setDate(d.getDate()+1)) clientBooked.add(fmtDate(d));
  });
  const adminBlocked = blockedRealSet();

  for(let i=0;i<offset;i++){const e=document.createElement('div');e.className='aday empty';grid.appendChild(e);}

  for(let d=1;d<=dim;d++){
    const ds=`${adminCalYear}-${String(adminCalMonth+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const el=document.createElement('div');
    el.className='aday';
    el.textContent=d;
    if(ds===todayS) el.classList.add('today');
    const isPast = new Date(adminCalYear,adminCalMonth,d) < today;
    if(isPast) el.classList.add('past');
    else if(clientBooked.has(ds)) el.classList.add('booked-client');
    else if(adminBlocked.has(ds)) el.classList.add('blocked-admin');

    if(adminSelStart && adminSelEnd && ds>=adminSelStart && ds<=adminSelEnd) el.classList.add('selected-admin');
    else if(adminSelStart && !adminSelEnd && ds===adminSelStart) el.classList.add('selected-admin');

    if(!isPast) {
      el.addEventListener('click', () => onAdminDay(ds));
    }
    grid.appendChild(el);
  }

  // Update selected display
  const el2 = document.getElementById('adminSelDates');
  if(adminSelStart && adminSelEnd) el2.textContent = `${fmtDateRu(adminSelStart)} → ${fmtDateRu(adminSelEnd)}`;
  else if(adminSelStart) el2.textContent = fmtDateRu(adminSelStart) + ' → ...';
  else el2.textContent = 'Выберите даты';
}

function onAdminDay(ds) {
  if(!adminSelStart || (adminSelStart && adminSelEnd)) { adminSelStart=ds; adminSelEnd=null; }
  else { if(ds<=adminSelStart) { adminSelStart=ds; adminSelEnd=null; } else adminSelEnd=ds; }
  renderAdminCal();
}

// ============================================================
// DASHBOARD — booking strip (1..N число текущего месяца)
// ============================================================
let dashStripDate = new Date();

function dashStripMonthShift(delta) {
  dashStripDate = new Date(dashStripDate.getFullYear(), dashStripDate.getMonth() + delta, 1);
  renderDashStrip();
}

function renderDashStrip() {
  const strip = document.getElementById('dashStrip');
  const label = document.getElementById('dashStripLabel');
  if(!strip || !label) return;

  const year = dashStripDate.getFullYear();
  const month = dashStripDate.getMonth();
  label.textContent = `${MONTHS_RU[month]} ${year}`;

  const dim = new Date(year, month + 1, 0).getDate();
  const today = new Date(); today.setHours(0,0,0,0);
  const isMobileNow = window.matchMedia('(max-width:768px)').matches;

  const clientBooked = new Set();
  (allBookings || []).filter(b => b.status !== 'cancelled' && b.status !== 'blocked').forEach(b => {
    const s = new Date(b.check_in), e = new Date(b.check_out);
    for(let d = new Date(s); d < e; d.setDate(d.getDate() + 1)) clientBooked.add(fmtDate(d));
  });
  const adminBlocked = blockedRealSet();

  function makeDayCell(d) {
    const dateObj = new Date(year, month, d);
    const ds = fmtDate(dateObj);
    const cell = document.createElement('div');
    cell.title = fmtDateRu(ds);
    const minW = isMobileNow ? '16px' : '20px';
    cell.style.cssText = `flex:1;min-width:${minW};height:40px;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:10px;border-radius:2px;`;
    cell.textContent = d;

    const isPast = dateObj < today;
    if(isPast) {
      cell.style.background = 'var(--black)';
      cell.style.color = 'var(--text-muted)';
      cell.style.opacity = '.35';
    } else if(clientBooked.has(ds)) {
      cell.style.background = 'var(--red)';
      cell.style.color = '#fff';
    } else if(adminBlocked.has(ds)) {
      cell.style.background = 'var(--text-muted)';
      cell.style.color = 'var(--black)';
    } else {
      cell.style.background = 'transparent';
      cell.style.border = '1px solid var(--black-border)';
      cell.style.color = 'var(--text-secondary)';
    }
    return cell;
  }

  strip.innerHTML = '';

  if(isMobileNow) {
    strip.style.flexDirection = 'column';
    strip.style.overflowX = 'visible';
    const half = Math.ceil(dim / 2);
    const row1 = document.createElement('div');
    row1.style.cssText = 'display:flex;gap:2px;margin-bottom:4px';
    const row2 = document.createElement('div');
    row2.style.cssText = 'display:flex;gap:2px';
    for(let d = 1; d <= dim; d++) {
      (d <= half ? row1 : row2).appendChild(makeDayCell(d));
    }
    strip.appendChild(row1);
    strip.appendChild(row2);
  } else {
    strip.style.flexDirection = 'row';
    strip.style.overflowX = 'auto';
    for(let d = 1; d <= dim; d++) {
      strip.appendChild(makeDayCell(d));
    }
  }
}

// ============================================================
// DASHBOARD — Ближайшие выезды (планирование уборки)
// ============================================================
let propertiesCache = null;

async function getPropertiesMap() {
  if(propertiesCache) return propertiesCache;
  try {
    const props = await apiGet('/api/admin/properties');
    propertiesCache = {};
    props.forEach(p => propertiesCache[p.id] = p.name);
  } catch(e) {
    propertiesCache = {1: 'Городская Пауза'};
  }
  return propertiesCache;
}

function checkoutWhenLabel(checkoutDate) {
  const today = new Date(); today.setHours(0,0,0,0);
  const d = new Date(checkoutDate); d.setHours(0,0,0,0);
  const diffDays = Math.round((d - today) / 86400000);
  if(diffDays < 0) return 'Просрочено';
  if(diffDays === 0) return 'Сегодня';
  if(diffDays === 1) return 'Завтра';
  return `Через ${diffDays} дн.`;
}

async function renderCheckoutSchedule() {
  const tbody = document.getElementById('checkoutScheduleBody');
  if(!tbody) return;
  const propsMap = await getPropertiesMap();

  const today = new Date(); today.setHours(0,0,0,0);
  const upcoming = (allBookings || [])
    .filter(b => b.status !== 'cancelled' && b.check_out)
    .filter(b => new Date(b.check_out) >= today)
    .sort((a,b) => new Date(a.check_out) - new Date(b.check_out))
    .slice(0, 10);

  if(!upcoming.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:32px;color:var(--text-muted)">Нет предстоящих выездов</td></tr>';
    return;
  }

  tbody.innerHTML = upcoming.map(b => {
    const propName = propsMap[b.property_id] || 'Квартира';
    const whenLabel = checkoutWhenLabel(b.check_out);
    const isUrgent = whenLabel === 'Сегодня' || whenLabel === 'Завтра';
    return `
      <tr>
        <td data-label="Квартира">${propName}</td>
        <td data-label="Гость"><strong style="color:var(--text-primary)">${b.guest_name || '—'}</strong></td>
        <td data-label="Дата выезда">${fmtDateRu(b.check_out)}</td>
        <td data-label="Когда"><span style="${isUrgent ? 'color:var(--gold);font-weight:600' : 'color:var(--text-muted)'}">${whenLabel}</span></td>
      </tr>
    `;
  }).join('');
}
async function loadNotif() {
  try {
    const s = await apiGet('/api/site-settings');
    document.getElementById('notifEmail').value = s.notify_email || '';
    document.getElementById('notifTg').value = s.notify_telegram_chat_id || '';
  } catch(e) {}
}

async function saveNotif() {
  const email = document.getElementById('notifEmail').value.trim();
  const tgId = document.getElementById('notifTg').value.trim();
  try {
    const current = await apiGet('/api/site-settings');
    await apiPost('/api/site-settings', {
      ...current,
      notify_email: email,
      notify_telegram_chat_id: tgId,
    });
    showToast('Настройки уведомлений сохранены', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

function saveApiBase() {
  const v = document.getElementById('apiBaseInput').value.trim();
  API_BASE = v;
  localStorage.setItem('gorodskaya-pauza_api_base', v);
  document.getElementById('apiBaseDisplay').textContent = v || 'localhost (режим разработки)';
  checkApi();
  showToast('URL сохранён', 'gold');
}

async function testApi() {
  const ok = await checkApi();
  showToast(ok ? '✓ API доступен' : '✗ API недоступен', ok ? 'gold' : 'err');
}

async function backupNow() {
  const btn = document.getElementById('backupNowBtn');
  const status = document.getElementById('backupStatus');
  btn.disabled = true;
  status.textContent = 'Создаю копию...';
  status.style.color = 'var(--text-muted)';
  try {
    const res = await apiPost('/api/admin/backup-now', {});
    status.textContent = `Копия создана (${res.filename}) — отправка в Telegram и на почту запущена, проверьте через минуту`;
    status.style.color = '#4ade80';
  } catch(e) {
    status.textContent = 'Ошибка: ' + e.message;
    status.style.color = '#f87171';
  }
  btn.disabled = false;
}

async function changePwd() {
  const oldPwd = document.getElementById('oldPwd').value;
  const newPwd = document.getElementById('newPwd').value;
  if (newPwd.length < 4) return showToast('Минимум 4 символа', 'err');
  if (!oldPwd) return showToast('Введите текущий пароль', 'err');
  try {
    await apiPost('/api/admin/change-password', {old_password: oldPwd, new_password: newPwd});
    document.getElementById('oldPwd').value = '';
    document.getElementById('newPwd').value = '';
    showToast('Пароль изменён', 'gold');
  } catch(e) {
    showToast('Не удалось сменить пароль — проверьте текущий пароль', 'err');
  }
}

// ============================================================
// UI HELPERS
// ============================================================
function toggleAdminSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('adminBackdrop').classList.toggle('open');
}
function closeAdminSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('adminBackdrop').classList.remove('open');
}

function showPanel(id, el) {
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  const panel = document.getElementById('panel-'+id);
  if(panel) panel.classList.add('active');
  document.querySelectorAll('.sb-item').forEach(i=>i.classList.remove('active'));
  if(el) el.classList.add('active');
  closeAdminSidebar();
  const titles = {dashboard:'Дашборд',bookings:'Все брони',manualbooking:'Ручная бронь (внешние площадки)',calendar:'Управление календарём',prices:'Цены',promo:'Промокоды',settings:'Настройки',contract:'Договор',contracts:'Архив договоров',checkin:'Памятка гостю',checkout:'Чек-лист выезда',houserules:'Правила проживания',sitesettings:'Настройки сайта',reviews:'Отзывы',places:'Куда сходить',discounts:'Скидки и акции',contacts:'Контакты',photos:'Фото и медиа'};
  document.getElementById('topbarTitle').textContent = titles[id]||id;
  if(id==='settings') { loadTimezone(); loadNotif(); }
  if(id==='contract')   { if(typeof loadContractForEditor==='function') loadContractForEditor(); }
  if(id==='contracts')  { if(typeof loadContractsArchive==='function') loadContractsArchive(); }
  if(id==='checkin')     { if(typeof loadCheckinMemo==='function') loadCheckinMemo(); }
  if(id==='checkout')    { if(typeof loadCheckoutChecklist==='function') loadCheckoutChecklist(); }
  if(id==='houserules')  { if(typeof loadHouseRules==='function') loadHouseRules(); }
  if(id==='sitesettings'){ if(typeof loadSiteSettings==='function') loadSiteSettings(); loadDesc(); }
  if(id==='reviews')     { if(typeof loadReviewsAdmin==='function') loadReviewsAdmin(); }
  if(id==='places')      { if(typeof loadPlacesAdmin==='function') loadPlacesAdmin(); }
  if(id==='discounts')   { if(typeof loadDiscountsAdmin==='function') loadDiscountsAdmin(); }
  if(id==='contacts') { if(typeof loadContacts==='function') loadContacts(); }
  if(id==='photos')   { if(typeof loadPhotosAdmin==='function') loadPhotosAdmin(); if(typeof loadSiteSettings==='function') loadSiteSettings(); if(typeof loadMediaItems==='function') loadMediaItems(); }
  if(id==='dashboard'){ if(typeof renderDashStrip==='function') renderDashStrip(); if(typeof renderCheckoutSchedule==='function') renderCheckoutSchedule(); }
}

function statusBadge(s) {
  const map = {
    confirmed:       '<span class="badge badge-green">Подтверждено</span>',
    fully_paid:      '<span class="badge badge-green" style="background:#2D6A4F">Оплачено полностью</span>',
    waiting_payment: '<span class="badge badge-gold">Ждёт оплаты</span>',
    payment_pending: '<span class="badge badge-blue">Оплата проверяется</span>',
    pending:         '<span class="badge badge-gold">Ожидает</span>',
    cancelled:       '<span class="badge badge-red">Отменено</span>',
    blocked:         '<span class="badge badge-red">Заблокировано</span>',
  };
  return map[s] || '<span class="badge">' + (s||'—') + '</span>';
}

function payBadge(m) {
  const map = {card:'<span class="badge badge-blue">Карта</span>', sbp:'<span class="badge badge-gold">СБП</span>', cash:'<span class="badge badge-green">Нал.</span>'};
  return map[m]||m;
}

function showToast(msg, type='gold') {
  const t=document.getElementById('toast');
  t.textContent=msg; t.className=`toast ${type} show`;
  setTimeout(()=>t.classList.remove('show'),3000);
}

// ============================================================
// KEYBOARD
// ============================================================
// ── ДОГОВОР ──────────────────────────────────────
async function loadContractForEditor() {
  try {
    const r = await fetch(`${API_BASE}/api/contract-template`);
    const text = await r.text();
    document.getElementById('contractEditor').value = text;
  } catch(e) {
    document.getElementById('contractEditor').value = 'Ошибка загрузки шаблона';
  }
}

async function saveContract() {
  const text = document.getElementById('contractEditor').value;
  try {
    await apiPost('/api/contract-template', { text });
    showToast('Договор сохранён', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения', 'err');
  }
}

async function resetContract() {
  if(!confirm('Сбросить договор к стандартному шаблону?')) return;
  try {
    const r = await fetch('/static/contract_template.txt');
    const text = await r.text();
    document.getElementById('contractEditor').value = text;
    showToast('Шаблон сброшен — нажмите «Сохранить»', 'gold');
  } catch(e) {
    showToast('Ошибка загрузки шаблона', 'err');
  }
}

function wrapSelectionBold() {
  const ta = document.getElementById('contractEditor');
  const start = ta.selectionStart, end = ta.selectionEnd;
  if (start === end) {
    showToast('Сначала выделите текст в поле договора', 'err');
    return;
  }
  const text = ta.value;
  const selected = text.slice(start, end);
  let replacement, newStart, newEnd;
  if (selected.startsWith('**') && selected.endsWith('**') && selected.length >= 4) {
    // Уже жирный — снимаем разметку (повторное нажатие работает как переключатель)
    replacement = selected.slice(2, -2);
  } else {
    replacement = '**' + selected + '**';
  }
  newStart = start;
  newEnd = start + replacement.length;
  ta.value = text.slice(0, start) + replacement + text.slice(end);
  ta.focus();
  ta.setSelectionRange(newStart, newEnd);
}

function _wrapLinesWithTag(openTag, closeTag) {
  const ta = document.getElementById('contractEditor');
  let start = ta.selectionStart, end = ta.selectionEnd;
  if (start === end) {
    showToast('Сначала выделите строку (или несколько строк) в поле договора', 'err');
    return;
  }
  const text = ta.value;
  // Расширяем выделение до границ строк — выравнивание применяется к строке целиком
  while (start > 0 && text[start - 1] !== '\n') start--;
  while (end < text.length && text[end] !== '\n') end++;
  const block = text.slice(start, end);
  const lines = block.split('\n').map(line => {
    if (line.startsWith(openTag) && line.endsWith(closeTag)) {
      // Уже обёрнуто этим тегом — снимаем (повторное нажатие работает как переключатель)
      return line.slice(openTag.length, line.length - closeTag.length);
    }
    if (line.trim() === '') return line;
    return openTag + line + closeTag;
  });
  const replacement = lines.join('\n');
  ta.value = text.slice(0, start) + replacement + text.slice(end);
  ta.focus();
  ta.setSelectionRange(start, start + replacement.length);
}

function alignSelectionCenter() { _wrapLinesWithTag('[[CENTER]]', '[[/CENTER]]'); }
function alignSelectionRight()  { _wrapLinesWithTag('[[RIGHT]]', '[[/RIGHT]]'); }

async function previewContract() {
  const text = document.getElementById('contractEditor').value;
  const btn = document.getElementById('btnPreviewContract');
  if (btn) { btn.textContent = 'Генерируем...'; btn.disabled = true; }
  try {
    const resp = await fetch(`${API_BASE}/api/admin/contract-preview`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {})
      },
      body: JSON.stringify({text})
    });
    if (!resp.ok) throw new Error('Не удалось сгенерировать предпросмотр');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  } catch(e) {
    showToast('Ошибка предпросмотра: ' + e.message, 'err');
  } finally {
    if (btn) { btn.textContent = 'Предпросмотр (PDF)'; btn.disabled = false; }
  }
}

// Загрузка договора встроена в основной showPanel

async function downloadContract(ref, guestName) {
  try {
    const resp = await fetch(`${API_BASE}/api/contracts/${ref}`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    if (!resp.ok) throw new Error('Не удалось загрузить договор');
    const text = await resp.text();
    const blob = new Blob([text], {type: 'text/plain;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dogovor_${ref}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  } catch(e) {
    showToast('Ошибка скачивания: ' + e.message, 'err');
  }
}

// CONTRACTS ARCHIVE
const PASSPORT_SLOT_LABELS = {main: '📄 Паспорт (главная)', reg1: '🏠 Паспорт (прописка)'};

async function loadContractsArchive() {
  const container = document.getElementById('contractsArchiveContent');
  container.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Загрузка...</div>';
  try {
    const contracts = await apiGet('/api/contracts');
    if (!contracts || contracts.length === 0) {
      container.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Договоров пока нет</div>';
      return;
    }
    container.innerHTML = `
      <table class="tbl">
        <thead><tr>
          <th>Бронь</th><th>Гость</th><th>Даты</th><th>Сумма</th><th>Создан</th><th>Документы</th><th></th>
        </tr></thead>
        <tbody>
          ${contracts.map(c => `
            <tr>
              <td data-label="Бронь" style="color:var(--gold);font-size:12px">${c.ref}</td>
              <td data-label="Гость">
                <div style="font-size:12px;color:var(--text-primary)">${c.guest_name || '—'}</div>
                <div style="font-size:11px;color:var(--text-muted)">${c.guest_email || ''}</div>
              </td>
              <td data-label="Даты" style="font-size:12px">${c.check_in || '—'} → ${c.check_out || '—'}</td>
              <td data-label="Сумма" style="font-size:12px">${c.total_price ? '₽' + Number(c.total_price).toLocaleString('ru') : '—'}</td>
              <td data-label="Создан" style="font-size:11px;color:var(--text-muted)">${c.created}</td>
              <td data-label="Документы" style="display:flex;flex-wrap:wrap;gap:6px">
                ${c.has_contract_pdf ? `<button class="btn btn-outline btn-sm" onclick="downloadArchivePdf('${c.ref}','contract')">📄 Договор (PDF)</button>` : ''}
                ${c.has_consent_pdf ? `<button class="btn btn-outline btn-sm" onclick="downloadArchivePdf('${c.ref}','consent')">📄 Согласие (PDF)</button>` : ''}
                ${!c.has_contract_pdf && c.has_draft ? `<button class="btn btn-ghost btn-sm" onclick="downloadContract('${c.ref}', '${(c.guest_name || c.ref).replace(/'/g,"\\'")}')">Черновик (.txt)</button>` : ''}
                ${(c.passport_photo_slots||[]).map(slot => `<button class="btn btn-ghost btn-sm" onclick="viewArchivePassportPhoto('${c.passport_ref}','${slot}')">${PASSPORT_SLOT_LABELS[slot]}</button>`).join('')}
                ${!c.has_contract_pdf && !c.has_draft && !c.has_passport_photo ? '—' : ''}
              </td>
              <td data-label=""><button class="btn btn-ghost btn-icon" title="Удалить из архива" onclick="deleteArchiveContract('${c.ref}','${(c.guest_name || c.ref).replace(/'/g,"\\'")}')">🗑</button></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch(e) {
    container.innerHTML = '<div style="color:var(--text-muted);padding:20px">Ошибка загрузки: ' + e.message + '</div>';
  }
}

async function downloadArchivePdf(ref, docType) {
  try {
    const resp = await fetch(`${API_BASE}/api/admin/contract-pdf/${ref}/${docType}`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    if (!resp.ok) throw new Error('Документ не найден');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  } catch(e) {
    showToast('Не удалось открыть документ: ' + e.message, 'err');
  }
}

async function viewArchivePassportPhoto(ref, slot) {
  try {
    const resp = await fetch(`${API_BASE}/api/admin/passport-photo/${ref}/${slot}`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    if(!resp.ok) throw new Error('not found');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  } catch(e) {
    showToast('Фото не найдено', 'err');
  }
}

async function deleteArchiveContract(ref, guestName) {
  if (!confirm(`Удалить договор «${guestName}» (${ref}) из архива безвозвратно?\n\nБудут удалены черновик, подписанный PDF, согласие на ПД и фото паспорта. Если по этой брони есть запись в списке броней — она тоже будет удалена.`)) return;
  try {
    await apiDelete(`/api/contracts/${ref}`);
    showToast('Договор удалён из архива', 'gold');
    loadContractsArchive();
  } catch(e) {
    showToast('Ошибка удаления: ' + e.message, 'err');
  }
}

// PHOTOS ADMIN
let photosOrder = [];

async function loadPhotosAdmin() {
  try {
    const photos = await apiGet('/api/photos');
    photosOrder = photos.map(p => p.filename);
    renderPhotosAdmin(photos);
  } catch(e) {
    document.getElementById('photosGrid').innerHTML = '<div style="color:var(--text-muted)">Ошибка загрузки</div>';
  }
}

function renderPhotosAdmin(photos) {
  const grid = document.getElementById('photosGrid');
  if (!photos || photos.length === 0) {
    grid.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Фотографий пока нет — загрузите первое фото</div>';
    return;
  }
  grid.innerHTML = photos.map((p, i) => `
    <div class="photo-card" data-filename="${p.filename}" style="background:var(--black-card);border:1px solid var(--black-border);position:relative">
      <img src="${p.url}" style="width:100%;height:140px;object-fit:cover;display:block">
      <div style="padding:10px 12px">
        <input type="text" value="${p.label}" placeholder="Подпись к фото"
          style="width:100%;background:var(--black);border:1px solid var(--black-border);color:var(--text-secondary);padding:6px 8px;font-family:'Montserrat',sans-serif;font-size:11px;margin-bottom:8px;outline:none"
          onchange="updatePhotoLabel('${p.filename}', this.value)">
        <div style="display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" style="flex:1" onclick="movePhoto('${p.filename}', -1)">↑</button>
          <button class="btn btn-ghost btn-sm" style="flex:1" onclick="movePhoto('${p.filename}', 1)">↓</button>
          <button class="btn btn-danger btn-sm" onclick="deletePhoto('${p.filename}')">✕</button>
        </div>
      </div>
    </div>
  `).join('');
  document.getElementById('saveOrderBtn').style.display = 'block';
}

async function updatePhotoLabel(filename, label) {
  try {
    await apiPost(`/api/photos/${filename}/label`, {label});
    showToast('Подпись сохранена', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения подписи', 'err');
  }
}

async function uploadPhoto() {
  const file = document.getElementById('photoFile').files[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) { showToast('Файл слишком большой (макс. 5 МБ)', 'err'); return; }
  const label = document.getElementById('photoLabel').value.trim();
  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', label);
  try {
    const resp = await fetch(`${API_BASE}/api/photos/upload`, {
      method: 'POST',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {},
      body: formData
    });
    if (!resp.ok) throw new Error(await resp.text());
    showToast('Фото загружено', 'gold');
    document.getElementById('photoFile').value = '';
    document.getElementById('photoLabel').value = '';
    loadPhotosAdmin();
  } catch(e) {
    showToast('Ошибка загрузки: ' + e.message, 'err');
  }
}

async function deletePhoto(filename, force) {
  if (!force && !confirm('Удалить это фото?')) return;
  try {
    const resp = await fetch(`${API_BASE}/api/photos/${filename}${force ? '?force=true' : ''}`, {
      method: 'DELETE',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    if (resp.status === 409) {
      const data = await resp.json().catch(() => ({}));
      const msg = (data.detail || 'Это фото сейчас где-то используется.') + '\n\nВсё равно удалить?';
      if (confirm(msg)) {
        return deletePhoto(filename, true);
      }
      return;
    }
    if (!resp.ok) {
      showToast('Ошибка удаления', 'err');
      return;
    }
    showToast('Фото удалено', 'err');
    loadPhotosAdmin();
  } catch(e) {
    showToast('Ошибка удаления', 'err');
  }
}

async function movePhoto(filename, dir) {
  const idx = photosOrder.indexOf(filename);
  if (idx === -1) return;
  const newIdx = idx + dir;
  if (newIdx < 0 || newIdx >= photosOrder.length) return;
  photosOrder.splice(idx, 1);
  photosOrder.splice(newIdx, 0, filename);
  await savePhotosOrder();
  loadPhotosAdmin();
}

async function savePhotosOrder() {
  try {
    await apiPost('/api/photos/reorder', {order: photosOrder});
    showToast('Порядок сохранён', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения порядка', 'err');
  }
}

// MANUAL BOOKING (внешние площадки)
async function createManualBooking() {
  const payload = {
    source:       document.getElementById('mbSource').value,
    check_in:     document.getElementById('mbCheckIn').value,
    check_out:    document.getElementById('mbCheckOut').value,
    guest_name:   document.getElementById('mbGuestName').value.trim(),
    guest_phone:  document.getElementById('mbPhone').value.trim(),
    guest_email:  document.getElementById('mbEmail').value.trim(),
    guests_count: parseInt(document.getElementById('mbGuests').value) || 2,
    passport:     document.getElementById('mbPassport').value.trim(),
    total_price:  parseInt(document.getElementById('mbTotal').value) || 0,
    deposit:      parseInt(document.getElementById('mbDeposit').value) || 0,
    notes:        document.getElementById('mbNotes').value.trim(),
  };
  if(!payload.check_in || !payload.check_out) {
    showToast('Укажите даты заезда и выезда', 'err');
    return;
  }
  try {
    const res = await apiPost('/api/admin/manual-booking', payload);
    showToast(`Бронь ${res.booking_ref} создана`, 'gold');

    document.getElementById('mbLinkBox').style.display = 'block';
    document.getElementById('mbLinkInput').value = res.sign_link;
    document.getElementById('mbLinkNote').textContent = res.email_sent
      ? 'Ссылка также отправлена гостю на email.'
      : 'Email не указан — скопируй ссылку и отправь гостю вручную (например, в чат Авито).';

    ['mbGuestName','mbPhone','mbEmail','mbPassport','mbTotal','mbDeposit','mbNotes','mbCheckIn','mbCheckOut'].forEach(id => {
      document.getElementById(id).value = '';
    });
    document.getElementById('mbGuests').value = 2;
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

function copyMbLink() {
  const input = document.getElementById('mbLinkInput');
  input.select();
  navigator.clipboard?.writeText(input.value).then(() => {
    showToast('Ссылка скопирована', 'gold');
  }).catch(() => {
    document.execCommand('copy');
    showToast('Ссылка скопирована', 'gold');
  });
}

async function resendContractManual() {
  const ref = document.getElementById('resendBookingRef').value.trim();
  const email = document.getElementById('resendEmail').value.trim();
  if(!ref || !email) {
    showToast('Укажите номер брони и email', 'err');
    return;
  }
  try {
    await apiPost(`/api/admin/bookings/${ref}/resend-contract`, {email});
    showToast('Договор отправлен на ' + email, 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

// CONTACTS ADMIN
async function loadContacts() {
  try {
    const c = await apiGet('/api/contacts');
    document.getElementById('contactsPhone').value    = c.phone    || '';
    document.getElementById('contactsEmail').value    = c.email    || '';
    document.getElementById('contactsTelegram').value = c.telegram || '';
    document.getElementById('contactsWhatsapp').value = c.whatsapp || '';
    document.getElementById('contactsMax').value      = c.max      || '';
  } catch(e) {}
  loadPaymentSettings();
}

async function saveContacts() {
  const payload = {
    phone:    document.getElementById('contactsPhone').value.trim(),
    email:    document.getElementById('contactsEmail').value.trim(),
    telegram: document.getElementById('contactsTelegram').value.trim().replace(/^@/, ''),
    whatsapp: document.getElementById('contactsWhatsapp').value.trim(),
    max:      document.getElementById('contactsMax').value.trim(),
  };
  try {
    await apiPost('/api/contacts', payload);
    showToast('Контакты сохранены', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения', 'err');
  }
}

// PAYMENT SETTINGS (СБП: ссылка, телефон, свой QR-код)
async function loadPaymentSettings() {
  try {
    const p = await apiGet('/api/payment-settings');
    document.getElementById('paySbpLink').value  = p.sbp_link  || '';
    document.getElementById('paySbpPhone').value = p.sbp_phone || '';
    const preview = document.getElementById('paymentQrPreview');
    const delBtn = document.getElementById('paymentQrDeleteBtn');
    if (p.qr_uploaded) {
      preview.src = '/api/payment-qr?t=' + Date.now();
      preview.style.display = 'block';
      delBtn.style.display = 'inline-block';
    } else {
      preview.style.display = 'none';
      delBtn.style.display = 'none';
    }
  } catch(e) {}
}

async function savePaymentSettings() {
  const payload = {
    sbp_link:  document.getElementById('paySbpLink').value.trim(),
    sbp_phone: document.getElementById('paySbpPhone').value.trim(),
  };
  try {
    await apiPost('/api/payment-settings', payload);
    showToast('Настройки оплаты сохранены', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения', 'err');
  }
}

async function uploadPaymentQr(input) {
  const file = input.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch(`${API_BASE}/api/payment-qr`, {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + ADMIN_TOKEN },
      body: formData,
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Ошибка загрузки');
    showToast('QR-код загружен', 'gold');
    loadPaymentSettings();
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
  input.value = '';
}

async function deletePaymentQr() {
  try {
    await fetch(`${API_BASE}/api/payment-qr`, {
      method: 'DELETE',
      headers: { 'Authorization': 'Bearer ' + ADMIN_TOKEN },
    });
    showToast('QR-код удалён', 'gold');
    loadPaymentSettings();
  } catch(e) {
    showToast('Ошибка удаления', 'err');
  }
}

// PLACES ADMIN
let allPlacesAdmin = [];

async function loadPlacesAdmin() {
  try {
    allPlacesAdmin = await apiGet('/api/places/all');
    renderPlacesAdmin(allPlacesAdmin);
  } catch(e) {
    document.getElementById('placesList').innerHTML = '<div style="color:var(--text-muted);padding:20px">Ошибка загрузки</div>';
  }
}

function renderPlacesAdmin(places) {
  const list = document.getElementById('placesList');
  if(!places || places.length === 0) {
    list.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Мест пока нет — нажмите «+ Добавить место»</div>';
    return;
  }
  list.innerHTML = places.map(p => `
    <div class="place-row" style="display:grid;grid-template-columns:120px 1fr auto;gap:16px;align-items:center;padding:16px;border:1px solid ${p.visible ? 'var(--black-border)' : 'rgba(90,74,48,.3)'};margin-bottom:8px;background:var(--black-card)">
      <div class="place-row-photo" style="height:80px;overflow:hidden;border:1px solid var(--black-border)">
        ${p.photo ? `<img src="${API_BASE}/data/photos/${p.photo}" style="width:100%;height:100%;object-fit:cover">` : '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:24px;background:var(--black)">📍</div>'}
      </div>
      <div style="min-width:0">
        <div style="font-size:10px;color:var(--gold);letter-spacing:.15em;margin-bottom:4px">${p.category || '—'}</div>
        <div style="font-size:14px;color:var(--text-primary);margin-bottom:4px">${p.name}</div>
        <div style="font-size:11px;color:var(--text-muted)">${p.distance || ''}</div>
        ${!p.visible ? '<span style="font-size:10px;color:var(--text-muted);background:rgba(90,74,48,.3);padding:2px 8px">скрыто</span>' : ''}
      </div>
      <div class="place-row-actions" style="display:flex;flex-direction:column;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="editPlace('${p.id}')">✎</button>
        <button class="btn btn-ghost btn-sm" onclick="togglePlaceVisibility('${p.id}', ${!p.visible})">${p.visible ? '👁' : '👁‍🗨'}</button>
        <button class="btn btn-danger btn-sm" onclick="deletePlace('${p.id}')">✕</button>
      </div>
    </div>
  `).join('');
}

function showPlaceForm() {
  document.getElementById('placeEditId').value = '';
  document.getElementById('placeName').value = '';
  document.getElementById('placeCategory').value = '';
  document.getElementById('placeDistance').value = '';
  document.getElementById('placeDescription').value = '';
  document.getElementById('placePhotoValue').value = '';
  document.getElementById('placePhotoName').textContent = 'не выбрано';
  document.getElementById('placePhotoPreview').style.display = 'none';
  document.getElementById('placeFormTitle').textContent = 'Новое место';
  document.getElementById('placeFormWrap').style.display = 'block';
}

function editPlace(id) {
  const p = allPlacesAdmin.find(x => x.id === id);
  if(!p) return;
  document.getElementById('placeEditId').value = p.id;
  document.getElementById('placeName').value = p.name || '';
  document.getElementById('placeCategory').value = p.category || '';
  document.getElementById('placeDistance').value = p.distance || '';
  document.getElementById('placeDescription').value = p.description || '';
  document.getElementById('placePhotoValue').value = p.photo || '';
  if(p.photo) {
    const img = document.getElementById('placePhotoPreview');
    img.src = `${API_BASE}/data/photos/${p.photo}`;
    img.style.display = 'block';
    document.getElementById('placePhotoName').textContent = p.photo;
  }
  document.getElementById('placeFormTitle').textContent = 'Редактировать место';
  document.getElementById('placeFormWrap').style.display = 'block';
}

function cancelPlaceForm() {
  document.getElementById('placeFormWrap').style.display = 'none';
}

async function uploadPlacePhoto() {
  const file = document.getElementById('placePhotoFile').files[0];
  if(!file) return;
  if(file.size > 10 * 1024 * 1024) { showToast('Файл слишком большой (макс. 10 МБ)', 'err'); return; }
  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', document.getElementById('placeName').value || 'Место');
  formData.append('purpose', 'place');
  try {
    const resp = await fetch(`${API_BASE}/api/photos/upload`, {
      method: 'POST',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {},
      body: formData
    });
    const data = await resp.json();
    document.getElementById('placePhotoValue').value = data.filename;
    document.getElementById('placePhotoName').textContent = data.filename;
    const img = document.getElementById('placePhotoPreview');
    img.src = `${API_BASE}/data/photos/${data.filename}`;
    img.style.display = 'block';
    showToast('Фото загружено', 'gold');
  } catch(e) { showToast('Ошибка загрузки фото', 'err'); }
}

async function savePlace() {
  const id = document.getElementById('placeEditId').value;
  const payload = {
    name:        document.getElementById('placeName').value.trim(),
    category:    document.getElementById('placeCategory').value.trim(),
    distance:    document.getElementById('placeDistance').value.trim(),
    description: document.getElementById('placeDescription').value.trim(),
    photo:       document.getElementById('placePhotoValue').value.trim(),
    visible:     true
  };
  { const cur = id ? allPlacesAdmin.find(x => x.id === id) : null; if(cur) payload.photo = cur.photo || ''; }
  if(!payload.name) { showToast('Введите название места', 'err'); return; }
  try {
    if(id) await apiPut('/api/places/' + id, payload);
    else   await apiPost('/api/places', payload);
    showToast('Место сохранено', 'gold');
    document.getElementById('placeFormWrap').style.display = 'none';
    loadPlacesAdmin();
  } catch(e) { showToast('Ошибка: ' + e.message, 'err'); }
}

async function togglePlaceVisibility(id, visible) {
  const p = allPlacesAdmin.find(x => x.id === id);
  if(!p) return;
  try {
    await apiPut('/api/places/' + id, {...p, visible});
    showToast(visible ? 'Место показано' : 'Место скрыто', 'gold');
    loadPlacesAdmin();
  } catch(e) { showToast('Ошибка', 'err'); }
}

async function deletePlace(id) {
  if(!confirm('Удалить это место?')) return;
  try {
    await fetch(`${API_BASE}/api/places/${id}`, {
      method: 'DELETE',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    showToast('Место удалено', 'err');
    loadPlacesAdmin();
  } catch(e) { showToast('Ошибка удаления', 'err'); }
}

// DISCOUNTS ADMIN (Скидки и акции)
let allDiscountsAdmin = [];

async function loadDiscountsAdmin() {
  try {
    allDiscountsAdmin = await apiGet('/api/discounts/all');
    renderDiscountsAdmin(allDiscountsAdmin);
  } catch(e) {
    document.getElementById('discountsList').innerHTML = '<div style="color:var(--text-muted);padding:20px">Ошибка загрузки</div>';
  }
}

function renderDiscountsAdmin(discounts) {
  const list = document.getElementById('discountsList');
  if(!discounts || discounts.length === 0) {
    list.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Акций пока нет — нажмите «+ Добавить акцию»</div>';
    return;
  }
  list.innerHTML = discounts.map(d => `
    <div class="place-row" style="display:grid;grid-template-columns:120px 1fr auto;gap:16px;align-items:center;padding:16px;border:1px solid ${d.visible ? 'var(--black-border)' : 'rgba(90,74,48,.3)'};margin-bottom:8px;background:var(--black-card)">
      <div class="place-row-photo" style="height:80px;overflow:hidden;border:1px solid var(--black-border)">
        ${d.photo ? `<img src="${API_BASE}/data/photos/${d.photo}" style="width:100%;height:100%;object-fit:cover">` : '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:24px;background:var(--black)">🏷️</div>'}
      </div>
      <div style="min-width:0">
        <div style="font-size:14px;color:var(--text-primary);margin-bottom:4px">${d.name}</div>
        <div style="font-size:11px;color:var(--text-muted)">${(d.description || '').slice(0, 80)}</div>
        ${!d.visible ? '<span style="font-size:10px;color:var(--text-muted);background:rgba(90,74,48,.3);padding:2px 8px">скрыто</span>' : ''}
      </div>
      <div class="place-row-actions" style="display:flex;flex-direction:column;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="editDiscount('${d.id}')">✎</button>
        <button class="btn btn-ghost btn-sm" onclick="toggleDiscountVisibility('${d.id}', ${!d.visible})">${d.visible ? '👁' : '👁‍🗨'}</button>
        <button class="btn btn-danger btn-sm" onclick="deleteDiscount('${d.id}')">✕</button>
      </div>
    </div>
  `).join('');
}

function showDiscountForm() {
  document.getElementById('discountEditId').value = '';
  document.getElementById('discountName').value = '';
  document.getElementById('discountDescription').value = '';
  document.getElementById('discountPhotoValue').value = '';
  document.getElementById('discountPhotoName').textContent = 'не выбрано';
  document.getElementById('discountPhotoPreview').style.display = 'none';
  document.getElementById('discountPhotoMobileValue').value = '';
  document.getElementById('discountPhotoMobileName').textContent = 'не выбрано';
  document.getElementById('discountPhotoMobilePreview').style.display = 'none';
  document.getElementById('discountFormTitle').textContent = 'Новая акция';
  document.getElementById('discountFormWrap').style.display = 'block';
}

function editDiscount(id) {
  const d = allDiscountsAdmin.find(x => x.id === id);
  if(!d) return;
  document.getElementById('discountEditId').value = d.id;
  document.getElementById('discountName').value = d.name || '';
  document.getElementById('discountDescription').value = d.description || '';
  document.getElementById('discountPhotoValue').value = d.photo || '';
  document.getElementById('discountPhotoMobileValue').value = d.photo_mobile || '';
  document.getElementById('discountPhotoMobileName').textContent = d.photo_mobile || 'не выбрано';
  document.getElementById('discountPhotoMobilePreview').style.display = d.photo_mobile ? 'block' : 'none';
  if(d.photo) {
    const img = document.getElementById('discountPhotoPreview');
    img.src = `${API_BASE}/data/photos/${d.photo}`;
    img.style.display = 'block';
    document.getElementById('discountPhotoName').textContent = d.photo;
  }
  if(d.photo_mobile) {
    document.getElementById('discountPhotoMobilePreview').src = `${API_BASE}/data/photos/${d.photo_mobile}`;
  }
  document.getElementById('discountFormTitle').textContent = 'Редактировать акцию';
  document.getElementById('discountFormWrap').style.display = 'block';
}

function cancelDiscountForm() {
  document.getElementById('discountFormWrap').style.display = 'none';
}

async function uploadDiscountPhoto(variant) {
  const isMobile = variant === 'mobile';
  const fileInputId = isMobile ? 'discountPhotoMobileFile' : 'discountPhotoFile';
  const valueId      = isMobile ? 'discountPhotoMobileValue' : 'discountPhotoValue';
  const nameId       = isMobile ? 'discountPhotoMobileName'  : 'discountPhotoName';
  const previewId    = isMobile ? 'discountPhotoMobilePreview' : 'discountPhotoPreview';
  const file = document.getElementById(fileInputId).files[0];
  if(!file) return;
  if(file.size > 10 * 1024 * 1024) { showToast('Файл слишком большой (макс. 10 МБ)', 'err'); return; }
  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', document.getElementById('discountName').value || 'Акция');
  formData.append('purpose', 'discount');
  try {
    const resp = await fetch(`${API_BASE}/api/photos/upload`, {
      method: 'POST',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {},
      body: formData
    });
    const data = await resp.json();
    document.getElementById(valueId).value = data.filename;
    document.getElementById(nameId).textContent = data.filename;
    const img = document.getElementById(previewId);
    img.src = `${API_BASE}/data/photos/${data.filename}`;
    img.style.display = 'block';
    showToast('Фото загружено', 'gold');
  } catch(e) { showToast('Ошибка загрузки фото', 'err'); }
}

async function saveDiscount() {
  const id = document.getElementById('discountEditId').value;
  const payload = {
    name:        document.getElementById('discountName').value.trim(),
    description: document.getElementById('discountDescription').value.trim(),
    photo:       document.getElementById('discountPhotoValue').value.trim(),
    photo_mobile: document.getElementById('discountPhotoMobileValue').value.trim(),
    visible:     true
  };
  { const cur = id ? allDiscountsAdmin.find(x => x.id === id) : null; if(cur) { payload.photo = cur.photo || ''; payload.photo_mobile = cur.photo_mobile || ''; } }
  if(!payload.name) { showToast('Введите название акции', 'err'); return; }
  try {
    if(id) await apiPut('/api/discounts/' + id, payload);
    else   await apiPost('/api/discounts', payload);
    showToast('Акция сохранена', 'gold');
    document.getElementById('discountFormWrap').style.display = 'none';
    loadDiscountsAdmin();
  } catch(e) { showToast('Ошибка: ' + e.message, 'err'); }
}

async function toggleDiscountVisibility(id, visible) {
  const d = allDiscountsAdmin.find(x => x.id === id);
  if(!d) return;
  try {
    await apiPut('/api/discounts/' + id, {...d, visible});
    showToast(visible ? 'Акция показана' : 'Акция скрыта', 'gold');
    loadDiscountsAdmin();
  } catch(e) { showToast('Ошибка', 'err'); }
}

async function deleteDiscount(id) {
  if(!confirm('Удалить эту акцию?')) return;
  try {
    await fetch(`${API_BASE}/api/discounts/${id}`, {
      method: 'DELETE',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    showToast('Акция удалена', 'err');
    loadDiscountsAdmin();
  } catch(e) { showToast('Ошибка удаления', 'err'); }
}

// ============================================================
// ФОТО И МЕДИА: фото акций и мест (загрузка в одном месте)
// ============================================================
let mediaPending = null;

function mediaEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function loadMediaItems() {
  try {
    const [discounts, places] = await Promise.all([apiGet('/api/discounts/all'), apiGet('/api/places/all')]);
    allDiscountsAdmin = discounts || [];
    allPlacesAdmin = places || [];
  } catch(e) {
    const err = '<div style="color:var(--text-muted);padding:12px">Ошибка загрузки</div>';
    document.getElementById('mediaDiscountsList').innerHTML = err;
    document.getElementById('mediaPlacesList').innerHTML = err;
    return;
  }
  renderMediaItems();
}

function mediaSlot(kind, id, field, file, caption, w, h, removable) {
  const thumb = file
    ? `<img src="${API_BASE}/data/photos/${mediaEsc(file)}" style="width:100%;height:100%;object-fit:cover;display:block">`
    : `<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:20px;color:var(--text-muted)">🖼</div>`;
  return `
    <div style="display:flex;gap:10px;align-items:center">
      <div style="width:${w}px;height:${h}px;background:var(--black);border:1px solid var(--black-border);overflow:hidden;flex-shrink:0">${thumb}</div>
      <div>
        <div style="font-size:10px;color:var(--text-muted);margin-bottom:6px">${caption}</div>
        <button type="button" class="btn btn-ghost btn-sm" onclick="mediaPick('${kind}','${mediaEsc(id)}','${field}')">${file ? 'Заменить' : 'Загрузить'}</button>
        ${removable && file ? `<button type="button" class="btn btn-danger btn-sm" style="margin-left:6px" onclick="mediaRemove('${kind}','${mediaEsc(id)}','${field}')">Убрать</button>` : ''}
      </div>
    </div>`;
}

function mediaRow(title, hidden, slots) {
  return `
    <div style="padding:14px 16px;border:1px solid var(--black-border);background:var(--black-card);margin-bottom:8px">
      <div style="font-size:13px;color:var(--text-primary);margin-bottom:12px">${mediaEsc(title)}
        ${hidden ? '<span style="font-size:10px;color:var(--text-muted);background:rgba(90,74,48,.3);padding:2px 8px;margin-left:8px">скрыто</span>' : ''}
      </div>
      <div style="display:flex;gap:20px 28px;flex-wrap:wrap">${slots}</div>
    </div>`;
}

function renderMediaItems() {
  const dBox = document.getElementById('mediaDiscountsList');
  const pBox = document.getElementById('mediaPlacesList');
  if(!dBox || !pBox) return;
  dBox.innerHTML = allDiscountsAdmin.length
    ? allDiscountsAdmin.map(d => mediaRow(d.name || 'Без названия', d.visible === false,
        mediaSlot('discount', d.id, 'photo', d.photo, 'Компьютер (16:9)', 128, 72, false) +
        mediaSlot('discount', d.id, 'photo_mobile', d.photo_mobile, 'Телефон (9:16), необязательно', 56, 100, true)
      )).join('')
    : '<div style="color:var(--text-muted);padding:12px 0">Акций пока нет. Создайте акцию в разделе «Скидки и акции».</div>';
  pBox.innerHTML = allPlacesAdmin.length
    ? allPlacesAdmin.map(p => mediaRow(p.name || 'Без названия', p.visible === false,
        mediaSlot('place', p.id, 'photo', p.photo, 'Фото места (3:2)', 120, 80, true)
      )).join('')
    : '<div style="color:var(--text-muted);padding:12px 0">Мест пока нет. Добавьте место в разделе «Куда сходить».</div>';
}

const MEDIA_KINDS = {
  discount: { purpose: 'discount', path: '/api/discounts/', list: () => allDiscountsAdmin, okMsg: 'Фото акции сохранено' },
  place:    { purpose: 'place',    path: '/api/places/',    list: () => allPlacesAdmin,    okMsg: 'Фото места сохранено' },
};

function mediaPick(kind, id, field) {
  mediaPending = {kind, id, field};
  const f = document.getElementById('mediaItemFile');
  f.value = '';
  f.click();
}

async function mediaSaveField(kind, id, field, filename) {
  const cfg = MEDIA_KINDS[kind];
  const item = cfg.list().find(x => String(x.id) === String(id));
  if(!item) throw new Error('Элемент не найден, обновите страницу');
  await apiPut(cfg.path + id, {...item, [field]: filename});
}

async function mediaItemFileChosen() {
  const f = document.getElementById('mediaItemFile');
  const file = f.files[0];
  const pend = mediaPending;
  if(!file || !pend) return;
  if(file.size > 10 * 1024 * 1024) { showToast('Файл слишком большой (макс. 10 МБ)', 'err'); return; }
  const cfg = MEDIA_KINDS[pend.kind];
  const item = cfg.list().find(x => String(x.id) === String(pend.id));
  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', (item && item.name) || (pend.kind === 'discount' ? 'Акция' : 'Место'));
  formData.append('purpose', cfg.purpose);
  try {
    showToast('Загружаю фото...', 'gold');
    const resp = await fetch(`${API_BASE}/api/photos/upload`, {
      method: 'POST',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {},
      body: formData
    });
    if(!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    await mediaSaveField(pend.kind, pend.id, pend.field, data.filename);
    showToast(cfg.okMsg, 'gold');
    await loadMediaItems();
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  } finally {
    f.value = '';
    mediaPending = null;
  }
}

async function mediaRemove(kind, id, field) {
  if(!confirm('Убрать это фото?')) return;
  try {
    await mediaSaveField(kind, id, field, '');
    showToast('Фото убрано', 'gold');
    await loadMediaItems();
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

// REVIEWS ADMIN
let allReviewsAdmin = [];

async function loadReviewsAdmin() {
  try {
    allReviewsAdmin = await apiGet('/api/reviews/all');
    renderReviewsAdmin(allReviewsAdmin);
  } catch(e) {
    document.getElementById('reviewsList').innerHTML = '<div style="color:var(--text-muted);padding:20px">Ошибка загрузки отзывов</div>';
  }
}

function renderReviewsAdmin(reviews) {
  const list = document.getElementById('reviewsList');
  if (!reviews || reviews.length === 0) {
    list.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Отзывов пока нет — нажмите «+ Добавить отзыв»</div>';
    return;
  }
  const stars = n => '★'.repeat(n)+'☆'.repeat(5-n);
  list.innerHTML = reviews.map(r => `
    <div style="background:var(--black-card);border:1px solid ${r.visible ? 'var(--black-border)' : 'rgba(90,74,48,.4)'};padding:16px 20px;margin-bottom:12px;display:flex;gap:16px;align-items:flex-start">
      <div style="flex:1">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">
          <span style="color:var(--gold);font-size:12px">${stars(r.rating||5)}</span>
          <span style="font-size:12px;color:var(--text-primary)">${r.author}</span>
          ${r.date ? `<span style="font-size:10px;color:var(--text-muted)">${r.date}</span>` : ''}
          ${!r.visible ? '<span style="font-size:10px;color:var(--text-muted);background:rgba(90,74,48,.3);padding:2px 8px">скрыт</span>' : ''}
        </div>
        <div style="font-size:12px;color:var(--text-secondary);line-height:1.6">${r.text.replace(/\n/g,'<br>')}</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0">
        <button class="btn btn-ghost btn-sm" onclick="editReview('${r.id}')">✎</button>
        <button class="btn btn-ghost btn-sm" onclick="toggleReviewVisibility('${r.id}', ${!r.visible})">${r.visible ? '👁' : '👁‍🗨'}</button>
        <button class="btn btn-danger btn-sm" onclick="deleteReview('${r.id}')">✕</button>
      </div>
    </div>
  `).join('');
}

function showAddReviewForm() {
  document.getElementById('reviewEditId').value = '';
  document.getElementById('reviewAuthor').value = '';
  document.getElementById('reviewText').value = '';
  document.getElementById('reviewRating').value = 5;
  document.getElementById('reviewDate').value = '';
  document.getElementById('reviewFormTitle').textContent = 'Новый отзыв';
  document.getElementById('reviewForm').style.display = 'block';
}

function editReview(id) {
  const r = allReviewsAdmin.find(x => x.id === id);
  if (!r) return;
  document.getElementById('reviewEditId').value = r.id;
  document.getElementById('reviewAuthor').value = r.author;
  document.getElementById('reviewText').value = r.text;
  document.getElementById('reviewRating').value = r.rating || 5;
  document.getElementById('reviewDate').value = r.date || '';
  document.getElementById('reviewFormTitle').textContent = 'Редактировать отзыв';
  document.getElementById('reviewForm').style.display = 'block';
}

function cancelReviewForm() {
  document.getElementById('reviewForm').style.display = 'none';
}

async function saveReview() {
  const id      = document.getElementById('reviewEditId').value;
  const author  = document.getElementById('reviewAuthor').value.trim();
  const text    = document.getElementById('reviewText').value.trim();
  const rating  = parseInt(document.getElementById('reviewRating').value) || 5;
  const date    = document.getElementById('reviewDate').value.trim();
  if (!author || !text) { showToast('Заполните имя и текст отзыва', 'err'); return; }
  const payload = { author, text, rating, date, visible: true };
  try {
    if (id) {
      await apiPut('/api/reviews/' + id, payload);
    } else {
      await apiPost('/api/reviews', payload);
    }
    document.getElementById('reviewForm').style.display = 'none';
    showToast('Отзыв сохранён', 'gold');
    loadReviewsAdmin();
  } catch(e) {
    showToast('Ошибка сохранения: ' + e.message, 'err');
  }
}

async function toggleReviewVisibility(id, visible) {
  const r = allReviewsAdmin.find(x => x.id === id);
  if (!r) return;
  try {
    await apiPut('/api/reviews/' + id, {...r, visible});
    showToast(visible ? 'Отзыв показан' : 'Отзыв скрыт', 'gold');
    loadReviewsAdmin();
  } catch(e) {
    showToast('Ошибка', 'err');
  }
}

async function deleteReview(id) {
  if (!confirm('Удалить отзыв?')) return;
  try {
    await fetch(`${API_BASE}/api/reviews/${id}`, {
      method: 'DELETE',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    showToast('Отзыв удалён', 'err');
    loadReviewsAdmin();
  } catch(e) {
    showToast('Ошибка удаления', 'err');
  }
}
// HOUSE RULES
async function loadHouseRules() {
  try {
    const r = await fetch(`${API_BASE}/api/house-rules`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    document.getElementById('houseRulesEditor').value = await r.text();
  } catch(e) { document.getElementById('houseRulesEditor').value = 'Ошибка загрузки'; }
}
async function saveHouseRules() {
  try {
    await apiPost('/api/house-rules', {text: document.getElementById('houseRulesEditor').value});
    showToast('Правила проживания сохранены', 'gold');
  } catch(e) { showToast('Ошибка сохранения', 'err'); }
}

// SITE SETTINGS
const FONT_OPTIONS = [
  {key: 'cormorant',  label: 'Cormorant Garamond', family: "'Cormorant Garamond',serif", weight: 400},
  {key: 'im_fell',    label: 'PT Serif',         family: "'PT Serif',serif",         weight: 700},
  {key: 'playfair',   label: 'IM Fell English',  family: "'IM Fell English',serif", weight: 400},
  {key: 'unifraktur', label: 'Yeseva One',       family: "'Yeseva One',serif",       weight: 400},
  {key: 'tangerine',  label: 'Marck Script',     family: "'Marck Script',cursive",   weight: 400},
  {key: 'pacifico',   label: 'Pacifico',         family: "'Pacifico',cursive",       weight: 400},
  {key: 'great_vibes', label: 'Great Vibes',     family: "'Great Vibes',cursive",    weight: 400},
  {key: 'berkshire',  label: 'Bad Script',       family: "'Bad Script',cursive",     weight: 400},
  {key: 'poiret',     label: 'Poiret One',       family: "'Poiret One',sans-serif",   weight: 400},
];
const HERO_FONT_OPTIONS = FONT_OPTIONS;
let selectedFont = 'im_fell';
let selectedBold = false;
let selectedScale = 1.0;
let selectedNavScale = 1.0;
let selectedColorTheme = 'gold';
let selectedBackgroundTheme = 'black';
let selectedHeroFont = 'cormorant';
let selectedHeroBold = false;
let selectedHeroTitleScale = 1.0;
let selectedHeroSubtitleScale = 1.0;
let selectedHeroPosition = 'center';
let selectedHeroCarouselEnabled = true;
let selectedHeroCarouselSeconds = 6;
let selectedHeaderOpacityLevel = 3;
let selectedHeaderBlurLevel = 2;
const SCALE_OPTIONS = [0.5, 0.7, 1.0, 1.5, 2.0, 2.5];
const HERO_SCALE_OPTIONS = [0.5, 0.7, 1.0, 1.5, 2.0];
const NAV_SCALE_OPTIONS = [1.0, 1.2, 1.4, 1.6, 1.8];
const HERO_POSITION_OPTIONS = [{v:'left',label:'Слева'},{v:'center',label:'По центру'},{v:'right',label:'Справа'}];
const COLOR_THEMES = [
  {key: 'gold',       label: 'Золото',        solid: '#D4A017', gradient: 'linear-gradient(180deg,#FFD060 0%,#D4920A 28%,#8B5E00 50%,#D4920A 72%,#FFD060 100%)'},
  {key: 'emerald',    label: 'Изумруд',       solid: '#2E8B57', gradient: 'linear-gradient(180deg,#8FE3B0 0%,#2E8B57 28%,#0E3D22 50%,#2E8B57 72%,#8FE3B0 100%)'},
  {key: 'sapphire',   label: 'Сапфир',        solid: '#2A5CAA', gradient: 'linear-gradient(180deg,#A8CFFF 0%,#2A5CAA 28%,#0C1E3D 50%,#2A5CAA 72%,#A8CFFF 100%)'},
  {key: 'burgundy',   label: 'Бордо',         solid: '#7B1E3A', gradient: 'linear-gradient(180deg,#DE93A9 0%,#7B1E3A 28%,#2E0A16 50%,#7B1E3A 72%,#DE93A9 100%)'},
  {key: 'amethyst',   label: 'Аметист',       solid: '#7B4B94', gradient: 'linear-gradient(180deg,#DDBFEA 0%,#7B4B94 28%,#2F1D3D 50%,#7B4B94 72%,#DDBFEA 100%)'},
  {key: 'dusty_rose', label: 'Пыльная роза',  solid: '#C08497', gradient: 'linear-gradient(180deg,#F5DEE3 0%,#C08497 28%,#5E3540 50%,#C08497 72%,#F5DEE3 100%)'},
  {key: 'teal',       label: 'Бирюза',        solid: '#1F8A8C', gradient: 'linear-gradient(180deg,#9FEAE5 0%,#1F8A8C 28%,#082D2E 50%,#1F8A8C 72%,#9FEAE5 100%)'},
  {key: 'copper',     label: 'Медь',          solid: '#B5651D', gradient: 'linear-gradient(180deg,#F3C495 0%,#B5651D 28%,#3E2008 50%,#B5651D 72%,#F3C495 100%)'},
  {key: 'graphite',   label: 'Графит',        solid: '#8A8D91', gradient: 'linear-gradient(180deg,#F2F3F4 0%,#8A8D91 28%,#232426 50%,#8A8D91 72%,#F2F3F4 100%)'},
  {key: 'onyx',       label: 'Оникс',         solid: '#6E6A63', gradient: 'linear-gradient(180deg,#A39C90 0%,#6E6A63 28%,#000000 50%,#6E6A63 72%,#A39C90 100%)'},
];

// Темы ФОНА сайта — отдельная ось от COLOR_THEMES (там акцентный цвет
// логотипа/кнопок, тут — сам фон страницы и цвет текста под него).
// Первая опция ("black") — нынешний фон проекта, значения 1-в-1 совпадают
// с текущими CSS-переменными, поэтому смена ничего не ломает по умолчанию.
const BACKGROUND_THEMES = [
  {key: 'black',     label: 'Чёрный',       swatch: '#0A0A0A',
    bg: '#0A0A0A', card: '#141414', border: '#1E1E1E',
    text_primary: '#F0E6C8', text_secondary: '#A89060', text_muted: '#5A4A30', white: '#FAF6EE'},
  {key: 'white',     label: 'Белый',        swatch: '#FFFFFF',
    bg: '#FFFFFF', card: '#F7F7F5', border: '#E5E3DD',
    text_primary: '#1A1A1A', text_secondary: '#6B6B63', text_muted: '#A8A69C', white: '#0A0A0A'},
  {key: 'pistachio', label: 'Фисташковый',  swatch: '#E8EDDC',
    bg: '#E8EDDC', card: '#DEE6CE', border: '#C9D4B4',
    text_primary: '#2B3620', text_secondary: '#5C6B47', text_muted: '#8A9678', white: '#1A2214'},
  {key: 'cream',     label: 'Кремовый',     swatch: '#FAF6EE',
    bg: '#FAF6EE', card: '#F0EADB', border: '#E0D6C0',
    text_primary: '#2A2318', text_secondary: '#6B5D45', text_muted: '#A6957A', white: '#1C1710'},
  {key: 'midnight',  label: 'Тёмно-синий',  swatch: '#0B1220',
    bg: '#0B1220', card: '#131C2E', border: '#1E2A40',
    text_primary: '#E8EDF5', text_secondary: '#93A3BD', text_muted: '#4C5A73', white: '#F5F8FC'},
  {key: 'sand',      label: 'Песочный',     swatch: '#EDE3D0',
    bg: '#EDE3D0', card: '#E3D7BE', border: '#D0C09E',
    text_primary: '#2E2416', text_secondary: '#6B5738', text_muted: '#9C8968', white: '#1C160D'},
  {key: 'mocha',        label: 'Мокко',              swatch: '#3D2F28',
    bg: '#3D2F28', card: '#4A3B32', border: '#5C4A3E',
    text_primary: '#F0E4D8', text_secondary: '#C4A688', text_muted: '#8A6F5C', white: '#FCF6EF'},
  {key: 'emerald_night', label: 'Изумрудная ночь',   swatch: '#0D2818',
    bg: '#0D2818', card: '#153322', border: '#1F4530',
    text_primary: '#E8F5EC', text_secondary: '#8FBFA0', text_muted: '#4A6B58', white: '#F5FAF7'},
  {key: 'terracotta',    label: 'Терракотовый',      swatch: '#5C3226',
    bg: '#5C3226', card: '#6B3D2F', border: '#7D4A3A',
    text_primary: '#F5E6DC', text_secondary: '#D4A88F', text_muted: '#9C7360', white: '#FCF3EC'},
  {key: 'indigo',        label: 'Индиго',            swatch: '#1A1440',
    bg: '#1A1440', card: '#241D52', border: '#332968',
    text_primary: '#EDEAFA', text_secondary: '#A79FD8', text_muted: '#5C5490', white: '#F7F5FC'},
];

function renderColorPicker() {
  const el = document.getElementById('colorPicker');
  el.innerHTML = COLOR_THEMES.map(c => `
    <div onclick="selectColorTheme('${c.key}')" id="colorOpt-${c.key}" style="cursor:pointer;padding:12px 6px;text-align:center;border:1px solid ${c.key === selectedColorTheme ? '#fff' : 'var(--black-border)'};background:var(--black-card);transition:border-color .2s">
      <div style="width:100%;height:28px;border-radius:2px;margin-bottom:6px;background:${c.gradient}"></div>
      <div style="font-size:9px;color:var(--text-muted);letter-spacing:.05em">${c.label}</div>
    </div>
  `).join('');
}

function renderBackgroundPicker() {
  const el = document.getElementById('backgroundPicker');
  el.innerHTML = BACKGROUND_THEMES.map(b => `
    <div onclick="selectBackgroundTheme('${b.key}')" id="bgOpt-${b.key}" style="cursor:pointer;padding:12px 6px;text-align:center;border:1px solid ${b.key === selectedBackgroundTheme ? 'var(--gold)' : 'var(--black-border)'};background:var(--black-card);transition:border-color .2s">
      <div style="width:100%;height:28px;border-radius:2px;margin-bottom:6px;background:${b.swatch};border:1px solid rgba(128,128,128,.25)"></div>
      <div style="font-size:9px;color:var(--text-muted);letter-spacing:.05em">${b.label}</div>
    </div>
  `).join('');
}

function selectBackgroundTheme(key) {
  selectedBackgroundTheme = key;
  renderBackgroundPicker();
  renderDesignPreview();
}

function selectColorTheme(key) {
  selectedColorTheme = key;
  renderColorPicker();
  renderDesignPreview();

}

const NAV_LABEL_KEYS = [
  {key: 'gallery',     def: 'Галерея'},
  {key: 'amenities',   def: 'Удобства'},
  {key: 'location',    def: 'Расположение'},
  {key: 'prices',      def: 'Цены'},
  {key: 'house_rules', def: 'Правила проживания'},
  {key: 'places',      def: 'Куда сходить?'},
  {key: 'contacts',    def: 'Контакты'},
  {key: 'booking',     def: 'Забронировать'},
];
let navLabels = {};
let amenitiesData = [];

function renderNavLabelsEditor() {
  const el = document.getElementById('navLabelsEditor');
  el.innerHTML = NAV_LABEL_KEYS.map(item => {
    const stored = navLabels[item.key];
    const val = (stored !== undefined ? stored : item.def).replace(/"/g,'&quot;');
    return `
    <div class="info-field">
      <div class="info-label" style="font-size:9px">${item.def}</div>
      <input type="text" class="info-input" id="navLabel-input-${item.key}" value="${val}" placeholder="${item.def}" style="width:100%">
    </div>
  `;
  }).join('');
}

function renderAmenitiesEditor() {
  const el = document.getElementById('amenitiesEditor');
  if(!el) return;
  el.innerHTML = amenitiesData.map((a, i) => `
    <div style="display:flex;gap:10px;align-items:center">
      <input type="text" class="info-input amenity-icon-input" data-idx="${i}"
             value="${(a.icon || '').replace(/"/g,'&quot;')}" placeholder="📶"
             style="width:56px;text-align:center;font-size:18px;flex-shrink:0">
      <input type="text" class="info-input amenity-name-input" data-idx="${i}"
             value="${(a.name || '').replace(/"/g,'&quot;')}" placeholder="Например: Кондиционер"
             style="flex:1">
    </div>
  `).join('');
}

async function saveAmenities() {
  const icons = document.querySelectorAll('.amenity-icon-input');
  const names = document.querySelectorAll('.amenity-name-input');
  const collected = [];
  for(let i = 0; i < 12; i++) {
    collected.push({
      icon: icons[i] ? icons[i].value.trim() : '',
      name: names[i] ? names[i].value.trim() : '',
    });
  }
  amenitiesData = collected;
  try {
    const current = await apiGet('/api/site-settings');
    await apiPost('/api/site-settings', {...current, amenities: collected});
    showToast('Удобства сохранены', 'gold');
  } catch(e) { showToast('Ошибка сохранения', 'err'); }
}

// РАСПОЛОЖЕНИЕ — ближайшие места (значок, название, расстояние, описание)
let locationPointsData = [];

function renderLocationPointsEditor() {
  const el = document.getElementById('locationPointsEditor');
  if(!el) return;
  el.innerHTML = locationPointsData.map((p, i) => `
    <div style="display:flex;gap:10px;align-items:flex-start;padding:12px;background:var(--black-card);border:1px solid var(--black-border)">
      <input type="text" class="info-input locpoint-icon-input" data-idx="${i}"
             value="${(p.icon || '').replace(/"/g,'&quot;')}" placeholder="📍"
             style="width:56px;text-align:center;font-size:18px;flex-shrink:0">
      <div style="flex:1;display:flex;flex-direction:column;gap:8px">
        <input type="text" class="info-input locpoint-name-input" data-idx="${i}"
               value="${(p.name || '').replace(/"/g,'&quot;')}" placeholder="Название места">
        <input type="text" class="info-input locpoint-dist-input" data-idx="${i}"
               value="${(p.distance || '').replace(/"/g,'&quot;')}" placeholder="Например: 700 м · 8 мин пешком">
        <input type="text" class="info-input locpoint-desc-input" data-idx="${i}"
               value="${(p.description || '').replace(/"/g,'&quot;')}" placeholder="Короткое описание">
      </div>
    </div>
  `).join('');
}

async function saveLocationPoints() {
  const icons = document.querySelectorAll('.locpoint-icon-input');
  const names = document.querySelectorAll('.locpoint-name-input');
  const dists = document.querySelectorAll('.locpoint-dist-input');
  const descs = document.querySelectorAll('.locpoint-desc-input');
  const collected = [];
  for(let i = 0; i < 5; i++) {
    collected.push({
      icon:        icons[i] ? icons[i].value.trim() : '',
      name:        names[i] ? names[i].value.trim() : '',
      distance:    dists[i] ? dists[i].value.trim() : '',
      description: descs[i] ? descs[i].value.trim() : '',
    });
  }
  locationPointsData = collected;
  try {
    const current = await apiGet('/api/site-settings');
    await apiPost('/api/site-settings', {...current, location_points: collected});
    showToast('Расположение сохранено', 'gold');
  } catch(e) { showToast('Ошибка сохранения', 'err'); }
}

function renderFontPicker() {
  const el = document.getElementById('fontPicker');
  el.innerHTML = FONT_OPTIONS.map(f => `
    <div onclick="selectFont('${f.key}')" id="fontOpt-${f.key}" style="cursor:pointer;padding:14px 8px;text-align:center;border:1px solid ${f.key === selectedFont ? 'var(--gold)' : 'var(--black-border)'};background:var(--black-card);transition:border-color .2s">
      <div style="font-family:${f.family};font-weight:${selectedBold ? 700 : f.weight};font-size:20px;letter-spacing:.03em;background:linear-gradient(180deg,#FFD060 0%,#D4920A 28%,#8B5E00 50%,#D4920A 72%,#FFD060 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:4px">Городская Пауза</div>
      <div style="font-size:9px;color:var(--text-muted);letter-spacing:.05em">${f.label}</div>
    </div>
  `).join('');
}

function renderBoldToggle() {
  const el = document.getElementById('boldToggle');
  const opts = [{v:false,label:'Обычный'},{v:true,label:'Жирный'}];
  el.innerHTML = opts.map(o => `
    <button type="button" onclick="selectBold(${o.v})" class="btn ${selectedBold===o.v ? 'btn-primary' : 'btn-ghost'} btn-sm">${o.label}</button>
  `).join('');
}

function renderScalePicker() {
  const el = document.getElementById('scalePicker');
  el.innerHTML = SCALE_OPTIONS.map(s => `
    <button type="button" onclick="selectScale(${s})" class="btn ${selectedScale===s ? 'btn-primary' : 'btn-ghost'} btn-sm">${s}x</button>
  `).join('');
}

function renderNavScalePicker() {
  const el = document.getElementById('navScalePicker');
  el.innerHTML = NAV_SCALE_OPTIONS.map(s => `
    <button type="button" onclick="selectNavScale(${s})" class="btn ${selectedNavScale===s ? 'btn-primary' : 'btn-ghost'} btn-sm">${s}x</button>
  `).join('');
}

function renderHeroFontPicker() {
  const el = document.getElementById('heroFontPicker');
  el.innerHTML = HERO_FONT_OPTIONS.map(f => `
    <div onclick="selectHeroFont('${f.key}')" id="heroFontOpt-${f.key}" style="cursor:pointer;padding:14px 8px;text-align:center;border:1px solid ${f.key === selectedHeroFont ? 'var(--gold)' : 'var(--black-border)'};background:var(--black-card);transition:border-color .2s">
      <div style="font-family:${f.family};font-weight:${selectedHeroBold ? 700 : f.weight};font-size:20px;letter-spacing:.03em;background:linear-gradient(180deg,#FFD060 0%,#D4920A 28%,#8B5E00 50%,#D4920A 72%,#FFD060 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:4px">Городская Пауза</div>
      <div style="font-size:9px;color:var(--text-muted);letter-spacing:.05em">${f.label}</div>
    </div>
  `).join('');
}

function selectHeroFont(key) {
  selectedHeroFont = key;
  renderHeroFontPicker();
  renderDesignPreview();
}

function renderHeroBoldToggle() {
  const el = document.getElementById('heroBoldToggle');
  const opts = [{v:false,label:'Обычный'},{v:true,label:'Жирный'}];
  el.innerHTML = opts.map(o => `
    <button type="button" onclick="selectHeroBold(${o.v})" class="btn ${selectedHeroBold===o.v ? 'btn-primary' : 'btn-ghost'} btn-sm">${o.label}</button>
  `).join('');
}

function selectHeroBold(v) {
  selectedHeroBold = v;
  renderHeroBoldToggle();
  renderHeroFontPicker();
  renderDesignPreview();
}

function renderHeroTitleScalePicker() {
  const el = document.getElementById('heroTitleScalePicker');
  el.innerHTML = HERO_SCALE_OPTIONS.map(s => `
    <button type="button" onclick="selectHeroTitleScale(${s})" class="btn ${selectedHeroTitleScale===s ? 'btn-primary' : 'btn-ghost'} btn-sm">${s}x</button>
  `).join('');
}

function selectHeroTitleScale(v) {
  selectedHeroTitleScale = v;
  renderHeroTitleScalePicker();
  renderDesignPreview();
}

function renderHeroSubtitleScalePicker() {
  const el = document.getElementById('heroSubtitleScalePicker');
  el.innerHTML = HERO_SCALE_OPTIONS.map(s => `
    <button type="button" onclick="selectHeroSubtitleScale(${s})" class="btn ${selectedHeroSubtitleScale===s ? 'btn-primary' : 'btn-ghost'} btn-sm">${s}x</button>
  `).join('');
}

function selectHeroSubtitleScale(v) {
  selectedHeroSubtitleScale = v;
  renderHeroSubtitleScalePicker();
  renderDesignPreview();
}

function renderHeroPositionPicker() {
  const el = document.getElementById('heroPositionPicker');
  el.innerHTML = HERO_POSITION_OPTIONS.map(o => `
    <button type="button" onclick="selectHeroPosition('${o.v}')" class="btn ${selectedHeroPosition===o.v ? 'btn-primary' : 'btn-ghost'} btn-sm">${o.label}</button>
  `).join('');
}

function selectHeroPosition(v) {
  selectedHeroPosition = v;
  renderHeroPositionPicker();
  renderDesignPreview();
}

const HERO_CAROUSEL_SECONDS_OPTIONS = [3, 4, 5, 6, 8, 10, 12, 15];

function renderHeroCarouselSpeedPicker() {
  const el = document.getElementById('heroCarouselSpeedPicker');
  el.innerHTML = HERO_CAROUSEL_SECONDS_OPTIONS.map(sec => `
    <button type="button" onclick="selectHeroCarouselSeconds(${sec})" class="btn ${selectedHeroCarouselSeconds===sec ? 'btn-primary' : 'btn-ghost'} btn-sm">${sec} сек</button>
  `).join('');
}

function selectHeroCarouselSeconds(sec) {
  selectedHeroCarouselSeconds = sec;
  renderHeroCarouselSpeedPicker();
}

function selectFont(key) {
  selectedFont = key;
  renderFontPicker();
  renderDesignPreview();
}

function selectBold(v) {
  selectedBold = v;
  renderBoldToggle();
  renderFontPicker();
  renderDesignPreview();
}

function selectScale(v) {
  selectedScale = v;
  renderScalePicker();
  renderDesignPreview();
}

function selectNavScale(v) {
  selectedNavScale = v;
  renderNavScalePicker();
}

function renderDesignPreview() {
  const logoEl     = document.getElementById('dpLogo');
  const btnEl      = document.getElementById('dpBookBtn');
  const heroTitleEl= document.getElementById('dpHeroTitle');
  const heroSubEl  = document.getElementById('dpHeroSub');
  const heroBoxEl  = document.getElementById('dpHero');
  if(!logoEl) return; // превью ещё не отрендерилось на странице

  const fontObj     = FONT_OPTIONS.find(f => f.key === selectedFont) || FONT_OPTIONS[0];
  const heroFontObj = HERO_FONT_OPTIONS.find(f => f.key === selectedHeroFont) || HERO_FONT_OPTIONS[0];
  const theme       = COLOR_THEMES.find(c => c.key === selectedColorTheme) || COLOR_THEMES[0];
  const bgTheme     = BACKGROUND_THEMES.find(b => b.key === selectedBackgroundTheme) || BACKGROUND_THEMES[0];
  if (heroBoxEl) heroBoxEl.style.background = bgTheme.card;

  const siteNameEl  = document.getElementById('settingsSiteName');
  const heroTitleIn = document.getElementById('settingsHeroTitle');
  const heroSubIn   = document.getElementById('settingsHeroSubtitle');
  const siteName  = (siteNameEl && siteNameEl.value.trim()) || 'Городская Пауза';
  const heroTitle = (heroTitleIn && heroTitleIn.value.trim()) || 'Искусство комфортного проживания';
  const heroSub   = (heroSubIn && heroSubIn.value.trim()) || 'Апартаменты премиум-класса · Посуточная аренда';

  // Логотип
  logoEl.textContent = siteName;
  logoEl.style.fontFamily = fontObj.family;
  logoEl.style.fontWeight = selectedBold ? 700 : fontObj.weight;
  logoEl.style.fontSize = (18 + Math.min(selectedScale, 2) * 3) + 'px';
  logoEl.style.background = theme.gradient;
  logoEl.style.webkitBackgroundClip = 'text';
  logoEl.style.webkitTextFillColor = 'transparent';
  logoEl.style.backgroundClip = 'text';

  // Кнопка «Забронировать»
  btnEl.style.borderColor = theme.solid;
  btnEl.style.background = theme.gradient;
  btnEl.style.webkitBackgroundClip = 'text';
  btnEl.style.webkitTextFillColor = 'transparent';
  btnEl.style.backgroundClip = 'text';
  btnEl.style.fontFamily = fontObj.family;

  // Hero-заголовок и подзаголовок
  heroTitleEl.textContent = heroTitle;
  heroTitleEl.style.fontFamily = heroFontObj.family;
  heroTitleEl.style.fontWeight = selectedHeroBold ? 700 : heroFontObj.weight;
  heroTitleEl.style.fontSize = (18 + selectedHeroTitleScale * 8) + 'px';
  heroTitleEl.style.background = theme.gradient;
  heroTitleEl.style.webkitBackgroundClip = 'text';
  heroTitleEl.style.webkitTextFillColor = 'transparent';
  heroTitleEl.style.backgroundClip = 'text';

  heroSubEl.textContent = heroSub;
  heroSubEl.style.fontFamily = heroFontObj.family;
  heroSubEl.style.fontWeight = selectedHeroBold ? 700 : heroFontObj.weight;
  heroSubEl.style.fontSize = (8 + selectedHeroSubtitleScale * 4) + 'px';
  heroSubEl.style.color = theme.solid;

  // Расположение hero-текста
  const align = selectedHeroPosition === 'left' ? 'flex-start' : selectedHeroPosition === 'right' ? 'flex-end' : 'center';
  const textAlign = selectedHeroPosition === 'left' ? 'left' : selectedHeroPosition === 'right' ? 'right' : 'center';
  heroBoxEl.style.alignItems = align;
  heroBoxEl.style.textAlign = textAlign;
}

async function loadSiteSettings() {
  try {
    const s = await apiGet('/api/site-settings');
    document.getElementById('settingsMapUrl').value       = s.map_url        || '';
    document.getElementById('settingsMapService').value   = s.map_service    || 'yandex';
    document.getElementById('settingsSiteName').value     = s.site_name      || 'Городская Пауза';
    document.getElementById('settingsHeroTitle').value    = s.hero_title     || '';
    document.getElementById('settingsHeroSubtitle').value = s.hero_subtitle  || '';
    document.getElementById('settingsHeroEyebrow').value  = s.hero_eyebrow   ?? 'Апартаменты в городе';
    document.getElementById('navExtraLabel').value        = s.nav_extra_label || '';
    document.getElementById('navExtraUrl').value          = s.nav_extra_url   || '';
    selectedFont = s.logo_font || 'im_fell';
    selectedBold = !!s.logo_bold;
    selectedScale = s.logo_scale || 1.0;
    selectedNavScale = s.nav_scale || 1.0;
    selectedColorTheme = s.color_theme || 'gold';
    selectedBackgroundTheme = s.background_theme || 'black';
    navLabels = s.nav_labels || {};
    amenitiesData = (s.amenities && s.amenities.length ? s.amenities : []).slice(0, 12);
    while(amenitiesData.length < 12) amenitiesData.push({icon:'', name:''});
    renderAmenitiesEditor();
    locationPointsData = (s.location_points && s.location_points.length ? s.location_points : []).slice(0, 5);
    while(locationPointsData.length < 5) locationPointsData.push({icon:'', name:'', distance:'', description:''});
    renderLocationPointsEditor();
    selectedHeroFont = s.hero_font || 'cormorant';
    selectedHeroBold = !!s.hero_bold;
    selectedHeroTitleScale = s.hero_title_scale || 1.0;
    selectedHeroSubtitleScale = s.hero_subtitle_scale || 1.0;
    selectedHeroPosition = s.hero_position || 'center';
    selectedHeroCarouselSeconds = s.hero_carousel_seconds || 6;
    selectedHeroCarouselEnabled = s.hero_carousel_enabled !== false;
    document.getElementById('heroCarouselEnabledCheck').checked = selectedHeroCarouselEnabled;
    selectedHeaderOpacityLevel = s.header_opacity_level || 3;
    selectedHeaderBlurLevel = s.header_blur_level || 2;
    document.getElementById('headerOpacitySlider').value = selectedHeaderOpacityLevel;
    document.getElementById('headerOpacityValue').textContent = selectedHeaderOpacityLevel;
    document.getElementById('headerBlurSlider').value = selectedHeaderBlurLevel;
    document.getElementById('headerBlurValue').textContent = selectedHeaderBlurLevel;
    renderFontPicker();
    renderBoldToggle();
    renderScalePicker();
    renderNavScalePicker();
    renderColorPicker();
    renderBackgroundPicker();
    renderNavLabelsEditor();
    renderHeroFontPicker();
    renderHeroBoldToggle();
    renderHeroTitleScalePicker();
    renderHeroSubtitleScalePicker();
    renderHeroPositionPicker();
    renderHeroCarouselSpeedPicker();
    renderDesignPreview();
    if(s.hero_photo) {
      const img = document.getElementById('heroPhotoImg');
      img.src = `${API_BASE}/data/photos/${s.hero_photo}`;
      img.style.display = 'block';
      document.getElementById('heroPhotoEmpty').style.display = 'none';
      document.getElementById('heroPhotoName').textContent = s.hero_photo;
    }
    if(s.hero_photo_mobile) {
      const img = document.getElementById('heroPhotoMobileImg');
      img.src = `${API_BASE}/data/photos/${s.hero_photo_mobile}`;
      img.style.display = 'block';
      document.getElementById('heroPhotoMobileEmpty').style.display = 'none';
      document.getElementById('heroPhotoMobileName').textContent = s.hero_photo_mobile;
    }
    if(s.map_photo) {
      const img = document.getElementById('mapPhotoImg');
      img.src = `${API_BASE}/data/photos/${s.map_photo}`;
      img.style.display = 'block';
      document.getElementById('mapPhotoEmpty').style.display = 'none';
      document.getElementById('mapPhotoName').textContent = s.map_photo;
    }
  } catch(e) {}
}

const PHOTO_UPLOAD_CONFIG = {
  hero:        { fileInputId: 'heroPhotoFile',       label: 'Обложка сайта',              settingsKey: 'hero_photo',        imgId: 'heroPhotoImg',       emptyId: 'heroPhotoEmpty',       nameId: 'heroPhotoName' },
  hero_mobile: { fileInputId: 'heroPhotoMobileFile', label: 'Обложка сайта (мобильная)',   settingsKey: 'hero_photo_mobile', imgId: 'heroPhotoMobileImg', emptyId: 'heroPhotoMobileEmpty', nameId: 'heroPhotoMobileName' },
  map:         { fileInputId: 'mapPhotoFile',        label: 'Фото карты',                 settingsKey: 'map_photo',         imgId: 'mapPhotoImg',        emptyId: 'mapPhotoEmpty',        nameId: 'mapPhotoName' },
};

async function uploadSettingsPhoto(type) {
  const cfg = PHOTO_UPLOAD_CONFIG[type];
  if (!cfg) return;
  const fileInput = document.getElementById(cfg.fileInputId);
  const file = fileInput.files[0];
  if(!file) return;
  if(file.size > 10 * 1024 * 1024) { showToast('Файл слишком большой (макс. 10 МБ)', 'err'); return; }
  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', cfg.label);
  formData.append('purpose', 'site');
  try {
    showToast('Загружаю фото...', 'gold');
    const resp = await fetch(`${API_BASE}/api/photos/upload`, {
      method: 'POST',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {},
      body: formData
    });
    if(!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    const filename = data.filename;
    // Сохраняем в настройки
    const current = await apiGet('/api/site-settings');
    const payload = {...current, [cfg.settingsKey]: filename};
    await apiPost('/api/site-settings', payload);
    // Обновляем превью
    const img = document.getElementById(cfg.imgId);
    img.src = `${API_BASE}/data/photos/${filename}`;
    img.style.display = 'block';
    document.getElementById(cfg.emptyId).style.display = 'none';
    document.getElementById(cfg.nameId).textContent = filename;
    showToast('Фото загружено и сохранено', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

async function saveSiteSettings() {
  const payload = {
    map_url:     document.getElementById('settingsMapUrl').value.trim(),
    map_service: document.getElementById('settingsMapService').value,
  };
  try {
    // Сохраняем только URL и сервис — фото уже сохраняются при загрузке
    const current = await apiGet('/api/site-settings');
    await apiPost('/api/site-settings', {...current, ...payload});
    showToast('Настройки сохранены', 'gold');
  } catch(e) { showToast('Ошибка сохранения', 'err'); }
}

async function saveDesignSettings() {
  const collectedNavLabels = {};
  NAV_LABEL_KEYS.forEach(item => {
    const el = document.getElementById(`navLabel-input-${item.key}`);
    collectedNavLabels[item.key] = el ? el.value.trim() : item.def;
  });
  const payload = {
    site_name:     document.getElementById('settingsSiteName').value.trim()     || 'Городская Пауза',
    hero_title:    document.getElementById('settingsHeroTitle').value.trim(),
    hero_subtitle: document.getElementById('settingsHeroSubtitle').value.trim(),
    hero_eyebrow:  document.getElementById('settingsHeroEyebrow').value.trim(),
    nav_extra_label: document.getElementById('navExtraLabel').value.trim(),
    nav_extra_url:   document.getElementById('navExtraUrl').value.trim(),
    logo_font:     selectedFont,
    logo_bold:     selectedBold,
    logo_scale:    selectedScale,
    nav_scale:     selectedNavScale,
    color_theme:   selectedColorTheme,
    background_theme: selectedBackgroundTheme,
    nav_labels:    collectedNavLabels,
    hero_font:     selectedHeroFont,
    hero_bold:     selectedHeroBold,
    hero_title_scale:    selectedHeroTitleScale,
    hero_subtitle_scale: selectedHeroSubtitleScale,
    hero_position: selectedHeroPosition,
    hero_carousel_seconds: selectedHeroCarouselSeconds,
    hero_carousel_enabled: selectedHeroCarouselEnabled,
    header_opacity_level: selectedHeaderOpacityLevel,
    header_blur_level: selectedHeaderBlurLevel,
  };
  try {
    const current = await apiGet('/api/site-settings');
    await apiPost('/api/site-settings', {...current, ...payload});
    showToast('Оформление сохранено', 'gold');
  } catch(e) { showToast('Ошибка сохранения', 'err'); }
}

async function loadCheckinMemo() {
  try {
    const r = await fetch(`${API_BASE}/api/checkin-memo`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    document.getElementById('checkinEditor').value = await r.text();
  } catch(e) {
    document.getElementById('checkinEditor').value = 'Ошибка загрузки';
  }
}

async function saveCheckinMemo() {
  const text = document.getElementById('checkinEditor').value;
  try {
    await apiPost('/api/checkin-memo', { text });
    showToast('Памятка сохранена', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения', 'err');
  }
}

// CHECKOUT CHECKLIST
async function loadCheckoutChecklist() {
  try {
    const r = await fetch(`${API_BASE}/api/checkout-checklist`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    document.getElementById('checkoutEditor').value = await r.text();
  } catch(e) {
    document.getElementById('checkoutEditor').value = 'Ошибка загрузки';
  }
}

async function saveCheckoutChecklist() {
  const text = document.getElementById('checkoutEditor').value;
  try {
    await apiPost('/api/checkout-checklist', { text });
    showToast('Чек-лист сохранён', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения', 'err');
  }
}

document.addEventListener('keydown', e => {
  if(e.key==='Escape') { closeModal(); }
  if(e.key==='Enter' && document.getElementById('loginScreen').style.display!=='none') { doLogin(); }
});

// Check if login needed
if(!ADMIN_TOKEN) {
  document.getElementById('loginPwd').focus();
} else {
  initAdmin();
}
