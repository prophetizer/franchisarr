// Showcase (0.47.0-0.49.0): the motion that CSS alone can't do. Loaded only for someone who
// picked the Showcase look. Each part is skipped when it would be unwelcome:
//   glow       -- the page takes the dominant colour of its artwork (--sc-glow)
//   parallax   -- a banner's backdrop scrolls slower than the page (not on phones)
//   count-up   -- headline numbers ([data-count]) run up from zero
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
    };
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
        ctx2.fillRect(-b.size / 2, -b.size / 4, b.size, b.size / 2);
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
  var OWN_MOTION = '.spotlight, .timeline, .collection-heading';
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
