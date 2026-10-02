// Showcase's franchise intros (0.57.0; their own file since 0.58.0; nineteen since 0.59.0): a nod to a franchise's films
// when its page opens -- once per visit to each page, skipped by a click or any key, and replayed
// from the ▶ Intro button. Off for anyone who turned them off in their menu (data-intros="off")
// and with "reduce motion". The words are this app's own; the looks are the films'.
//
// Each intro gets a curtain (a full-screen layer) and the page's facts: its name, how much of it
// is owned, the missing titles, the release-order strip's posters and years.
(function () {
  'use strict';

  var root = document.documentElement;
  if (root.dataset.look !== 'showcase') { return; }
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  // The intro mark's clapperboard: dark on the gold badge in any theme (0.61.1).
  root.style.setProperty('--sc-mark-ink', 'rgb(46 30 6)');

  // Which franchise a page is, by its name. The first match wins, so the specific ones come first.
  var WHICH = [
    [/star wars/i, 'crawl'],
    [/matrix/i, 'rain'],
    [/harry potter|wizarding world|fantastic beasts/i, 'sparks'],
    [/marvel cinematic universe|^the avengers collection$/i, 'flip'],
    [/james bond/i, 'barrel'],
    [/star trek/i, 'warp'],
    [/jurassic (park|world)/i, 'ripple'],
    [/back to the future/i, 'circuits'],
    [/mission: impossible/i, 'fuse'],
    [/^alien\b/i, 'tracker'],
    [/batman|dark knight/i, 'signal'],
    [/^jaws\b/i, 'fin'],
    [/terminator/i, 'hud'],
    [/indiana jones/i, 'map'],
    [/lord of the rings|hobbit|middle-earth/i, 'ring'],
    [/ghostbusters/i, 'slime'],
    [/godzilla|monsterverse/i, 'footsteps'],
    [/mad max|furiosa/i, 'storm'],
    [/toy story/i, 'clouds'],
  ];
  function introFor(name) { return WHICH.filter(function (w) { return w[0].test(name); })[0]; }

  // ------------------------------------------------------------ marks (0.61.0)
  // A clapperboard on every card for a collection or franchise whose page opens with an intro: the lists'
  // posters (and so their shelf spines), the home page's rows and spotlight, the Trophy case,
  // search and Ctrl+K. Not for someone who switched intros off -- ▶ Intro still works for them.
  var SET_PAGE = /\/(collections\/\d+|franchises\/Q\d+)\/?(?:[?#]|$)/;
  var badge = function () {
    var mark = document.createElement('span');
    mark.className = 'sc-intro-mark';
    // A drawn clapperboard, not the 🎬 emoji: not every system has a colour emoji font.
    mark.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round">' +
      '<path d="M4 11h16v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"/>' +
      '<path d="M4 11 3.3 7.6a1 1 0 0 1 .8-1.2l13.7-2.8a1 1 0 0 1 1.2.8L19.6 7.8z"/>' +
      '<path d="m7.6 6.2 2.6 3.3M12.6 5.2l2.6 3.3"/></svg>';
    mark.title = 'Opens with an intro';
    mark.setAttribute('role', 'img');
    mark.setAttribute('aria-label', 'opens with an intro');
    return mark;
  };
  var flag = function (host, name, href) {
    if (!host || host.querySelector(':scope > .sc-intro-mark') || !SET_PAGE.test(href || '') || !introFor(name || '')) { return; }
    host.appendChild(badge());
  };
  var markCards = function (scope) {
    // List and search cards: the poster carries it.
    scope.querySelectorAll('.collection-card').forEach(function (card) {
      var link = card.querySelector('header a');
      if (link) { flag(card.querySelector('.collection-poster'), link.textContent.trim(), link.getAttribute('href')); }
    });
    // The home page's poster rows, and the spotlight (beside its kicker).
    scope.querySelectorAll('a.poster-row-card').forEach(function (a) { flag(a, a.title, a.getAttribute('href')); });
    scope.querySelectorAll('a.spotlight-slide').forEach(function (a) {
      var logo = a.querySelector('.spotlight-logo');
      var title = a.querySelector('.spotlight-title');
      flag(a.querySelector('.spotlight-kicker'), logo ? logo.alt : (title ? title.textContent.trim() : ''), a.getAttribute('href'));
    });
    // The Trophy case.
    scope.querySelectorAll('a.trophy').forEach(function (a) {
      var name = a.querySelector(':scope > strong');
      flag(a.querySelector('.trophy-frame'), name ? name.textContent.trim() : '', a.getAttribute('href'));
    });
    // Ctrl+K's lines, after the name: only the sets' own. A film's line links to its set's page
    // too, but it's the set that has the intro, not the film.
    scope.querySelectorAll('.sc-quick-list a').forEach(function (a) {
      var name = a.querySelector('strong');
      var kind = a.querySelector('small');
      if (!kind || !/^(Collection|Franchise)\b/.test(kind.textContent.trim())) { return; }
      flag(name, name ? name.textContent.trim() : '', a.getAttribute('href'));
    });
  };
  if (root.dataset.intros !== 'off') {
    markCards(document);
    document.addEventListener('htmx:afterSwap', function (event) {
      if (event.target && event.target.querySelectorAll) { markCards(event.target); }
    });
  }

  var heading = document.querySelector('.collection-heading');
  if (!heading) { return; }

  // ------------------------------------------------------------ what the page says
  function plain(el) {
    if (!el) { return ''; }
    var copy = el.cloneNode(true);
    copy.querySelectorAll('.sc-odo').forEach(function (odo) { odo.remove(); });   // a rolled number's columns
    return copy.textContent.replace(/\s+/g, ' ').trim();
  }
  var h1 = heading.querySelector('h1');
  var logo = h1 && h1.querySelector('img');
  var name = (logo ? logo.alt : plain(h1)).trim();
  var counts = /([0-9,]+) of ([0-9,]+)/.exec(plain(heading.querySelector('hgroup p'))) || [];
  var steps = Array.prototype.map.call(document.querySelectorAll('.timeline-step'), function (step) {
    var img = step.querySelector('img');
    return { title: img ? img.alt : plain(step.querySelector('.timeline-placeholder')),
             year: parseInt(plain(step.querySelector('.timeline-year')), 10) || null,
             owned: step.classList.contains('timeline-step--owned'),
             poster: img ? (img.currentSrc || img.src) : null };
  });
  var missing = Array.prototype.map.call(document.querySelectorAll('.film-tile.missing .film-title'), plain);
  if (!missing.length) { missing = steps.filter(function (s) { return !s.owned; }).map(function (s) { return s.title; }); }
  var years = steps.map(function (s) { return s.year; }).filter(Boolean);
  var page = {
    name: name, have: counts[1] || '', total: counts[2] || '', missing: missing, steps: steps,
    first: years.length ? Math.min.apply(null, years) : null, latest: years.length ? Math.max.apply(null, years) : null,
    posters: steps.map(function (s) { return s.poster; }).filter(Boolean),
  };

  // ------------------------------------------------------------ the curtain
  // opts.through: the page stays usable underneath (the overlay only decorates it).
  function curtain(opts) {
    var el = document.createElement('div');
    el.className = 'sc-intro' + (opts.through ? ' sc-intro--through' : '');
    el.setAttribute('role', 'presentation');
    if (opts.background) { el.style.background = opts.background; }
    var done = false, cleanups = [];
    var finish = function () {
      if (done) { return; }
      done = true;
      el.classList.add('is-leaving');
      document.removeEventListener('keydown', skip, true);
      cleanups.forEach(function (fn) { fn(); });
      window.setTimeout(function () { el.remove(); }, 900);
    };
    var skip = function () { finish(); };
    if (!opts.through) {
      el.addEventListener('click', finish);
      var hint = document.createElement('span');
      hint.className = 'sc-intro-skip';
      hint.textContent = 'Click or press any key to skip';
      el.appendChild(hint);
    }
    document.addEventListener('keydown', skip, true);
    window.setTimeout(finish, opts.max || 8000);   // however few frames it got
    document.body.appendChild(el);
    return {
      el: el, finish: finish, done: function () { return done; },
      onFinish: function (fn) { cleanups.push(fn); },
      canvas: function () {
        var c = document.createElement('canvas');
        c.width = window.innerWidth; c.height = window.innerHeight;
        el.insertBefore(c, el.firstChild);
        return c;
      },
    };
  }
  // A frame loop timed from its start: draw(seconds) until it returns false or the curtain goes.
  function run(c, draw) {
    var began = performance.now();
    var frame = function (now) {
      if (c.done()) { return; }
      if (draw((now - began) / 1000) === false) { c.finish(); return; }
      window.requestAnimationFrame(frame);
    };
    window.requestAnimationFrame(frame);
  }
  function text(tag, cls, words, parent) {
    var el = document.createElement(tag);
    if (cls) { el.className = cls; }
    el.textContent = words;
    if (parent) { parent.appendChild(el); }
    return el;
  }
  function typeOut(el, words, perChar, then) {
    var i = 0;
    var next = function () {
      el.textContent = words.slice(0, ++i);
      if (i < words.length) { window.setTimeout(next, perChar); } else if (then) { then(); }
    };
    next();
  }
  function bigger(src) { return src ? src.replace(/\/t\/p\/w\d+\//, '/t/p/w342/') : src; }
  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }

  // ------------------------------------------------------------ the intros
  var INTROS = {
    // Star Wars: an opening line, then a crawl about this collection, receding into the stars.
    crawl: function () {
      var c = curtain({ max: 25000, background:
        'radial-gradient(1px 1px at 20% 30%, white, transparent), radial-gradient(1px 1px at 70% 60%, white, transparent), ' +
        'radial-gradient(1px 1px at 40% 80%, white, transparent), radial-gradient(1.5px 1.5px at 85% 20%, white, transparent), ' +
        'radial-gradient(1px 1px at 10% 70%, white, transparent), radial-gradient(1px 1px at 55% 15%, white, transparent) 0 0 / 260px 260px, black' });
      var opening = text('p', 'sc-crawl-opening', 'A short while ago, in a library not so far away….', c.el);
      opening.style.color = 'rgb(75 213 238)';
      var stage = document.createElement('div');
      stage.className = 'sc-crawl-stage';
      var crawl = document.createElement('div');
      crawl.className = 'sc-crawl-text';
      crawl.style.color = 'rgb(255 214 64)';
      text('h2', null, page.name, crawl);
      text('p', null, (page.total ? 'It is a period of collecting. Of ' + page.total + ' films released, ' + page.have +
        ' are safely in the library. ' : 'It is a period of collecting. ') +
        'The rest remain at large, scattered across the galaxy’s streaming services and bargain bins. ' +
        'Pursued by an import list, one collector races home aboard a humble media server, ' +
        'custodian of a franchise that can still be made whole….', crawl);
      stage.appendChild(crawl);
      c.el.appendChild(stage);
      window.setTimeout(c.finish, 23000);
    },

    // The Matrix: falling code, the newest glyph of each column bright.
    rain: function () {
      var c = curtain({ max: 5000, background: 'black' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var size = 16, columns = Math.ceil(W / size), drops = [];
      for (var i = 0; i < columns; i++) { drops.push(Math.random() * -40); }
      var glyphs = 'アイウエオカキクケコサシスセソ0123456789';
      run(c, function (t) {
        g.fillStyle = 'rgba(0, 0, 0, 0.08)'; g.fillRect(0, 0, W, H);
        g.font = size + 'px monospace';
        for (var col = 0; col < columns; col++) {
          g.fillStyle = Math.random() > 0.97 ? 'rgb(200 255 200)' : 'rgb(0 255 70)';
          g.fillText(glyphs[Math.floor(Math.random() * glyphs.length)], col * size, drops[col] * size);
          if (drops[col] * size > H && Math.random() > 0.96) { drops[col] = 0; }
          drops[col] += 1;
        }
        return t < 3.2;
      });
    },

    // Harry Potter: gold sparks thrown from the title, as from a wand. The page stays usable.
    sparks: function () {
      var c = curtain({ max: 4000, through: true });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var box = h1 ? h1.getBoundingClientRect() : { left: W / 2, top: H / 3, width: 0, height: 0 };
      var bits = [];
      for (var n = 0; n < 140; n++) {
        bits.push({ x: box.left + Math.random() * Math.max(box.width, 40), y: box.top + box.height / 2,
                    vx: (Math.random() - 0.5) * 5, vy: -Math.random() * 6 - 1, life: 0.6 + Math.random() * 0.6 });
      }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        bits.forEach(function (b) {
          b.vy += 0.12; b.x += b.vx; b.y += b.vy;
          g.globalAlpha = Math.max(0, 1 - t / (b.life * 2.2));
          g.fillStyle = Math.random() > 0.5 ? 'rgb(255 214 120)' : 'rgb(255 245 210)';
          g.beginPath(); g.arc(b.x, b.y, 1.8, 0, Math.PI * 2); g.fill();
        });
        return t < 2.6;
      });
    },

    // The MCU: this franchise's own posters flicker past like a comic's pages, then a red flash.
    flip: function () {
      var srcs = page.posters.map(bigger);
      if (srcs.length < 3) { return; }
      var c = curtain({ max: 4500, background: 'black' });
      srcs.forEach(function (src) { var pre = new Image(); pre.src = src; });
      var img = document.createElement('img');
      img.className = 'sc-flip-page';
      img.alt = '';
      c.el.appendChild(img);
      var flash = document.createElement('div');
      flash.className = 'sc-flip-flash';
      flash.style.background = 'rgb(226 30 40)';
      c.el.appendChild(flash);
      var i = 0, began = performance.now();
      var turn = function () {
        if (c.done()) { return; }
        var age = performance.now() - began;
        if (age > 2600) { flash.classList.add('is-on'); window.setTimeout(c.finish, 500); return; }
        img.src = srcs[i++ % srcs.length];
        img.style.rotate = ((Math.random() - 0.5) * 8).toFixed(1) + 'deg';
        img.style.scale = (1 + Math.random() * 0.12).toFixed(2);
        window.setTimeout(turn, Math.max(55, 150 - age / 22));   // faster and faster
      };
      turn();
    },

    // James Bond: dots across a black screen, a barrel opening onto the page, a red wash, then the
    // circle widens to give the page back.
    barrel: function () {
      var c = curtain({ max: 6500 });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var R = Math.min(W, H) * 0.26, full = Math.hypot(W, H);
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.globalCompositeOperation = 'source-over';
        g.fillStyle = 'black'; g.fillRect(0, 0, W, H);
        if (t < 1.8) {
          g.fillStyle = 'white';
          for (var d = 0; d < 4; d++) {
            var x = -60 + (t / 1.8) * (W * 0.78) - d * 140;
            if (x > -20) { g.beginPath(); g.arc(x, H / 2, 14, 0, Math.PI * 2); g.fill(); }
          }
          return true;
        }
        var u = Math.min(1, (t - 1.8) / 1.2);
        var cx = W * 0.75 - (W * 0.25) * u, cy = H / 2;
        var r = t < 4.3 ? R : R + (full - R) * Math.min(1, (t - 4.3) / 0.7);
        // The barrel's rifling: grey spirals round the opening, turning.
        g.save(); g.translate(cx, cy); g.rotate(t * 0.9);
        for (var k = 0; k < 8; k++) {
          g.rotate(Math.PI / 4);
          g.strokeStyle = 'rgba(90, 90, 90, ' + (t < 4.3 ? 0.8 : 0.8 * (1 - (t - 4.3) / 0.7)) + ')';
          g.lineWidth = 10;
          g.beginPath(); g.arc(0, 0, r * 1.45, 0, 0.5); g.stroke();
        }
        g.restore();
        g.globalCompositeOperation = 'destination-out';
        g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.fill();
        g.globalCompositeOperation = 'source-over';
        if (t > 3.2) {   // the red wash, running down, then thinning as the circle opens
          var fall = Math.min(1, (t - 3.2) / 0.9);
          g.fillStyle = 'rgba(170, 0, 10, ' + (t < 4.3 ? 0.85 : 0.85 * (1 - (t - 4.3) / 0.7)) + ')';
          g.beginPath();
          g.moveTo(0, 0);
          for (var x2 = 0; x2 <= W; x2 += 40) { g.lineTo(x2, fall * H * (0.85 + 0.15 * Math.sin(x2 / 70 + t * 3))); }
          g.lineTo(W, 0); g.closePath(); g.fill();
        }
        return t < 5.0;
      });
    },

    // Star Trek: stars stretch into streaks, the jump to warp, a white flash, and out.
    warp: function () {
      var c = curtain({ max: 5000 });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var stars = [];
      for (var i = 0; i < 450; i++) { stars.push({ x: (Math.random() - 0.5) * W, y: (Math.random() - 0.5) * H, z: Math.random() * W }); }
      run(c, function (t) {
        var speed = 2 + Math.pow(Math.min(t, 2.6) / 2.6, 3) * 70;
        g.fillStyle = 'rgba(0, 0, 0, ' + (t < 2 ? 0.6 : 0.25) + ')'; g.fillRect(0, 0, W, H);
        g.strokeStyle = 'rgb(220 235 255)';
        stars.forEach(function (s) {
          var px = s.x / s.z * W / 2 + W / 2, py = s.y / s.z * W / 2 + H / 2;
          s.z -= speed;
          if (s.z < 1) { s.z = W; s.x = (Math.random() - 0.5) * W; s.y = (Math.random() - 0.5) * H; return; }
          var nx = s.x / s.z * W / 2 + W / 2, ny = s.y / s.z * W / 2 + H / 2;
          g.lineWidth = Math.max(0.5, 2.5 - s.z / W * 2);
          g.beginPath(); g.moveTo(px, py); g.lineTo(nx, ny); g.stroke();
        });
        if (t > 2.6) { g.fillStyle = 'rgba(255, 255, 255, ' + Math.min(1, (t - 2.6) / 0.25) + ')'; g.fillRect(0, 0, W, H); }
        return t < 3.0;
      });
    },

    // Jurassic Park: a glass of water in the corner ripples with each distant thud, and the page
    // shakes. The page stays usable.
    ripple: function () {
      var c = curtain({ max: 5000, through: true });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W - 130, cy = H - 140, r = 85, thuds = [0.4, 1.4, 2.4, 3.3], shaken = 0;
      var main = document.querySelector('main');
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.globalAlpha = Math.min(1, t * 3, (4.3 - t) * 2);
        g.fillStyle = 'rgba(160, 205, 230, 0.35)'; g.strokeStyle = 'rgba(230, 240, 250, 0.8)'; g.lineWidth = 4;
        g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.fill(); g.stroke();
        thuds.forEach(function (at, i) {
          var age = t - at;
          if (age > 0 && i >= shaken) {
            shaken = i + 1;
            if (main && main.animate) {
              main.animate([{ translate: '0 0' }, { translate: '0 3px' }, { translate: '0 -2px' }, { translate: '0 0' }], { duration: 260 });
            }
          }
          if (age > 0 && age < 0.9) {
            for (var ring = 0; ring < 3; ring++) {
              var rr = (age * 1.4 - ring * 0.18) * r;
              if (rr > 0 && rr < r) {
                g.strokeStyle = 'rgba(255, 255, 255, ' + (0.7 * (1 - rr / r)) + ')'; g.lineWidth = 2;
                g.beginPath(); g.arc(cx, cy, rr, 0, Math.PI * 2); g.stroke();
              }
            }
          }
        });
        return t < 4.3;
      });
    },

    // Back to the Future: a time-circuit display of this franchise's span, then twin fire trails.
    circuits: function () {
      var c = curtain({ max: 5500, background: 'rgb(12 12 16)' });
      var panel = document.createElement('div');
      panel.className = 'sc-circuits';
      var now = new Date();
      var months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
      var pad = function (n) { return (n < 10 ? '0' : '') + n; };
      [['LATEST FILM', page.latest ? '—— —— ' + page.latest : '—', 'rgb(255 70 60)'],
       ['PRESENT TIME', months[now.getMonth()] + ' ' + pad(now.getDate()) + ' ' + now.getFullYear(), 'rgb(80 255 120)'],
       ['FIRST FILM', page.first ? '—— —— ' + page.first : '—', 'rgb(255 190 40)']].forEach(function (row) {
        var line = document.createElement('div');
        text('span', 'sc-circuits-time', row[1], line).style.color = row[2];
        text('small', null, row[0], line);
        panel.appendChild(line);
      });
      c.el.appendChild(panel);
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        if (t > 2.3) {
          panel.style.opacity = String(Math.max(0, 1 - (t - 2.3) * 2));
          var reach = Math.min(1, (t - 2.3) / 0.5) * W;
          [H * 0.6, H * 0.72].forEach(function (y) {
            for (var x = 0; x < reach; x += 6) {
              var flicker = Math.random() * 14;
              g.fillStyle = Math.random() > 0.5 ? 'rgb(255 140 20)' : 'rgb(255 220 80)';
              g.fillRect(x, y - flicker, 6, 4 + flicker);
            }
          });
          if (t > 3.0) { g.fillStyle = 'rgba(255, 255, 255, ' + Math.min(1, (t - 3.0) / 0.2) + ')'; g.fillRect(0, 0, W, H); }
        }
        return t < 3.3;
      });
    },

    // Mission: Impossible: a fuse burns across the screen while a briefing types out; then it
    // goes up in smoke.
    fuse: function () {
      var c = curtain({ max: 7000, background: 'black' });
      var n = page.missing.length;
      var brief = n ? 'Good evening. ' + plural(n, 'film') + ' missing from ' + page.name + ': ' +
        page.missing.slice(0, 4).join(', ') + (n > 4 ? ' and more' : '') + '. Recover them.' :
        'Good evening. Every film of ' + page.name + ' is accounted for.';
      var note = text('p', 'sc-brief', '', c.el);
      typeOut(note, brief + ' This message will self-destruct in five seconds.', 28);
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var smoke = [];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var y = H * 0.82, at = Math.min(1, t / 3.6) * W;
        g.strokeStyle = 'rgb(120 120 120)'; g.lineWidth = 3;
        g.beginPath(); g.moveTo(at, y); g.lineTo(W, y); g.stroke();
        if (t < 3.6) {
          for (var s = 0; s < 6; s++) {
            g.fillStyle = Math.random() > 0.5 ? 'rgb(255 200 80)' : 'rgb(255 120 20)';
            g.fillRect(at + (Math.random() - 0.5) * 16, y + (Math.random() - 0.5) * 16, 3, 3);
          }
        } else {
          if (!note.classList.contains('is-smoke')) {
            note.classList.add('is-smoke');
            for (var p = 0; p < 60; p++) { smoke.push({ x: W / 2 + (Math.random() - 0.5) * W * 0.5, y: H * 0.45, r: 10, a: 0.5 }); }
          }
          smoke.forEach(function (puff) {
            puff.y -= 0.8 + Math.random(); puff.x += (Math.random() - 0.5) * 2; puff.r += 0.6; puff.a *= 0.985;
            g.fillStyle = 'rgba(160, 160, 160, ' + puff.a + ')';
            g.beginPath(); g.arc(puff.x, puff.y, puff.r, 0, Math.PI * 2); g.fill();
          });
        }
        return t < 5.2;
      });
    },

    // Alien: a motion tracker -- one contact for each missing film, closing in.
    tracker: function () {
      var c = curtain({ max: 6000, background: 'rgb(4 14 8)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H * 0.86, R = Math.min(W * 0.45, H * 0.75);
      var count = Math.min(page.missing.length, 12), contacts = [];
      for (var i = 0; i < count; i++) { contacts.push({ angle: -Math.PI / 2 + (Math.random() - 0.5) * 1.6, d: 0.9 + Math.random() * 0.1 }); }
      var label = text('p', 'sc-tracker-label', count ? plural(count, 'contact') : 'No movement', c.el);
      label.style.color = 'rgb(110 255 140)';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgba(80, 255, 120, 0.25)'; g.lineWidth = 1;
        for (var ring = 1; ring <= 4; ring++) { g.beginPath(); g.arc(cx, cy, R * ring / 4, Math.PI * 1.1, Math.PI * 1.9); g.stroke(); }
        var sweep = -Math.PI / 2 + Math.sin(t * 2.4) * 0.8;
        g.strokeStyle = 'rgba(120, 255, 150, 0.8)'; g.lineWidth = 2;
        g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(sweep) * R, cy + Math.sin(sweep) * R); g.stroke();
        contacts.forEach(function (k) {
          var d = Math.max(0.18, k.d - t * 0.2) * R;
          var pulse = 0.5 + 0.5 * Math.abs(Math.sin(t * 4 + k.angle * 3));
          g.fillStyle = 'rgba(140, 255, 160, ' + pulse + ')';
          g.beginPath(); g.arc(cx + Math.cos(k.angle) * d, cy + Math.sin(k.angle) * d, 6 + pulse * 3, 0, Math.PI * 2); g.fill();
        });
        if (count) { label.textContent = plural(count, 'contact') + ' · ' + Math.max(1, Math.round(30 - t * 7)) + ' m'; }
        return t < 4.2;
      });
    },

    // Batman: a searchlight sweeps the clouds and settles into a bat-shaped signal.
    signal: function () {
      var c = curtain({ max: 6000, background: 'linear-gradient(to bottom, rgb(10 14 30), rgb(26 32 52))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var clouds = [];
      for (var i = 0; i < 9; i++) { clouds.push({ x: Math.random() * W, y: Math.random() * H * 0.5, r: 120 + Math.random() * 160 }); }
      var bat = function (x, y, s) {   // a generic bat silhouette, wings out
        g.beginPath();
        g.moveTo(x, y - 0.35 * s);
        g.quadraticCurveTo(x + 0.15 * s, y - 0.5 * s, x + 0.25 * s, y - 0.3 * s);
        g.quadraticCurveTo(x + 0.6 * s, y - 0.55 * s, x + s, y - 0.15 * s);
        g.quadraticCurveTo(x + 0.75 * s, y - 0.1 * s, x + 0.7 * s, y + 0.15 * s);
        g.quadraticCurveTo(x + 0.5 * s, y, x + 0.4 * s, y + 0.2 * s);
        g.quadraticCurveTo(x + 0.2 * s, y + 0.05 * s, x, y + 0.4 * s);
        g.quadraticCurveTo(x - 0.2 * s, y + 0.05 * s, x - 0.4 * s, y + 0.2 * s);
        g.quadraticCurveTo(x - 0.5 * s, y, x - 0.7 * s, y + 0.15 * s);
        g.quadraticCurveTo(x - 0.75 * s, y - 0.1 * s, x - s, y - 0.15 * s);
        g.quadraticCurveTo(x - 0.6 * s, y - 0.55 * s, x - 0.25 * s, y - 0.3 * s);
        g.quadraticCurveTo(x - 0.15 * s, y - 0.5 * s, x, y - 0.35 * s);
        g.fill();
      };
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        clouds.forEach(function (cl) {
          var grad = g.createRadialGradient(cl.x, cl.y, 0, cl.x, cl.y, cl.r);
          grad.addColorStop(0, 'rgba(90, 100, 130, 0.35)'); grad.addColorStop(1, 'rgba(90, 100, 130, 0)');
          g.fillStyle = grad; g.beginPath(); g.arc(cl.x + t * 6, cl.y, cl.r, 0, Math.PI * 2); g.fill();
        });
        var u = Math.min(1, t / 2.4);
        var tx = W * (0.5 + 0.32 * Math.sin(u * Math.PI * 2) * (1 - u));   // sweeps, then settles mid-sky
        var ty = H * 0.3, rx = Math.min(W, H) * 0.2, ry = rx * 0.62;
        var beam = g.createLinearGradient(W / 2, H, tx, ty);
        beam.addColorStop(0, 'rgba(255, 240, 180, 0.35)'); beam.addColorStop(1, 'rgba(255, 240, 180, 0.12)');
        g.fillStyle = beam;
        g.beginPath(); g.moveTo(W / 2 - 30, H + 10); g.lineTo(tx - rx * 0.9, ty); g.lineTo(tx + rx * 0.9, ty); g.lineTo(W / 2 + 30, H + 10); g.fill();
        g.fillStyle = 'rgba(255, 238, 170, 0.75)';
        g.beginPath(); g.ellipse(tx, ty, rx, ry, 0, 0, Math.PI * 2); g.fill();
        if (u >= 1) {
          g.fillStyle = 'rgba(15, 15, 20, ' + Math.min(1, (t - 2.4) * 2) + ')';
          bat(tx, ty, rx * 0.85);
        }
        return t < 4.2;
      });
    },

    // Jaws: the page under water; a fin cuts slowly across, and the water drains away.
    fin: function () {
      var c = curtain({ max: 6000, through: true });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var line = H * 0.5;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var drain = t > 3.6 ? Math.min(1, (t - 3.6) / 0.7) : 0;
        var top = line + drain * H;
        g.fillStyle = 'rgba(8, 60, 110, ' + (0.55 * (1 - drain * 0.6)) + ')';
        g.beginPath(); g.moveTo(0, top);
        for (var x = 0; x <= W; x += 20) { g.lineTo(x, top + Math.sin(x / 60 + t * 2) * 6); }
        g.lineTo(W, H); g.lineTo(0, H); g.fill();
        g.strokeStyle = 'rgba(200, 230, 255, 0.25)'; g.lineWidth = 1;
        for (var w = 1; w < 6; w++) {
          g.beginPath();
          for (var x2 = 0; x2 <= W; x2 += 30) { g.lineTo(x2, top + w * 40 + Math.sin(x2 / 45 + t * 1.6 + w) * 8); }
          g.stroke();
        }
        if (!drain) {
          var fx = -120 + (t / 3.6) * (W + 240), fy = top + Math.sin(fx / 60 + t * 2) * 6;
          g.fillStyle = 'rgb(40 50 60)';
          g.beginPath(); g.moveTo(fx - 50, fy); g.quadraticCurveTo(fx - 10, fy - 30, fx + 25, fy - 85);
          g.quadraticCurveTo(fx + 20, fy - 40, fx + 45, fy); g.closePath(); g.fill();
          g.strokeStyle = 'rgba(255, 255, 255, 0.5)'; g.lineWidth = 2;
          g.beginPath(); g.moveTo(fx + 45, fy); g.lineTo(fx - 70, fy - 6); g.moveTo(fx + 45, fy); g.lineTo(fx - 70, fy + 8); g.stroke();
        }
        return t < 4.4;
      });
    },

    // Terminator: a red targeting display scans the page and lists its targets.
    hud: function () {
      var c = curtain({ max: 7000, background: 'rgba(200, 0, 0, 0.32)' });
      c.el.style.mixBlendMode = 'normal';
      var panel = document.createElement('div');
      panel.className = 'sc-hud';
      c.el.appendChild(panel);
      var lines = ['ANALYSIS: ' + page.name.toUpperCase(),
                   page.total ? 'IN LIBRARY: ' + page.have + '/' + page.total : 'IN LIBRARY: ' + page.have]
        .concat(page.missing.slice(0, 6).map(function (title, i) { return 'TARGET ' + (i + 1) + ': ' + title.toUpperCase(); }))
        .concat([page.missing.length ? 'PRIORITY: ACQUIRE' : 'NO TARGETS REMAIN']);
      var i = 0;
      var nextLine = function () {
        if (c.done() || i >= lines.length) { return; }
        var row = text('div', null, '', panel);
        typeOut(row, lines[i++], 18, function () { window.setTimeout(nextLine, 120); });
      };
      nextLine();
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var target = heading.querySelector('.collection-heading-poster') || heading;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var scan = (t * 0.45 % 1) * H;
        g.fillStyle = 'rgba(255, 220, 220, 0.18)'; g.fillRect(0, scan, W, 3);
        var box = target.getBoundingClientRect(), pad = 12 + Math.sin(t * 6) * 4;
        g.strokeStyle = 'rgba(255, 240, 240, 0.9)'; g.lineWidth = 2;
        [[box.left - pad, box.top - pad, 1, 1], [box.right + pad, box.top - pad, -1, 1],
         [box.left - pad, box.bottom + pad, 1, -1], [box.right + pad, box.bottom + pad, -1, -1]].forEach(function (k) {
          g.beginPath(); g.moveTo(k[0], k[1] + 22 * k[3]); g.lineTo(k[0], k[1]); g.lineTo(k[0] + 22 * k[2], k[1]); g.stroke();
        });
        return t < 5.0;
      });
    },

    // Indiana Jones: an old map, and a red line travelling stop to stop -- a film at each, in
    // release order.
    map: function () {
      var c = curtain({ max: 6500, background: 'radial-gradient(ellipse at center, rgb(236 214 168), rgb(196 160 104))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var stops = page.steps.slice(0, 12);
      if (stops.length < 2) { c.finish(); return; }
      var points = stops.map(function (s, i) {
        return { x: W * (0.1 + 0.8 * i / (stops.length - 1)), y: H * (0.5 + 0.25 * Math.sin(i * 2.1 + 0.6)), s: s };
      });
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgba(120, 80, 40, 0.15)'; g.lineWidth = 1;
        for (var gx = 0; gx < W; gx += 80) { g.beginPath(); g.moveTo(gx, 0); g.lineTo(gx, H); g.stroke(); }
        for (var gy = 0; gy < H; gy += 80) { g.beginPath(); g.moveTo(0, gy); g.lineTo(W, gy); g.stroke(); }
        var travelled = Math.min(1, t / 3.4) * (points.length - 1);
        g.strokeStyle = 'rgb(180 20 20)'; g.lineWidth = 4; g.setLineDash([12, 8]);
        g.beginPath(); g.moveTo(points[0].x, points[0].y);
        for (var i = 1; i <= Math.ceil(travelled); i++) {
          var a = points[i - 1], b = points[i], f = Math.min(1, travelled - (i - 1));
          g.lineTo(a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f);
        }
        g.stroke(); g.setLineDash([]);
        points.forEach(function (p, i) {
          if (i > travelled + 0.01) { return; }
          g.fillStyle = p.s.owned ? 'rgb(120 20 20)' : 'rgba(0, 0, 0, 0)';
          g.strokeStyle = 'rgb(120 20 20)'; g.lineWidth = 3;
          g.beginPath(); g.arc(p.x, p.y, 7, 0, Math.PI * 2); g.fill(); g.stroke();
          g.fillStyle = 'rgb(70 45 20)'; g.font = '600 13px Georgia, serif'; g.textAlign = 'center';
          g.fillText((p.s.year || '') + '', p.x, p.y - 16);
          g.font = 'italic 12px Georgia, serif';
          g.fillText(p.s.title.length > 26 ? p.s.title.slice(0, 25) + '…' : p.s.title, p.x, p.y + 24);
        });
        return t < 4.6;
      });
    },

    // Middle-earth: a gold ring turning in the dark, glowing hotter, then flaring.
    ring: function () {
      var c = curtain({ max: 5500, background: 'black' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var embers = [];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var heat = Math.min(1, t / 3);
        if (embers.length < 80) { embers.push({ x: W / 2 + (Math.random() - 0.5) * 300, y: H * 0.75, v: 0.6 + Math.random() * 1.6 }); }
        embers.forEach(function (e) {
          e.y -= e.v; e.x += Math.sin(e.y / 30) * 0.5;
          g.fillStyle = 'rgba(255, 140, 40, ' + Math.max(0, (e.y - H * 0.2) / H) + ')';
          g.fillRect(e.x, e.y, 2, 2);
        });
        var R = Math.min(W, H) * 0.16, squash = Math.abs(Math.cos(t * 1.6)) * 0.55 + 0.25;
        g.save();
        g.shadowBlur = 20 + heat * 60; g.shadowColor = 'rgb(255 170 40)';
        var grad = g.createLinearGradient(W / 2 - R, H / 2, W / 2 + R, H / 2);
        grad.addColorStop(0, 'rgb(180 120 20)'); grad.addColorStop(0.5, 'rgb(255 225 120)'); grad.addColorStop(1, 'rgb(170 110 20)');
        g.strokeStyle = grad; g.lineWidth = 16;
        g.beginPath(); g.ellipse(W / 2, H / 2, R, R * squash, 0, 0, Math.PI * 2); g.stroke();
        g.restore();
        if (t > 3.0) { g.fillStyle = 'rgba(255, 230, 170, ' + Math.min(1, (t - 3.0) / 0.4) + ')'; g.fillRect(0, 0, W, H); }
        return t < 3.5;
      });
    },

    // Ghostbusters: green slime runs down the screen in thick drips, then slides away.
    slime: function () {
      var c = curtain({ max: 5500 });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var drips = [];
      // Uneven, like the real thing: drips of every width and reach, with gaps between.
      for (var x = 10; x < W; x += 40 + Math.random() * 70) {
        drips.push({ x: x, w: 14 + Math.random() * 40, speed: 0.3 + Math.random() * 0.6,
                     reach: 0.15 + Math.pow(Math.random(), 1.6) * 0.75, wobble: Math.random() * 6 });
      }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var slide = t > 3.0 ? Math.min(1, (t - 3.0) / 0.9) : 0;
        g.save();
        g.translate(0, slide * H);
        g.globalAlpha = 1 - slide * 0.6;
        var top = H * 0.08;
        g.fillStyle = 'rgba(110, 230, 60, 0.88)';
        g.beginPath(); g.moveTo(0, 0); g.lineTo(W, 0);
        for (var edge = W; edge >= 0; edge -= 30) { g.lineTo(edge, top + Math.sin(edge / 45) * 10); }
        g.fill();
        drips.forEach(function (d) {
          var len = top + Math.min(1, t * d.speed) * H * d.reach;
          g.beginPath();
          g.moveTo(d.x - d.w / 2, 0);
          g.lineTo(d.x - d.w / 2 + Math.sin(t * 2 + d.wobble) * 2, len - d.w / 2);
          g.arc(d.x, len - d.w / 2, d.w / 2, Math.PI, 0, true);
          g.lineTo(d.x + d.w / 2, 0);
          g.fill();
        });
        g.fillStyle = 'rgba(210, 255, 170, 0.35)';   // a wet shine down each drip
        drips.forEach(function (d) {
          g.fillRect(d.x - d.w / 4, 0, 3, top + Math.min(1, t * d.speed) * H * d.reach - d.w);
        });
        g.restore();
        return t < 3.9;
      });
    },

    // Godzilla: footsteps that shake the page, dust falling from the ceiling, a vast shadow
    // passing, and a blue glow rising at the last. The page stays usable.
    footsteps: function () {
      var c = curtain({ max: 6000, through: true });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var steps = [0.3, 1.25, 2.2, 3.1], stepped = 0, dust = [];
      var main = document.querySelector('main');
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        steps.forEach(function (at, i) {
          if (t > at && i >= stepped) {
            stepped = i + 1;
            var shake = 3 + i * 3;
            if (main && main.animate) {
              main.animate([{ translate: '0 0' }, { translate: '0 ' + shake + 'px' }, { translate: '0 -' + (shake * 0.6) + 'px' },
                            { translate: '0 ' + (shake * 0.3) + 'px' }, { translate: '0 0' }], { duration: 420 });
            }
            for (var d = 0; d < 40; d++) { dust.push({ x: Math.random() * W, y: -10 - Math.random() * 40, v: 1 + Math.random() * 2.5 }); }
          }
        });
        var pass = Math.min(1, Math.max(0, (t - 0.6) / 3));   // the shadow crosses
        var sx = -W * 0.6 + pass * W * 1.6;
        var shadow = g.createRadialGradient(sx, H * 0.55, 0, sx, H * 0.55, W * 0.55);
        shadow.addColorStop(0, 'rgba(0, 0, 0, 0.8)'); shadow.addColorStop(0.6, 'rgba(0, 0, 0, 0.45)'); shadow.addColorStop(1, 'rgba(0, 0, 0, 0)');
        g.fillStyle = shadow; g.fillRect(0, 0, W, H);
        g.fillStyle = 'rgba(170, 160, 140, 0.8)';
        dust.forEach(function (p) { p.y += p.v; p.x += Math.sin(p.y / 40) * 0.4; g.fillRect(p.x, p.y, 2, 2); });
        if (t > 3.3) {
          var glow = Math.sin(Math.min(1, (t - 3.3) / 0.8) * Math.PI);
          var blue = g.createLinearGradient(0, H, 0, H * 0.5);
          blue.addColorStop(0, 'rgba(80, 190, 255, ' + 0.55 * glow + ')'); blue.addColorStop(1, 'rgba(80, 190, 255, 0)');
          g.fillStyle = blue; g.fillRect(0, 0, W, H);
        }
        return t < 4.2;
      });
    },

    // Mad Max: a sandstorm tears across the screen, then blows itself out.
    storm: function () {
      var c = curtain({ max: 5500, through: true });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var grains = [];
      for (var i = 0; i < 700; i++) {
        grains.push({ x: Math.random() * W, y: Math.random() * H, v: 6 + Math.random() * 18, l: 4 + Math.random() * 18 });
      }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var strength = Math.min(1, t / 0.6) * (t > 3.0 ? Math.max(0, 1 - (t - 3.0) / 1.0) : 1);
        var haze = g.createLinearGradient(0, 0, W, H);
        haze.addColorStop(0, 'rgba(210, 120, 40, ' + 0.55 * strength + ')');
        haze.addColorStop(1, 'rgba(150, 70, 20, ' + 0.65 * strength + ')');
        g.fillStyle = haze; g.fillRect(0, 0, W, H);
        g.strokeStyle = 'rgba(255, 210, 150, ' + 0.6 * strength + ')'; g.lineWidth = 1.5;
        g.beginPath();
        grains.forEach(function (p) {
          p.x += p.v * (0.4 + strength); p.y += Math.sin(p.x / 90 + t) * 0.8;
          if (p.x > W + 20) { p.x = -20; p.y = Math.random() * H; }
          g.moveTo(p.x, p.y); g.lineTo(p.x - p.l, p.y - p.l * 0.08);
        });
        g.stroke();
        return t < 4.0;
      });
    },

    // Toy Story: a blue sky of fluffy clouds, which part to let the page through.
    clouds: function () {
      // The sky is the curtain's own colour, so it's there before the first frame is drawn.
      var c = curtain({ max: 5000, background: 'rgb(90 170 240)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var puffs = [];
      for (var i = 0; i < 22; i++) {
        var cx = Math.random() * W, cy = Math.random() * H, size = 40 + Math.random() * 60;
        var bits = [];
        for (var b = 0; b < 6; b++) { bits.push([(b - 2.5) * size * 0.45, (Math.random() - 0.3) * size * 0.4, size * (0.45 + Math.random() * 0.35)]); }
        puffs.push({ x: cx, y: cy, bits: bits, side: cx < W / 2 ? -1 : 1 });
      }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var part = t > 2.2 ? Math.min(1, (t - 2.2) / 1.1) : 0;
        c.el.style.background = 'rgba(90, 170, 240, ' + (1 - part) + ')';
        puffs.forEach(function (p) {
          var x = p.x + t * 12 + p.side * part * part * W * 0.7;
          g.fillStyle = 'rgba(255, 255, 255, 0.95)';
          p.bits.forEach(function (bit) { g.beginPath(); g.arc(x + bit[0], p.y + bit[1], bit[2], 0, Math.PI * 2); g.fill(); });
          g.fillStyle = 'rgba(200, 225, 245, 0.6)';   // a soft shade under each cloud
          g.beginPath(); g.ellipse(x, p.y + p.bits[0][2] * 0.5, p.bits[0][2] * 2.2, p.bits[0][2] * 0.35, 0, 0, Math.PI * 2); g.fill();
        });
        return t < 3.4;
      });
    },
  };

  var which = introFor(name);
  if (!which || reduce) { return; }
  var play = INTROS[which[1]];

  // ▶ Intro: watch it again, whatever the menu says.
  var again = document.createElement('button');
  again.type = 'button';
  again.className = 'sc-intro-replay secondary outline';
  again.textContent = '▶ Intro';
  again.title = 'Play this page’s intro again';
  again.addEventListener('click', function () { play(); });
  var actions = heading.querySelector('.heading-actions');
  if (actions) { actions.insertBefore(again, actions.firstChild); } else { (heading.querySelector('hgroup') || heading).appendChild(again); }

  var key = 'sc-intro:' + window.location.pathname;
  var seen = false;
  try { seen = window.sessionStorage.getItem(key) === '1'; } catch (e) { seen = true; }
  if (seen || root.dataset.intros === 'off') { return; }
  try { window.sessionStorage.setItem(key, '1'); } catch (e) { /* shown anyway, once */ }
  play();
})();
