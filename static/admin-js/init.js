// admin-js/init.js: Чек-лист выезда и запуск (должен загружаться последним).
// Часть админки (ранее единого admin.js). Файлы подключаются подряд, в порядке из admin.html.
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
