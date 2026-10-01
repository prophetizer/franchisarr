// Showcase (0.47.0-0.49.0): the motion that CSS alone can't do. Loaded only for someone who
// picked the Showcase look. Each part is skipped when it would be unwelcome:
//   glow       -- the page takes the dominant colour of its artwork (--sc-glow)
//   parallax   -- a banner's backdrop scrolls slower than the page (not on phones)
//   numbers    -- headline numbers ([data-count]) roll up digit by digit, like an odometer
//   spotlight  -- the home page's big banner turns (not with reduce motion)
//   row arrows -- poster rows slide a screen at a time (not on phones)
//   strip      -- the release-order strip plays when it comes on screen
//   transition -- the clicked poster grows into the next page (view transitions)
//   confetti   -- a collection just completed (not on phones)
//   tilt       -- cards lean toward the pointer, with a glare (mouse and pen only)
//   shrink     -- the spotlight shrinks to a strip as you scroll (not on phones)
//   fade-in    -- posters sharpen in as they load, a shimmer where they'll be
//   busy bar   -- a glow runs along the top while a button's request works
//   rings      -- a card's completeness as a ring; one film from done, a light runs round it
//   peek       -- pausing on a collection or franchise card previews what it's missing (not phones)
//   flip       -- a missing film's poster turns over to its plot
//   ambient    -- a blurred copy of the page's artwork lights the whole page (not phones)
//   seasons    -- October leaves on horror pages, December frost
//   quick find -- Ctrl+K (or Cmd+K) searches from anywhere
//   surprise   -- Surprise me's pick lands after a slot-machine spin of posters
//   reveal     -- cards glide up as they scroll into view, with a glint across each poster
//   motes      -- specks of light drift up through a banner (fewer on phones)
//   holo       -- rainbow foil on a complete collection's poster and on trophies
//   tab        -- a running scan's progress in the browser tab's icon and title
//   watermark  -- a banner's name, huge and outlined, behind it
//   mini bar   -- past a detail page's banner, a slim bar says what page this is
//   fan        -- a collection card fans three of its films out from behind its poster
//   (intros    -- the franchise intros are in showcase-intros.js since 0.58.0)
//   VHS        -- the Konami code turns the app into a worn videotape, and back
// "Reduce motion" turns off all but the glow, which doesn't move.
(function () {
  'use strict';

  // The app's address, from this script's own: everything is under BASE_URL.
  var script = document.currentScript;
  var base = script ? script.src.replace(/\/static\/showcase\.js.*$/, '') : '';
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var phone = window.matchMedia('(pointer: coarse), (max-width: 767px)').matches;
  var root = document.documentElement;
  // The Trophy case's gold (0.52.0). Set here, not in showcase.css, which holds no colour of its
  // own so that a theme can repaint everything; a trophy's gold is the one thing it shouldn't.
  root.style.setProperty('--sc-gold', 'rgb(232 186 84)');
  // The holographic finish's foil (0.56.0), set here for the same reason as the gold.
  root.style.setProperty('--sc-rainbow', 'linear-gradient(115deg, transparent 15%, rgb(255 60 150 / 0.7) 28%, ' +
    'rgb(255 214 60 / 0.7) 38%, rgb(60 255 180 / 0.7) 50%, rgb(60 170 255 / 0.7) 62%, rgb(180 80 255 / 0.7) 74%, transparent 87%)');

  // ------------------------------------------------------------ glow
  // TMDb's image server allows cross-origin reads, so a copy loaded with crossOrigin can be
  // sampled on a tiny canvas. Vivid pixels count for more than grey ones: a poster's colour is
  // its reds and greens, not the black around them.
  var heldGlow = false;   // a season has chosen the colour; the artwork doesn't get a say
  function glowFrom(src) {
    var img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = function () {
      if (heldGlow) { return; }
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
  function glowOf(art) {
    if (!art) { return; }
    var wide = art.classList.contains('collection-backdrop') || art.classList.contains('spotlight-backdrop');
    var src = (art.currentSrc || art.src || '').replace(/\/t\/p\/[^/]+\//, '/t/p/' + (wide ? 'w300' : 'w92') + '/');
    if (src.indexOf('image.tmdb.org') !== -1) {
      glowFrom(src);
      // Ambient light (0.51.0): the same small copy, blurred to nothing but colour behind the
      // page. Only a wide picture: a poster blown up to a screen is a smear, not a light.
      if (wide && !phone) { root.style.setProperty('--sc-ambient', 'url("' + src + '")'); }
    }
  }
  glowOf(document.querySelector('.collection-backdrop, .spotlight-slide.is-current .spotlight-backdrop, ' +
                                 '.collection-heading-poster img, img.collection-heading-poster, .poster-row-card img'));

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

  // ------------------------------------------------------------ rolling numbers (0.57.0)
  // Headline numbers roll up like an odometer: each digit a column of 0-9 sliding to its value,
  // the units first. Screen readers get the number itself; the columns are hidden from them.
  // (Until 0.57.0 they counted up, frame by frame.)
  if (!reduce) {
    document.querySelectorAll('[data-count]').forEach(function (el) {
      var text = el.textContent.trim();
      if (!/[0-9]/.test(text) || el.querySelector('.sc-odo')) { return; }
      var said = document.createElement('span');
      said.className = 'sc-sr';
      said.textContent = text;
      var odo = document.createElement('span');
      odo.className = 'sc-odo';
      odo.setAttribute('aria-hidden', 'true');
      var chars = text.split('');
      chars.forEach(function (ch, i) {
        if (!/[0-9]/.test(ch)) { var mark = document.createElement('span'); mark.textContent = ch; odo.appendChild(mark); return; }
        var column = document.createElement('span');
        column.className = 'sc-odo-col';
        column.style.setProperty('--sc-digit', ch);
        column.style.setProperty('--sc-wait', (0.1 * (chars.length - 1 - i)).toFixed(2) + 's');
        for (var d = 0; d < 10; d++) { var digit = document.createElement('span'); digit.textContent = String(d); column.appendChild(digit); }
        odo.appendChild(column);
      });
      el.textContent = '';
      el.append(said, odo);
      // Rolled once it's on the page (two frames), or by the timeout if frames are scarce.
      var roll = function () { odo.classList.add('is-rolled'); };
      window.requestAnimationFrame(function () { window.requestAnimationFrame(roll); });
      window.setTimeout(roll, 150);
    });
  }

  // ------------------------------------------------------------ spotlight (0.48.0)
  // The home page's big banner turns every seven seconds, pausing while pointed at or focused;
  // the dots choose a slide. "Reduce motion": no turning, the dots still work.
  var spot = document.querySelector('.spotlight');
  if (spot) {
    var slides = spot.querySelectorAll('.spotlight-slide');
    var dots = spot.querySelectorAll('.spotlight-dots button');
    var at = 0, paused = false;
    var go = function (n) {
      at = (n + slides.length) % slides.length;
      slides.forEach(function (slide, i) {
        var on = i === at;
        slide.classList.toggle('is-current', on);
        if (on) { slide.removeAttribute('aria-hidden'); slide.removeAttribute('tabindex'); }
        else { slide.setAttribute('aria-hidden', 'true'); slide.setAttribute('tabindex', '-1'); }
      });
      dots.forEach(function (dot, i) { dot.setAttribute('aria-selected', i === at ? 'true' : 'false'); });
      glowOf(slides[at].querySelector('.spotlight-backdrop'));   // the page's colour follows the slide
      pointTrailer();
    };
    // ▶ Trailer (0.54.0): the film that would finish the slide's set.
    var trailerButton = spot.querySelector('.spotlight-trailer');
    var pointTrailer = function () {
      if (!trailerButton) { return; }
      var slide = slides[at];
      // Not "and htmx": this file runs before htmx.min.js has (both deferred, this one first).
      trailerButton.hidden = !(slide && slide.dataset.trailer);
      if (!trailerButton.hidden) {
        trailerButton.textContent = '▶ Trailer: ' + slide.dataset.trailerTitle;
        trailerButton.setAttribute('aria-label', 'Play the trailer for ' + slide.dataset.trailerTitle);
      }
    };
    if (trailerButton) {
      trailerButton.addEventListener('click', function () {
        var slide = slides[at];
        if (slide && slide.dataset.trailer && window.htmx) {
          window.htmx.ajax('GET', slide.dataset.trailer, { target: '#trailer', swap: 'innerHTML' });
        }
      });
    }
    pointTrailer();
    dots.forEach(function (dot) {
      dot.addEventListener('click', function () { go(parseInt(dot.dataset.slide, 10)); });
    });
    ['mouseenter', 'focusin'].forEach(function (e) { spot.addEventListener(e, function () { paused = true; }); });
    ['mouseleave', 'focusout'].forEach(function (e) { spot.addEventListener(e, function () { paused = false; }); });
    if (!reduce && slides.length > 1) {
      window.setInterval(function () { if (!paused && !document.hidden) { go(at + 1); } }, 7000);
    }
  }

  // ------------------------------------------------------------ spotlight shrinks (0.50.0)
  // showcase.css does the sizing from two numbers: how far the page has scrolled (--sc-y) and
  // where the band starts (--sc-top), which it stays pinned to while it shrinks. Past the point
  // where it's a strip nothing changes, so the page stops being told.
  if (spot && !reduce && !phone) {
    var shrinking = false, lastY = -1;
    var place = function () {
      spot.style.setProperty('--sc-top', (spot.getBoundingClientRect().top + window.scrollY).toFixed(0) + 'px');
    };
    var shrink = function () {
      shrinking = false;
      var y = Math.min(Math.max(window.scrollY, 0), window.innerHeight);
      if (y !== lastY) { lastY = y; spot.style.setProperty('--sc-y', y.toFixed(0) + 'px'); }
    };
    place();
    shrink();
    window.addEventListener('scroll', function () {
      if (!shrinking) { shrinking = true; window.requestAnimationFrame(shrink); }
    }, { passive: true });
    window.addEventListener('resize', place);
    // Whatever sits above it can change height after load -- the scan status when a scan starts,
    // a Surprise me card (0.53.0) -- and the band must stay pinned where it now starts.
    if ('ResizeObserver' in window) {
      var main = spot.closest('main');
      if (main) { new ResizeObserver(place).observe(main); }
    }
  }

  // ------------------------------------------------------------ rows that glide (0.48.0)
  // Arrows on a poster row that runs off the screen, each sliding it most of a screen along.
  if (!phone) {
    document.querySelectorAll('.poster-row').forEach(function (row) {
      var list = row.querySelector('.poster-row-cards');
      if (!list) { return; }
      var arrows = [-1, 1].map(function (dir) {
        var b = document.createElement('button');
        b.type = 'button'; b.className = 'sc-row-nav'; b.dataset.dir = String(dir);
        b.setAttribute('aria-label', dir < 0 ? 'Scroll back' : 'Scroll on');
        b.textContent = dir < 0 ? '‹' : '›';
        b.addEventListener('click', function () { list.scrollBy({ left: dir * list.clientWidth * 0.8 }); });
        row.appendChild(b);
        return b;
      });
      var update = function () {
        arrows[0].hidden = list.scrollLeft < 8;
        arrows[1].hidden = list.scrollLeft + list.clientWidth > list.scrollWidth - 8;
      };
      list.addEventListener('scroll', update, { passive: true });
      window.addEventListener('resize', update);
      update();
    });
  }

  // ------------------------------------------------------------ the strip plays (0.48.0)
  // Armed now (posters hidden, ring empty), played when it's on screen: posters fly in in
  // release order, owned ones light up, the ring fills to how much of it you have.
  // Armed only when it can certainly be played: an observer, and a plain on-screen check at load
  // and on scroll besides -- a strip left armed and never played would be invisible.
  if (!reduce) {
    document.querySelectorAll('.timeline').forEach(function (strip) {
      var played = false, seen = null;
      var play = function () {
        if (played) { return; }
        played = true;
        strip.classList.add('sc-play');
        if (seen) { seen.disconnect(); }
        window.removeEventListener('scroll', check);
      };
      var check = function () {
        var rect = strip.getBoundingClientRect();
        if (rect.top < window.innerHeight * 0.9 && rect.bottom > 0) { play(); }
      };
      strip.classList.add('sc-armed');
      if ('IntersectionObserver' in window) {
        seen = new IntersectionObserver(function (entries) {
          if (entries.some(function (e) { return e.isIntersecting; })) { play(); }
        }, { threshold: 0.2 });
        seen.observe(strip);
      }
      window.addEventListener('scroll', check, { passive: true });
      window.setTimeout(check, 50);
    });
  }

  // ------------------------------------------------------------ poster grows into the page (0.48.0)
  // The page being left names the poster that was clicked, and the detail page names its own
  // (showcase.css): the browser morphs one into the other. A spotlight slide's backdrop becomes
  // the collection's banner the same way. One name per page, so it's set on the click only.
  document.addEventListener('click', function (event) {
    var link = event.target.closest && event.target.closest('a[href]');
    if (!link || event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey) { return; }
    var backdrop = link.classList.contains('spotlight-slide') && link.querySelector('.spotlight-backdrop');
    var poster = null;
    if (!backdrop) {
      // The link's own image, or -- for a card's title link -- the card's poster.
      poster = link.querySelector('img');
      var card = !poster && link.closest('.collection-card');
      if (card) { poster = card.querySelector('.collection-poster img'); }
    }
    // Back to a page from the browser's cache keeps the last click's name: two of a name and
    // the browser skips the transition, so clear any first.
    document.querySelectorAll('img[style*="view-transition-name"]').forEach(function (img) {
      img.style.viewTransitionName = '';
    });
    if (backdrop) { backdrop.style.viewTransitionName = 'sc-backdrop'; }
    else if (poster && !poster.closest('.collection-heading')) { poster.style.viewTransitionName = 'sc-poster'; }
  }, true);

  // Confetti themes (0.58.0): [name, colours, shape] for the franchises with intros.
  var CONFETTI = [
    [/harry potter|wizarding world|fantastic beasts/i, ['rgb(255 214 120)', 'rgb(255 245 210)', 'rgb(230 170 60)'], 'spark'],
    [/matrix/i, ['rgb(0 255 70)', 'rgb(170 255 180)'], 'glyph'],
    [/star wars/i, ['rgb(80 160 255)', 'rgb(255 60 60)', 'rgb(90 255 120)'], 'rod'],
    [/james bond/i, ['rgb(212 175 55)', 'rgb(240 240 240)', 'rgb(190 20 30)'], 'rect'],
    [/marvel cinematic|avengers collection/i, ['rgb(226 54 54)', 'rgb(255 210 80)', 'rgb(240 240 240)'], 'rect'],
    [/star trek/i, ['rgb(255 204 0)', 'rgb(0 130 255)', 'rgb(210 20 20)'], 'rect'],
    [/jurassic/i, ['rgb(255 170 30)', 'rgb(70 150 70)', 'rgb(200 40 30)'], 'rect'],
    [/back to the future/i, ['rgb(255 120 0)', 'rgb(255 210 60)', 'rgb(120 220 255)'], 'spark'],
    [/mission: impossible/i, ['rgb(255 150 30)', 'rgb(255 230 140)'], 'spark'],
    [/^alien|alien collection|alien vs/i, ['rgb(90 255 120)', 'rgb(30 160 70)'], 'spark'],
    [/batman|dark knight/i, ['rgb(255 215 0)', 'rgb(40 40 40)', 'rgb(240 240 240)'], 'rect'],
    [/jaws/i, ['rgb(120 200 255)', 'rgb(240 250 255)', 'rgb(30 90 160)'], 'spark'],
    [/terminator/i, ['rgb(255 30 30)', 'rgb(200 200 210)'], 'rod'],
    [/indiana jones/i, ['rgb(160 100 40)', 'rgb(230 190 90)', 'rgb(200 40 30)'], 'rect'],
    [/lord of the rings|hobbit|middle-earth/i, ['rgb(255 200 80)', 'rgb(255 120 30)'], 'spark'],
  ];

  // ------------------------------------------------------------ confetti (0.49.0)
  // A collection just completed: one burst from the top, a few seconds, then gone. Not on a
  // phone (a lighter look there) and not with reduce motion -- the message shows regardless.
  if (document.querySelector('[data-confetti]') && !reduce && !phone) {
    var canvas = document.createElement('canvas');
    canvas.className = 'sc-confetti';
    document.body.appendChild(canvas);
    var ctx2 = canvas.getContext('2d');
    var W = canvas.width = window.innerWidth, H = canvas.height = window.innerHeight;
    var glow = getComputedStyle(root).getPropertyValue('--sc-glow').trim() || 'gold';
    var primary = getComputedStyle(root).getPropertyValue('--pico-primary').trim() || 'deepskyblue';
    var colours = [glow, primary, 'gold', 'white', 'hotpink'];
    // Themed for the franchises that have an intro (0.58.0): the first one celebrated picks.
    var shape = 'rect';
    var said = document.querySelector('[data-confetti]').textContent;
    var themed = CONFETTI.filter(function (t) { return t[0].test(said); })[0];
    if (themed) { colours = themed[1]; shape = themed[2]; }
    var bits = [];
    for (var n = 0; n < 160; n++) {
      bits.push({
        x: W / 2 + (Math.random() - 0.5) * W * 0.3, y: -20 - Math.random() * H * 0.2,
        vx: (Math.random() - 0.5) * 9, vy: Math.random() * 4 + 2,
        size: Math.random() * 7 + 4, spin: Math.random() * Math.PI, turn: (Math.random() - 0.5) * 0.3,
        colour: colours[n % colours.length],
      });
    }
    var began = performance.now();
    var frame = function (now) {
      var age = now - began;
      ctx2.clearRect(0, 0, W, H);
      ctx2.globalAlpha = Math.max(0, Math.min(1, (4200 - age) / 900));
      bits.forEach(function (b) {
        b.vy += 0.12; b.vx *= 0.99; b.x += b.vx; b.y += b.vy; b.spin += b.turn;
        ctx2.save();
        ctx2.translate(b.x, b.y); ctx2.rotate(b.spin);
        ctx2.fillStyle = b.colour;
        if (shape === 'glyph') {
          ctx2.font = (b.size * 2.2).toFixed(0) + 'px monospace';
          ctx2.fillText(b.glyph || (b.glyph = '\u30a2\u30ab\u30b5\u30bf\u30ca01'[Math.floor(Math.random() * 7)]), 0, 0);
        } else if (shape === 'rod') {
          ctx2.shadowBlur = 8; ctx2.shadowColor = b.colour;
          ctx2.fillRect(-b.size * 1.6, -1, b.size * 3.2, 2);
        } else if (shape === 'spark') {
          ctx2.shadowBlur = 10; ctx2.shadowColor = b.colour;
          ctx2.beginPath(); ctx2.arc(0, 0, b.size / 3, 0, Math.PI * 2); ctx2.fill();
        } else {
          ctx2.fillRect(-b.size / 2, -b.size / 4, b.size, b.size / 2);
        }
        ctx2.restore();
      });
      if (age < 4200) { window.requestAnimationFrame(frame); } else { canvas.remove(); }
    };
    window.requestAnimationFrame(frame);
    window.setTimeout(function () { canvas.remove(); }, 6000);   // however few frames it got
  }

  // ------------------------------------------------------------ posters fade in (0.50.0)
  // An image still loading gets a shimmer (.sc-pending), and sharpens in when it arrives. One
  // already loaded -- from the cache, usually -- is left as it is, as are the images something
  // else animates: the spotlight's, the release strip's, and the detail page's own poster and
  // banner, which the page transition hands over from the page before.
  var OWN_MOTION = '.spotlight, .timeline, .collection-heading, .poster-wall';
  var soften = function (img) {
    if (img.dataset.scSoft || (img.complete && img.naturalWidth) || img.closest(OWN_MOTION)) { return; }
    img.dataset.scSoft = '1';
    img.classList.add('sc-pending');
    var arrived = function () {
      img.classList.remove('sc-pending');
      if (!reduce && img.naturalWidth) { img.classList.add('sc-arrived'); }
    };
    img.addEventListener('load', arrived, { once: true });
    img.addEventListener('error', arrived, { once: true });
  };
  var softenIn = function (el) {
    if (el.tagName === 'IMG') { soften(el); } else if (el.querySelectorAll) { el.querySelectorAll('main img').forEach(soften); }
  };
  softenIn(document);
  // htmx puts new content in (a panel, a list after a dismiss): the same for its images.
  document.addEventListener('htmx:load', function (event) {
    if (event.target.closest && event.target.closest('main')) { softenIn(event.target); }
  });

  // ------------------------------------------------------------ busy bar (0.50.0)
  // For a button's request -- an add, a scan, a sync, a form sent -- not for the page's own polls
  // (GETs), and only once it has taken a moment, so a quick one doesn't flash. A form that sends
  // the whole page away has nothing to say it's done: the next page doesn't have the bar on, and
  // one that never leaves (a download) is let go of after 20 seconds.
  var bar = document.createElement('div');
  bar.className = 'sc-busy';
  bar.setAttribute('aria-hidden', 'true');
  document.body.appendChild(bar);
  var working = new Set(), leaving = false, soon = null, giveUp = null;
  var paint = function () {
    var on = leaving || working.size > 0;
    window.clearTimeout(soon);
    if (on && !bar.classList.contains('is-on')) {
      soon = window.setTimeout(function () { bar.classList.add('is-on'); }, 150);
      window.clearTimeout(giveUp);
      giveUp = window.setTimeout(function () { working.clear(); leaving = false; paint(); }, 20000);
    } else if (!on) {
      bar.classList.remove('is-on');
      window.clearTimeout(giveUp);
    }
  };
  document.addEventListener('htmx:beforeRequest', function (event) {
    var config = event.detail && event.detail.requestConfig;
    if (!config || String(config.verb).toLowerCase() === 'get') { return; }
    working.add(event.detail.xhr);
    paint();
  });
  ['htmx:afterRequest', 'htmx:sendError', 'htmx:timeout', 'htmx:sendAbort'].forEach(function (name) {
    document.addEventListener(name, function (event) {
      if (event.detail && working.delete(event.detail.xhr)) { paint(); }
    });
  });
  // Last in line, so it sees whether a confirm() said no or htmx took the form over.
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (event.defaultPrevented || (form.target && form.target !== '_self')) { return; }
    leaving = true;
    paint();
  });
  window.addEventListener('pageshow', function () { working.clear(); leaving = false; paint(); });

  // ------------------------------------------------------------ rings and the almost-there light (0.51.0)
  // Each card's completeness bar gets a ring beside it; a card one film from done gets a light
  // running round its border. Both read the bar itself, so any card with one gets them.
  var ringsIn = function (scope) {
    scope.querySelectorAll('.collection-card progress.completeness').forEach(function (bar) {
      if (bar.closest('.sc-meter')) { return; }
      var have = Number(bar.value), all = Number(bar.max);
      if (!all) { return; }
      var meter = document.createElement('span');
      meter.className = 'sc-meter';
      bar.parentNode.insertBefore(meter, bar);
      meter.appendChild(bar);
      var ring = document.createElement('span');
      ring.className = 'sc-ring';
      ring.setAttribute('aria-hidden', 'true');   // the bar already says it
      ring.style.setProperty('--sc-p', (have / all).toFixed(3));
      var label = document.createElement('span');
      label.textContent = Math.floor(have * 100 / all) + '%';
      ring.appendChild(label);
      meter.appendChild(ring);
      if (all - have === 1) { bar.closest('.collection-card').classList.add('sc-almost'); }
    });
  };
  ringsIn(document);

  // ------------------------------------------------------------ peek (0.51.0)
  // Pausing on a collection or franchise card opens a preview over it: its backdrop and the
  // posters it's missing, copied out of the card's inert <template>. Mouse and pen only.
  if (!phone) {
    var peeking = null, peekTimer = null, waitingOn = null;
    var closePeek = function () {
      window.clearTimeout(peekTimer);
      waitingOn = null;
      if (peeking) { peeking.remove(); peeking = null; }
    };
    document.addEventListener('pointerover', function (event) {
      if (event.pointerType === 'touch') { return; }
      var card = event.target.closest && event.target.closest('.collection-card');
      var template = card && card.querySelector(':scope > template.sc-peek');
      if (!template || card === waitingOn) { return; }   // already open, or about to be
      closePeek();
      waitingOn = card;
      peekTimer = window.setTimeout(function () {
        var pop = document.createElement('div');
        pop.className = 'sc-peek-pop';
        pop.setAttribute('aria-hidden', 'true');   // the card itself says all of this
        pop.appendChild(template.content.cloneNode(true));
        document.body.appendChild(pop);
        var rect = card.getBoundingClientRect(), width = pop.offsetWidth;
        var left = Math.max(8, Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - 8));
        // Above the card when there's room (clear of the pinned top bar), else below it; with
        // room for neither, the roomier side, kept on screen even if it covers part of the card.
        var height = pop.offsetHeight, bar = 100;
        var above = rect.top - bar, below = window.innerHeight - rect.bottom;
        var top = height + 10 <= above ? rect.top - height - 10
          : height + 10 <= below ? rect.bottom + 10
            : above > below ? Math.max(bar, rect.top - height - 10)
              : Math.min(rect.bottom + 10, window.innerHeight - height - 8);
        pop.style.left = (left + window.scrollX) + 'px';
        pop.style.top = (top + window.scrollY) + 'px';
        peeking = pop;
      }, 550);
    });
    document.addEventListener('pointerout', function (event) {
      var card = event.target.closest && event.target.closest('.collection-card');
      if (card && !card.contains(event.relatedTarget)) { closePeek(); }
    });
    window.addEventListener('scroll', closePeek, { passive: true });
  }

  // ------------------------------------------------------------ flip (0.51.0)
  // A missing film's poster turns the card over: its plot, genres and score on the back, with
  // the card's own buttons. A click or tap on the poster does it, or resting the pointer there;
  // the pointer leaving the card, or the ↺, turns it back. The back is fetched once, when first
  // needed. The turn is a transition of `rotate` -- a swapped animation would replay the card's
  // entrance -- and the faces change over at its midpoint, edge-on.
  var turn = function (card, over) {
    if (card.classList.contains('sc-flipped') === over) { return; }
    if (over && !card.querySelector(':scope > .sc-back')) { card.appendChild(backOf(card)); }
    var swap = function () {
      card.classList.toggle('sc-flipped', over);
      card.classList.remove('sc-turning');
    };
    if (reduce) { swap(); return; }
    card.classList.add('sc-turning');
    var done = false;
    var half = function () { if (!done) { done = true; swap(); } };
    card.addEventListener('transitionend', function end(event) {
      if (event.propertyName === 'rotate') { card.removeEventListener('transitionend', end); half(); }
    });
    window.setTimeout(half, 400);   // a transition that never ends is still over
  };
  var backOf = function (card) {
    var back = document.createElement('div');
    back.className = 'sc-back';
    var title = document.createElement('strong');
    title.className = 'sc-back-title';
    var front = card.querySelector('.film-title');
    title.textContent = front ? front.textContent : '';
    var body = document.createElement('div');
    body.className = 'sc-back-body';
    body.innerHTML = '<p class="sc-back-plot muted">…</p>';
    var again = document.createElement('button');
    again.type = 'button';
    again.className = 'sc-back-turn secondary outline';
    again.setAttribute('aria-label', 'Turn back');
    again.textContent = '↺';
    again.addEventListener('click', function () { turn(card, false); });
    back.append(again, title, body);
    var actions = card.querySelector(':scope > .card-actions');
    if (actions) {
      var copy = actions.cloneNode(true);
      copy.querySelectorAll('[id]').forEach(function (el) { el.removeAttribute('id'); });
      back.appendChild(copy);
      if (window.htmx) { window.htmx.process(copy); }
    }
    fetch(base + '/about/' + card.dataset.about, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(r.status); })
      .then(function (html) { body.innerHTML = html; })
      .catch(function () { body.innerHTML = '<p class="sc-back-plot muted">Couldn\u2019t fetch the details just now.</p>'; });
    return back;
  };
  var flipsIn = function (scope) {
    scope.querySelectorAll('.film-tile[data-about] > .collection-poster').forEach(function (poster) {
      if (poster.dataset.scFlip) { return; }
      poster.dataset.scFlip = '1';
      var card = poster.parentNode, rest = null, away = null;
      poster.setAttribute('role', 'button');
      poster.setAttribute('tabindex', '0');
      poster.setAttribute('aria-label', 'Show what it\u2019s about');
      poster.addEventListener('click', function () { turn(card, !card.classList.contains('sc-flipped')); });
      poster.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); turn(card, true); }
      });
      poster.addEventListener('pointerenter', function (event) {
        if (event.pointerType !== 'mouse') { return; }
        rest = window.setTimeout(function () { turn(card, true); }, 700);
      });
      poster.addEventListener('pointerleave', function () { window.clearTimeout(rest); });
      card.addEventListener('pointerenter', function () { window.clearTimeout(away); });
      card.addEventListener('pointerleave', function (event) {
        if (event.pointerType !== 'mouse') { return; }
        away = window.setTimeout(function () { turn(card, false); }, 350);
      });
    });
  };
  flipsIn(document);
  // A dismiss re-renders the missing list: its new cards want rings and flips too.
  document.addEventListener('htmx:load', function (event) {
    if (event.target.querySelectorAll) { ringsIn(event.target); flipsIn(event.target); }
  });

  // ------------------------------------------------------------ seasons (0.51.0)
  // October: a horror collection or franchise glows pumpkin and a few leaves fall, once. December:
  // frost along the top bar, and a little snow on the home page. `?season=10` tries a month out.
  var tried = /[?&]season=(\d{1,2})\b/.exec(window.location.search);
  var month = tried ? parseInt(tried[1], 10) - 1 : new Date().getMonth();
  var fall = function (marks, count) {
    if (reduce) { return; }
    var sky = document.createElement('div');
    sky.className = 'sc-sky';
    sky.setAttribute('aria-hidden', 'true');
    for (var n = 0; n < (phone ? Math.ceil(count / 2) : count); n++) {
      var bit = document.createElement('span');
      bit.textContent = marks[n % marks.length];
      bit.style.setProperty('--sc-x', (Math.random() * 100).toFixed(1) + 'vw');
      bit.style.setProperty('--sc-sway', ((Math.random() - 0.5) * 30).toFixed(1) + 'vw');
      bit.style.setProperty('--sc-wait', (Math.random() * 6).toFixed(2) + 's');
      bit.style.setProperty('--sc-fall', (9 + Math.random() * 7).toFixed(2) + 's');
      bit.style.setProperty('--sc-size', (0.9 + Math.random() * 0.9).toFixed(2) + 'rem');
      sky.appendChild(bit);
    }
    document.body.appendChild(sky);
    window.setTimeout(function () { sky.remove(); }, 24000);
  };
  if (month === 9 && document.querySelector('[data-sc-horror]')) {
    heldGlow = true;
    root.classList.add('sc-october');
    root.style.setProperty('--sc-glow', 'rgb(255 132 24)');
    fall(['🍂', '🍁', '🍂'], 12);
  } else if (month === 11) {
    root.classList.add('sc-december');
    if (spot) { fall(['❄', '❅', '❆'], 16); }
  }

  // ------------------------------------------------------------ quick find (0.51.0)
  // Ctrl+K or Cmd+K opens a search box over the page; results arrive as you type (the search
  // page's own, one line each) and the arrow keys and Enter pick one.
  var finder = null;
  var openFinder = function () {
    if (!window.htmx) { window.location.href = base + '/search'; return; }
    if (!finder) {
      finder = document.createElement('dialog');
      finder.className = 'sc-quick';
      finder.setAttribute('aria-label', 'Quick search');
      finder.innerHTML = '<article><input type="search" name="q" autocomplete="off" ' +
        'placeholder="Collection, franchise, director, film or show" aria-label="Search">' +
        '<a class="sc-quick-surprise" href="' + base + '/?surprise=1">🎲 Surprise me ' +
        '<small class="muted">a well-rated film you\u2019re missing</small></a>' +
        '<div id="quick-results"></div><p class="sc-quick-keys"><small class="muted">' +
        '↑ ↓ to choose · Enter to go · Esc to close</small></p></article>';
      var box = finder.querySelector('input');
      box.setAttribute('hx-get', base + '/search');
      box.setAttribute('hx-trigger', 'input changed delay:200ms, search');
      box.setAttribute('hx-target', '#quick-results');
      box.setAttribute('hx-sync', 'this:replace');
      document.body.appendChild(finder);
      window.htmx.process(finder);
      var links = function () { return Array.prototype.slice.call(finder.querySelectorAll('.sc-quick-list a')); };
      finder.addEventListener('keydown', function (event) {
        var all = links(), at = all.indexOf(document.activeElement);
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault();
          if (!all.length) { return; }
          var next = event.key === 'ArrowDown' ? at + 1 : at - 1;
          if (next < 0) { box.focus(); } else { all[Math.min(next, all.length - 1)].focus(); }
        } else if (event.key === 'Enter' && event.target === box && all.length) {
          event.preventDefault();
          all[0].click();
        }
      });
      finder.addEventListener('click', function (event) { if (event.target === finder) { finder.close(); } });
    }
    finder.showModal();
    var input = finder.querySelector('input');
    input.focus();
    input.select();
  };
  document.addEventListener('keydown', function (event) {
    if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      openFinder();
    }
  });
  document.querySelectorAll('a.nav-search').forEach(function (link) {
    link.title = (link.title ? link.title + ' ' : 'Search ') + '(Ctrl+K)';
  });

  // ------------------------------------------------------------ surprise (0.53.0)
  // The pick arrives with the posters to roll past (data-reel). They run down a window over its
  // poster, slowing like a reel, and land on it; its details come up once it has.
  document.addEventListener('htmx:afterSwap', function (event) {
    var card = event.target.id === 'surprise-card' && event.target.querySelector('.surprise-card[data-reel]');
    if (!card || reduce) { return; }
    var reel;
    try { reel = JSON.parse(card.dataset.reel || '[]'); } catch (e) { reel = []; }
    var frame = card.querySelector('.surprise-poster');
    var final = frame && frame.querySelector('img');
    if (!reel.length || !final || !frame.animate) { return; }
    var body = card.querySelector('.surprise-body');
    var slot = document.createElement('div');
    slot.className = 'sc-slot';
    slot.setAttribute('aria-hidden', 'true');
    var strip = document.createElement('div');
    strip.className = 'sc-slot-strip';
    reel.concat([final.currentSrc || final.src]).forEach(function (src) {
      var img = document.createElement('img');
      img.src = src; img.alt = ''; img.decoding = 'async';
      strip.appendChild(img);
    });
    slot.appendChild(strip);
    frame.appendChild(slot);
    body.classList.add('sc-hold');
    var ended = false;
    var land = function () {
      if (ended) { return; }
      ended = true;
      slot.remove();
      body.classList.remove('sc-hold');
    };
    var steps = reel.length;
    strip.animate([{ translate: '0 0' }, { translate: '0 ' + (-100 * steps / (steps + 1)).toFixed(3) + '%' }],
                  { duration: 1900, easing: 'cubic-bezier(0.12, 0.6, 0.15, 1)', fill: 'forwards' })
      .finished.then(land, land);
    window.setTimeout(land, 2600);   // however few frames it got
  });

  // ------------------------------------------------------------ reveal (0.56.0)
  // Cards and poster-row entries glide up as they come into view, in small staggered batches.
  // One is only veiled once something can certainly reveal it: an observer, with an on-screen
  // check at load and on scroll behind it (the browser pane has been known to skip observers).
  if (!reduce && 'IntersectionObserver' in window) {
    var REVEAL = '.collection-grid > *, .poster-row-cards > li';
    var batch = [], batchTimer = null;
    var flush = function () {
      batchTimer = null;
      batch.forEach(function (el, i) {
        el.style.setProperty('--sc-d', (Math.min(i, 10) * 0.05).toFixed(2) + 's');
        el.classList.add('sc-seen');
      });
      batch = [];
    };
    var reveal = function (el) {
      if (el.classList.contains('sc-seen') || batch.indexOf(el) !== -1) { return; }
      batch.push(el);
      if (!batchTimer) { batchTimer = window.setTimeout(flush, 30); }
    };
    var watcher = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { reveal(e.target); watcher.unobserve(e.target); } });
    }, { rootMargin: '0px 0px -4% 0px' });
    var veil = function (scope) {
      scope.querySelectorAll(REVEAL).forEach(function (el) {
        if (el.dataset.scVeiled) { return; }
        el.dataset.scVeiled = '1';
        el.classList.add('sc-veiled');
        watcher.observe(el);
      });
    };
    var sweep = function () {
      document.querySelectorAll('.sc-veiled:not(.sc-seen)').forEach(function (el) {
        var rect = el.getBoundingClientRect();
        if (rect.top < window.innerHeight && rect.bottom > 0) { reveal(el); }
      });
    };
    veil(document);
    window.setTimeout(sweep, 80);
    var sweeping = false;
    window.addEventListener('scroll', function () {
      if (!sweeping) { sweeping = true; window.setTimeout(function () { sweeping = false; sweep(); }, 150); }
    }, { passive: true });
    document.addEventListener('htmx:load', function (event) {
      if (event.target.querySelectorAll) { veil(event.target); window.setTimeout(sweep, 80); }
    });
  }

  // ------------------------------------------------------------ banner layer (0.56.0, 0.57.0)
  // Between a banner's picture and its text: the name, huge and outlined (0.57.0), and a few
  // specks of light rising and fading at their own pace (0.56.0; not with reduce motion).
  document.querySelectorAll('.collection-heading.has-backdrop').forEach(function (band) {
    var layer = document.createElement('div');
    layer.className = 'sc-motes';
    layer.setAttribute('aria-hidden', 'true');
    var heading = band.querySelector('h1');
    var logo = heading && heading.querySelector('img');
    var name = logo ? logo.alt : (heading ? heading.textContent.trim() : '');
    if (name) {
      var mark = document.createElement('span');
      mark.className = 'sc-watermark';
      mark.textContent = name.replace(/\s+collection$/i, '');
      layer.appendChild(mark);
    }
    for (var n = 0; n < (reduce ? 0 : phone ? 6 : 16); n++) {
      var mote = document.createElement('span');
      var t = 9 + Math.random() * 10;
      mote.style.setProperty('--sc-x', (Math.random() * 100).toFixed(1) + '%');
      mote.style.setProperty('--sc-y', (45 + Math.random() * 55).toFixed(1) + '%');
      mote.style.setProperty('--sc-size', (2 + Math.random() * 5).toFixed(1) + 'px');
      mote.style.setProperty('--sc-t', t.toFixed(1) + 's');
      mote.style.setProperty('--sc-wait', (-Math.random() * t).toFixed(1) + 's');   // already on its way
      mote.style.setProperty('--sc-dx', ((Math.random() - 0.5) * 6).toFixed(1) + 'rem');
      layer.appendChild(mote);
    }
    band.appendChild(layer);   // under the content (z-index 1), over the picture and its shading
  });

  // ------------------------------------------------------------ holo (0.56.0)
  // Rainbow foil on a complete collection's or franchise's poster, and on every trophy, the
  // light moving as the pointer does. An <img> can't carry the foil layer, so it's wrapped.
  var foil = function (el) {
    el.classList.add('sc-holo');
    el.addEventListener('pointermove', function (event) {
      var rect = el.getBoundingClientRect();
      el.style.setProperty('--sc-hx', ((event.clientX - rect.left) / rect.width * 100).toFixed(1) + '%');
      el.style.setProperty('--sc-hy', ((event.clientY - rect.top) / rect.height * 100).toFixed(1) + '%');
    });
  };
  document.querySelectorAll('.collection-heading[data-complete] .collection-heading-poster').forEach(function (poster) {
    if (poster.tagName === 'IMG') {
      var wrap = document.createElement('span');
      wrap.className = 'sc-holo-wrap';
      poster.parentNode.insertBefore(wrap, poster);
      wrap.appendChild(poster);
      foil(wrap);
    } else {
      foil(poster);   // a mosaic is a block already
    }
  });
  document.querySelectorAll('.trophy-frame').forEach(foil);

  // ------------------------------------------------------------ tab (0.56.0)
  // While a scan runs (the scan status box is on the page), the tab's icon becomes a ring
  // filling to its progress and the title leads with the percentage; both go back after.
  var icon = document.querySelector('link[rel="icon"]');
  var plainIcon = icon ? icon.getAttribute('href') : null, plainTitle = document.title;
  var glowColour = function () {
    var probe = document.createElement('span');
    probe.style.color = 'var(--sc-glow)';
    document.body.appendChild(probe);
    var colour = getComputedStyle(probe).color;
    probe.remove();
    return colour;
  };
  var tabProgress = function () {
    var status = document.getElementById('scan-status');
    var bar = status && status.querySelector('progress');
    var running = !!(status && status.hasAttribute('hx-trigger') && bar);
    if (!running) {
      document.title = plainTitle;
      if (icon && plainIcon) { icon.setAttribute('href', plainIcon); icon.setAttribute('type', 'image/svg+xml'); }
      return;
    }
    var known = bar.hasAttribute('max') && Number(bar.max) > 0;
    var share = known ? Math.min(1, Number(bar.value) / Number(bar.max)) : null;
    document.title = (share === null ? 'Scanning' : Math.round(share * 100) + '%') + ' · ' + plainTitle;
    if (!icon) { return; }
    var size = 64, c = document.createElement('canvas');
    c.width = c.height = size;
    var g = c.getContext('2d');
    if (!g) { return; }
    var colour = glowColour();
    g.lineWidth = 9;
    g.strokeStyle = 'rgba(128, 128, 128, 0.35)';
    g.beginPath(); g.arc(32, 32, 26, 0, Math.PI * 2); g.stroke();
    g.strokeStyle = colour;
    g.lineCap = 'round';
    g.beginPath();
    var start = -Math.PI / 2;
    g.arc(32, 32, 26, start, start + Math.PI * 2 * (share === null ? 0.3 : Math.max(0.04, share)));
    g.stroke();
    g.fillStyle = colour;
    g.beginPath(); g.arc(32, 32, 9, 0, Math.PI * 2); g.fill();
    icon.setAttribute('type', 'image/png');
    icon.setAttribute('href', c.toDataURL('image/png'));
  };
  tabProgress();
  // The status box replaces itself every two seconds while a scan runs.
  document.addEventListener('htmx:afterSettle', tabProgress);

  // An element's words as a reader sees them: a rolled number's digit columns left out.
  function plainText(el) {
    if (!el) { return ''; }
    var copy = el.cloneNode(true);
    copy.querySelectorAll('.sc-odo').forEach(function (odo) { odo.remove(); });
    return copy.textContent.replace(/\s+/g, ' ').trim();
  }

  // ------------------------------------------------------------ mini bar (0.57.0)
  // Once a detail page's banner has scrolled away, a slim bar slides out from under the top
  // bar: its poster, its name, how much of it you have.
  var heading = document.querySelector('.collection-heading');
  if (heading) {
    var title = heading.querySelector('h1');
    var titleLogo = title && title.querySelector('img');
    var label = titleLogo ? titleLogo.alt : (title ? title.textContent.trim() : '');
    var poster = heading.querySelector('img.collection-heading-poster, .collection-heading-poster img');
    var line = heading.querySelector('hgroup p');
    if (label) {
      var mini = document.createElement('div');
      mini.className = 'sc-mini';
      mini.setAttribute('aria-hidden', 'true');   // the page's own heading says all this
      var inner = document.createElement('div');
      inner.className = 'container';
      if (poster) { var thumb = document.createElement('img'); thumb.src = poster.currentSrc || poster.src; thumb.alt = ''; inner.appendChild(thumb); }
      var strong = document.createElement('strong'); strong.textContent = label; inner.appendChild(strong);
      if (line) {
        var small = document.createElement('small');
        small.textContent = plainText(line).split('.')[0];
        inner.appendChild(small);
      }
      mini.appendChild(inner);
      document.body.appendChild(mini);
      var bar = document.querySelector('body > header');
      var placeMini = function () {
        if (bar) { mini.style.setProperty('--sc-mini-top', Math.round(bar.getBoundingClientRect().height) + 'px'); }
      };
      var checkMini = function () {
        mini.classList.toggle('is-on', heading.getBoundingClientRect().bottom < (bar ? bar.getBoundingClientRect().height : 0));
      };
      placeMini();
      checkMini();
      window.addEventListener('scroll', checkMini, { passive: true });
      window.addEventListener('resize', placeMini);
    }
  }

  // ------------------------------------------------------------ fan (0.57.0)
  // A collection card's <template> holds three of its films; they sit stacked behind its poster
  // and fan out when the card is pointed at (showcase.css). Laid out once, on first approach.
  if (!phone) {
    document.addEventListener('pointerover', function (event) {
      var card = event.target.closest && event.target.closest('.collection-card');
      var template = card && card.querySelector(':scope > template.sc-fan');
      if (!template || card.querySelector(':scope > .sc-fanned')) { return; }   // not .sc-fan: that's the template
      var poster = card.querySelector(':scope > .collection-poster');
      if (!poster) { return; }
      var fan = document.createElement('div');
      fan.className = 'sc-fanned';
      fan.setAttribute('aria-hidden', 'true');
      fan.appendChild(template.content.cloneNode(true));
      fan.style.left = poster.offsetLeft + 'px';
      fan.style.top = poster.offsetTop + 'px';
      fan.style.width = poster.offsetWidth + 'px';
      fan.style.height = poster.offsetHeight + 'px';
      card.insertBefore(fan, poster);
    });
  }

  // ------------------------------------------------------------ intros
  // The franchise intros live in showcase-intros.js (0.58.0), loaded after this file.

  // ------------------------------------------------------------ VHS (0.57.0)
  // Up, up, down, down, left, right, left, right, B, A: the app becomes a worn videotape until
  // the same again. Kept in this browser only; it's a game, not a setting.
  var vhsOn = function (on, fresh) {
    root.classList.toggle('sc-vhs', on);
    root.style.setProperty('--sc-vhs-a', 'rgb(255 40 80 / 0.55)');
    root.style.setProperty('--sc-vhs-b', 'rgb(40 200 255 / 0.55)');
    var band = document.querySelector('.sc-vhs-band');
    if (on && !band && !reduce) {
      band = document.createElement('div'); band.className = 'sc-vhs-band'; band.setAttribute('aria-hidden', 'true');
      document.body.appendChild(band);
    } else if (!on && band) { band.remove(); }
    if (on) {
      var osd = document.createElement('div');
      osd.className = 'sc-vhs-osd'; osd.setAttribute('aria-hidden', 'true');
      osd.textContent = fresh ? '\u25b6 PLAY' : 'SP \u25b6';
      document.body.appendChild(osd);
      window.setTimeout(function () { osd.remove(); }, 3600);
    }
  };
  try { if (window.localStorage.getItem('sc-vhs') === '1') { vhsOn(true, false); } } catch (e) { /* off */ }
  var KONAMI = ['arrowup', 'arrowup', 'arrowdown', 'arrowdown', 'arrowleft', 'arrowright', 'arrowleft', 'arrowright', 'b', 'a'];
  var typed = [];
  document.addEventListener('keydown', function (event) {
    var t = event.target;
    if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) { return; }
    typed.push(String(event.key).toLowerCase());
    typed = typed.slice(-KONAMI.length);
    if (typed.join(' ') === KONAMI.join(' ')) {
      typed = [];
      var on = !root.classList.contains('sc-vhs');
      vhsOn(on, true);
      try { window.localStorage.setItem('sc-vhs', on ? '1' : '0'); } catch (e) { /* this page only */ }
    }
  });

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
