/* chat-widget.js: чат-помощник на странице квартиры: популярные вопросы и ответы (без ИИ).
   Вопросы гостей наш сервер не принимает: «Другой вопрос» открывает WhatsApp, Telegram или почту гостя.
   Включается в админке (раздел «Чат-помощник»). Если выключен или нет ответов, на странице ничего не появляется. */
(function () {
  'use strict';
  if (window.__cpxChat) return;
  window.__cpxChat = true;

  var m = location.pathname.match(/^\/o\/([a-z0-9\-]+)/i);
  var slug = (m && m[1]) || new URLSearchParams(location.search).get('property') || '';
  var qs = slug ? '?property=' + encodeURIComponent(slug) : '';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function copyText(t) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(t).catch(function () { fallbackCopy(t); });
        return true;
      }
    } catch (e) { /* ниже запасной способ */ }
    return fallbackCopy(t);
  }
  function fallbackCopy(t) {
    var ta = document.createElement('textarea');
    ta.value = t; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    ta.remove();
    return ok;
  }

  // Способы связи: только те, что заполнены в разделе «Контакты»
  function channels(c) {
    var out = [];
    var wa = String(c.whatsapp || '').replace(/\D/g, '');
    if (wa) out.push({ label: 'WhatsApp', go: function (t) { window.open('https://wa.me/' + wa + '?text=' + encodeURIComponent(t), '_blank', 'noopener'); return ''; } });
    var tg = String(c.telegram || '').trim().replace(/^@/, '');
    if (tg) out.push({ label: 'Telegram', go: function (t) {
      copyText(t);   // в личный чат Telegram текст подставить нельзя: копируем вопрос, гость вставит его сам
      window.open('https://t.me/' + encodeURIComponent(tg), '_blank', 'noopener');
      return 'Вопрос скопирован: вставьте его в чат Telegram.';
    } });
    var em = String(c.email || '').trim();
    if (em) out.push({ label: 'Почта', go: function (t) {
      location.href = 'mailto:' + em + '?subject=' + encodeURIComponent('Вопрос по апартаментам') + '&body=' + encodeURIComponent(t);
      return '';
    } });
    return out;
  }

  var CSS = '' +
    '.cpx-fab{position:fixed;right:24px;bottom:24px;z-index:900;width:58px;height:58px;border-radius:50%;border:1px solid var(--gold,#D4A017);background:var(--black-card,#141414);color:var(--gold,#D4A017);cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;padding:0;box-shadow:0 8px 24px rgba(0,0,0,.35);transition:transform .2s,box-shadow .2s}' +
    '.cpx-fab:hover{transform:translateY(-2px);box-shadow:0 12px 28px rgba(0,0,0,.45)}' +
    '.cpx-fab svg{width:24px;height:24px}' +
    '.cpx-lbl{font-size:11px;line-height:1;letter-spacing:.08em;text-transform:uppercase;font-weight:600}' +
    '@media(min-width:601px){.cpx-fab{width:112px;height:112px;gap:4px;border-width:2px}.cpx-fab svg{width:48px;height:48px}.cpx-lbl{font-size:20px}.cpx-panel{bottom:150px;height:min(560px,calc(100vh - 190px))}}' +
    '.cpx-panel{position:fixed;right:24px;bottom:94px;z-index:900;width:370px;max-width:calc(100vw - 24px);height:min(560px,calc(100vh - 130px));display:flex;flex-direction:column;border:1px solid rgba(201,168,76,.35);border-radius:22px;background:var(--black-card,#141414);color:var(--text-primary,#F5F0E8);box-shadow:0 18px 48px rgba(0,0,0,.5);overflow:hidden;animation:cpxIn .22s ease}' +
    '.cpx-panel[hidden]{display:none}' +
    '@keyframes cpxIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}' +
    '.cpx-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:14px 18px;border-bottom:1px solid rgba(201,168,76,.25)}' +
    '.cpx-title{font-size:15px;letter-spacing:.04em}' +
    '.cpx-close{width:32px;height:32px;border-radius:50%;border:1px solid rgba(201,168,76,.3);background:transparent;color:inherit;font-size:18px;line-height:1;cursor:pointer}' +
    '.cpx-close:hover{border-color:var(--gold,#D4A017)}' +
    '.cpx-menu{display:block;width:100%;padding:10px 18px;border:0;border-bottom:1px solid rgba(201,168,76,.25);background:rgba(201,168,76,.08);color:var(--gold,#D4A017);font:inherit;font-size:13px;letter-spacing:.04em;text-align:left;cursor:pointer}' +
    '.cpx-menu:hover{background:rgba(201,168,76,.16)}' +
    '.cpx-body{flex:1;overflow-y:auto;padding:16px 16px 8px;display:flex;flex-direction:column;gap:10px}' +
    '.cpx-msg{max-width:86%;padding:10px 14px;font-size:14px;line-height:1.55;white-space:pre-wrap;word-wrap:break-word}' +
    '.cpx-bot{align-self:flex-start;background:rgba(255,255,255,.06);border-radius:16px 16px 16px 4px}' +
    '.cpx-user{align-self:flex-end;background:var(--gold,#D4A017);color:var(--black,#0A0A0A);border-radius:16px 16px 4px 16px}' +
    '.cpx-chips{display:flex;flex-wrap:wrap;gap:8px;padding:2px 0 6px}' +
    '.cpx-chip{padding:8px 14px;border-radius:999px;border:1px solid var(--gold,#D4A017);background:transparent;color:inherit;font:inherit;font-size:13px;cursor:pointer;text-align:left;transition:background .15s}' +
    '.cpx-chip:hover{background:rgba(201,168,76,.16)}' +
    '.cpx-chip.cpx-other{border-style:dashed}' +
    '.cpx-form{display:flex;flex-direction:column;gap:10px;padding:2px 0 8px}' +
    '.cpx-form textarea{width:100%;min-height:84px;resize:vertical;padding:10px 12px;border-radius:14px;border:1px solid rgba(201,168,76,.35);background:transparent;color:inherit;font:inherit;font-size:14px;line-height:1.5;box-sizing:border-box}' +
    '.cpx-send{display:flex;flex-wrap:wrap;gap:8px}' +
    '.cpx-send button{flex:1 1 90px;padding:10px 12px;border-radius:999px;border:1px solid var(--gold,#D4A017);background:var(--gold,#D4A017);color:var(--black,#0A0A0A);font:inherit;font-size:13px;font-weight:600;cursor:pointer}' +
    '.cpx-send button:disabled{opacity:.45;cursor:default}' +
    '.cpx-note{font-size:12px;opacity:.75;line-height:1.5}' +
    '@media(max-width:600px){.cpx-fab{right:16px;bottom:16px}.cpx-panel{right:12px;left:12px;width:auto;max-width:none;bottom:84px;height:min(560px,calc(100vh - 110px))}}';

  function build(cfg, contacts) {
    var style = el('style'); style.textContent = CSS; document.head.appendChild(style);

    var fab = el('button', 'cpx-fab');
    fab.type = 'button'; fab.setAttribute('aria-label', 'Открыть чат-помощник');
    fab.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12z"/></svg><span class="cpx-lbl">Чат</span>';
    var panel = el('div', 'cpx-panel'); panel.hidden = true;
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', cfg.title || 'Помощник');
    var head = el('div', 'cpx-head');
    var close = el('button', 'cpx-close', '×'); close.type = 'button'; close.setAttribute('aria-label', 'Закрыть');
    head.append(el('div', 'cpx-title', cfg.title || 'Помощник'), close);
    var menu = el('button', 'cpx-menu', '‹ Частые вопросы'); menu.type = 'button';
    var body = el('div', 'cpx-body');
    panel.append(head, menu, body);
    document.body.append(fab, panel);

    var chans = channels(contacts || {});
    var asked = {};
    var started = false;

    function scroll() { body.scrollTop = body.scrollHeight; }
    function say(text, who) { var d = el('div', 'cpx-msg ' + (who === 'user' ? 'cpx-user' : 'cpx-bot'), text); body.appendChild(d); scroll(); return d; }

    function chips() {
      var box = el('div', 'cpx-chips');
      cfg.items.forEach(function (it) {
        if (asked[it.id]) return;
        var b = el('button', 'cpx-chip', it.question); b.type = 'button';
        b.onclick = function () { box.remove(); asked[it.id] = true; say(it.question, 'user'); say(it.answer, 'bot'); chips(); };
        box.appendChild(b);
      });
      if (chans.length) {
        var o = el('button', 'cpx-chip cpx-other', 'Другой вопрос'); o.type = 'button';
        o.onclick = function () { box.remove(); say('Другой вопрос', 'user'); form(); };
        box.appendChild(o);
      }
      if (box.childNodes.length) { body.appendChild(box); scroll(); }
    }

    // Возврат к списку вопросов (например, после «Другого вопроса»): убираем форму и прежние кнопки, показываем все вопросы заново
    function showMenu() {
      body.querySelectorAll('.cpx-chips, .cpx-form').forEach(function (n) { n.remove(); });
      asked = {};
      chips();
    }
    menu.onclick = showMenu;

    function form() {
      say('Напишите вопрос и выберите, куда отправить: он откроется у вас в мессенджере или почте, и мы ответим по мере возможности.', 'bot');
      var f = el('div', 'cpx-form');
      var ta = el('textarea'); ta.maxLength = 500; ta.placeholder = 'Ваш вопрос';
      var send = el('div', 'cpx-send');
      var note = el('div', 'cpx-note');
      var buttons = chans.map(function (c) {
        var b = el('button', null, c.label); b.type = 'button'; b.disabled = true;
        b.onclick = function () {
          var text = 'Здравствуйте! ' + ta.value.trim() + '\n\n(Вопрос со страницы ' + location.origin + location.pathname + ')';
          note.textContent = c.go(text) || '';
        };
        send.appendChild(b); return b;
      });
      ta.oninput = function () { var empty = !ta.value.trim(); buttons.forEach(function (b) { b.disabled = empty; }); };
      f.append(ta, send, note);
      body.appendChild(f); scroll(); ta.focus();
    }

    function open() {
      panel.hidden = false;
      if (!started) { started = true; say(cfg.greeting, 'bot'); chips(); }
      fab.setAttribute('aria-expanded', 'true');
    }
    function shut() { panel.hidden = true; fab.setAttribute('aria-expanded', 'false'); }
    fab.onclick = function () { if (panel.hidden) open(); else shut(); };
    close.onclick = shut;
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) shut(); });
  }

  function start() {
    fetch('/api/chat-faq' + qs).then(function (r) { return r.json(); }).then(function (cfg) {
      if (!cfg || !cfg.enabled || !cfg.items || !cfg.items.length) return;
      return fetch('/api/contacts' + qs).then(function (r) { return r.json(); }).catch(function () { return {}; })
        .then(function (contacts) { build(cfg, contacts); });
    }).catch(function () { /* чат необязателен: при любой ошибке страница работает как обычно */ });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
