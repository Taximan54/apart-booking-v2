// admin-js/chat-faq.js: раздел «Чат-помощник»: вопросы и ответы для чата на странице квартиры. У каждого объекта свои.

let chatFaqState = null;

function cfEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function loadChatFaq() {
  try {
    chatFaqState = await apiGet('/api/admin/chat-faq');
    renderChatFaq();
  } catch(e) {
    if (String(e.message) !== '401') showToast('Не удалось загрузить чат-помощник: ' + e.message, 'err');
  }
}

function renderChatFaq() {
  if (!chatFaqState) return;
  const s = chatFaqState.settings;
  document.getElementById('cfEnabled').checked = !!s.enabled;
  document.getElementById('cfTitle').value = s.title || '';
  document.getElementById('cfGreeting').value = s.greeting || '';
  renderChatFaqItems();
}

function renderChatFaqItems() {
  const items = chatFaqState.settings.items, defs = chatFaqState.defaults || {}, lim = chatFaqState.limits || {};
  document.getElementById('cfItems').innerHTML = items.map((it, i) => {
    const d = defs[it.id];
    const hint = d ? d.hint : '';
    return `<div style="padding:14px;border:1px solid var(--black-border);background:var(--black-card);margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
        <label style="display:flex;gap:8px;align-items:center;font-size:12px;color:var(--text-secondary);cursor:pointer">
          <input type="checkbox" id="cfVis_${i}" ${it.visible ? 'checked' : ''}> Показывать${it.answer ? '' : ' (без ответа не показывается)'}</label>
        <div style="display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" ${i === 0 ? 'disabled' : ''} onclick="moveChatFaqItem(${i}, -1)" title="Выше">↑</button>
          <button class="btn btn-ghost btn-sm" ${i === items.length - 1 ? 'disabled' : ''} onclick="moveChatFaqItem(${i}, 1)" title="Ниже">↓</button>
          <button class="btn btn-ghost btn-sm" onclick="removeChatFaqItem(${i})" title="Удалить">✕</button>
        </div>
      </div>
      <div class="info-field" style="margin-bottom:10px"><div class="info-label">Вопрос</div>
        <input type="text" class="info-input" id="cfQ_${i}" maxlength="${lim.question || 120}" value="${cfEsc(it.question)}" style="width:100%"></div>
      <div class="info-field"><div class="info-label">Ответ</div>
        <textarea class="info-input" id="cfA_${i}" rows="3" maxlength="${lim.answer || 1000}" style="width:100%;resize:vertical;line-height:1.5" placeholder="${cfEsc(d && !d.example ? hint : 'Ответ гостю')}">${cfEsc(it.answer)}</textarea></div>
      ${d && d.example ? `<div style="margin-top:8px;font-size:11px;color:var(--text-muted);line-height:1.6">Пример: ${cfEsc(hint)}
        <a href="#" style="color:var(--gold);margin-left:6px" onclick="useChatFaqExample(${i});return false">Вставить пример</a></div>` : ''}
    </div>`;
  }).join('') || '<div style="color:var(--text-muted);font-size:12px;margin-bottom:12px">Вопросов пока нет</div>';
}

// Забирает введённое в форме в состояние (чтобы при перестановке и удалении ничего не терялось)
function collectChatFaq() {
  const s = chatFaqState.settings;
  s.enabled = document.getElementById('cfEnabled').checked;
  s.title = document.getElementById('cfTitle').value.trim();
  s.greeting = document.getElementById('cfGreeting').value.trim();
  s.items.forEach((it, i) => {
    it.visible = document.getElementById('cfVis_' + i).checked;
    it.question = document.getElementById('cfQ_' + i).value.trim();
    it.answer = document.getElementById('cfA_' + i).value.trim();
  });
}

function moveChatFaqItem(i, dir) {
  collectChatFaq();
  const items = chatFaqState.settings.items, j = i + dir;
  if (j < 0 || j >= items.length) return;
  [items[i], items[j]] = [items[j], items[i]];
  renderChatFaqItems();
}

function removeChatFaqItem(i) {
  collectChatFaq();
  const it = chatFaqState.settings.items[i];
  if (!confirm('Удалить вопрос «' + (it.question || 'без названия') + '»?')) return;
  chatFaqState.settings.items.splice(i, 1);
  renderChatFaqItems();
}

function addChatFaqItem() {
  collectChatFaq();
  const lim = (chatFaqState.limits || {}).items || 30;
  if (chatFaqState.settings.items.length >= lim) { showToast('Можно не больше ' + lim + ' вопросов', 'err'); return; }
  chatFaqState.settings.items.push({ id: '', visible: true, question: 'Новый вопрос', answer: '' });
  renderChatFaqItems();
}

function useChatFaqExample(i) {
  collectChatFaq();
  const it = chatFaqState.settings.items[i], d = (chatFaqState.defaults || {})[it.id];
  if (!d) return;
  if (it.answer && !confirm('Заменить текущий ответ примером?')) return;
  it.answer = d.hint;
  renderChatFaqItems();
}

async function saveChatFaq() {
  collectChatFaq();
  const s = chatFaqState.settings;
  if (s.items.some(it => !it.question)) { showToast('У каждого вопроса должен быть текст', 'err'); return; }
  try {
    chatFaqState = await apiRequest('POST', '/api/admin/chat-faq', { enabled: s.enabled, title: s.title, greeting: s.greeting, items: s.items });
    renderChatFaq();
    showToast('Чат-помощник сохранён', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

// Раздел «Чат-помощник»: данные загружаются при каждом открытии
(function() {
  const menuItem = document.getElementById('sbChatFaq');
  if (menuItem) menuItem.addEventListener('click', () => {
    const title = document.getElementById('topbarTitle');
    if (title) title.textContent = 'Чат-помощник';
    loadChatFaq();
  });
  // при смене объекта в админке перезагружаем набор вопросов, если раздел открыт
  try {
    if (typeof switchProperty === 'function') {
      const original = switchProperty;
      switchProperty = async function() {
        const result = await original.apply(this, arguments);
        const panel = document.getElementById('panel-chatfaq');
        if (panel && panel.classList.contains('active')) loadChatFaq();
        return result;
      };
    }
  } catch(e) { /* если функция недоступна для замены, раздел обновляется при следующем открытии */ }
})();
