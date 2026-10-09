// admin-js/site-settings.js: Настройки сайта: оформление, шрифты, цвета, меню, удобства, расположение, памятка гостю.
// Часть админки (ранее единого admin.js). Файлы подключаются подряд, в порядке из admin.html.
// SITE SETTINGS
const FONT_OPTIONS = [
  {key: 'cormorant',  label: 'Cormorant Garamond', family: "'Cormorant Garamond',serif", weight: 400},
  {key: 'im_fell',    label: 'PT Serif',         family: "'PT Serif',serif",         weight: 700},
  {key: 'playfair',   label: 'IM Fell English',  family: "'IM Fell English',serif", weight: 400},
  {key: 'unifraktur', label: 'Yeseva One',       family: "'Yeseva One',serif",       weight: 400},
  {key: 'tangerine',  label: 'Marck Script',     family: "'Marck Script',cursive",   weight: 400},
  {key: 'pacifico',   label: 'Pacifico',         family: "'Pacifico',cursive",       weight: 400},
  {key: 'great_vibes', label: 'Great Vibes',     family: "'Great Vibes',cursive",    weight: 400},
  {key: 'berkshire',  label: 'Bad Script',       family: "'Bad Script',cursive",     weight: 400},
  {key: 'poiret',     label: 'Poiret One',       family: "'Poiret One',sans-serif",   weight: 400},
];
const HERO_FONT_OPTIONS = FONT_OPTIONS;
let selectedFont = 'im_fell';
let selectedBold = false;
let selectedScale = 1.0;
let selectedNavScale = 1.0;
let selectedColorTheme = 'gold';
let selectedBackgroundTheme = 'black';
let selectedHeroFont = 'cormorant';
let selectedHeroBold = false;
let selectedHeroTitleScale = 1.0;
let selectedHeroSubtitleScale = 1.0;
let selectedHeroPosition = 'center';
let selectedHeroCarouselEnabled = true;
let selectedHeroCarouselSeconds = 6;
let selectedHeaderOpacityLevel = 3;
let selectedHeaderBlurLevel = 2;
const SCALE_OPTIONS = [0.5, 0.7, 1.0, 1.5, 2.0, 2.5];
const HERO_SCALE_OPTIONS = [0.5, 0.7, 1.0, 1.5, 2.0];
const NAV_SCALE_OPTIONS = [1.0, 1.2, 1.4, 1.6, 1.8];
const HERO_POSITION_OPTIONS = [{v:'left',label:'Слева'},{v:'center',label:'По центру'},{v:'right',label:'Справа'}];
const COLOR_THEMES = [
  {key: 'gold',       label: 'Золото',        solid: '#D4A017', gradient: 'linear-gradient(180deg,#FFD060 0%,#D4920A 28%,#8B5E00 50%,#D4920A 72%,#FFD060 100%)'},
  {key: 'emerald',    label: 'Изумруд',       solid: '#2E8B57', gradient: 'linear-gradient(180deg,#8FE3B0 0%,#2E8B57 28%,#0E3D22 50%,#2E8B57 72%,#8FE3B0 100%)'},
  {key: 'sapphire',   label: 'Сапфир',        solid: '#2A5CAA', gradient: 'linear-gradient(180deg,#A8CFFF 0%,#2A5CAA 28%,#0C1E3D 50%,#2A5CAA 72%,#A8CFFF 100%)'},
  {key: 'burgundy',   label: 'Бордо',         solid: '#7B1E3A', gradient: 'linear-gradient(180deg,#DE93A9 0%,#7B1E3A 28%,#2E0A16 50%,#7B1E3A 72%,#DE93A9 100%)'},
  {key: 'amethyst',   label: 'Аметист',       solid: '#7B4B94', gradient: 'linear-gradient(180deg,#DDBFEA 0%,#7B4B94 28%,#2F1D3D 50%,#7B4B94 72%,#DDBFEA 100%)'},
  {key: 'dusty_rose', label: 'Пыльная роза',  solid: '#C08497', gradient: 'linear-gradient(180deg,#F5DEE3 0%,#C08497 28%,#5E3540 50%,#C08497 72%,#F5DEE3 100%)'},
  {key: 'teal',       label: 'Бирюза',        solid: '#1F8A8C', gradient: 'linear-gradient(180deg,#9FEAE5 0%,#1F8A8C 28%,#082D2E 50%,#1F8A8C 72%,#9FEAE5 100%)'},
  {key: 'copper',     label: 'Медь',          solid: '#B5651D', gradient: 'linear-gradient(180deg,#F3C495 0%,#B5651D 28%,#3E2008 50%,#B5651D 72%,#F3C495 100%)'},
  {key: 'graphite',   label: 'Графит',        solid: '#8A8D91', gradient: 'linear-gradient(180deg,#F2F3F4 0%,#8A8D91 28%,#232426 50%,#8A8D91 72%,#F2F3F4 100%)'},
  {key: 'onyx',       label: 'Оникс',         solid: '#6E6A63', gradient: 'linear-gradient(180deg,#A39C90 0%,#6E6A63 28%,#000000 50%,#6E6A63 72%,#A39C90 100%)'},
];

