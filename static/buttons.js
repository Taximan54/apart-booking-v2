// Волна от точки нажатия на кнопках (оформление — в buttons.css). Работает и для кнопок, которые появляются позже.
(function () {
  var SELECTOR = '.btn, .btn-gold, .btn-gold-w, .btn-outline, .btn-outline-s, .nav-btn, .catalog-link, .cal-nav, .cal-nav-btn';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;
  document.addEventListener('pointerdown', function (e) {
    var target = e.target;
    var btn = target && target.closest ? target.closest(SELECTOR) : null;
    if (!btn || btn.disabled || btn.getAttribute('aria-disabled') === 'true') return;
    var rect = btn.getBoundingClientRect();
    var size = Math.max(rect.width, rect.height);
    var wave = document.createElement('span');
    wave.className = 'ripple';
    wave.style.cssText = 'width:' + size + 'px;height:' + size + 'px;left:' + (e.clientX - rect.left - size / 2) + 'px;top:' + (e.clientY - rect.top - size / 2) + 'px';
    btn.appendChild(wave);
    setTimeout(function () { if (wave.parentNode) wave.parentNode.removeChild(wave); }, 650);
  }, { passive: true });
})();
