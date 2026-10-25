// admin-js/catalog.js: раздел «Каталог сайта» — страница «Все апартаменты» (/apartments), где гость выбирает квартиру.
// Настройки общие для всех объектов. Список объектов берётся из раздела «Объекты» автоматически.

let catalogState = null;

const CATALOG_BACKGROUNDS = [['', 'Как у основного сайта'], ['black', 'Чёрный'], ['white', 'Белый'], ['pistachio', 'Фисташковый'], ['cream', 'Кремовый'],
  ['midnight', 'Полночь'], ['sand', 'Песочный'], ['mocha', 'Мокко'], ['emerald_night', 'Изумрудная ночь'], ['terracotta', 'Терракота'], ['indigo', 'Индиго']];
const CATALOG_COLORS = [['', 'Как у основного сайта'], ['gold', 'Золото'], ['emerald', 'Изумруд'], ['sapphire', 'Сапфир'], ['burgundy', 'Бордо'],
  ['amethyst', 'Аметист'], ['dusty_rose', 'Пыльная роза'], ['teal', 'Бирюза'], ['copper', 'Медь'], ['graphite', 'Графит'], ['onyx', 'Оникс']];

const CATALOG_COLUMNS = [['auto', 'Автоматически (сколько поместится)'], ['1', 'По 1 в ряд'], ['2', 'По 2 в ряд'], ['3', 'По 3 в ряд'], ['4', 'По 4 в ряд']];
const CATALOG_FONT_LIST = [['', 'По умолчанию'], ['cormorant', 'Cormorant Garamond (классика)'], ['im_fell', 'PT Serif (строгий)'], ['unifraktur', 'Yeseva One (выразительный)'],
  ['tangerine', 'Marck Script (рукописный)'], ['pacifico', 'Pacifico (мягкий рукописный)'], ['berkshire', 'Bad Script (рукописный)'],
  ['poiret', 'Poiret One (тонкий декоративный)'], ['montserrat', 'Montserrat (без засечек)']];
const CATALOG_SCALES = [[0.7, 'Мелкий'], [0.85, 'Меньше обычного'], [1, 'Обычный'], [1.15, 'Чуть крупнее'], [1.3, 'Крупный'], [1.5, 'Очень крупный'], [2, 'Огромный']];
// группы шрифтов: ключ, название, есть ли выбор «жирный»
const CATALOG_FONT_GROUPS = [['brand', 'Название сети (шапка страницы)', true], ['title', 'Заголовок страницы', true], ['subtitle', 'Подзаголовок', true],
  ['card', 'Названия квартир в карточках', true], ['text', 'Текст в карточках (подпись, удобства, цена, кнопка)', false]];

function catEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function loadCatalogAdmin() {
  try {
    catalogState = await apiGet('/api/admin/catalog', { 'X-Property-Id': '1' });
    renderCatalogAdmin();
  } catch(e) {
    if (String(e.message) !== '401') showToast('Не удалось загрузить каталог: ' + e.message, 'err');
  }
}

function fillCatalogSelect(id, options, value) {
  const sel = document.getElementById(id);
  sel.innerHTML = options.map(([v, label]) => `<option value="${v}">${catEsc(label)}</option>`).join('');
  sel.value = value || '';
}

function renderCatalogAdmin() {
  if (!catalogState) return;
  const s = catalogState.settings, d = catalogState.defaults;
  document.getElementById('catBrand').value = s.brand || '';
  document.getElementById('catBrand').placeholder = d.brand;
  document.getElementById('catTitle').value = s.title || '';
  document.getElementById('catTitle').placeholder = d.title;
  document.getElementById('catSubtitle').value = s.subtitle || '';
  document.getElementById('catSubtitle').placeholder = d.subtitle;
  fillCatalogSelect('catBackground', CATALOG_BACKGROUNDS, s.background_theme);
  fillCatalogSelect('catColor', CATALOG_COLORS, s.color_theme);
  document.getElementById('catButtonLabel').value = s.button_label || '';
  document.getElementById('catButtonLabel').placeholder = d.button_label;
  fillCatalogSelect('catColumns', CATALOG_COLUMNS, s.columns || 'auto');
  renderCatalogFonts();
  renderCatalogItems();
}

// Шрифты: для каждой группы — шрифт, жирность и размер
function renderCatalogFonts() {
  const f = catalogState.settings.fonts || {};
  const box = document.getElementById('catFonts');
  box.innerHTML = CATALOG_FONT_GROUPS.map(([g, label, hasBold]) => {
    const scale = Number(f[g + '_scale']) || 1;
    const scales = CATALOG_SCALES.some(([v]) => v === scale) ? CATALOG_SCALES : CATALOG_SCALES.concat([[scale, 'Свой размер (' + scale + ')']]);
    return `<div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;padding:12px 0;border-top:1px solid var(--black-border)">
      <div style="flex:1 1 100%;font-size:12px;color:var(--text-primary)">${catEsc(label)}</div>
      <div class="info-field" style="flex:2;min-width:200px"><div class="info-label">Шрифт</div>
        <select class="info-input" id="catFont_${g}" style="width:100%">${CATALOG_FONT_LIST.map(([v, l]) => `<option value="${v}" ${v === (f[g + '_font'] || '') ? 'selected' : ''}>${catEsc(l)}</option>`).join('')}</select></div>
      <div class="info-field" style="flex:1;min-width:150px"><div class="info-label">Размер</div>
        <select class="info-input" id="catScale_${g}" style="width:100%">${scales.map(([v, l]) => `<option value="${v}" ${v === scale ? 'selected' : ''}>${catEsc(l)}</option>`).join('')}</select></div>
      ${hasBold ? `<label style="display:flex;gap:8px;align-items:center;font-size:12px;color:var(--text-secondary);padding-bottom:10px;cursor:pointer">
        <input type="checkbox" id="catBold_${g}" ${f[g + '_bold'] ? 'checked' : ''}> Жирный</label>` : ''}
    </div>`;
  }).join('');
}

