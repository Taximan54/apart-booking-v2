// Фото-полосы и «набор» цифр (включается классом fx-bands на <body>; см. premium.css)
(function () {
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches, started = false;
  function photos() {
    return [].map.call(document.querySelectorAll('.gitem img'), function (i) { return i.getAttribute('src'); }).filter(Boolean);
  }
  function setBg(el, src) { el.style.backgroundImage = 'url("' + src.replace(/"/g, '%22') + '")'; }
  function countUp(el) {
    var raw = el.textContent.trim();
    if (reduce || !/^\d+([.,]\d+)?$/.test(raw)) return;
    var dec = (raw.split(/[.,]/)[1] || '').length, to = parseFloat(raw.replace(',', '.')), t0 = performance.now();
    (function step(t) {
      var k = Math.min(1, (t - t0) / 1400), v = to * (1 - Math.pow(1 - k, 3));
      el.textContent = k < 1 ? (dec ? v.toFixed(dec) : String(Math.round(v))) : raw;
      if (k < 1) requestAnimationFrame(step);
    })(t0);
  }
  function parallax() {
    if (reduce) return;
    [].forEach.call(document.querySelectorAll('.cp-band-bg'), function (b) {
      var r = b.parentElement.getBoundingClientRect();
      if (r.bottom < 0 || r.top > innerHeight) return;
      b.style.transform = 'translateY(' + ((r.top + r.height / 2 - innerHeight / 2) * -0.14) + 'px)';
    });
  }
  function build() {
    var ph = photos(), about = document.getElementById('about'), booking = document.getElementById('booking');
    var card = document.querySelector('#reviewsGrid .review-card');
    if (about && ph.length && !about.querySelector('.cp-band-bg')) {
      var bg = document.createElement('div'); bg.className = 'cp-band-bg'; setBg(bg, ph[1] || ph[0]); about.insertBefore(bg, about.firstChild);
    }
    if (booking && card && ph.length && !document.querySelector('.cp-quote-band')) {
      var t = card.querySelector('.review-text'), a = card.querySelector('.review-author');
      var text = t ? t.textContent.trim() : '';
      if (text) {
        var s = document.createElement('section'); s.className = 'cp-quote-band';
        var b2 = document.createElement('div'); b2.className = 'cp-band-bg'; setBg(b2, ph[2] || ph[0]);
        var inn = document.createElement('div'); inn.className = 'cp-quote-in';
        var q = document.createElement('div'); q.className = 'cp-quote'; q.textContent = '«' + text + '»';
        var by = document.createElement('span'); by.className = 'cp-quote-by'; by.textContent = a ? '— ' + a.textContent.trim() : '— отзыв гостя';
        inn.appendChild(q); inn.appendChild(by); s.appendChild(b2); s.appendChild(inn);
        booking.parentNode.insertBefore(s, booking);
      }
    }
    parallax();
    return !!document.querySelector('#about .cp-band-bg') && !!document.querySelector('.cp-quote-band');
  }
  function start() {
    if (started || !document.body.classList.contains('fx-bands')) return;
    started = true;
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { countUp(e.target); io.unobserve(e.target); } });
    }, { threshold: .4 });
    [].forEach.call(document.querySelectorAll('#about .stat-num'), function (el) { io.observe(el); });
    var n = 0, timer = setInterval(function () { if (build() || ++n > 30) clearInterval(timer); }, 600);
    addEventListener('scroll', function () { requestAnimationFrame(parallax); }, { passive: true });
  }
  start();
  new MutationObserver(start).observe(document.body, { attributes: true, attributeFilter: ['class'] });
})();
