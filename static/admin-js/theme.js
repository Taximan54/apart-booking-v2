// admin-js/theme.js: цвета админки = тема сайта выбранного объекта (фон и цвет акцентов из «Настройки сайта → Бренд»).
// У каждого объекта своя тема, поэтому при переключении объекта цвет админки меняется, и сразу видно, в каком объекте вы работаете.
// Подключается сразу после core.js (нужны ADMIN_PROPERTY_ID, API_BASE, ADMIN_TOKEN).

async function loadAdminTheme() {
  if (!window.CityPauseTheme) return;
  try {
    // номер объекта к запросу добавляется автоматически (заголовок X-Property-Id из core.js)
    const r = await fetch(`${API_BASE}/api/site-settings`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    if (!r.ok) return;
    const s = await r.json();
    window.CityPauseTheme.apply(s.background_theme, s.color_theme);
    try {
      localStorage.setItem('adminTheme:' + ADMIN_PROPERTY_ID, JSON.stringify({ bg: s.background_theme, color: s.color_theme }));
    } catch(e) {}
  } catch(e) {}
}

// После сохранения «Настроек сайта» цвета админки обновляются сразу, без перезагрузки страницы
(function() {
  const originalFetch = window.fetch.bind(window);
  window.fetch = function(input, init) {
    const result = originalFetch(input, init);
    try {
      const url = typeof input === 'string' ? input : ((input && input.url) || '');
      const method = String((init && init.method) || (input && input.method) || 'GET').toUpperCase();
      if (method !== 'GET' && /\/api\/site-settings(\?|$)/.test(url)) {
        result.then(r => { if (r && r.ok) setTimeout(loadAdminTheme, 300); }).catch(() => {});
      }
    } catch(e) {}
    return result;
  };
})();

loadAdminTheme();