// Темы ФОНА сайта — отдельная ось от COLOR_THEMES (там акцентный цвет
// логотипа/кнопок, тут — сам фон страницы и цвет текста под него).
// Первая опция ("black") — нынешний фон проекта, значения 1-в-1 совпадают
// с текущими CSS-переменными, поэтому смена ничего не ломает по умолчанию.
const BACKGROUND_THEMES = [
  {key: 'black',     label: 'Чёрный',       swatch: '#0A0A0A',
    bg: '#0A0A0A', card: '#141414', border: '#1E1E1E',
    text_primary: '#F0E6C8', text_secondary: '#A89060', text_muted: '#5A4A30', white: '#FAF6EE'},
  {key: 'white',     label: 'Белый',        swatch: '#FFFFFF',
    bg: '#FFFFFF', card: '#F7F7F5', border: '#E5E3DD',
    text_primary: '#1A1A1A', text_secondary: '#6B6B63', text_muted: '#A8A69C', white: '#0A0A0A'},
  {key: 'pistachio', label: 'Фисташковый',  swatch: '#E8EDDC',
    bg: '#E8EDDC', card: '#DEE6CE', border: '#C9D4B4',
    text_primary: '#2B3620', text_secondary: '#5C6B47', text_muted: '#8A9678', white: '#1A2214'},
  {key: 'cream',     label: 'Кремовый',     swatch: '#FAF6EE',
    bg: '#FAF6EE', card: '#F0EADB', border: '#E0D6C0',
    text_primary: '#2A2318', text_secondary: '#6B5D45', text_muted: '#A6957A', white: '#1C1710'},
  {key: 'midnight',  label: 'Тёмно-синий',  swatch: '#0B1220',
    bg: '#0B1220', card: '#131C2E', border: '#1E2A40',
    text_primary: '#E8EDF5', text_secondary: '#93A3BD', text_muted: '#4C5A73', white: '#F5F8FC'},
  {key: 'sand',      label: 'Песочный',     swatch: '#EDE3D0',
    bg: '#EDE3D0', card: '#E3D7BE', border: '#D0C09E',
    text_primary: '#2E2416', text_secondary: '#6B5738', text_muted: '#9C8968', white: '#1C160D'},
  {key: 'mocha',        label: 'Мокко',              swatch: '#3D2F28',
    bg: '#3D2F28', card: '#4A3B32', border: '#5C4A3E',
    text_primary: '#F0E4D8', text_secondary: '#C4A688', text_muted: '#8A6F5C', white: '#FCF6EF'},
  {key: 'emerald_night', label: 'Изумрудная ночь',   swatch: '#0D2818',
    bg: '#0D2818', card: '#153322', border: '#1F4530',
    text_primary: '#E8F5EC', text_secondary: '#8FBFA0', text_muted: '#4A6B58', white: '#F5FAF7'},
  {key: 'terracotta',    label: 'Терракотовый',      swatch: '#5C3226',
    bg: '#5C3226', card: '#6B3D2F', border: '#7D4A3A',
    text_primary: '#F5E6DC', text_secondary: '#D4A88F', text_muted: '#9C7360', white: '#FCF3EC'},
  {key: 'indigo',        label: 'Индиго',            swatch: '#1A1440',
    bg: '#1A1440', card: '#241D52', border: '#332968',
    text_primary: '#EDEAFA', text_secondary: '#A79FD8', text_muted: '#5C5490', white: '#F7F5FC'},
];

