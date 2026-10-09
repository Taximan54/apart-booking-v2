// admin-js/ui-contract.js: Интерфейс (меню, панели, уведомления), редактор договора.
// Часть админки (ранее единого admin.js). Файлы подключаются подряд, в порядке из admin.html.
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
  if(id==='settings') { loadTimezone(); loadNotif(); loadLandlord(); }
  if(id==='contract')   { if(typeof loadContractForEditor==='function') loadContractForEditor(); }
  if(id==='contracts')  { if(typeof loadContractsArchive==='function') loadContractsArchive(); }
  if(id==='checkin')     { if(typeof loadCheckinMemo==='function') loadCheckinMemo(); }
  if(id==='checkout')    { if(typeof loadCheckoutChecklist==='function') loadCheckoutChecklist(); }
  if(id==='houserules')  { if(typeof loadHouseRules==='function') loadHouseRules(); }
  if(id==='sitesettings'){ if(typeof loadSiteSettings==='function') loadSiteSettings(); loadDesc(); showSiteTab(currentSiteTab); }
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

