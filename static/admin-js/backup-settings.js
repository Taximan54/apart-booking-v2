// Настройки резервных копий (карточка «Настройки копий» в разделе с «Резервным копированием»)
(function () {
  var IDS = {
    daily_keep: 'bkDailyKeep',
    docs_days: 'bkDocsDays',
    docs_keep: 'bkDocsKeep',
    photos_days: 'bkPhotosDays',
    photos_keep: 'bkPhotosKeep'
  };

  function setStatus(text, isError) {
    var el = document.getElementById('bkSettingsStatus');
    if (!el) return;
    el.textContent = text || '';
    el.style.color = isError ? '#e57373' : 'var(--text-muted)';
  }

  // Ответ может прийти уже разобранным или как Response — понимаем оба варианта
  async function unwrap(r) {
    if (r && typeof r.json === 'function') {
      var j = {};
      try { j = await r.json(); } catch (e) {}
      if (r.ok === false) throw new Error((j && j.detail) || ('Ошибка ' + r.status));
      return j;
    }
    return r;
  }

  async function loadBackupSettings() {
    try {
      var d = await unwrap(await apiGet('/api/admin/backup-settings'));
      Object.keys(IDS).forEach(function (k) {
        var el = document.getElementById(IDS[k]);
        if (el && d && d[k] !== undefined) el.value = d[k];
      });
      setStatus('');
    } catch (e) {
      setStatus('Не удалось загрузить настройки копий', true);
    }
  }

  async function saveBackupSettings() {
    var payload = {};
    for (var k in IDS) {
      var raw = (document.getElementById(IDS[k]).value || '').trim();
      if (raw === '' || isNaN(Number(raw))) {
        setStatus('Заполните все поля числами', true);
        return;
      }
      payload[k] = Number(raw);
    }
    setStatus('Сохраняю…');
    try {
      var d = await unwrap(await apiRequest('POST', '/api/admin/backup-settings', payload));
      if (d && d.detail && !d.ok) throw new Error(d.detail);
      setStatus('Сохранено');
      if (typeof showToast === 'function') showToast('Настройки копий сохранены');
    } catch (e) {
      setStatus((e && e.message) || 'Не удалось сохранить', true);
    }
  }
  window.saveBackupSettings = saveBackupSettings;

  // Загружаем значения, когда карточка становится видимой (раздел открыт и админ уже вошёл)
  function watch() {
    var card = document.getElementById('bkSettingsCard');
    if (!card) return;
    var wasVisible = false;
    function check() {
      var visible = card.offsetParent !== null;
      if (visible && !wasVisible) loadBackupSettings();
      wasVisible = visible;
    }
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function () { check(); }).observe(card);
    }
    setInterval(check, 1500);   // запасной вариант, если наблюдатель не сработал
    check();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watch);
  else watch();
})();
