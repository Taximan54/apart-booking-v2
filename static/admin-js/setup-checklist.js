// Карточка «Что осталось заполнить» на дашборде. Показывает только незаполненное; когда всё заполнено, скрыта.
(function () {
  var TOKEN_KEY = 'gorodskaya-pauza_token';
  var HIDE_KEY = 'cpSetupChecklistHidden';
  var lastLoad = 0;
  var lastProperty = null;

  function propertyId() {
    try { return typeof ADMIN_PROPERTY_ID !== 'undefined' ? String(ADMIN_PROPERTY_ID) : '1'; } catch (e) { return '1'; }
  }

  async function unwrap(r) {
    if (r && typeof r.json === 'function') {
      if (r.ok === false) throw new Error('Ошибка ' + r.status);
      return await r.json();
    }
    return r;
  }

  function readHidden() {
    try { return JSON.parse(localStorage.getItem(HIDE_KEY) || '{}') || {}; } catch (e) { return {}; }
  }
  function writeHidden(obj) {
    try { localStorage.setItem(HIDE_KEY, JSON.stringify(obj)); } catch (e) {}
  }

  function cardEl() {
    var card = document.getElementById('setupChecklistCard');
    if (card) return card;
    var panel = document.getElementById('panel-dashboard');
    if (!panel) return null;
    card = document.createElement('div');
    card.className = 'card';
    card.id = 'setupChecklistCard';
    card.style.cssText = 'margin-bottom:24px;display:none';
    var stats = document.getElementById('statsRow');
    if (stats && stats.parentNode === panel) panel.insertBefore(card, stats.nextSibling);
    else panel.insertBefore(card, panel.firstChild);
    return card;
  }

  function goTo(item) {
    var el = Array.prototype.find.call(document.querySelectorAll('.sb-item'), function (a) {
      return (a.getAttribute('onclick') || '').indexOf("'" + item.panel + "'") > -1;
    });
    if (typeof showPanel === 'function') showPanel(item.panel, el || null);
    if (item.tab && typeof showSiteTab === 'function') showSiteTab(item.tab);
  }

  function render(data) {
    var card = cardEl();
    if (!card) return;
    var undone = (data.items || []).filter(function (i) { return !i.done; });
    var signature = undone.map(function (i) { return i.key; }).join(',');
    var hidden = readHidden();
    if (!undone.length || hidden[propertyId()] === signature) {
      card.style.display = 'none';
      return;
    }
    card.innerHTML = '';
    var head = document.createElement('div');
    head.className = 'card-header';
    var title = document.createElement('span');
    title.className = 'card-title';
    title.textContent = 'Что осталось заполнить (' + data.done + ' из ' + data.total + ' готово)';
    var hideBtn = document.createElement('button');
    hideBtn.className = 'btn btn-ghost btn-sm';
    hideBtn.textContent = 'Скрыть';
    hideBtn.onclick = function () {
      var h = readHidden();
      h[propertyId()] = signature;
      writeHidden(h);
      card.style.display = 'none';
    };
    head.appendChild(title);
    head.appendChild(hideBtn);
    card.appendChild(head);

    var body = document.createElement('div');
    body.className = 'card-body';
    undone.forEach(function (item) {
      var row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:8px 0;border-bottom:1px solid var(--border,rgba(255,255,255,.08))';
      var text = document.createElement('div');
      text.style.cssText = 'flex:1;min-width:220px;font-size:13px';
      text.textContent = '○ ' + item.title;
      if (item.hint) {
        var hint = document.createElement('div');
        hint.style.cssText = 'font-size:11px;color:var(--text-muted);margin-top:3px;line-height:1.5';
        hint.textContent = item.hint;
        text.appendChild(hint);
      }
      row.appendChild(text);
      if (item.panel) {
        var go = document.createElement('button');
        go.className = 'btn btn-ghost btn-sm';
        go.textContent = item.server ? 'Открыть раздел →' : 'Заполнить →';
        go.onclick = function () { goTo(item); };
        row.appendChild(go);
      }
      body.appendChild(row);
    });
    card.appendChild(body);
    card.style.display = '';
  }

  async function load() {
    lastLoad = Date.now();
    lastProperty = propertyId();
    try {
      var data = await unwrap(await apiGet('/api/admin/setup-checklist'));
      if (data && data.items) render(data);
    } catch (e) {
      var card = document.getElementById('setupChecklistCard');
      if (card) card.style.display = 'none';
    }
  }

  // Загружаем, когда дашборд открыт и админ вошёл; обновляем не чаще раза в минуту
  function check() {
    try {
      if (!localStorage.getItem(TOKEN_KEY)) return;
    } catch (e) { return; }
    var panel = document.getElementById('panel-dashboard');
    if (!panel || !panel.classList.contains('active')) return;
    if (!lastLoad || Date.now() - lastLoad > 60000 || lastProperty !== propertyId()) load();
  }

  function start() { setInterval(check, 2000); check(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
