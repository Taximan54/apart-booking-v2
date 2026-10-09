// admin-js/prices-promo.js: Брони (загрузка), алерты дашборда, цены, праздники, промокоды, код замка, часовой пояс, описание, блокировка дат.
// Часть админки (ранее единого admin.js). Файлы подключаются подряд, в порядке из admin.html.
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