function renderCatalogItems() {
  const box = document.getElementById('catItems');
  const items = catalogState.items;
  box.innerHTML = items.map((it, i) => `
    <div style="padding:16px;border:1px solid var(--black-border);background:var(--black-card);margin-bottom:14px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px">
        <div style="font-size:13px;color:var(--text-primary)">${catEsc(it.site_name)}
          <span style="font-size:11px;color:var(--text-muted)">· объект № ${it.id}${it.is_default ? ' · основной' : ''}${it.active ? '' : ' · отключён, в каталоге не виден'}</span></div>
        <div style="display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" ${i === 0 ? 'disabled' : ''} onclick="moveCatalogItem(${it.id}, -1)" title="Выше">↑</button>
          <button class="btn btn-ghost btn-sm" ${i === items.length - 1 ? 'disabled' : ''} onclick="moveCatalogItem(${it.id}, 1)" title="Ниже">↓</button>
        </div>
      </div>
      <label style="display:flex;gap:8px;align-items:center;font-size:12px;color:var(--text-secondary);margin-bottom:12px;cursor:pointer">
        <input type="checkbox" id="catVisible_${it.id}" ${it.visible ? 'checked' : ''}> Показывать в каталоге</label>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <div class="info-field" style="flex:1;min-width:200px"><div class="info-label">Название в каталоге</div>
          <input type="text" class="info-input" id="catItemTitle_${it.id}" maxlength="80" value="${catEsc(it.title)}" placeholder="${catEsc(it.site_name)}"></div>
        <div class="info-field" style="flex:1;min-width:200px"><div class="info-label">Подпись в карточке (до 200 символов)</div>
          <textarea class="info-input" id="catCaption_${it.id}" rows="3" maxlength="200" style="width:100%;resize:vertical;line-height:1.5" placeholder="Например: Центр, рядом с оперным театром">${catEsc(it.caption)}</textarea></div>
        <div class="info-field" style="flex:1;min-width:200px"><div class="info-label">Свой адрес сайта (если есть отдельный домен)</div>
          <input type="text" class="info-input" id="catSiteUrl_${it.id}" maxlength="300" value="${catEsc(it.site_url)}" placeholder="${catEsc(it.url)}"></div>
      </div>
    </div>`).join('') || '<div style="color:var(--text-muted);font-size:12px">Объектов пока нет</div>';
}

// Забирает введённое в форме в catalogState (чтобы при перестановке ничего не терялось)
function collectCatalogForm() {
  const s = catalogState.settings;
  s.brand = document.getElementById('catBrand').value.trim();
  s.title = document.getElementById('catTitle').value.trim();
  s.subtitle = document.getElementById('catSubtitle').value.trim();
  s.background_theme = document.getElementById('catBackground').value;
  s.color_theme = document.getElementById('catColor').value;
  s.button_label = document.getElementById('catButtonLabel').value.trim();
  s.columns = document.getElementById('catColumns').value;
  s.fonts = s.fonts || {};
  CATALOG_FONT_GROUPS.forEach(([g, label, hasBold]) => {
    s.fonts[g + '_font'] = document.getElementById('catFont_' + g).value;
    s.fonts[g + '_scale'] = parseFloat(document.getElementById('catScale_' + g).value) || 1;
    if (hasBold) s.fonts[g + '_bold'] = document.getElementById('catBold_' + g).checked;
  });
  catalogState.items.forEach(it => {
    it.visible = document.getElementById('catVisible_' + it.id).checked;
    it.title = document.getElementById('catItemTitle_' + it.id).value.trim();
    it.caption = document.getElementById('catCaption_' + it.id).value.trim();
    it.site_url = document.getElementById('catSiteUrl_' + it.id).value.trim();
  });
}

function moveCatalogItem(id, dir) {
  collectCatalogForm();
  const items = catalogState.items;
  const i = items.findIndex(x => x.id === id), j = i + dir;
  if (i < 0 || j < 0 || j >= items.length) return;
  [items[i], items[j]] = [items[j], items[i]];
  renderCatalogItems();
}

async function saveCatalog() {
  collectCatalogForm();
  const s = catalogState.settings;
  const payload = {
    brand: s.brand, title: s.title, subtitle: s.subtitle,
    background_theme: s.background_theme, color_theme: s.color_theme,
    button_label: s.button_label, columns: s.columns, fonts: s.fonts,
    items: catalogState.items.map(it => ({ id: it.id, visible: it.visible, title: it.title, caption: it.caption, site_url: it.site_url }))
  };
  try {
    catalogState = await apiRequest('POST', '/api/admin/catalog', payload);
    renderCatalogAdmin();
    showToast('Каталог сохранён', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

// Раздел «Каталог сайта»: данные загружаются при каждом открытии раздела
(function() {
  const menuItem = document.getElementById('sbCatalog');
  if (menuItem) menuItem.addEventListener('click', () => {
    const title = document.getElementById('topbarTitle');
    if (title) title.textContent = 'Каталог сайта';
    loadCatalogAdmin();
  });
})();
