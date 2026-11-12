// admin-js/booking-rules.js: «Минимальный срок бронирования» (Настройки сайта → О квартире). У каждого объекта свой.

async function loadBookingRules() {
  const input = document.getElementById('brMinNights');
  if (!input) return;
  try {
    const r = await apiGet('/api/admin/booking-rules');
    input.value = r.min_nights;
  } catch(e) {
    if (String(e.message) !== '401') showToast('Не удалось загрузить минимальный срок: ' + e.message, 'err');
  }
}

async function saveBookingRules() {
  const n = parseInt(document.getElementById('brMinNights').value, 10);
  if (!(n >= 1 && n <= 30)) { showToast('Укажите число ночей от 1 до 30', 'err'); return; }
  try {
    const r = await apiRequest('POST', '/api/admin/booking-rules', { min_nights: n });
    document.getElementById('brMinNights').value = r.min_nights;
    showToast('Минимальный срок сохранён: ' + r.min_nights, 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

// Подгружается вместе с настройками сайта: при открытии раздела и при смене объекта
(function() {
  if (typeof loadSiteSettings !== 'function') return;
  const original = loadSiteSettings;
  loadSiteSettings = async function() {
    const result = await original.apply(this, arguments);
    loadBookingRules();
    return result;
  };
})();