function renderColorPicker() {
  const el = document.getElementById('colorPicker');
  el.innerHTML = COLOR_THEMES.map(c => `
    <div onclick="selectColorTheme('${c.key}')" id="colorOpt-${c.key}" style="cursor:pointer;padding:12px 6px;text-align:center;border:1px solid ${c.key === selectedColorTheme ? '#fff' : 'var(--black-border)'};background:var(--black-card);transition:border-color .2s">
      <div style="width:100%;height:28px;border-radius:2px;margin-bottom:6px;background:${c.gradient}"></div>
      <div style="font-size:9px;color:var(--text-muted);letter-spacing:.05em">${c.label}</div>
    </div>
  `).join('');
}

function renderBackgroundPicker() {
  const el = document.getElementById('backgroundPicker');
  el.innerHTML = BACKGROUND_THEMES.map(b => `
    <div onclick="selectBackgroundTheme('${b.key}')" id="bgOpt-${b.key}" style="cursor:pointer;padding:12px 6px;text-align:center;border:1px solid ${b.key === selectedBackgroundTheme ? 'var(--gold)' : 'var(--black-border)'};background:var(--black-card);transition:border-color .2s">
      <div style="width:100%;height:28px;border-radius:2px;margin-bottom:6px;background:${b.swatch};border:1px solid rgba(128,128,128,.25)"></div>
      <div style="font-size:9px;color:var(--text-muted);letter-spacing:.05em">${b.label}</div>
    </div>
  `).join('');
}

function selectBackgroundTheme(key) {
  selectedBackgroundTheme = key;
  renderBackgroundPicker();
  renderDesignPreview();
}

function selectColorTheme(key) {
  selectedColorTheme = key;
  renderColorPicker();
  renderDesignPreview();

}

const NAV_LABEL_KEYS = [
  {key: 'gallery',     def: 'Галерея'},
  {key: 'amenities',   def: 'Удобства'},
  {key: 'location',    def: 'Расположение'},
  {key: 'prices',      def: 'Цены'},
  {key: 'house_rules', def: 'Правила проживания'},
  {key: 'places',      def: 'Куда сходить?'},
  {key: 'contacts',    def: 'Контакты'},
  {key: 'booking',     def: 'Забронировать'},
];
let navLabels = {};
let amenitiesData = [];

