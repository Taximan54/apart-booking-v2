// Тема оформления отдельных страниц сайта (правила проживания, акции):
// те же фон и цвета, которые выбраны для сайта в админке («Настройки сайта → Бренд»).
// Цвета тем должны совпадать со списками BACKGROUND_THEMES и COLOR_THEMES в index.html.
(function() {
  var BACKGROUND_THEMES = {
    black:     {bg:'#0A0A0A', card:'#141414', border:'#1E1E1E', text_primary:'#F0E6C8', text_secondary:'#A89060', text_muted:'#5A4A30', white:'#FAF6EE', rgb:'10,10,10'},
    white:     {bg:'#FFFFFF', card:'#F7F7F5', border:'#E5E3DD', text_primary:'#1A1A1A', text_secondary:'#6B6B63', text_muted:'#A8A69C', white:'#0A0A0A', rgb:'255,255,255'},
    pistachio: {bg:'#E8EDDC', card:'#DEE6CE', border:'#C9D4B4', text_primary:'#2B3620', text_secondary:'#5C6B47', text_muted:'#8A9678', white:'#1A2214', rgb:'232,237,220'},
    cream:     {bg:'#FAF6EE', card:'#F0EADB', border:'#E0D6C0', text_primary:'#2A2318', text_secondary:'#6B5D45', text_muted:'#A6957A', white:'#1C1710', rgb:'250,246,238'},
    midnight:  {bg:'#0B1220', card:'#131C2E', border:'#1E2A40', text_primary:'#E8EDF5', text_secondary:'#93A3BD', text_muted:'#4C5A73', white:'#F5F8FC', rgb:'11,18,32'},
    sand:      {bg:'#EDE3D0', card:'#E3D7BE', border:'#D0C09E', text_primary:'#2E2416', text_secondary:'#6B5738', text_muted:'#9C8968', white:'#1C160D', rgb:'237,227,208'},
    mocha:        {bg:'#3D2F28', card:'#4A3B32', border:'#5C4A3E', text_primary:'#F0E4D8', text_secondary:'#C4A688', text_muted:'#8A6F5C', white:'#FCF6EF', rgb:'61,47,40'},
    emerald_night:{bg:'#0D2818', card:'#153322', border:'#1F4530', text_primary:'#E8F5EC', text_secondary:'#8FBFA0', text_muted:'#4A6B58', white:'#F5FAF7', rgb:'13,40,24'},
    terracotta:   {bg:'#5C3226', card:'#6B3D2F', border:'#7D4A3A', text_primary:'#F5E6DC', text_secondary:'#D4A88F', text_muted:'#9C7360', white:'#FCF3EC', rgb:'92,50,38'},
    indigo:       {bg:'#1A1440', card:'#241D52', border:'#332968', text_primary:'#EDEAFA', text_secondary:'#A79FD8', text_muted:'#5C5490', white:'#F7F5FC', rgb:'26,20,64'},
  };
  var COLOR_THEMES = {
    gold:       {gold:'#D4A017', light:'#F0C040', dark:'#8B6914', muted:'#6B5420', gradient:'linear-gradient(180deg,#FFD060 0%,#D4920A 28%,#8B5E00 50%,#D4920A 72%,#FFD060 100%)'},
    emerald:    {gold:'#2E8B57', light:'#6FCF97', dark:'#145A32', muted:'#1F6B45', gradient:'linear-gradient(180deg,#8FE3B0 0%,#2E8B57 28%,#0E3D22 50%,#2E8B57 72%,#8FE3B0 100%)'},
    sapphire:   {gold:'#2A5CAA', light:'#7EB6FF', dark:'#12294F', muted:'#1F3D6E', gradient:'linear-gradient(180deg,#A8CFFF 0%,#2A5CAA 28%,#0C1E3D 50%,#2A5CAA 72%,#A8CFFF 100%)'},
    burgundy:   {gold:'#7B1E3A', light:'#C2607F', dark:'#3D0E1C', muted:'#5C1730', gradient:'linear-gradient(180deg,#DE93A9 0%,#7B1E3A 28%,#2E0A16 50%,#7B1E3A 72%,#DE93A9 100%)'},
    amethyst:   {gold:'#7B4B94', light:'#C6A2D9', dark:'#3F2650', muted:'#5C3A70', gradient:'linear-gradient(180deg,#DDBFEA 0%,#7B4B94 28%,#2F1D3D 50%,#7B4B94 72%,#DDBFEA 100%)'},
    dusty_rose: {gold:'#C08497', light:'#ECC9D2', dark:'#7A4653', muted:'#9A6575', gradient:'linear-gradient(180deg,#F5DEE3 0%,#C08497 28%,#5E3540 50%,#C08497 72%,#F5DEE3 100%)'},
    teal:       {gold:'#1F8A8C', light:'#6FD8D2', dark:'#0D4547', muted:'#166668', gradient:'linear-gradient(180deg,#9FEAE5 0%,#1F8A8C 28%,#082D2E 50%,#1F8A8C 72%,#9FEAE5 100%)'},
    copper:     {gold:'#B5651D', light:'#E8A15C', dark:'#5C310C', muted:'#8A4A15', gradient:'linear-gradient(180deg,#F3C495 0%,#B5651D 28%,#3E2008 50%,#B5651D 72%,#F3C495 100%)'},
    graphite:   {gold:'#8A8D91', light:'#E4E6E9', dark:'#3A3C3F', muted:'#5F6266', gradient:'linear-gradient(180deg,#F2F3F4 0%,#8A8D91 28%,#232426 50%,#8A8D91 72%,#F2F3F4 100%)'},
    onyx:       {gold:'#6E6A63', light:'#A39C90', dark:'#000000', muted:'#3D3A35', gradient:'linear-gradient(180deg,#A39C90 0%,#6E6A63 28%,#000000 50%,#6E6A63 72%,#A39C90 100%)'},
  };

  // Объект: адрес страницы приходит в ?property=название (основной объект — без параметра)
  var slug = new URLSearchParams(location.search).get('property') || '';
  var CACHE_KEY = 'cpPageTheme:' + slug;

  function apply(bgKey, colorKey) {
    var root = document.documentElement;
    var bg = BACKGROUND_THEMES[bgKey] || BACKGROUND_THEMES.black;
    var c = COLOR_THEMES[colorKey] || COLOR_THEMES.gold;
    root.style.setProperty('--black', bg.bg);
    root.style.setProperty('--black-card', bg.card);
    root.style.setProperty('--black-border', bg.border);
    root.style.setProperty('--black-rgb', bg.rgb);
    root.style.setProperty('--text-primary', bg.text_primary);
    root.style.setProperty('--text-secondary', bg.text_secondary);
    root.style.setProperty('--text-muted', bg.text_muted);
    root.style.setProperty('--white', bg.white);
    root.style.setProperty('--gold', c.gold);
    root.style.setProperty('--gold-light', c.light);
    root.style.setProperty('--gold-dark', c.dark);
    root.style.setProperty('--gold-muted', c.muted);
    root.style.setProperty('--accent-gradient', c.gradient);
  }

  // Сначала — запомненная тема (чтобы страница не мигала чёрным), потом — свежая с сервера
  try {
    var cached = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null');
    if (cached) apply(cached.bg, cached.color);
  } catch (e) {}

  fetch('/api/site-settings' + (slug ? '?property=' + encodeURIComponent(slug) : ''))
    .then(function(r) { return r.json(); })
    .then(function(s) {
      apply(s.background_theme, s.color_theme);
      try { localStorage.setItem(CACHE_KEY, JSON.stringify({ bg: s.background_theme, color: s.color_theme })); } catch (e) {}
    })
    .catch(function() {});
})();
