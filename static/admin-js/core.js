// admin-js/core.js: Основа: настройки, вход, состояние, запуск админки и запросы к серверу.
// Часть админки (ранее единого admin.js). Файлы подключаются подряд, в порядке из admin.html.
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