function renderNavLabelsEditor() {
  const el = document.getElementById('navLabelsEditor');
  el.innerHTML = NAV_LABEL_KEYS.map(item => {
    const stored = navLabels[item.key];
    const val = (stored !== undefined ? stored : item.def).replace(/"/g,'&quot;');
    return `
    <div class="info-field">
      <div class="info-label" style="font-size:9px">${item.def}</div>
      <input type="text" class="info-input" id="navLabel-input-${item.key}" value="${val}" placeholder="${item.def}" style="width:100%">
    </div>
  `;
  }).join('');
}

function renderAmenitiesEditor() {
  const el = document.getElementById('amenitiesEditor');
  if(!el) return;
  el.innerHTML = amenitiesData.map((a, i) => `
    <div style="display:flex;gap:10px;align-items:center">
      <input type="text" class="info-input amenity-icon-input" data-idx="${i}"
             value="${(a.icon || '').replace(/"/g,'&quot;')}" placeholder="📶"
             style="width:56px;text-align:center;font-size:18px;flex-shrink:0">
      <input type="text" class="info-input amenity-name-input" data-idx="${i}"
             value="${(a.name || '').replace(/"/g,'&quot;')}" placeholder="Например: Кондиционер"
             style="flex:1">
    </div>
  `).join('');
}

async function saveAmenities() {
  const icons = document.querySelectorAll('.amenity-icon-input');
  const names = document.querySelectorAll('.amenity-name-input');
  const collected = [];
  for(let i = 0; i < 12; i++) {
    collected.push({
      icon: icons[i] ? icons[i].value.trim() : '',
      name: names[i] ? names[i].value.trim() : '',
    });
  }
  amenitiesData = collected;
  try {
    const current = await apiGet('/api/site-settings');
    await apiPost('/api/site-settings', {...current, amenities: collected});
    showToast('Удобства сохранены', 'gold');
  } catch(e) { showToast('Ошибка сохранения', 'err'); }
}

// РАСПОЛОЖЕНИЕ — ближайшие места (значок, название, расстояние, описание)
let locationPointsData = [];

function renderLocationPointsEditor() {
  const el = document.getElementById('locationPointsEditor');
  if(!el) return;
  el.innerHTML = locationPointsData.map((p, i) => `
    <div style="display:flex;gap:10px;align-items:flex-start;padding:12px;background:var(--black-card);border:1px solid var(--black-border)">
      <input type="text" class="info-input locpoint-icon-input" data-idx="${i}"
             value="${(p.icon || '').replace(/"/g,'&quot;')}" placeholder="📍"
             style="width:56px;text-align:center;font-size:18px;flex-shrink:0">
      <div style="flex:1;display:flex;flex-direction:column;gap:8px">
        <input type="text" class="info-input locpoint-name-input" data-idx="${i}"
               value="${(p.name || '').replace(/"/g,'&quot;')}" placeholder="Название места">
        <input type="text" class="info-input locpoint-dist-input" data-idx="${i}"
               value="${(p.distance || '').replace(/"/g,'&quot;')}" placeholder="Например: 700 м · 8 мин пешком">
        <input type="text" class="info-input locpoint-desc-input" data-idx="${i}"
               value="${(p.description || '').replace(/"/g,'&quot;')}" placeholder="Короткое описание">
      </div>
    </div>
  `).join('');
}

async function saveLocationPoints() {
  const icons = document.querySelectorAll('.locpoint-icon-input');
  const names = document.querySelectorAll('.locpoint-name-input');
  const dists = document.querySelectorAll('.locpoint-dist-input');
  const descs = document.querySelectorAll('.locpoint-desc-input');
  const collected = [];
  for(let i = 0; i < 5; i++) {
    collected.push({
      icon:        icons[i] ? icons[i].value.trim() : '',
      name:        names[i] ? names[i].value.trim() : '',
      distance:    dists[i] ? dists[i].value.trim() : '',
      description: descs[i] ? descs[i].value.trim() : '',
    });
  }
  locationPointsData = collected;
  try {
    const current = await apiGet('/api/site-settings');
    await apiPost('/api/site-settings', {...current, location_points: collected});
    showToast('Расположение сохранено', 'gold');
  } catch(e) { showToast('Ошибка сохранения', 'err'); }
}

function renderFontPicker() {
  const el = document.getElementById('fontPicker');
  el.innerHTML = FONT_OPTIONS.map(f => `
    <div onclick="selectFont('${f.key}')" id="fontOpt-${f.key}" style="cursor:pointer;padding:14px 8px;text-align:center;border:1px solid ${f.key === selectedFont ? 'var(--gold)' : 'var(--black-border)'};background:var(--black-card);transition:border-color .2s">
      <div style="font-family:${f.family};font-weight:${selectedBold ? 700 : f.weight};font-size:20px;letter-spacing:.03em;background:linear-gradient(180deg,#FFD060 0%,#D4920A 28%,#8B5E00 50%,#D4920A 72%,#FFD060 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:4px">Городская Пауза</div>
      <div style="font-size:9px;color:var(--text-muted);letter-spacing:.05em">${f.label}</div>
    </div>
  `).join('');
}

function renderBoldToggle() {
  const el = document.getElementById('boldToggle');
  const opts = [{v:false,label:'Обычный'},{v:true,label:'Жирный'}];
  el.innerHTML = opts.map(o => `
    <button type="button" onclick="selectBold(${o.v})" class="btn ${selectedBold===o.v ? 'btn-primary' : 'btn-ghost'} btn-sm">${o.label}</button>
  `).join('');
}

function renderScalePicker() {
  const el = document.getElementById('scalePicker');
  el.innerHTML = SCALE_OPTIONS.map(s => `
    <button type="button" onclick="selectScale(${s})" class="btn ${selectedScale===s ? 'btn-primary' : 'btn-ghost'} btn-sm">${s}x</button>
  `).join('');
}

function renderNavScalePicker() {
  const el = document.getElementById('navScalePicker');
  el.innerHTML = NAV_SCALE_OPTIONS.map(s => `
    <button type="button" onclick="selectNavScale(${s})" class="btn ${selectedNavScale===s ? 'btn-primary' : 'btn-ghost'} btn-sm">${s}x</button>
  `).join('');
}

function renderHeroFontPicker() {
  const el = document.getElementById('heroFontPicker');
  el.innerHTML = HERO_FONT_OPTIONS.map(f => `
    <div onclick="selectHeroFont('${f.key}')" id="heroFontOpt-${f.key}" style="cursor:pointer;padding:14px 8px;text-align:center;border:1px solid ${f.key === selectedHeroFont ? 'var(--gold)' : 'var(--black-border)'};background:var(--black-card);transition:border-color .2s">
      <div style="font-family:${f.family};font-weight:${selectedHeroBold ? 700 : f.weight};font-size:20px;letter-spacing:.03em;background:linear-gradient(180deg,#FFD060 0%,#D4920A 28%,#8B5E00 50%,#D4920A 72%,#FFD060 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:4px">Городская Пауза</div>
      <div style="font-size:9px;color:var(--text-muted);letter-spacing:.05em">${f.label}</div>
    </div>
  `).join('');
}

function selectHeroFont(key) {
  selectedHeroFont = key;
  renderHeroFontPicker();
  renderDesignPreview();
}

function renderHeroBoldToggle() {
  const el = document.getElementById('heroBoldToggle');
  const opts = [{v:false,label:'Обычный'},{v:true,label:'Жирный'}];
  el.innerHTML = opts.map(o => `
    <button type="button" onclick="selectHeroBold(${o.v})" class="btn ${selectedHeroBold===o.v ? 'btn-primary' : 'btn-ghost'} btn-sm">${o.label}</button>
  `).join('');
}

function selectHeroBold(v) {
  selectedHeroBold = v;
  renderHeroBoldToggle();
  renderHeroFontPicker();
  renderDesignPreview();
}

function renderHeroTitleScalePicker() {
  const el = document.getElementById('heroTitleScalePicker');
  el.innerHTML = HERO_SCALE_OPTIONS.map(s => `
    <button type="button" onclick="selectHeroTitleScale(${s})" class="btn ${selectedHeroTitleScale===s ? 'btn-primary' : 'btn-ghost'} btn-sm">${s}x</button>
  `).join('');
}

function selectHeroTitleScale(v) {
  selectedHeroTitleScale = v;
  renderHeroTitleScalePicker();
  renderDesignPreview();
}

function renderHeroSubtitleScalePicker() {
  const el = document.getElementById('heroSubtitleScalePicker');
  el.innerHTML = HERO_SCALE_OPTIONS.map(s => `
    <button type="button" onclick="selectHeroSubtitleScale(${s})" class="btn ${selectedHeroSubtitleScale===s ? 'btn-primary' : 'btn-ghost'} btn-sm">${s}x</button>
  `).join('');
}

function selectHeroSubtitleScale(v) {
  selectedHeroSubtitleScale = v;
  renderHeroSubtitleScalePicker();
  renderDesignPreview();
}

function renderHeroPositionPicker() {
  const el = document.getElementById('heroPositionPicker');
  el.innerHTML = HERO_POSITION_OPTIONS.map(o => `
    <button type="button" onclick="selectHeroPosition('${o.v}')" class="btn ${selectedHeroPosition===o.v ? 'btn-primary' : 'btn-ghost'} btn-sm">${o.label}</button>
  `).join('');
}

function selectHeroPosition(v) {
  selectedHeroPosition = v;
  renderHeroPositionPicker();
  renderDesignPreview();
}

const HERO_CAROUSEL_SECONDS_OPTIONS = [3, 4, 5, 6, 8, 10, 12, 15];

function renderHeroCarouselSpeedPicker() {
  const el = document.getElementById('heroCarouselSpeedPicker');
  el.innerHTML = HERO_CAROUSEL_SECONDS_OPTIONS.map(sec => `
    <button type="button" onclick="selectHeroCarouselSeconds(${sec})" class="btn ${selectedHeroCarouselSeconds===sec ? 'btn-primary' : 'btn-ghost'} btn-sm">${sec} сек</button>
  `).join('');
}

function selectHeroCarouselSeconds(sec) {
  selectedHeroCarouselSeconds = sec;
  renderHeroCarouselSpeedPicker();
}

function selectFont(key) {
  selectedFont = key;
  renderFontPicker();
  renderDesignPreview();
}

function selectBold(v) {
  selectedBold = v;
  renderBoldToggle();
  renderFontPicker();
  renderDesignPreview();
}

function selectScale(v) {
  selectedScale = v;
  renderScalePicker();
  renderDesignPreview();
}

function selectNavScale(v) {
  selectedNavScale = v;
  renderNavScalePicker();
}

function renderDesignPreview() {
  const logoEl     = document.getElementById('dpLogo');
  const btnEl      = document.getElementById('dpBookBtn');
  const heroTitleEl= document.getElementById('dpHeroTitle');
  const heroSubEl  = document.getElementById('dpHeroSub');
  const heroBoxEl  = document.getElementById('dpHero');
  if(!logoEl) return; // превью ещё не отрендерилось на странице

  const fontObj     = FONT_OPTIONS.find(f => f.key === selectedFont) || FONT_OPTIONS[0];
  const heroFontObj = HERO_FONT_OPTIONS.find(f => f.key === selectedHeroFont) || HERO_FONT_OPTIONS[0];
  const theme       = COLOR_THEMES.find(c => c.key === selectedColorTheme) || COLOR_THEMES[0];
  const bgTheme     = BACKGROUND_THEMES.find(b => b.key === selectedBackgroundTheme) || BACKGROUND_THEMES[0];
  if (heroBoxEl) heroBoxEl.style.background = bgTheme.card;

  const siteNameEl  = document.getElementById('settingsSiteName');
  const heroTitleIn = document.getElementById('settingsHeroTitle');
  const heroSubIn   = document.getElementById('settingsHeroSubtitle');
  const siteName  = (siteNameEl && siteNameEl.value.trim()) || 'Городская Пауза';
  const heroTitle = (heroTitleIn && heroTitleIn.value.trim()) || 'Искусство комфортного проживания';
  const heroSub   = (heroSubIn && heroSubIn.value.trim()) || 'Апартаменты премиум-класса · Посуточная аренда';

  // Логотип
  logoEl.textContent = siteName;
  logoEl.style.fontFamily = fontObj.family;
  logoEl.style.fontWeight = selectedBold ? 700 : fontObj.weight;
  logoEl.style.fontSize = (18 + Math.min(selectedScale, 2) * 3) + 'px';
  logoEl.style.background = theme.gradient;
  logoEl.style.webkitBackgroundClip = 'text';
  logoEl.style.webkitTextFillColor = 'transparent';
  logoEl.style.backgroundClip = 'text';

  // Кнопка «Забронировать»
  btnEl.style.borderColor = theme.solid;
  btnEl.style.background = theme.gradient;
  btnEl.style.webkitBackgroundClip = 'text';
  btnEl.style.webkitTextFillColor = 'transparent';
  btnEl.style.backgroundClip = 'text';
  btnEl.style.fontFamily = fontObj.family;

  // Hero-заголовок и подзаголовок
  heroTitleEl.textContent = heroTitle;
  heroTitleEl.style.fontFamily = heroFontObj.family;
  heroTitleEl.style.fontWeight = selectedHeroBold ? 700 : heroFontObj.weight;
  heroTitleEl.style.fontSize = (18 + selectedHeroTitleScale * 8) + 'px';
  heroTitleEl.style.background = theme.gradient;
  heroTitleEl.style.webkitBackgroundClip = 'text';
  heroTitleEl.style.webkitTextFillColor = 'transparent';
  heroTitleEl.style.backgroundClip = 'text';

  heroSubEl.textContent = heroSub;
  heroSubEl.style.fontFamily = heroFontObj.family;
  heroSubEl.style.fontWeight = selectedHeroBold ? 700 : heroFontObj.weight;
  heroSubEl.style.fontSize = (8 + selectedHeroSubtitleScale * 4) + 'px';
  heroSubEl.style.color = theme.solid;

  // Расположение hero-текста
  const align = selectedHeroPosition === 'left' ? 'flex-start' : selectedHeroPosition === 'right' ? 'flex-end' : 'center';
  const textAlign = selectedHeroPosition === 'left' ? 'left' : selectedHeroPosition === 'right' ? 'right' : 'center';
  heroBoxEl.style.alignItems = align;
  heroBoxEl.style.textAlign = textAlign;
}

async function loadSiteSettings() {
  try {
    const s = await apiGet('/api/site-settings');
    document.getElementById('settingsMapUrl').value       = s.map_url        || '';
    document.getElementById('settingsMapService').value   = s.map_service    || 'yandex';
    document.getElementById('settingsSiteName').value     = s.site_name      || 'Городская Пауза';
    document.getElementById('settingsHeroTitle').value    = s.hero_title     || '';
    document.getElementById('settingsHeroSubtitle').value = s.hero_subtitle  || '';
    document.getElementById('settingsHeroEyebrow').value  = s.hero_eyebrow   ?? 'Апартаменты в городе';
    document.getElementById('navExtraLabel').value        = s.nav_extra_label || '';
    document.getElementById('navExtraUrl').value          = s.nav_extra_url   || '';
    selectedFont = s.logo_font || 'im_fell';
    selectedBold = !!s.logo_bold;
    selectedScale = s.logo_scale || 1.0;
    selectedNavScale = s.nav_scale || 1.0;
    selectedColorTheme = s.color_theme || 'gold';
    selectedBackgroundTheme = s.background_theme || 'black';
    navLabels = s.nav_labels || {};
    amenitiesData = (s.amenities && s.amenities.length ? s.amenities : []).slice(0, 12);
    while(amenitiesData.length < 12) amenitiesData.push({icon:'', name:''});
    renderAmenitiesEditor();
    locationPointsData = (s.location_points && s.location_points.length ? s.location_points : []).slice(0, 5);
    while(locationPointsData.length < 5) locationPointsData.push({icon:'', name:'', distance:'', description:''});
    renderLocationPointsEditor();
    selectedHeroFont = s.hero_font || 'cormorant';
    selectedHeroBold = !!s.hero_bold;
    selectedHeroTitleScale = s.hero_title_scale || 1.0;
    selectedHeroSubtitleScale = s.hero_subtitle_scale || 1.0;
    selectedHeroPosition = s.hero_position || 'center';
    selectedHeroCarouselSeconds = s.hero_carousel_seconds || 6;
    selectedHeroCarouselEnabled = s.hero_carousel_enabled !== false;
    document.getElementById('heroCarouselEnabledCheck').checked = selectedHeroCarouselEnabled;
    selectedHeaderOpacityLevel = s.header_opacity_level || 3;
    selectedHeaderBlurLevel = s.header_blur_level || 2;
    document.getElementById('headerOpacitySlider').value = selectedHeaderOpacityLevel;
    document.getElementById('headerOpacityValue').textContent = selectedHeaderOpacityLevel;
    document.getElementById('headerBlurSlider').value = selectedHeaderBlurLevel;
    document.getElementById('headerBlurValue').textContent = selectedHeaderBlurLevel;
    renderFontPicker();
    renderBoldToggle();
    renderScalePicker();
    renderNavScalePicker();
    renderColorPicker();
    renderBackgroundPicker();
    renderNavLabelsEditor();
    renderHeroFontPicker();
    renderHeroBoldToggle();
    renderHeroTitleScalePicker();
    renderHeroSubtitleScalePicker();
    renderHeroPositionPicker();
    renderHeroCarouselSpeedPicker();
    renderDesignPreview();
    if(s.hero_photo) {
      const img = document.getElementById('heroPhotoImg');
      img.src = `${API_BASE}/data/photos/${s.hero_photo}`;
      img.style.display = 'block';
      document.getElementById('heroPhotoEmpty').style.display = 'none';
      document.getElementById('heroPhotoName').textContent = s.hero_photo;
    }
    if(s.hero_photo_mobile) {
      const img = document.getElementById('heroPhotoMobileImg');
      img.src = `${API_BASE}/data/photos/${s.hero_photo_mobile}`;
      img.style.display = 'block';
      document.getElementById('heroPhotoMobileEmpty').style.display = 'none';
      document.getElementById('heroPhotoMobileName').textContent = s.hero_photo_mobile;
    }
    if(s.map_photo) {
      const img = document.getElementById('mapPhotoImg');
      img.src = `${API_BASE}/data/photos/${s.map_photo}`;
      img.style.display = 'block';
      document.getElementById('mapPhotoEmpty').style.display = 'none';
      document.getElementById('mapPhotoName').textContent = s.map_photo;
    }
  } catch(e) {}
}

const PHOTO_UPLOAD_CONFIG = {
  hero:        { fileInputId: 'heroPhotoFile',       label: 'Обложка сайта',              settingsKey: 'hero_photo',        imgId: 'heroPhotoImg',       emptyId: 'heroPhotoEmpty',       nameId: 'heroPhotoName' },
  hero_mobile: { fileInputId: 'heroPhotoMobileFile', label: 'Обложка сайта (мобильная)',   settingsKey: 'hero_photo_mobile', imgId: 'heroPhotoMobileImg', emptyId: 'heroPhotoMobileEmpty', nameId: 'heroPhotoMobileName' },
  map:         { fileInputId: 'mapPhotoFile',        label: 'Фото карты',                 settingsKey: 'map_photo',         imgId: 'mapPhotoImg',        emptyId: 'mapPhotoEmpty',        nameId: 'mapPhotoName' },
};

async function uploadSettingsPhoto(type) {
  const cfg = PHOTO_UPLOAD_CONFIG[type];
  if (!cfg) return;
  const fileInput = document.getElementById(cfg.fileInputId);
  const file = fileInput.files[0];
  if(!file) return;
  if(file.size > 10 * 1024 * 1024) { showToast('Файл слишком большой (макс. 10 МБ)', 'err'); return; }
  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', cfg.label);
  formData.append('purpose', 'site');
  try {
    showToast('Загружаю фото...', 'gold');
    const resp = await fetch(`${API_BASE}/api/photos/upload`, {
      method: 'POST',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {},
      body: formData
    });
    if(!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    const filename = data.filename;
    // Сохраняем в настройки
    const current = await apiGet('/api/site-settings');
    const payload = {...current, [cfg.settingsKey]: filename};
    await apiPost('/api/site-settings', payload);
    // Обновляем превью
    const img = document.getElementById(cfg.imgId);
    img.src = `${API_BASE}/data/photos/${filename}`;
    img.style.display = 'block';
    document.getElementById(cfg.emptyId).style.display = 'none';
    document.getElementById(cfg.nameId).textContent = filename;
    showToast('Фото загружено и сохранено', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

async function saveSiteSettings() {
  const payload = {
    map_url:     document.getElementById('settingsMapUrl').value.trim(),
    map_service: document.getElementById('settingsMapService').value,
  };
  try {
    // Сохраняем только URL и сервис — фото уже сохраняются при загрузке
    const current = await apiGet('/api/site-settings');
    await apiPost('/api/site-settings', {...current, ...payload});
    showToast('Настройки сохранены', 'gold');
  } catch(e) { showToast('Ошибка сохранения', 'err'); }
}

async function saveDesignSettings() {
  const collectedNavLabels = {};
  NAV_LABEL_KEYS.forEach(item => {
    const el = document.getElementById(`navLabel-input-${item.key}`);
    collectedNavLabels[item.key] = el ? el.value.trim() : item.def;
  });
  const payload = {
    site_name:     document.getElementById('settingsSiteName').value.trim()     || 'Городская Пауза',
    hero_title:    document.getElementById('settingsHeroTitle').value.trim(),
    hero_subtitle: document.getElementById('settingsHeroSubtitle').value.trim(),
    hero_eyebrow:  document.getElementById('settingsHeroEyebrow').value.trim(),
    nav_extra_label: document.getElementById('navExtraLabel').value.trim(),
    nav_extra_url:   document.getElementById('navExtraUrl').value.trim(),
    logo_font:     selectedFont,
    logo_bold:     selectedBold,
    logo_scale:    selectedScale,
    nav_scale:     selectedNavScale,
    color_theme:   selectedColorTheme,
    background_theme: selectedBackgroundTheme,
    nav_labels:    collectedNavLabels,
    hero_font:     selectedHeroFont,
    hero_bold:     selectedHeroBold,
    hero_title_scale:    selectedHeroTitleScale,
    hero_subtitle_scale: selectedHeroSubtitleScale,
    hero_position: selectedHeroPosition,
    hero_carousel_seconds: selectedHeroCarouselSeconds,
    hero_carousel_enabled: selectedHeroCarouselEnabled,
    header_opacity_level: selectedHeaderOpacityLevel,
    header_blur_level: selectedHeaderBlurLevel,
  };
  try {
    const current = await apiGet('/api/site-settings');
    await apiPost('/api/site-settings', {...current, ...payload});
    showToast('Оформление сохранено', 'gold');
  } catch(e) { showToast('Ошибка сохранения', 'err'); }
}

async function loadCheckinMemo() {
  try {
    const r = await fetch(`${API_BASE}/api/checkin-memo`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    document.getElementById('checkinEditor').value = await r.text();
  } catch(e) {
    document.getElementById('checkinEditor').value = 'Ошибка загрузки';
  }
}

async function saveCheckinMemo() {
  const text = document.getElementById('checkinEditor').value;
  try {
    await apiPost('/api/checkin-memo', { text });
    showToast('Памятка сохранена', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения', 'err');
  }
}

