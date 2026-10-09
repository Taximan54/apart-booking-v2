// admin-js/bookings-dashboard.js: Дашборд, таблица броней, карточка брони, календарь, полоса броней, выезды, уведомления, смена пароля.
// Часть админки (ранее единого admin.js). Файлы подключаются подряд, в порядке из admin.html.
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
    if (res.encrypted === false) {
      status.textContent = `Копия создана на сервере (${res.filename}), но НЕ отправлена: не задан пароль для шифрования. Укажите BACKUP_PASSWORD в config.py на сервере.`;
      status.style.color = '#f87171';
    } else {
      status.textContent = `Копия создана и защищена паролем (${res.filename}) — отправка в Telegram и на почту запущена, проверьте через минуту`;
      status.style.color = '#4ade80';
    }
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

