// Showcase (0.47.0): the motion that CSS alone can't do. Loaded only for someone who picked the
// Showcase look. Four things, each skipped when it would be unwelcome:
//   glow      -- the page takes the dominant colour of its artwork (--sc-glow)
//   parallax  -- a banner's backdrop scrolls slower than the page (not on phones)
//   count-up  -- headline numbers ([data-count]) run up from zero
//   tilt      -- cards lean toward the pointer, with a glare (mouse and pen only)
// "Reduce motion" turns off all but the glow, which doesn't move.
(function () {
  'use strict';

  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var phone = window.matchMedia('(pointer: coarse), (max-width: 767px)').matches;
  var root = document.documentElement;

  // ------------------------------------------------------------ glow
  // TMDb's image server allows cross-origin reads, so a copy loaded with crossOrigin can be
  // sampled on a tiny canvas. Vivid pixels count for more than grey ones: a poster's colour is
  // its reds and greens, not the black around them.
  function glowFrom(src) {
    var img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = function () {
      try {
        var size = 24, canvas = document.createElement('canvas');
        canvas.width = size; canvas.height = size;
        var ctx = canvas.getContext('2d', { willReadFrequently: true });
        ctx.drawImage(img, 0, 0, size, size);
        var data = ctx.getImageData(0, 0, size, size).data;
        var r = 0, g = 0, b = 0, weight = 0;
        for (var i = 0; i < data.length; i += 4) {
          var max = Math.max(data[i], data[i + 1], data[i + 2]);
          var min = Math.min(data[i], data[i + 1], data[i + 2]);
          var w = (max - min) * (max / 255) + 1;   // saturation times brightness
          r += data[i] * w; g += data[i + 1] * w; b += data[i + 2] * w; weight += w;
        }
        r /= weight; g /= weight; b /= weight;
        // Its hue at a glow's brightness: Star Wars' backdrop averages near-black navy, which
        // as a glow is no glow at all.
        var lift = 210 / Math.max(r, g, b, 1);
        root.style.setProperty('--sc-glow', 'rgb(' + [r, g, b].map(function (c) {
          return Math.min(255, Math.round(c * lift));
        }).join(' ') + ')');
      } catch (e) { /* a tainted canvas or no 2D context: keep the theme's colour */ }
    };
    img.src = src;
  }

  // A small copy, not the one on the page: the browser keeps that one cached from a plain
  // (non-CORS) request, and reusing it for a cross-origin read fails. A different size is a
  // different URL, and a few kilobytes besides.
  var art = document.querySelector('.collection-backdrop, .collection-heading-poster img, img.collection-heading-poster, .poster-row-card img');
  if (art) {
    var size = art.classList.contains('collection-backdrop') ? 'w300' : 'w92';
    var src = (art.currentSrc || art.src || '').replace(/\/t\/p\/[^/]+\//, '/t/p/' + size + '/');
    if (src.indexOf('image.tmdb.org') !== -1) { glowFrom(src); }
  }

  // ------------------------------------------------------------ parallax
  var backdrop = document.querySelector('.collection-backdrop');
  if (backdrop && !reduce && !phone) {
    var band = backdrop.closest('.collection-heading');
    var ticking = false;
    var move = function () {
      ticking = false;
      var rect = band.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > window.innerHeight) { return; }
      // Up to 12% of the band's height either way: the image is 124% tall (showcase.css).
      var shift = Math.max(-0.12, Math.min(0.12, -rect.top / window.innerHeight * 0.25)) * rect.height;
      backdrop.style.translate = '0 ' + shift.toFixed(1) + 'px';
    };
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; window.requestAnimationFrame(move); }
    }, { passive: true });
    move();
  }

  // ------------------------------------------------------------ count-up
  if (!reduce) {
    document.querySelectorAll('[data-count]').forEach(function (el) {
      var text = el.textContent.trim();
      var target = parseInt(text.replace(/[^0-9]/g, ''), 10);
      if (!target || target < 2) { return; }
      var grouped = text.indexOf(',') !== -1;
      var start = performance.now(), duration = Math.min(1400, 500 + target * 4), done = false;
      var show = function (n) { el.textContent = grouped ? n.toLocaleString('en-US') : String(n); };
      // Timed from now, not from the first frame, and finished for good by the timeout: a tab
      // in the background gets few or no frames, and a late one mustn't undo the real number.
      var step = function () {
        if (done) { return; }
        var t = Math.min(1, (performance.now() - start) / duration);
        show(Math.round(target * (1 - Math.pow(1 - t, 3))));
        if (t < 1) { window.requestAnimationFrame(step); } else { done = true; }
      };
      show(0);
      window.requestAnimationFrame(step);
      window.setTimeout(function () { done = true; show(target); }, duration + 250);
    });
  }

  // ------------------------------------------------------------ tilt
  if (!reduce && !phone) {
    var CARDS = '.collection-card, .film-tile, .poster-row-card, .timeline-poster';
    var current = null;
    var release = function (card) {
      card.classList.remove('sc-tilting');
      card.style.removeProperty('--sc-rx'); card.style.removeProperty('--sc-ry');
    };
    document.addEventListener('pointermove', function (event) {
      if (event.pointerType === 'touch') { return; }
      var card = event.target.closest && event.target.closest(CARDS);
      if (current && current !== card) { release(current); current = null; }
      if (!card) { return; }
      current = card;
      var rect = card.getBoundingClientRect();
      var x = (event.clientX - rect.left) / rect.width, y = (event.clientY - rect.top) / rect.height;
      // Posters lean up to 4 degrees each way, wide cards 2.
      var tilt = rect.width > 260 ? 4 : 8;
      card.classList.add('sc-tilting');
      card.style.setProperty('--sc-rx', ((0.5 - y) * tilt).toFixed(2) + 'deg');
      card.style.setProperty('--sc-ry', ((x - 0.5) * tilt).toFixed(2) + 'deg');
      card.style.setProperty('--sc-gx', (x * 100).toFixed(1) + '%');
      card.style.setProperty('--sc-gy', (y * 100).toFixed(1) + '%');
    }, { passive: true });
    document.addEventListener('pointerleave', function () { if (current) { release(current); current = null; } });
  }
})();
