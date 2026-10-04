// Showcase's franchise intros (0.57.0; their own file since 0.58.0; a hundred and twenty-eight since 0.69.0, and a
// genre intro for every other collection and franchise since 0.70.0): a nod to a franchise's films
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
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
    document.documentElement.dataset.effects === 'off';   // the effects dial (0.71.0)
  // The intro mark's clapperboard: dark on the gold badge in any theme (0.61.1).
  root.style.setProperty('--sc-mark-ink', 'rgb(46 30 6)');

  // Which franchise a page is, by its name. The first match wins, so the specific ones come first.
  var WHICH = [
    [/star wars/i, 'crawl'],
    [/matrix/i, 'rain'],
    [/harry potter|wizarding world|fantastic beasts/i, 'sparks'],
    [/marvel cinematic universe|^the avengers collection$|^(iron man|thor|captain america|captain marvel|ant-man|guardians of the galaxy|black panther|doctor strange) collection$|^spider-man \(mcu\)/i, 'flip'],
    [/james bond/i, 'barrel'],
    [/star trek/i, 'warp'],
    [/jurassic (park|world)/i, 'ripple'],
    [/back to the future/i, 'circuits'],
    [/mission: impossible/i, 'fuse'],
    [/^alien\b|^prometheus\b|^avp\b/i, 'tracker'],
    [/batman|dark knight/i, 'signal'],
    [/^jaws\b/i, 'fin'],
    [/terminator/i, 'hud'],
    [/indiana jones/i, 'map'],
    [/lord of the rings|hobbit|middle-earth/i, 'ring'],
    [/ghostbusters/i, 'slime'],
    [/godzilla|monsterverse/i, 'footsteps'],
    [/mad max|furiosa/i, 'storm'],
    [/toy story/i, 'clouds'],
    [/fast (and|&) (the )?furious|fast saga|hobbs (and|&) shaw/i, 'nitro'],
    [/^(rocky|creed)\b/i, 'steps'],
    [/^die hard/i, 'tower'],
    [/transformers|^bumblebee/i, 'panels'],
    [/^scream\b/i, 'phone'],
    [/paranormal activity/i, 'nightvision'],
    [/final destination/i, 'dominoes'],
    [/predator/i, 'thermal'],
    [/dragon ball/i, 'powerup'],
    [/x-men|^(the )?wolverine/i, 'dome'],
    [/pirates of the caribbean/i, 'compass'],
    [/resident evil/i, 'lasers'],
    [/bourne/i, 'surveil'],
    [/^ice age\b/i, 'freeze'],
    [/^(the )?twilight( saga| collection|$)/i, 'forest'],
    [/shrek|puss in boots/i, 'storybook'],
    [/^halloween\b/i, 'pumpkin'],
    [/conjuring|^annabelle/i, 'polaroid'],
    [/exorcist/i, 'streetlamp'],
    [/^(the )?purge\b/i, 'broadcast'],
    [/john wick/i, 'coin'],
    [/^bad boys\b/i, 'spin'],
    [/rambo|^first blood/i, 'jungle'],
    [/starship troopers/i, 'newsreel'],
    [/home alone/i, 'paintcan'],
    [/kung fu panda/i, 'ink'],
    [/jumanji/i, 'dice'],
    [/^avatar( collection)?$/i, 'glow'],
    [/hunger games/i, 'arena'],
    [/^the mummy\b/i, 'sand'],
    [/superman|man of steel/i, 'flight'],
    [/sharknado/i, 'twister'],
    [/^the ring\b/i, 'well'],
    [/28 (days|weeks|years)/i, 'outbreak'],
    [/blair witch/i, 'torch'],
    [/deadpool/i, 'captions'],
    [/^blade\b(?! runner)/i, 'blade'],
    [/robocop/i, 'directive'],
    [/kingsman/i, 'umbrella'],
    [/men in black/i, 'flash'],
    [/^tron\b/i, 'grid'],
    [/godfather/i, 'sepia'],
    [/planet of the apes/i, 'ruins'],
    [/how to train your dragon/i, 'dragon'],
    [/^cars\b/i, 'flag'],
    [/night at the museum/i, 'museum'],
    [/narnia/i, 'wardrobe'],
    [/insidious/i, 'reddoor'],
    [/^the shining\b|doctor sleep/i, 'corridor'],
    [/^the thing\b/i, 'blizzard'],
    [/^underworld\b/i, 'moonrain'],
    [/top gun/i, 'jets'],
    [/^ocean'?s\b/i, 'vault'],
    [/equalizer/i, 'stopwatch'],
    [/lethal weapon/i, 'siren'],
    [/space odyssey|^2001\b/i, 'monolith'],
    [/^venom\b/i, 'tendrils'],
    [/wonder woman/i, 'lasso'],
    [/^(the amazing )?spider-man\b|spider-verse/i, 'web'],
    [/lion king/i, 'savanna'],
    [/wreck-it ralph/i, 'pixels'],
    [/incredibles/i, 'retro'],
    [/despicable me|^minions\b/i, 'shrink'],
    [/beverly hills cop/i, 'boulevard'],
    [/kill bill/i, 'katana'],
    [/^taken\b/i, 'pinpoint'],
    [/expendables/i, 'firewalk'],
    [/austin powers/i, 'groovy'],
    [/^the mask( collection)?$|son of the mask/i, 'whirlwind'],
    [/zombieland/i, 'rules'],
    [/hotel transylvania/i, 'bats'],
    [/tomb raider/i, 'tomb'],
    [/pacific rim/i, 'mech'],
    [/national treasure/i, 'cipher'],
    [/sherlock holmes/i, 'magnifier'],
    [/knives out|glass onion|wake up dead man/i, 'knives'],
    [/ninja turtles/i, 'masks'],
    [/sonic the hedgehog/i, 'rings'],
    [/^it( collection|$| chapter)/i, 'balloon'],
    [/evil dead/i, 'cabin'],
    [/beetlejuice/i, 'stripes'],
    [/hocus pocus/i, 'witches'],
    [/^dune\b/i, 'worm'],
    [/blade runner/i, 'neon'],
    [/hellboy/i, 'fist'],
    [/^gladiator\b/i, 'wheat'],
    [/^frozen\b/i, 'snowflake'],
    [/finding (nemo|dory)/i, 'reef'],
    [/monsters,? inc|monsters university/i, 'doors'],
    [/inside out/i, 'orbs'],
    [/^the hangover\b/i, 'snapshots'],
    [/scooby-doo/i, 'van'],
    [/^joker\b/i, 'card'],
    [/elm street/i, 'claws'],
    [/^saw\b/i, 'jigsaw'],
    [/^psycho\b/i, 'shower'],
    [/world war z/i, 'swarm'],
    [/^300\b/i, 'arrows'],
    [/karate kid|cobra kai/i, 'crane'],
    [/^(the )?meg\b/i, 'shadow'],
    [/mortal kombat/i, 'fireice'],
    [/^airplane/i, 'seatbelt'],
    [/ace ventura/i, 'parade'],
    [/anchorman/i, 'newsdesk'],
    [/spaceballs/i, 'longship'],
    [/neverending story/i, 'pages'],
    [/polar express/i, 'train'],
    [/^moana\b/i, 'wave'],
    [/paddington/i, 'label'],
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
    short: name.replace(/\s+collection$/i, ''),   // "Scream", for a sentence that already says what it is
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
  // A jolt of the page under an intro: a quake, an impact, a power surging.
  function shakePage(px, ms) {
    var main = document.querySelector('main');
    if (!main || !main.animate) { return; }
    main.animate([{ translate: '0 0' }, { translate: px + 'px ' + (px * 0.5) + 'px' }, { translate: (-px * 0.8) + 'px ' + (-px * 0.3) + 'px' },
                  { translate: (px * 0.4) + 'px 0' }, { translate: '0 0' }], { duration: ms || 350 });
  }

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

    // ---------------------------------------------------------------- 0.63.0

    // Fast & Furious: a speedometer swings into the red, a blue flash, and the page tears past in
    // streaks of speed and tyre smoke.
    nitro: function () {
      var c = curtain({ max: 5000, background: 'rgb(8 8 12)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H * 0.6, R = Math.min(W, H) * 0.27;
      var streaks = [], smoke = [];
      for (var i = 0; i < 170; i++) { streaks.push({ x: Math.random() * W, y: Math.random() * H, l: 40 + Math.random() * 220, v: 18 + Math.random() * 40 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var swing = Math.min(1, t / 1.6), ease = 1 - Math.pow(1 - swing, 3);
        if (t < 2.0) {
          g.lineCap = 'round';
          g.lineWidth = 7; g.strokeStyle = 'rgb(70 70 82)';
          g.beginPath(); g.arc(cx, cy, R, Math.PI * 0.75, Math.PI * 2.25); g.stroke();
          g.strokeStyle = 'rgb(230 40 30)';
          g.beginPath(); g.arc(cx, cy, R, Math.PI * 1.95, Math.PI * 2.25); g.stroke();
          for (var k = 0; k <= 10; k++) {
            var a = Math.PI * 0.75 + k / 10 * Math.PI * 1.5;
            g.strokeStyle = k >= 8 ? 'rgb(230 40 30)' : 'rgb(205 205 215)'; g.lineWidth = 3;
            g.beginPath(); g.moveTo(cx + Math.cos(a) * R * 0.8, cy + Math.sin(a) * R * 0.8);
            g.lineTo(cx + Math.cos(a) * R * 0.93, cy + Math.sin(a) * R * 0.93); g.stroke();
          }
          var needle = Math.PI * 0.75 + ease * Math.PI * 1.45 + (swing === 1 ? Math.sin(t * 70) * 0.02 : 0);
          g.strokeStyle = 'rgb(255 140 20)'; g.lineWidth = 5;
          g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(needle) * R * 0.88, cy + Math.sin(needle) * R * 0.88); g.stroke();
          g.fillStyle = 'rgb(240 240 245)'; g.textAlign = 'center';
          g.font = '700 ' + Math.round(R * 0.3) + 'px ui-monospace, monospace';
          g.fillText(String(Math.round(ease * 210)), cx, cy + R * 0.5);
        }
        if (t > 1.7 && t < 2.1) { g.fillStyle = 'rgba(90, 170, 255, ' + (1 - Math.abs(t - 1.9) / 0.2) * 0.85 + ')'; g.fillRect(0, 0, W, H); }
        if (t > 1.9) {
          var speed = Math.min(1, (t - 1.9) / 0.6);
          g.strokeStyle = 'rgba(255, 255, 255, 0.5)'; g.lineWidth = 2; g.beginPath();
          streaks.forEach(function (s) {
            s.x -= s.v * (1 + speed * 2);
            if (s.x + s.l * 2 < 0) { s.x = W + Math.random() * 200; s.y = Math.random() * H; }
            g.moveTo(s.x, s.y); g.lineTo(s.x + s.l * (1 + speed), s.y);
          });
          g.stroke();
          if (t < 3.0) { for (var p = 0; p < 3; p++) { smoke.push({ x: W * (Math.random() > 0.5 ? 0.25 : 0.75), y: H * 0.97, r: 12, a: 0.45 }); } }
          smoke.forEach(function (puff) {
            puff.x -= 6 + Math.random() * 4; puff.y -= 0.6; puff.r += 2.2; puff.a *= 0.965;
            g.fillStyle = 'rgba(200, 200, 205, ' + puff.a + ')';
            g.beginPath(); g.arc(puff.x, puff.y, puff.r, 0, Math.PI * 2); g.fill();
          });
          c.el.style.background = 'rgba(8, 8, 12, ' + Math.max(0, 1 - (t - 2.6)) + ')';
        }
        return t < 3.8;
      });
    },

    // Rocky: a bell, then a run up a long flight of steps at dawn -- a step for each film -- to
    // arms raised at the top.
    steps: function () {
      var c = curtain({ max: 6000, background: 'linear-gradient(to top, rgb(255 150 70), rgb(120 70 120) 55%, rgb(30 30 60))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var n = Math.max(6, Math.min(16, page.steps.length * 2 || 8));
      var x0 = W * 0.16, y0 = H * 0.92, sw = (W * 0.6) / n, sh = (H * 0.52) / n, u = Math.max(14, H * 0.03);
      var caption = text('p', 'sc-intro-caption', '', c.el);
      caption.style.color = 'rgb(255 236 200)';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        if (t < 0.9) {
          g.strokeStyle = 'rgba(255, 230, 160, ' + (1 - t / 0.9) + ')'; g.lineWidth = 6;
          g.beginPath(); g.arc(W / 2, H * 0.25, t * Math.max(W, H) * 0.6, 0, Math.PI * 2); g.stroke();
        }
        var rise = Math.min(1, t / 3.6), sunY = H * 0.55 - rise * H * 0.18;
        var glow = g.createRadialGradient(W * 0.8, sunY, 0, W * 0.8, sunY, H * 0.45);
        glow.addColorStop(0, 'rgba(255, 225, 150, ' + (0.45 + rise * 0.45) + ')'); glow.addColorStop(1, 'rgba(255, 200, 120, 0)');
        g.fillStyle = glow; g.fillRect(0, 0, W, H);
        g.fillStyle = 'rgb(42 30 46)';
        g.beginPath(); g.moveTo(x0, y0);
        for (var i = 0; i < n; i++) { g.lineTo(x0 + i * sw, y0 - (i + 1) * sh); g.lineTo(x0 + (i + 1) * sw, y0 - (i + 1) * sh); }
        g.lineTo(x0 + n * sw, y0); g.closePath(); g.fill();
        var climb = Math.min(n, Math.max(0, (t - 0.7) / 2.5 * n)), step = Math.floor(climb), hop = climb - step;
        var top = climb >= n;
        var fx = x0 + Math.min(climb + 0.5, n - 0.5) * sw, fy = y0 - Math.min(n, step + 1) * sh - (top ? 0 : Math.sin(hop * Math.PI) * sh * 0.5);
        g.strokeStyle = 'rgb(20 14 22)'; g.fillStyle = 'rgb(20 14 22)'; g.lineWidth = u * 0.28; g.lineCap = 'round';
        g.beginPath(); g.arc(fx, fy - u * 3.3, u * 0.5, 0, Math.PI * 2); g.fill();
        g.beginPath(); g.moveTo(fx, fy - u * 2.8); g.lineTo(fx, fy - u * 1.3); g.stroke();
        var stride = top ? 0 : Math.sin(climb * Math.PI) * u * 0.7;
        g.beginPath(); g.moveTo(fx, fy - u * 1.3); g.lineTo(fx + stride, fy); g.moveTo(fx, fy - u * 1.3); g.lineTo(fx - stride, fy); g.stroke();
        g.beginPath();
        if (top) { g.moveTo(fx, fy - u * 2.6); g.lineTo(fx - u * 0.9, fy - u * 3.9); g.moveTo(fx, fy - u * 2.6); g.lineTo(fx + u * 0.9, fy - u * 3.9); }
        else { g.moveTo(fx, fy - u * 2.5); g.lineTo(fx + stride * 0.8, fy - u * 1.7); g.moveTo(fx, fy - u * 2.5); g.lineTo(fx - stride * 0.8, fy - u * 1.7); }
        g.stroke();
        if (top && !caption.textContent) {
          caption.textContent = page.total ? (page.have === page.total ? 'All ' + page.total + ' — the whole way up' : page.have + ' of ' + page.total + ' — still climbing') : 'The top';
        }
        if (t > 3.8) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.8) / 0.6)); }
        return t < 4.5;
      });
    },

    // Die Hard: a tower block's windows light up floor by floor, then glass bursts out across the
    // screen.
    tower: function () {
      var c = curtain({ max: 6000, background: 'linear-gradient(to bottom, rgb(6 8 20), rgb(20 24 44))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var floors = Math.max(12, Math.min(32, (page.steps.length || 5) * 5)), cols = 8;
      var bw = Math.min(W * 0.32, 340), bh = H * 0.82, bx = W / 2 - bw / 2, by = H - bh, fh = bh / floors, ww = bw / cols;
      var windows = [];
      for (var f = 0; f < floors; f++) { var row = []; for (var k = 0; k < cols; k++) { row.push(Math.random() > 0.25); } windows.push(row); }
      var shards = [], burst = false;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var fade = t > 3.3 ? Math.max(0, 1 - (t - 3.3) / 0.9) : 1;
        c.el.style.background = fade < 1 ? 'rgba(10, 12, 28, ' + fade + ')' : '';
        g.globalAlpha = fade;
        g.fillStyle = 'rgb(14 16 30)';
        g.fillRect(bx - bw * 0.9, by + bh * 0.45, bw * 0.6, bh); g.fillRect(bx + bw * 1.25, by + bh * 0.3, bw * 0.55, bh);
        g.fillStyle = 'rgb(26 28 44)'; g.fillRect(bx, by, bw, bh);
        var up = t / 2.4 * floors;
        for (var f = 0; f < floors; f++) {
          for (var k = 0; k < cols; k++) {
            g.fillStyle = f < up && windows[f][k] ? 'rgb(255 214 120)' : 'rgb(42 46 62)';
            g.fillRect(bx + k * ww + ww * 0.2, by + bh - (f + 1) * fh + fh * 0.25, ww * 0.6, fh * 0.5);
          }
        }
        if (t > 2.7 && !burst) {
          burst = true;
          shakePage(7, 420);
          for (var s = 0; s < 140; s++) {
            var ang = Math.random() * Math.PI * 2, v = 4 + Math.random() * 12;
            shards.push({ x: bx + Math.random() * bw, y: by + bh * (0.15 + Math.random() * 0.2), vx: Math.cos(ang) * v, vy: Math.sin(ang) * v - 3,
                          a: Math.random() * 6, va: (Math.random() - 0.5) * 0.4, s: 6 + Math.random() * 16 });
          }
        }
        shards.forEach(function (p) {
          p.vy += 0.3; p.x += p.vx; p.y += p.vy; p.a += p.va;
          g.save(); g.translate(p.x, p.y); g.rotate(p.a);
          g.fillStyle = 'rgba(200, 230, 255, 0.7)';
          g.beginPath(); g.moveTo(0, -p.s); g.lineTo(p.s * 0.6, p.s * 0.5); g.lineTo(-p.s * 0.5, p.s * 0.3); g.closePath(); g.fill();
          g.restore();
        });
        g.globalAlpha = 1;
        return t < 4.3;
      });
    },

    // Transformers: the poster in mechanical panels, flung apart, that slide, turn and lock back
    // together.
    panels: function () {
      var backdrop = document.querySelector('.collection-backdrop');
      var src = page.posters.length ? bigger(page.posters[0]) : (backdrop ? backdrop.currentSrc || backdrop.src : null);
      var c = curtain({ max: 5000, background: 'radial-gradient(circle at 50% 40%, rgb(60 66 76), rgb(12 14 18))' });
      var board = document.createElement('div');
      board.className = 'sc-panels';
      var cols = 4, rows = 6, n = 0;
      for (var r = 0; r < rows; r++) {
        for (var k = 0; k < cols; k++) {
          var tile = document.createElement('span');
          tile.className = 'sc-panel';
          tile.style.background = src ? 'url("' + src.replace(/"/g, '%22') + '") ' + (k / (cols - 1) * 100) + '% ' + (r / (rows - 1) * 100) + '% / ' +
            (cols * 100) + '% ' + (rows * 100) + '%' : 'linear-gradient(135deg, rgb(150 156 168), rgb(70 74 84))';
          tile.style.boxShadow = 'inset 0 0 0 1px rgba(255, 255, 255, 0.18), 0 0 0 1px rgba(0, 0, 0, 0.6)';
          board.appendChild(tile);
          if (tile.animate) {
            tile.animate([
              { translate: ((Math.random() - 0.5) * 140) + 'vw ' + ((Math.random() - 0.5) * 120) + 'vh', rotate: ((Math.random() - 0.5) * 540) + 'deg', opacity: 0 },
              { translate: '0 0', rotate: '0deg', opacity: 1 },
            ], { duration: 700, delay: 200 + n * 55 + Math.random() * 200, easing: 'cubic-bezier(.2, 1.35, .45, 1)', fill: 'both' });
          }
          n++;
        }
      }
      c.el.appendChild(board);
      window.setTimeout(function () { board.classList.add('is-locked'); shakePage(3, 200); }, 200 + n * 55 + 900);
      window.setTimeout(c.finish, 200 + n * 55 + 1900);
    },

    // Scream: a phone rings in the dark -- caller unknown -- with a question about the missing
    // films, then a slash cuts the dark in two.
    phone: function () {
      var c = curtain({ max: 7500, background: 'black' });
      var call = document.createElement('div');
      call.className = 'sc-call';
      call.style.color = 'rgb(235 235 240)';
      call.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z"/></svg>';
      text('strong', null, 'Incoming call', call);
      text('small', null, 'Unknown', call);
      c.el.appendChild(call);
      var ring = function () {
        if (call.animate) {
          call.animate([{ rotate: '0deg' }, { rotate: '-6deg' }, { rotate: '6deg' }, { rotate: '-6deg' }, { rotate: '0deg' }], { duration: 360, iterations: 3 });
        }
      };
      ring(); window.setTimeout(ring, 1300);
      var line = text('p', 'sc-brief sc-brief--centre', '', c.el);
      line.style.top = '70%';
      var n = page.missing.length;
      window.setTimeout(function () {
        typeOut(line, n ? 'Do you know how many ' + page.short + ' films you still don’t have? … ' + n + '.'
                        : 'You have every last one of them. For now.', 32);
      }, 1700);
      window.setTimeout(function () {
        call.remove(); line.remove();
        var slash = document.createElement('span');
        slash.className = 'sc-slash';
        slash.style.background = 'rgb(255 255 255)';
        c.el.appendChild(slash);
        window.setTimeout(function () {
          slash.remove();
          c.el.style.background = 'transparent';
          [['polygon(0 0, 100% 0, 100% 40%, 0 62%)', '0 -70vh'], ['polygon(0 62%, 100% 40%, 100% 100%, 0 100%)', '0 70vh']].forEach(function (half) {
            var part = document.createElement('span');
            part.className = 'sc-half';
            part.style.background = 'black';
            part.style.clipPath = half[0];
            c.el.appendChild(part);
            if (part.animate) { part.animate([{ translate: '0 0' }, { translate: half[1] }], { duration: 800, easing: 'cubic-bezier(.6, 0, .8, .4)', fill: 'forwards' }); }
          });
          window.setTimeout(c.finish, 700);
        }, 260);
      }, 5200);
    },

    // Paranormal Activity: the page as night-vision footage with a running timestamp; it
    // flickers, and the frame jolts. The page stays usable.
    nightvision: function () {
      var c = curtain({ max: 6000, through: true });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var stamp = text('p', 'sc-hud sc-hud--left', '', c.el);
      stamp.style.color = 'rgb(220 255 220)';
      var rec = text('p', 'sc-hud', '● REC', c.el);
      rec.style.color = 'rgb(255 70 70)';
      rec.style.top = '6%';
      var start = 3 * 3600 + 12 * 60 + 7, jolted = false;
      var two = function (v) { return (v < 10 ? '0' : '') + v; };
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var fade = t > 3.6 ? Math.max(0, 1 - (t - 3.6) / 0.6) : 1;
        g.globalAlpha = fade;
        g.fillStyle = 'rgba(16, 52, 22, 0.55)'; g.fillRect(0, 0, W, H);
        g.fillStyle = 'rgba(200, 255, 200, 0.16)';
        for (var i = 0; i < 1100; i++) { g.fillRect(Math.random() * W, Math.random() * H, 1.5, 1.5); }
        var edge = g.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.3, W / 2, H / 2, Math.max(W, H) * 0.7);
        edge.addColorStop(0, 'rgba(0, 0, 0, 0)'); edge.addColorStop(1, 'rgba(0, 0, 0, 0.75)');
        g.fillStyle = edge; g.fillRect(0, 0, W, H);
        if (t > 2.3 && t < 2.62) { g.fillStyle = 'rgba(0, 0, 0, 0.92)'; g.fillRect(0, 0, W, H); }
        if (t > 2.62 && !jolted) { jolted = true; shakePage(12, 320); }
        g.globalAlpha = 1;
        var secs = start + Math.floor(t * 41);
        stamp.textContent = 'NIGHT #' + Math.max(1, page.missing.length) + '   ' + two(Math.floor(secs / 3600)) + ':' +
          two(Math.floor(secs / 60) % 60) + ':' + two(secs % 60) + ' AM';
        stamp.style.opacity = rec.style.opacity = String(fade);
        if (Math.floor(t * 2) % 2) { rec.style.opacity = String(0.2 * fade); }
        return t < 4.2;
      });
    },

    // Final Destination: a chain reaction -- a domino for each film -- until the last one brings
    // the whole curtain down.
    dominoes: function () {
      var c = curtain({ max: 6500, background: 'rgb(10 10 12)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var n = Math.max(6, Math.min(16, page.steps.length * 2 || 8));
      var gap = Math.min(72, W * 0.7 / n), dw = gap * 0.3, dh = gap * 1.35, x0 = W / 2 - gap * (n - 1) / 2, base = H * 0.66;
      var begin = 0.5, each = 0.19, dropped = false;
      var left = page.missing.length;
      var caption = text('p', 'sc-intro-caption', left ? 'One thing leads to another… ' + plural(left, 'film') + ' still out there' : 'One thing leads to another…', c.el);
      caption.style.color = 'rgb(220 220 225)';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.fillStyle = 'rgba(255, 255, 255, 0.08)'; g.fillRect(0, base, W, 2);
        for (var i = 0; i < n; i++) {
          var lean = Math.max(0, Math.min(1, (t - begin - i * each) / 0.22)) * (i === n - 1 ? Math.PI / 2 : 0.95);
          g.save(); g.translate(x0 + i * gap + dw / 2, base); g.rotate(lean);
          g.fillStyle = i === n - 1 ? 'rgb(205 40 40)' : 'rgb(235 233 226)';
          g.fillRect(-dw, -dh, dw, dh);
          g.fillStyle = 'rgb(20 20 24)';
          g.beginPath(); g.arc(-dw / 2, -dh * 0.72, dw * 0.12, 0, Math.PI * 2); g.arc(-dw / 2, -dh * 0.28, dw * 0.12, 0, Math.PI * 2); g.fill();
          g.restore();
        }
        if (t > begin + n * each + 0.35 && !dropped) {
          dropped = true;
          shakePage(5, 300);
          if (c.el.animate) { c.el.animate([{ translate: '0 0' }, { translate: '0 110vh' }], { duration: 750, easing: 'cubic-bezier(.5, 0, .75, 0)', fill: 'forwards' }); }
          window.setTimeout(c.finish, 700);
        }
        return true;
      });
    },

    // Predator: the page in heat colours, a shimmering outline crossing it, and three red dots
    // that settle on the title. The page stays usable.
    thermal: function () {
      var c = curtain({ max: 6000, through: true });
      var marks = c.canvas(), heat = c.canvas();   // heat is underneath (the later one goes first)
      var W = heat.width, H = heat.height, h = heat.getContext('2d'), g = marks.getContext('2d');
      heat.style.mixBlendMode = 'color';
      var hot = h.createRadialGradient(W / 2, H * 0.45, 0, W / 2, H * 0.45, Math.max(W, H) * 0.65);
      hot.addColorStop(0, 'rgb(255 255 140)'); hot.addColorStop(0.25, 'rgb(255 90 20)');
      hot.addColorStop(0.55, 'rgb(150 20 170)'); hot.addColorStop(1, 'rgb(20 30 150)');
      h.fillStyle = hot; h.fillRect(0, 0, W, H);
      var box = h1 ? h1.getBoundingClientRect() : { left: W / 2, top: H / 3, width: 0, height: 0 };
      var aim = { x: box.left + Math.min(box.width, 300) / 2, y: box.top + box.height / 2 };
      var dots = [0, 1, 2].map(function (i) { return { x: Math.random() * W, y: Math.random() * H, ox: Math.cos(i * 2.094 - 1.57) * 14, oy: Math.sin(i * 2.094 - 1.57) * 14 }; });
      run(c, function (t) {
        var fade = t > 3.7 ? Math.max(0, 1 - (t - 3.7) / 0.6) : Math.min(1, t / 0.4);
        heat.style.opacity = String(0.85 * fade);
        g.clearRect(0, 0, W, H);
        var walk = Math.min(1, t / 2.6), sx = W * 0.1 + walk * W * 0.35, sy = H * 0.55, s = H * 0.28;
        g.strokeStyle = 'rgba(255, 255, 255, ' + 0.4 * fade + ')'; g.lineWidth = 2;
        g.beginPath();
        for (var a = 0; a <= Math.PI * 2 + 0.01; a += 0.12) {
          var wob = Math.sin(a * 7 + t * 9) * 4;
          var px = sx + Math.cos(a) * (s * 0.18 + wob) * (a > Math.PI ? 1.6 : 0.9), py = sy + Math.sin(a) * (s * 0.5 + wob);
          if (a === 0) { g.moveTo(px, py); } else { g.lineTo(px, py); }
        }
        g.stroke();
        var lock = Math.min(1, Math.max(0, (t - 1.6) / 1.4)), e = 1 - Math.pow(1 - lock, 3);
        dots.forEach(function (d) {
          var x = d.x + (aim.x + d.ox - d.x) * e + (lock < 1 ? (Math.random() - 0.5) * 3 : 0);
          var y = d.y + (aim.y + d.oy - d.y) * e + (lock < 1 ? (Math.random() - 0.5) * 3 : 0);
          g.fillStyle = 'rgba(255, 30, 20, ' + fade + ')';
          g.shadowColor = 'rgb(255 30 20)'; g.shadowBlur = 10;
          g.beginPath(); g.arc(x, y, 4, 0, Math.PI * 2); g.fill();
          g.shadowBlur = 0;
        });
        return t < 4.3;
      });
    },

    // Dragon Ball Z: an aura builds round the title, crackling, the page shakes harder and harder,
    // and a blast of light whites it all out. The page stays usable.
    powerup: function () {
      var c = curtain({ max: 5000, through: true });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var box = h1 ? h1.getBoundingClientRect() : { left: W * 0.3, top: H * 0.4, width: W * 0.4, height: 60 };
      var wide = Math.min(box.width, W * 0.8), flames = [], lastShake = 0;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var k = Math.min(1, t / 2.6);
        var aura = g.createRadialGradient(box.left + wide / 2, box.top + box.height / 2, 0, box.left + wide / 2, box.top + box.height / 2, wide * (0.5 + k * 0.5));
        aura.addColorStop(0, 'rgba(255, 230, 90, ' + 0.35 * k + ')'); aura.addColorStop(1, 'rgba(255, 200, 40, 0)');
        g.fillStyle = aura; g.fillRect(0, 0, W, H);
        for (var f = 0; f < 6 + k * 18; f++) {
          flames.push({ x: box.left + Math.random() * wide, y: box.top + box.height + 10, v: 2 + Math.random() * 5 * (0.5 + k), life: 1 });
        }
        flames.forEach(function (p) {
          p.y -= p.v; p.x += (Math.random() - 0.5) * 2; p.life -= 0.03;
          if (p.life > 0) {
            g.fillStyle = 'rgba(255, ' + Math.round(200 + Math.random() * 55) + ', 80, ' + p.life * 0.8 + ')';
            g.fillRect(p.x, p.y, 3, 7);
          }
        });
        flames = flames.filter(function (p) { return p.life > 0; });
        if (Math.random() < k * 0.45) {
          g.strokeStyle = 'rgba(200, 230, 255, 0.95)'; g.lineWidth = 2;
          var x = box.left + Math.random() * wide, y = box.top - 30;
          g.beginPath(); g.moveTo(x, y);
          for (var j = 0; j < 6; j++) { x += (Math.random() - 0.5) * 40; y += box.height / 3 + Math.random() * 20; g.lineTo(x, y); }
          g.stroke();
        }
        if (t - lastShake > 0.28 && t < 2.8) { lastShake = t; shakePage(2 + k * 8, 240); }
        if (t > 2.7) {
          var w = t < 3.0 ? (t - 2.7) / 0.3 : Math.max(0, 1 - (t - 3.0) / 0.9);
          c.el.style.background = 'rgba(255, 255, 255, ' + w + ')';
        }
        return t < 3.95;
      });
    },

    // X-Men: a dome of light scans a crowd of points and locks on to one for each film you own,
    // then flashes outward.
    dome: function () {
      var c = curtain({ max: 6000, background: 'radial-gradient(circle at 50% 50%, rgb(20 32 78), rgb(4 6 18))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H / 2, R = Math.min(W, H) * 0.4;
      var have = parseInt(page.have, 10) || 6, dots = [];
      for (var i = 0; i < 180; i++) {
        var a = Math.random() * Math.PI * 2, d = Math.sqrt(Math.random()) * R * 0.92;
        dots.push({ x: cx + Math.cos(a) * d, y: cy + Math.sin(a) * d, a: a, found: false, pick: false });
      }
      dots.slice(0, Math.min(have, 30)).forEach(function (dot) { dot.pick = true; });
      var label = text('p', 'sc-tracker-label', 'Searching…', c.el);
      label.style.color = 'rgb(170 205 255)';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var beam = (t * 2.4) % (Math.PI * 2);
        g.strokeStyle = 'rgba(120, 180, 255, 0.35)'; g.lineWidth = 1.5;
        for (var ring = 1; ring <= 3; ring++) { g.beginPath(); g.arc(cx, cy, R * ring / 3, 0, Math.PI * 2); g.stroke(); }
        g.fillStyle = 'rgba(120, 180, 255, 0.16)';
        g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, R, beam - 0.45, beam); g.closePath(); g.fill();
        var count = 0;
        dots.forEach(function (dot) {
          var diff = (beam - ((dot.a % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2) + Math.PI * 4) % (Math.PI * 2);
          if (dot.pick && diff < 0.3 && t > 0.6) { dot.found = true; }
          if (dot.found) {
            count++;
            g.fillStyle = 'rgb(255 255 255)'; g.beginPath(); g.arc(dot.x, dot.y, 3.5, 0, Math.PI * 2); g.fill();
            g.strokeStyle = 'rgba(255, 70, 70, 0.9)'; g.beginPath(); g.arc(dot.x, dot.y, 8, 0, Math.PI * 2); g.stroke();
          } else {
            g.fillStyle = 'rgba(150, 190, 255, 0.4)'; g.fillRect(dot.x - 1, dot.y - 1, 2, 2);
          }
        });
        label.textContent = count ? 'Located ' + count + (page.total ? ' of ' + page.total : '') : 'Searching…';
        if (t > 3.3) {
          var grow = (t - 3.3) / 0.9;
          g.strokeStyle = 'rgba(200, 225, 255, ' + Math.max(0, 1 - grow) + ')'; g.lineWidth = 10;
          g.beginPath(); g.arc(cx, cy, R * (1 + grow * 2.5), 0, Math.PI * 2); g.stroke();
          c.el.style.opacity = String(Math.max(0, 1 - grow));
        }
        return t < 4.2;
      });
    },

    // Pirates of the Caribbean: a compass needle spins and settles, the sea rolls in, and the
    // waves part to let the page through.
    compass: function () {
      var c = curtain({ max: 6000, background: 'linear-gradient(to bottom, rgb(10 20 40), rgb(14 42 62))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H * 0.4, Rc = Math.min(W, H) * 0.18, settle = Math.PI * 12 + 0.5;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var part = t > 3.0 ? Math.min(1, (t - 3.0) / 1.0) : 0;
        c.el.style.background = part ? 'rgba(12, 30, 50, ' + (1 - part) + ')' : '';
        g.globalAlpha = 1 - part;
        g.strokeStyle = 'rgb(205 165 85)'; g.lineWidth = 5;
        g.beginPath(); g.arc(cx, cy, Rc, 0, Math.PI * 2); g.stroke();
        g.fillStyle = 'rgb(205 165 85)'; g.font = '700 ' + Math.round(Rc * 0.22) + 'px Georgia, serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
        [['N', 0], ['E', 0.5], ['S', 1], ['W', 1.5]].forEach(function (p) {
          var a = p[1] * Math.PI - Math.PI / 2;
          g.fillText(p[0], cx + Math.cos(a) * Rc * 0.75, cy + Math.sin(a) * Rc * 0.75);
        });
        var damp = Math.exp(-t * 1.5), na = settle * (1 - damp) + Math.sin(t * 9) * damp * 0.5 - Math.PI / 2;
        g.fillStyle = 'rgb(200 50 40)';
        g.beginPath(); g.moveTo(cx + Math.cos(na) * Rc * 0.62, cy + Math.sin(na) * Rc * 0.62);
        g.lineTo(cx + Math.cos(na + 1.57) * Rc * 0.07, cy + Math.sin(na + 1.57) * Rc * 0.07);
        g.lineTo(cx + Math.cos(na - 1.57) * Rc * 0.07, cy + Math.sin(na - 1.57) * Rc * 0.07); g.closePath(); g.fill();
        g.globalAlpha = 1;
        if (t > 1.5) {
          var level = H * (1 - Math.min(0.85, (t - 1.5) / 1.3 * 0.85));
          [['rgba(25, 80, 130, 0.92)', 0, 30], ['rgba(35, 105, 155, 0.85)', 1.3, 22], ['rgba(50, 130, 175, 0.8)', 2.6, 16]].forEach(function (wave, i) {
            var shift = (i % 2 ? -1 : 1) * part * W * 0.6;
            g.fillStyle = wave[0];
            [-1, 1].forEach(function (side) {
              g.beginPath();
              var from = side < 0 ? 0 : W / 2, to = side < 0 ? W / 2 : W, dx = side * Math.abs(shift);
              g.moveTo(from + dx, H);
              for (var x = from; x <= to; x += 12) { g.lineTo(x + dx, level + i * 26 + Math.sin(x / 70 + t * 2.4 + wave[1]) * wave[2]); }
              g.lineTo(to + dx, H); g.closePath(); g.fill();
            });
          });
        }
        return t < 4.2;
      });
    },

    // Resident Evil: a red laser grid sweeps down a dark corridor, then a containment report
    // lists your missing films as unaccounted for.
    lasers: function () {
      var c = curtain({ max: 8000, background: 'black' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H / 2, w0 = W * 0.08, h0 = H * 0.08, reported = false;
      var report = text('p', 'sc-brief sc-brief--report', '', c.el);
      report.style.color = 'rgb(255 95 85)';
      var at = function (d) { return { l: cx - w0 - (cx - w0) * d, r: cx + w0 + (W - cx - w0) * d, t: cy - h0 - (cy - h0) * d, b: cy + h0 + (H - cy - h0) * d }; };
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgba(120, 130, 140, 0.35)'; g.lineWidth = 1;
        var far = at(0);
        g.strokeRect(far.l, far.t, far.r - far.l, far.b - far.t);
        [[0, 0, far.l, far.t], [W, 0, far.r, far.t], [0, H, far.l, far.b], [W, H, far.r, far.b]].forEach(function (s) { g.beginPath(); g.moveTo(s[0], s[1]); g.lineTo(s[2], s[3]); g.stroke(); });
        for (var d = 0.2; d < 1; d += 0.2) { var q = at(d); g.strokeRect(q.l, q.t, q.r - q.l, q.b - q.t); }
        var pass = function (start, grid) {
          var d = Math.min(1, Math.max(0, (t - start) / 1.1));
          if (d <= 0 || d >= 1) { return; }
          var q = at(d * d);
          g.strokeStyle = 'rgba(255, 40, 30, 0.95)'; g.lineWidth = 2 + d * 2; g.shadowColor = 'rgb(255 40 30)'; g.shadowBlur = 12;
          g.beginPath();
          var lines = grid ? 6 : 1;
          for (var i = 1; i <= lines; i++) { var y = q.t + (q.b - q.t) * i / (lines + 1); g.moveTo(q.l, y); g.lineTo(q.r, y); }
          if (grid) { for (var j = 1; j <= 6; j++) { var x = q.l + (q.r - q.l) * j / 7; g.moveTo(x, q.t); g.lineTo(x, q.b); } }
          g.stroke(); g.shadowBlur = 0;
        };
        pass(0.3, false); pass(1.4, true);
        if (t > 2.6 && !reported) {
          reported = true;
          var gone = page.missing;
          typeOut(report, 'CONTAINMENT REPORT — ' + page.name.toUpperCase() + '\n' +
            (page.total ? 'In the library: ' + page.have + ' of ' + page.total + '\n' : '') +
            (gone.length ? 'Unaccounted for: ' + gone.slice(0, 4).join(', ') + (gone.length > 4 ? ' and ' + (gone.length - 4) + ' more' : '') : 'All specimens contained.'), 22);
        }
        return t < 6.8;
      });
    },

    // Bourne: a surveillance map; a dot hops from city to city, a city for each film, with
    // readouts updating, until the feed is lost.
    surveil: function () {
      var c = curtain({ max: 7000, background: 'rgb(6 12 16)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cities = [], route = [], hops = Math.max(3, Math.min(8, page.steps.length || 4));
      for (var i = 0; i < 46; i++) { cities.push({ x: W * (0.08 + Math.random() * 0.62), y: H * (0.15 + Math.random() * 0.7) }); }
      for (var h = 0; h < hops; h++) { route.push(cities[Math.floor(Math.random() * cities.length)]); }
      var feed = text('p', 'sc-hud', '', c.el);
      feed.style.color = 'rgb(120 230 220)';
      feed.style.whiteSpace = 'pre-line';
      var each = 0.5, lostAt = hops * each + 0.6;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgba(80, 200, 200, 0.1)'; g.lineWidth = 1;
        for (var x = 0; x < W; x += 40) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); }
        for (var y = 0; y < H; y += 40) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
        g.fillStyle = 'rgba(120, 230, 220, 0.45)';
        cities.forEach(function (city) { g.fillRect(city.x - 1.5, city.y - 1.5, 3, 3); });
        var leg = Math.min(hops - 1, Math.floor(t / each)), along = Math.min(1, (t - leg * each) / (each * 0.7));
        g.strokeStyle = 'rgba(255, 70, 60, 0.85)'; g.lineWidth = 2;
        g.beginPath(); g.moveTo(route[0].x, route[0].y);
        for (var r = 1; r <= leg; r++) { g.lineTo(route[r].x, route[r].y); }
        var from = route[leg], to = route[Math.min(hops - 1, leg + 1)], px = from.x + (to.x - from.x) * along, py = from.y + (to.y - from.y) * along;
        if (leg < hops - 1) { g.lineTo(px, py); }
        g.stroke();
        var pulse = 6 + Math.abs(Math.sin(t * 6)) * 6;
        g.strokeStyle = 'rgba(255, 70, 60, 0.9)'; g.beginPath(); g.arc(px, py, pulse, 0, Math.PI * 2); g.stroke();
        feed.textContent = 'SUBJECT    ' + page.name.toUpperCase() + '\nPOSITION   ' + (py / H * 90).toFixed(4) + ' N  ' + (px / W * 180).toFixed(4) + ' E' +
          '\nSIGHTING   ' + (leg + 1) + ' of ' + hops + '\nSTATUS     ' + (t < lostAt ? 'TRACKING' : 'SIGNAL LOST');
        if (t > lostAt) {
          for (var b = 0; b < 14; b++) {
            g.fillStyle = 'rgba(' + (Math.random() > 0.5 ? '120, 230, 220' : '6, 12, 16') + ', 0.8)';
            g.fillRect(0, Math.random() * H, W, 2 + Math.random() * 18);
          }
        }
        return t < lostAt + 0.7;
      });
    },

    // Ice Age: frost creeps in from the edges and freezes the screen, then cracks and falls
    // away. The page stays usable.
    freeze: function () {
      var c = curtain({ max: 5500, through: true });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var segs = [], reach = Math.min(W, H) * 0.12;
      var grow = function (x, y, ang, len, depth, born) {
        var x2 = x + Math.cos(ang) * len, y2 = y + Math.sin(ang) * len;
        segs.push([x, y, x2, y2, born]);
        if (depth < 4) {
          grow(x2, y2, ang + 0.5 + Math.random() * 0.3, len * 0.68, depth + 1, born + 0.18);
          grow(x2, y2, ang - 0.5 - Math.random() * 0.3, len * 0.68, depth + 1, born + 0.18);
        }
      };
      for (var i = 0; i < 40; i++) {
        var side = i % 4, f = Math.random();
        var x = side === 0 ? f * W : side === 1 ? W : side === 2 ? f * W : 0;
        var y = side === 0 ? 0 : side === 1 ? f * H : side === 2 ? H : f * H;
        var ang = [Math.PI / 2, Math.PI, -Math.PI / 2, 0][side] + (Math.random() - 0.5) * 0.8;
        grow(x, y, ang, reach * (0.6 + Math.random() * 0.6), 0, Math.random() * 0.5);
      }
      var crack = [[W * 0.15, H * 0.55]];
      for (var k = 1; k <= 10; k++) { crack.push([W * 0.15 + W * 0.7 * k / 10, H * 0.55 + (Math.random() - 0.5) * H * 0.18]); }
      var fell = false;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var haze = Math.min(1, t / 2.4);
        var edge = g.createRadialGradient(W / 2, H / 2, Math.min(W, H) * (0.6 - haze * 0.3), W / 2, H / 2, Math.max(W, H) * 0.75);
        edge.addColorStop(0, 'rgba(225, 245, 255, 0)'); edge.addColorStop(1, 'rgba(225, 245, 255, ' + 0.7 * haze + ')');
        g.fillStyle = edge; g.fillRect(0, 0, W, H);
        g.strokeStyle = 'rgba(240, 250, 255, 0.85)'; g.lineWidth = 1.4;
        g.beginPath();
        segs.forEach(function (s) {
          if (t < s[4]) { return; }
          var p = Math.min(1, (t - s[4]) / 0.25);
          g.moveTo(s[0], s[1]); g.lineTo(s[0] + (s[2] - s[0]) * p, s[1] + (s[3] - s[1]) * p);
        });
        g.stroke();
        if (t > 2.5) {
          var shown = Math.min(crack.length, Math.ceil((t - 2.5) / 0.3 * crack.length));
          g.strokeStyle = 'rgba(255, 255, 255, 0.95)'; g.lineWidth = 3;
          g.beginPath(); g.moveTo(crack[0][0], crack[0][1]);
          for (var j = 1; j < shown; j++) { g.lineTo(crack[j][0], crack[j][1]); }
          g.stroke();
        }
        if (t > 3.0 && !fell) {
          fell = true;
          if (canvas.animate) { canvas.animate([{ translate: '0 0', opacity: 1 }, { translate: '0 45vh', opacity: 0 }], { duration: 900, easing: 'ease-in', fill: 'forwards' }); }
        }
        return t < 4.0;
      });
    },

    // Twilight: a misty blue-grey forest; a shaft of sunlight breaks through and the title
    // sparkles in it.
    forest: function () {
      var c = curtain({ max: 6000, background: 'linear-gradient(to bottom, rgb(150 165 175), rgb(70 85 95))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var layers = [['rgb(96 112 120)', 0.55], ['rgb(52 66 72)', 0.75], ['rgb(22 30 34)', 1]].map(function (layer) {
        var trees = [];
        for (var i = 0; i < 22; i++) { trees.push({ x: Math.random() * W, w: 18 + Math.random() * 30, h: H * layer[1] * (0.6 + Math.random() * 0.4) }); }
        return { colour: layer[0], trees: trees, depth: layer[1] };
      });
      var box = h1 ? h1.getBoundingClientRect() : { left: W * 0.3, top: H * 0.4, width: W * 0.4, height: 60 };
      var glints = [];
      for (var s = 0; s < 40; s++) { glints.push({ x: box.left + Math.random() * Math.min(box.width, W * 0.8), y: box.top + Math.random() * box.height, p: Math.random() * 6 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var clear = t > 3.0 ? Math.min(1, (t - 3.0) / 0.9) : 0;
        if (clear) { c.el.style.background = 'transparent'; }
        g.globalAlpha = 1 - clear;
        var sky = g.createLinearGradient(0, 0, 0, H);
        sky.addColorStop(0, 'rgb(150 165 175)'); sky.addColorStop(1, 'rgb(70 85 95)');
        if (clear) { g.fillStyle = sky; g.fillRect(0, 0, W, H); }
        layers.forEach(function (layer, li) {
          g.fillStyle = layer.colour;
          layer.trees.forEach(function (tree) {
            var x = tree.x + t * (li + 1) * 4;
            g.beginPath(); g.moveTo(x, H - tree.h); g.lineTo(x + tree.w / 2, H); g.lineTo(x - tree.w / 2, H); g.closePath(); g.fill();
          });
          g.fillStyle = 'rgba(210, 220, 225, 0.18)';
          g.fillRect(0, H * (0.55 + li * 0.12) + Math.sin(t + li) * 10, W, H * 0.08);
        });
        if (t > 1.8) {
          var beam = Math.min(1, (t - 1.8) / 0.8);
          g.fillStyle = 'rgba(255, 250, 230, ' + 0.28 * beam + ')';
          g.beginPath(); g.moveTo(W * 0.85, 0); g.lineTo(W, 0); g.lineTo(box.left + Math.min(box.width, W * 0.8), box.top + box.height + 40); g.lineTo(box.left, box.top + box.height + 40); g.closePath(); g.fill();
        }
        g.globalAlpha = 1;
        if (t > 2.2) {
          glints.forEach(function (p) {
            var a = Math.max(0, Math.sin(t * 5 + p.p)) * Math.min(1, (t - 2.2) / 0.5) * (t > 3.9 ? Math.max(0, 1 - (t - 3.9) / 0.5) : 1);
            g.fillStyle = 'rgba(255, 255, 255, ' + a + ')';
            g.beginPath(); g.moveTo(p.x, p.y - 6); g.lineTo(p.x + 1.5, p.y); g.lineTo(p.x, p.y + 6); g.lineTo(p.x - 1.5, p.y); g.closePath(); g.fill();
            g.beginPath(); g.moveTo(p.x - 6, p.y); g.lineTo(p.x, p.y + 1.5); g.lineTo(p.x + 6, p.y); g.lineTo(p.x, p.y - 1.5); g.closePath(); g.fill();
          });
        }
        return t < 4.5;
      });
    },

    // Shrek: a storybook opens on this collection's tale; a page turns, then one is torn out and
    // the page behind it appears.
    storybook: function () {
      var c = curtain({ max: 7500, background: 'radial-gradient(circle at 50% 45%, rgb(70 92 40), rgb(16 24 10))' });
      var paper = 'rgb(242 230 198)', ink = 'rgb(62 42 22)';
      var book = document.createElement('div');
      book.className = 'sc-book';
      var leftPage = document.createElement('div'), rightPage = document.createElement('div'), leaf = document.createElement('div');
      leftPage.className = 'sc-book-page sc-book-left';
      rightPage.className = 'sc-book-page sc-book-right';
      leaf.className = 'sc-book-leaf';
      var front = document.createElement('div'), back = document.createElement('div');
      front.className = 'sc-book-page sc-book-front';
      back.className = 'sc-book-page sc-book-back';
      [leftPage, rightPage, front, back].forEach(function (p) { p.style.background = paper; p.style.color = ink; });
      var n = page.missing.length;
      text('p', 'sc-book-big', 'Once upon a time', leftPage);
      text('p', null, 'there was a collection called ' + page.short + '.', front);
      text('p', null, page.total ? 'Of its ' + page.total + ' films, ' + page.have + ' lived happily in the library…' : 'Its films lived happily in the library…', back);
      text('p', null, n ? '…and ' + plural(n, 'film') + ' were still out in the wide world.' : '…every last one of them. The end.', rightPage);
      leaf.appendChild(front);
      leaf.appendChild(back);
      book.appendChild(leftPage);
      book.appendChild(rightPage);
      book.appendChild(leaf);
      c.el.appendChild(book);
      if (book.animate) { book.animate([{ opacity: 0, scale: 0.85 }, { opacity: 1, scale: 1 }], { duration: 600, easing: 'ease-out', fill: 'both' }); }
      window.setTimeout(function () {
        if (leaf.animate) { leaf.animate([{ rotate: 'y 0deg' }, { rotate: 'y -180deg' }], { duration: 1100, easing: 'ease-in-out', fill: 'forwards' }); }
      }, 1700);
      window.setTimeout(function () {
        if (rightPage.animate) { rightPage.animate([{ translate: '0 0', rotate: '0deg', opacity: 1 }, { translate: '30vw 80vh', rotate: '38deg', opacity: 0 }], { duration: 900, easing: 'ease-in', fill: 'forwards' }); }
        window.setTimeout(c.finish, 350);
      }, 4700);
    },

    // ---------------------------------------------------------------- 0.64.0

    // Halloween: a carved pumpkin flickers in the dark, its candle guttering, until it blows out.
    pumpkin: function () {
      var c = curtain({ max: 6000, background: 'black' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H * 0.52, R = Math.min(W, H) * 0.22, smoke = [], out = false;
      var n = page.missing.length;
      var caption = text('p', 'sc-intro-caption', n ? plural(n, 'film') + ' still out there tonight…' : 'All of them home tonight.', c.el);
      caption.style.color = 'rgb(255 160 60)';
      caption.style.top = '82%';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var life = t < 3.2 ? 1 - t / 4.5 : 0;
        var flame = life * (0.75 + Math.random() * 0.25);
        if (flame > 0) {
          var halo = g.createRadialGradient(cx, cy, R * 0.3, cx, cy, R * 2.6);
          halo.addColorStop(0, 'rgba(255, 140, 30, ' + 0.35 * flame + ')'); halo.addColorStop(1, 'rgba(255, 120, 20, 0)');
          g.fillStyle = halo; g.fillRect(0, 0, W, H);
        }
        var shade = 0.25 + flame * 0.75;
        g.fillStyle = 'rgb(' + Math.round(230 * shade) + ' ' + Math.round(110 * shade) + ' ' + Math.round(20 * shade) + ')';
        g.beginPath(); g.ellipse(cx, cy, R * 1.25, R, 0, 0, Math.PI * 2); g.fill();
        g.strokeStyle = 'rgba(0, 0, 0, 0.35)'; g.lineWidth = 3;
        [-0.6, -0.2, 0.2, 0.6].forEach(function (k) { g.beginPath(); g.ellipse(cx + k * R * 0.8, cy, R * 0.35, R * 0.98, 0, 0, Math.PI * 2); g.stroke(); });
        g.fillStyle = 'rgb(70 90 30)'; g.fillRect(cx - R * 0.08, cy - R * 1.18, R * 0.16, R * 0.28);
        g.fillStyle = flame > 0 ? 'rgba(255, ' + Math.round(200 + flame * 40) + ', 80, ' + (0.4 + flame * 0.6) + ')' : 'rgb(10 6 2)';
        g.beginPath();
        g.moveTo(cx - R * 0.6, cy - R * 0.15); g.lineTo(cx - R * 0.35, cy - R * 0.5); g.lineTo(cx - R * 0.15, cy - R * 0.15); g.closePath();
        g.moveTo(cx + R * 0.6, cy - R * 0.15); g.lineTo(cx + R * 0.35, cy - R * 0.5); g.lineTo(cx + R * 0.15, cy - R * 0.15); g.closePath();
        g.moveTo(cx - R * 0.7, cy + R * 0.45);
        for (var k = 0; k <= 8; k++) { g.lineTo(cx - R * 0.7 + k * R * 0.175, cy + R * (k % 2 ? 0.32 : 0.45)); }
        g.lineTo(cx + R * 0.6, cy + R * 0.62); g.lineTo(cx - R * 0.6, cy + R * 0.62); g.closePath();
        g.fill();
        if (t >= 3.2 && !out) {
          out = true;
          for (var s = 0; s < 30; s++) { smoke.push({ x: cx + (Math.random() - 0.5) * R * 0.3, y: cy - R * 0.9, r: 4, a: 0.5 }); }
        }
        smoke.forEach(function (p) {
          p.y -= 1.2; p.x += Math.sin(p.y / 20) * 0.8; p.r += 0.5; p.a *= 0.975;
          g.fillStyle = 'rgba(180, 180, 180, ' + p.a + ')'; g.beginPath(); g.arc(p.x, p.y, p.r, 0, Math.PI * 2); g.fill();
        });
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.7)); }
        return t < 4.3;
      });
    },

    // The Conjuring: an instant photo slides in and develops into the collection's poster -- with
    // a shadow in it that wasn't there before.
    polaroid: function () {
      var backdrop = document.querySelector('.collection-backdrop');
      var src = page.posters.length ? bigger(page.posters[0]) : (backdrop ? backdrop.currentSrc || backdrop.src : null);
      var c = curtain({ max: 6500, background: 'radial-gradient(circle at 50% 45%, rgb(36 32 28), rgb(10 9 8))' });
      var card = document.createElement('div');
      card.className = 'sc-polaroid';
      card.style.background = 'rgb(240 236 226)';
      var photo = document.createElement('div');
      photo.className = 'sc-polaroid-photo';
      photo.style.background = src ? 'url("' + src.replace(/"/g, '%22') + '") center / cover' : 'rgb(60 60 60)';
      var ghost = document.createElement('span');
      ghost.className = 'sc-polaroid-ghost';
      ghost.style.background = 'radial-gradient(ellipse at 50% 30%, rgba(0, 0, 0, 0.85), rgba(0, 0, 0, 0) 65%)';
      photo.appendChild(ghost);
      card.appendChild(photo);
      text('p', 'sc-polaroid-note', page.short, card).style.color = 'rgb(40 40 60)';
      c.el.appendChild(card);
      if (card.animate) {
        card.animate([{ translate: '-50% 80vh', rotate: '-14deg' }, { translate: '-50% -50%', rotate: '-4deg' }], { duration: 900, easing: 'cubic-bezier(.2, .9, .3, 1)', fill: 'both' });
        photo.animate([{ filter: 'brightness(2.6) sepia(1) contrast(0.25) blur(6px)' }, { filter: 'brightness(1) sepia(0.15) contrast(1) blur(0)' }],
                      { duration: 3200, delay: 700, easing: 'ease-in', fill: 'both' });
        ghost.animate([{ opacity: 0 }, { opacity: 0 }, { opacity: 0.9 }], { duration: 4400, easing: 'ease-in', fill: 'both' });
      }
      window.setTimeout(c.finish, 5400);
    },

    // The Exorcist: a foggy street at night, a lone figure under a streetlamp, the light
    // flickering as the fog rolls in.
    streetlamp: function () {
      var c = curtain({ max: 6000, background: 'rgb(8 10 14)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var lx = W * 0.32, ground = H * 0.84, fog = [];
      for (var i = 0; i < 9; i++) { fog.push({ x: Math.random() * W, y: ground - Math.random() * H * 0.35, r: 120 + Math.random() * 160, v: 0.3 + Math.random() * 0.6 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var fade = t > 3.7 ? Math.max(0, 1 - (t - 3.7) / 0.7) : 1;
        if (fade < 1) { c.el.style.background = 'rgba(8, 10, 14, ' + fade + ')'; }
        g.globalAlpha = fade;
        var flick = (t > 1.5 && t < 1.62) || (t > 2.3 && t < 2.36) || (t > 2.45 && t < 2.6) ? 0.15 : 0.9 + Math.random() * 0.1;
        g.fillStyle = 'rgb(16 18 24)'; g.fillRect(W * 0.6, H * 0.3, W * 0.32, ground - H * 0.3);
        g.fillStyle = 'rgba(255, 200, 110, 0.85)'; g.fillRect(W * 0.7, H * 0.38, W * 0.05, H * 0.07);
        g.fillStyle = 'rgb(20 22 28)'; g.fillRect(0, ground, W, H - ground);
        var cone = g.createRadialGradient(lx, H * 0.3, 0, lx, ground, H * 0.6);
        cone.addColorStop(0, 'rgba(255, 230, 170, ' + 0.55 * flick + ')'); cone.addColorStop(1, 'rgba(255, 230, 170, 0)');
        g.fillStyle = cone;
        g.beginPath(); g.moveTo(lx - 12, H * 0.3); g.lineTo(lx + 12, H * 0.3); g.lineTo(lx + H * 0.28, ground + 20); g.lineTo(lx - H * 0.28, ground + 20); g.closePath(); g.fill();
        g.fillStyle = 'rgb(30 32 38)'; g.fillRect(lx - 4, H * 0.3, 8, ground - H * 0.3);
        g.fillStyle = 'rgba(255, 235, 190, ' + flick + ')'; g.beginPath(); g.arc(lx, H * 0.3, 10, 0, Math.PI * 2); g.fill();
        var fx = lx + H * 0.06, s = H * 0.2;
        g.fillStyle = 'rgb(6 6 8)';
        g.beginPath(); g.ellipse(fx, ground - s * 0.92, s * 0.08, s * 0.08, 0, 0, Math.PI * 2); g.fill();
        g.fillRect(fx - s * 0.17, ground - s * 1.0, s * 0.34, s * 0.035);
        g.beginPath(); g.moveTo(fx - s * 0.12, ground - s * 0.82); g.lineTo(fx + s * 0.12, ground - s * 0.82); g.lineTo(fx + s * 0.16, ground); g.lineTo(fx - s * 0.16, ground); g.closePath(); g.fill();
        g.fillRect(fx + s * 0.16, ground - s * 0.35, s * 0.14, s * 0.1);
        fog.forEach(function (f) {
          f.x += f.v; if (f.x - f.r > W) { f.x = -f.r; }
          var puff = g.createRadialGradient(f.x, f.y, 0, f.x, f.y, f.r);
          puff.addColorStop(0, 'rgba(170, 180, 190, ' + 0.12 * Math.min(1, t / 1.5) + ')'); puff.addColorStop(1, 'rgba(170, 180, 190, 0)');
          g.fillStyle = puff; g.fillRect(f.x - f.r, f.y - f.r, f.r * 2, f.r * 2);
        });
        g.globalAlpha = 1;
        return t < 4.4;
      });
    },

    // The Purge: an emergency broadcast -- alert bars, a notice about the missing films and a
    // red siren sweep.
    broadcast: function () {
      var c = curtain({ max: 7000, background: 'black' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var n = page.missing.length;
      var notice = text('p', 'sc-brief sc-brief--centre', '', c.el);
      notice.style.color = 'rgb(240 240 240)';
      typeOut(notice, 'THIS IS NOT A TEST. ' + (n ? plural(n, 'film') + ' of ' + page.short + ' remain at large tonight. Secure your library.' :
        'Every film of ' + page.short + ' is safely inside tonight.'), 30);
      var ticker = text('p', 'sc-ticker', (page.missing.length ? 'STILL OUT: ' + page.missing.join(' · ') + ' · ' : '') + 'IN THE LIBRARY: ' + page.have + (page.total ? ' OF ' + page.total : '') + ' · ', c.el);
      ticker.style.color = 'rgb(255 255 255)';
      ticker.style.background = 'rgb(170 20 20)';
      if (ticker.animate) { ticker.animate([{ translate: '100vw 0' }, { translate: '-100% 0' }], { duration: 9000, easing: 'linear', fill: 'both' }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var on = Math.floor(t * 3) % 2 === 0;
        for (var b = 0; b < 3; b++) { g.fillStyle = on === (b % 2 === 0) ? 'rgb(200 20 20)' : 'rgb(240 240 240)'; g.fillRect(0, b * 14, W, 14); }
        g.fillStyle = 'rgb(240 240 240)'; g.font = '700 ' + Math.round(Math.min(W, 900) / 26) + 'px ui-monospace, monospace'; g.textAlign = 'center';
        g.fillText('EMERGENCY BROADCAST', W / 2, H * 0.18);
        var a = t * 3.2;
        var beam = g.createRadialGradient(W / 2, H * 0.02, 0, W / 2, H * 0.02, Math.max(W, H));
        beam.addColorStop(0, 'rgba(255, 30, 20, 0.45)'); beam.addColorStop(1, 'rgba(255, 30, 20, 0)');
        g.fillStyle = beam;
        g.beginPath(); g.moveTo(W / 2, H * 0.02); g.arc(W / 2, H * 0.02, Math.max(W, H), a - 0.3, a + 0.3); g.closePath(); g.fill();
        return t < 6.2;
      });
    },

    // John Wick: neon rain on a dark street, and a gold coin spinning down to land on the title.
    coin: function () {
      var c = curtain({ max: 5500, background: 'rgb(10 8 16)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var drops = [];
      for (var i = 0; i < 260; i++) { drops.push({ x: Math.random() * W, y: Math.random() * H, l: 10 + Math.random() * 20, v: 12 + Math.random() * 10 }); }
      var box = h1 ? h1.getBoundingClientRect() : { left: W * 0.4, top: H * 0.4, width: W * 0.2, height: 40 };
      var land = { x: box.left + Math.min(box.width, W * 0.6) / 2, y: box.top + box.height / 2 };
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var fade = t > 3.3 ? Math.max(0, 1 - (t - 3.3) / 0.8) : 1;
        if (fade < 1) { c.el.style.background = 'rgba(10, 8, 16, ' + fade + ')'; }
        g.globalAlpha = fade;
        [['rgba(255, 40, 160, 0.35)', 0.2, 0.35], ['rgba(40, 220, 255, 0.3)', 0.8, 0.3]].forEach(function (n) {
          var glow = g.createRadialGradient(W * n[1], H * n[2], 0, W * n[1], H * n[2], W * 0.35);
          glow.addColorStop(0, n[0]); glow.addColorStop(1, 'rgba(0, 0, 0, 0)');
          g.fillStyle = glow; g.fillRect(0, 0, W, H);
          var wet = g.createRadialGradient(W * n[1], H * (1.3 - n[2]), 0, W * n[1], H * (1.3 - n[2]), W * 0.2);
          wet.addColorStop(0, n[0]); wet.addColorStop(1, 'rgba(0, 0, 0, 0)');
          g.fillStyle = wet; g.fillRect(0, H * 0.7, W, H * 0.3);
        });
        g.strokeStyle = 'rgba(170, 190, 220, 0.4)'; g.lineWidth = 1; g.beginPath();
        drops.forEach(function (d) { d.y += d.v; d.x -= d.v * 0.15; if (d.y > H) { d.y = -20; d.x = Math.random() * W * 1.1; } g.moveTo(d.x, d.y); g.lineTo(d.x - d.l * 0.15, d.y + d.l); });
        g.stroke();
        var fall = Math.min(1, t / 2.4), x = W * 0.5 + (land.x - W * 0.5) * fall, y = -40 + (land.y + 40) * (1 - Math.pow(1 - fall, 2)) - Math.sin(fall * Math.PI) * H * 0.25;
        var face = fall < 1 ? Math.abs(Math.cos(t * 14)) : 1, r = Math.max(14, H * 0.035);
        var gold = g.createLinearGradient(x - r, y - r, x + r, y + r);
        gold.addColorStop(0, 'rgb(255 230 140)'); gold.addColorStop(0.5, 'rgb(212 160 50)'); gold.addColorStop(1, 'rgb(150 100 20)');
        g.fillStyle = gold; g.beginPath(); g.ellipse(x, y, r * Math.max(0.08, face), r, 0, 0, Math.PI * 2); g.fill();
        if (fall >= 1 && t < 3.0) {
          g.fillStyle = 'rgba(255, 255, 240, ' + Math.max(0, 1 - (t - 2.4) / 0.5) + ')';
          g.beginPath(); g.moveTo(x - r * 1.6, y); g.lineTo(x, y - 3); g.lineTo(x + r * 1.6, y); g.lineTo(x, y + 3); g.closePath(); g.fill();
        }
        g.globalAlpha = 1;
        return t < 4.1;
      });
    },

    // Bad Boys: the title turns a slow full circle against a hot sunset and palm trees.
    spin: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(255 120 60), rgb(240 70 110) 45%, rgb(70 30 90))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var palms = [];
      for (var i = 0; i < 7; i++) { palms.push({ x: Math.random() * W, h: H * (0.35 + Math.random() * 0.25), lean: (Math.random() - 0.5) * 0.4 }); }
      var stage = document.createElement('div');
      stage.className = 'sc-spin-stage';
      var title = text('p', 'sc-spin-title', page.short, stage);
      title.style.color = 'rgb(255 245 230)';
      c.el.appendChild(stage);
      if (title.animate) { title.animate([{ rotate: 'y 0deg' }, { rotate: 'y 360deg' }], { duration: 3200, easing: 'cubic-bezier(.45, .05, .55, .95)', fill: 'both' }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var sun = g.createRadialGradient(W / 2, H * 0.62, 0, W / 2, H * 0.62, H * 0.3);
        sun.addColorStop(0, 'rgba(255, 220, 120, 0.9)'); sun.addColorStop(1, 'rgba(255, 180, 90, 0)');
        g.fillStyle = sun; g.fillRect(0, 0, W, H);
        g.fillStyle = 'rgb(40 16 40)'; g.fillRect(0, H * 0.82, W, H * 0.18);
        palms.forEach(function (p) {
          var x = (p.x - t * 120 + W * 2) % (W + 200) - 100, base = H * 0.84;
          g.strokeStyle = 'rgb(30 12 30)'; g.lineWidth = 8;
          g.beginPath(); g.moveTo(x, base); g.quadraticCurveTo(x + p.lean * p.h, base - p.h * 0.5, x + p.lean * p.h * 1.4, base - p.h); g.stroke();
          g.fillStyle = 'rgb(30 12 30)';
          for (var f = 0; f < 6; f++) {
            var a = -Math.PI / 2 + (f - 2.5) * 0.5, tx = x + p.lean * p.h * 1.4, ty = base - p.h;
            g.beginPath(); g.ellipse(tx + Math.cos(a) * 34, ty + Math.sin(a) * 18 + 10, 40, 8, a, 0, Math.PI * 2); g.fill();
          }
        });
        if (t > 3.4) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.4) / 0.6)); }
        return t < 4.0;
      });
    },

    // Rambo: dense jungle fills the screen, rustling, then is slashed apart.
    jungle: function () {
      var c = curtain({ max: 5000, background: 'rgb(8 26 10)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var leaves = [], greens = ['rgb(30 90 30)', 'rgb(46 120 40)', 'rgb(20 70 26)', 'rgb(70 140 50)'];
      for (var i = 0; i < 260; i++) {
        var x = Math.random() * W, y = Math.random() * H;
        var side = (y - H) * (W * 0.9) - (x - W * 0.1) * (-H) > 0 ? 1 : -1;   // which side of the slash it's on
        leaves.push({ x: x, y: y, a: Math.random() * Math.PI, s: 30 + Math.random() * 60, c: greens[i % 4], side: side, p: Math.random() * 6 });
      }
      var cut = false;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var slash = t > 2.2 ? Math.min(1, (t - 2.2) / 0.15) : 0, part = t > 2.35 ? (t - 2.35) : 0;
        if (part && !cut) { cut = true; c.el.style.background = 'transparent'; }
        leaves.forEach(function (l) {
          var away = part * part * 900 * l.side;
          var x = l.x + away * 0.6, y = l.y - away * 0.4;
          g.save(); g.translate(x, y); g.rotate(l.a + Math.sin(t * 3 + l.p) * 0.08 + part * l.side * 2);
          g.fillStyle = l.c; g.beginPath(); g.ellipse(0, 0, l.s, l.s * 0.32, 0, 0, Math.PI * 2); g.fill();
          g.strokeStyle = 'rgba(0, 0, 0, 0.25)'; g.lineWidth = 1.5; g.beginPath(); g.moveTo(-l.s, 0); g.lineTo(l.s, 0); g.stroke();
          g.restore();
        });
        if (slash && !part) {
          g.strokeStyle = 'rgba(255, 255, 255, 0.95)'; g.lineWidth = 5;
          g.beginPath(); g.moveTo(W * 0.1, H); g.lineTo(W * 0.1 + W * 0.9 * slash, H - H * slash); g.stroke();
        }
        return t < 3.4;
      });
    },

    // Starship Troopers: an old newsreel -- a service bulletin tallying the films enlisted and
    // the ones still out there, and a swarm massing on the horizon.
    newsreel: function () {
      var c = curtain({ max: 6500, background: 'rgb(26 22 16)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var head = text('p', 'sc-intro-caption', 'SERVICE BULLETIN', c.el);
      head.style.color = 'rgb(240 220 170)';
      var n = page.missing.length;
      var body = text('p', 'sc-brief sc-brief--centre', '', c.el);
      body.style.color = 'rgb(240 230 200)';
      typeOut(body, (page.total ? page.have + ' of ' + page.total + ' films of ' + page.short + ' have enlisted in the library. ' : '') +
        (n ? plural(n, 'film') + ' still out on the frontier. Everyone is doing their part.' : 'Every one present and correct.'), 30);
      var bugs = [];
      for (var i = 0; i < 300; i++) { bugs.push({ x: Math.random() * W, y: H * 0.86 + Math.random() * H * 0.04, p: Math.random() * 6 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.fillStyle = 'rgba(60, 50, 34, 0.5)'; g.fillRect(0, H * 0.88, W, H * 0.12);
        var mass = Math.min(1, Math.max(0, (t - 2.2) / 2));
        g.fillStyle = 'rgba(10, 8, 6, 0.9)';
        bugs.forEach(function (b, i) { if (i / bugs.length < mass) { g.fillRect(b.x + Math.sin(t * 4 + b.p) * 3, b.y - Math.abs(Math.sin(t * 6 + b.p)) * 4, 3, 2); } });
        g.fillStyle = 'rgba(255, 240, 200, 0.06)';
        for (var s = 0; s < 500; s++) { g.fillRect(Math.random() * W, Math.random() * H, 1, 1); }
        if (Math.random() > 0.7) { g.fillStyle = 'rgba(255, 240, 200, 0.15)'; g.fillRect(Math.random() * W, 0, 1, H); }
        g.fillStyle = 'rgba(0, 0, 0, ' + (Math.random() * 0.08) + ')'; g.fillRect(0, 0, W, H);
        if (t > 5.0) { c.el.style.opacity = String(Math.max(0, 1 - (t - 5.0) / 0.6)); }
        return t < 5.6;
      });
    },

    // Home Alone: a snowy house at night with its lights on -- and a paint can on a rope swinging
    // down across the screen.
    paintcan: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(14 20 46), rgb(30 40 70))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var flakes = [], hit = false;
      for (var i = 0; i < 160; i++) { flakes.push({ x: Math.random() * W, y: Math.random() * H, v: 0.6 + Math.random() * 1.4, r: 1 + Math.random() * 2 }); }
      var hx = W / 2, hy = H * 0.5, hw = Math.min(W * 0.5, 520), hh = H * 0.34;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var fade = t > 3.4 ? Math.max(0, 1 - (t - 3.4) / 0.7) : 1;
        if (fade < 1) { c.el.style.background = 'rgba(20, 28, 56, ' + fade + ')'; }
        g.globalAlpha = fade;
        g.fillStyle = 'rgb(235 240 250)'; g.fillRect(0, H * 0.84, W, H * 0.16);
        g.fillStyle = 'rgb(60 30 34)'; g.fillRect(hx - hw / 2, hy, hw, hh);
        g.fillStyle = 'rgb(40 26 30)';
        g.beginPath(); g.moveTo(hx - hw * 0.6, hy); g.lineTo(hx, hy - hh * 0.6); g.lineTo(hx + hw * 0.6, hy); g.closePath(); g.fill();
        g.fillStyle = 'rgb(240 244 250)';
        g.beginPath(); g.moveTo(hx - hw * 0.6, hy); g.lineTo(hx, hy - hh * 0.6); g.lineTo(hx + hw * 0.6, hy); g.lineTo(hx + hw * 0.5, hy - 6); g.lineTo(hx, hy - hh * 0.55); g.lineTo(hx - hw * 0.5, hy - 6); g.closePath(); g.fill();
        for (var r = 0; r < 2; r++) {
          for (var k = 0; k < 4; k++) {
            g.fillStyle = 'rgba(255, 210, 120, ' + (0.8 + Math.sin(t * 3 + k + r) * 0.1) + ')';
            g.fillRect(hx - hw / 2 + hw * (0.1 + k * 0.22), hy + hh * (0.15 + r * 0.42), hw * 0.13, hh * 0.25);
          }
        }
        g.fillStyle = 'rgba(255, 255, 255, 0.9)';
        flakes.forEach(function (f) { f.y += f.v; f.x += Math.sin(f.y / 30) * 0.4; if (f.y > H) { f.y = -5; f.x = Math.random() * W; } g.beginPath(); g.arc(f.x, f.y, f.r, 0, Math.PI * 2); g.fill(); });
        if (t > 1.4) {
          var swing = Math.min(1, (t - 1.4) / 1.1), angle = -1.25 + swing * 2.1, px = W * 0.5, py = -H * 0.15, len = H * 0.75;
          var cx = px + Math.sin(angle) * len, cy = py + Math.cos(angle) * len;
          g.strokeStyle = 'rgb(200 180 140)'; g.lineWidth = 3; g.beginPath(); g.moveTo(px, py); g.lineTo(cx, cy); g.stroke();
          g.fillStyle = 'rgb(150 155 165)'; g.fillRect(cx - 34, cy, 68, 80);
          g.fillStyle = 'rgb(200 40 40)'; g.fillRect(cx - 34, cy + 22, 68, 34);
          g.strokeStyle = 'rgb(90 90 100)'; g.beginPath(); g.arc(cx, cy, 30, Math.PI, 0); g.stroke();
          if (swing > 0.55 && !hit) { hit = true; shakePage(9, 320); }
          if (hit && t < 2.4) { g.fillStyle = 'rgba(255, 255, 255, ' + Math.max(0, 0.6 - (t - 2.0)) + ')'; g.fillRect(0, 0, W, H); }
        }
        g.globalAlpha = 1;
        return t < 4.1;
      });
    },

    // Kung Fu Panda: ink brush strokes sweep across rice paper and the title is painted, with
    // peach blossom drifting.
    ink: function () {
      var c = curtain({ max: 5500, background: 'rgb(238 228 204)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H * 0.45, R = Math.min(W, H) * 0.28;
      var blossoms = [];
      for (var i = 0; i < 26; i++) { blossoms.push({ x: Math.random() * W, y: Math.random() * H - H, v: 0.8 + Math.random() * 1.2, a: Math.random() * 6, s: 5 + Math.random() * 5 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var fade = t > 3.7 ? Math.max(0, 1 - (t - 3.7) / 0.7) : 1;
        if (fade < 1) { c.el.style.background = 'rgba(238, 228, 204, ' + fade + ')'; }
        g.globalAlpha = fade;
        var sweep = Math.min(1, t / 1.4), steps = Math.floor(sweep * 120);
        for (var s = 0; s < steps; s++) {
          var a = -Math.PI * 0.6 + s / 120 * Math.PI * 1.85, w = 8 + Math.sin(s / 120 * Math.PI) * 22;
          g.fillStyle = 'rgba(22, 20, 18, 0.9)';
          g.beginPath(); g.arc(cx + Math.cos(a) * R, cy + Math.sin(a) * R, w / 2, 0, Math.PI * 2); g.fill();
        }
        if (t > 1.5) {
          g.globalAlpha = fade * Math.min(1, (t - 1.5) / 0.6);
          g.fillStyle = 'rgb(22 20 18)'; g.textAlign = 'center'; g.textBaseline = 'middle';
          g.font = 'italic 700 ' + Math.round(Math.min(W / Math.max(8, page.short.length * 0.6), R * 0.5)) + 'px Georgia, serif';
          g.fillText(page.short, cx, cy);
          g.fillStyle = 'rgb(190 30 30)'; g.fillRect(cx + R * 0.75, cy + R * 0.55, R * 0.18, R * 0.18);
          g.globalAlpha = fade;
        }
        blossoms.forEach(function (b) {
          b.y += b.v; b.x += 0.6 + Math.sin(b.y / 40); b.a += 0.03;
          g.fillStyle = 'rgba(245, 160, 190, 0.9)';
          for (var p = 0; p < 5; p++) {
            var pa = b.a + p * Math.PI * 0.4;
            g.beginPath(); g.ellipse(b.x + Math.cos(pa) * b.s * 0.6, b.y + Math.sin(pa) * b.s * 0.6, b.s * 0.5, b.s * 0.3, pa, 0, Math.PI * 2); g.fill();
          }
        });
        g.globalAlpha = 1;
        return t < 4.4;
      });
    },

    // Jumanji: two dice roll across a wooden board -- landing on the number still missing -- and
    // jungle vines grow in from the edges to cover the screen.
    dice: function () {
      var c = curtain({ max: 6000, background: 'linear-gradient(135deg, rgb(110 70 36), rgb(70 42 20))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var n = Math.max(2, Math.min(12, page.missing.length || 2)), first = Math.min(6, n - 1), faces = [first, n - first];
      var pips = { 1: [[0, 0]], 2: [[-1, -1], [1, 1]], 3: [[-1, -1], [0, 0], [1, 1]], 4: [[-1, -1], [1, -1], [-1, 1], [1, 1]],
                   5: [[-1, -1], [1, -1], [0, 0], [-1, 1], [1, 1]], 6: [[-1, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [1, 1]] };
      var vines = [];
      for (var v = 0; v < 18; v++) {
        var side = v % 4, f = Math.random();
        vines.push({ x: side === 1 ? W : side === 3 ? 0 : f * W, y: side === 0 ? 0 : side === 2 ? H : f * H, tx: W * (0.2 + Math.random() * 0.6), ty: H * (0.2 + Math.random() * 0.6), bend: (Math.random() - 0.5) * 300 });
      }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgba(40, 24, 10, 0.35)'; g.lineWidth = 2;
        for (var d = -H; d < W; d += 60) { g.beginPath(); g.moveTo(d, 0); g.lineTo(d + H, H); g.stroke(); g.beginPath(); g.moveTo(d + H, 0); g.lineTo(d, H); g.stroke(); }
        var roll = Math.min(1, t / 1.8), e = 1 - Math.pow(1 - roll, 3), s = Math.min(W, H) * 0.12;
        faces.forEach(function (face, i) {
          var x = -s + (W / 2 - s * 0.8 + i * s * 1.6 + s) * e, y = H * 0.48 + (i ? 1 : -1) * s * 0.2;
          var shown = roll < 1 ? 1 + Math.floor(Math.random() * 6) : face;
          g.save(); g.translate(x, y); g.rotate((1 - e) * 14 * (i ? 1 : -1));
          g.fillStyle = 'rgb(246 242 232)'; g.fillRect(-s / 2, -s / 2, s, s);
          g.fillStyle = 'rgb(30 20 14)';
          pips[shown].forEach(function (p) { g.beginPath(); g.arc(p[0] * s * 0.27, p[1] * s * 0.27, s * 0.08, 0, Math.PI * 2); g.fill(); });
          g.restore();
        });
        if (t > 2.2) {
          var grow = Math.min(1, (t - 2.2) / 1.6);
          vines.forEach(function (vine) {
            g.strokeStyle = 'rgb(40 110 30)'; g.lineWidth = 10;
            g.beginPath(); g.moveTo(vine.x, vine.y);
            var steps = 30;
            for (var k = 1; k <= steps * grow; k++) {
              var q = k / steps, mx = (vine.x + vine.tx) / 2 + vine.bend, my = (vine.y + vine.ty) / 2 - vine.bend * 0.5;
              var px = (1 - q) * (1 - q) * vine.x + 2 * (1 - q) * q * mx + q * q * vine.tx, py = (1 - q) * (1 - q) * vine.y + 2 * (1 - q) * q * my + q * q * vine.ty;
              g.lineTo(px, py);
              if (k % 4 === 0) { g.save(); g.fillStyle = 'rgb(60 140 40)'; g.beginPath(); g.ellipse(px + 10, py, 16, 7, k, 0, Math.PI * 2); g.fill(); g.restore(); }
            }
            g.stroke();
          });
        }
        if (t > 4.0) { c.el.style.opacity = String(Math.max(0, 1 - (t - 4.0) / 0.6)); }
        return t < 4.6;
      });
    },

    // Avatar: a dark forest lights up -- plants glowing blue and violet in ripples, step by step,
    // with drifting seeds of light.
    glow: function () {
      var c = curtain({ max: 5500, background: 'rgb(4 10 22)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var plants = [], seeds = [], stepsAt = [[0.5, 0.25], [1.2, 0.45], [1.9, 0.62], [2.6, 0.8]];
      for (var i = 0; i < 70; i++) {
        var x = Math.random() * W, h = H * (0.12 + Math.random() * 0.3);
        plants.push({ x: x, h: h, sway: Math.random() * 6, hue: Math.random() > 0.5 ? [80, 220, 255] : [190, 110, 255], dots: Math.floor(4 + Math.random() * 6) });
      }
      for (var s = 0; s < 28; s++) { seeds.push({ x: Math.random() * W, y: H * (0.4 + Math.random() * 0.6), v: 0.3 + Math.random() * 0.5, p: Math.random() * 6 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var fade = t > 3.6 ? Math.max(0, 1 - (t - 3.6) / 0.8) : 1;
        if (fade < 1) { c.el.style.background = 'rgba(4, 10, 22, ' + fade + ')'; }
        g.globalAlpha = fade;
        plants.forEach(function (p) {
          var lit = 0;
          stepsAt.forEach(function (st) { if (t > st[0]) { var r = (t - st[0]) * W * 0.5; lit = Math.max(lit, Math.max(0, 1 - Math.abs(Math.abs(p.x - W * st[1]) - r) / 160) * 0.6 + (Math.abs(p.x - W * st[1]) < r ? 0.4 : 0)); } });
          var bx = p.x + Math.sin(t + p.sway) * 6, top = H - p.h;
          g.strokeStyle = 'rgba(20, 40, 60, 0.9)'; g.lineWidth = 3;
          g.beginPath(); g.moveTo(p.x, H); g.quadraticCurveTo(p.x, H - p.h * 0.5, bx, top); g.stroke();
          for (var d = 0; d < p.dots; d++) {
            var q = d / p.dots, dx = p.x + (bx - p.x) * q, dy = H - p.h * q;
            g.fillStyle = 'rgba(' + p.hue[0] + ', ' + p.hue[1] + ', ' + p.hue[2] + ', ' + (0.15 + lit * 0.85) + ')';
            g.shadowColor = 'rgb(' + p.hue.join(' ') + ')'; g.shadowBlur = lit * 12;
            g.beginPath(); g.arc(dx + 4, dy, 2.5 + lit * 2, 0, Math.PI * 2); g.fill();
          }
          g.shadowBlur = 0;
        });
        seeds.forEach(function (sd) {
          sd.y -= sd.v; sd.x += Math.sin(t * 1.5 + sd.p) * 0.6;
          g.fillStyle = 'rgba(230, 250, 255, ' + (0.4 + Math.sin(t * 3 + sd.p) * 0.3) + ')';
          g.beginPath(); g.arc(sd.x, sd.y, 2.2, 0, Math.PI * 2); g.fill();
        });
        g.globalAlpha = 1;
        return t < 4.4;
      });
    },

    // The Hunger Games: an arena countdown, a cannon for each missing film, and three lights
    // rising across the sky like a three-note signal.
    arena: function () {
      var c = curtain({ max: 7000, background: 'rgb(8 8 10)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var shots = Math.min(8, page.missing.length), boomed = 0;
      var caption = text('p', 'sc-intro-caption', '', c.el);
      caption.style.color = 'rgb(230 200 120)';
      caption.style.top = '78%';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        if (t < 1.6) {
          var count = Math.max(0, 10 - Math.floor(t / 1.6 * 11));
          g.fillStyle = 'rgb(230 200 120)'; g.textAlign = 'center'; g.textBaseline = 'middle';
          g.font = '700 ' + Math.round(H * 0.3) + 'px ui-monospace, monospace';
          g.fillText(String(count), W / 2, H * 0.45);
        }
        var shotAt = function (i) { return 1.8 + i * 0.42; };
        for (var i = 0; i < shots; i++) {
          var since = t - shotAt(i);
          if (since > 0 && i >= boomed) { boomed = i + 1; shakePage(6, 260); caption.textContent = plural(boomed, 'film') + ' still in the arena'; }
          if (since > 0 && since < 0.7) {
            g.strokeStyle = 'rgba(255, 220, 160, ' + (1 - since / 0.7) + ')'; g.lineWidth = 4;
            g.beginPath(); g.arc(W / 2, H * 0.45, since * W * 0.6, 0, Math.PI * 2); g.stroke();
          }
        }
        if (!shots && t > 1.8) { caption.textContent = 'No one left in the arena'; }
        var signal = shotAt(shots) + 0.3;
        [0, 1, 2].forEach(function (k) {
          var on = t - signal - k * 0.35;
          if (on > 0) {
            var a = Math.min(1, on / 0.3) * (t > signal + 2.2 ? Math.max(0, 1 - (t - signal - 2.2) / 0.6) : 1);
            var x = W * (0.3 + k * 0.2), top = H * (0.32 - k * 0.07);
            var beam = g.createLinearGradient(x, H, x, top);
            beam.addColorStop(0, 'rgba(255, 230, 170, 0)'); beam.addColorStop(1, 'rgba(255, 230, 170, ' + 0.7 * a + ')');
            g.fillStyle = beam; g.fillRect(x - 6, top, 12, H - top);
          }
        });
        return t < signal + 2.9;
      });
    },

    // The Mummy: sand blows across a wall of carved symbols, gathers into a great face, and
    // crumbles away.
    sand: function () {
      var c = curtain({ max: 6500, background: 'linear-gradient(to bottom, rgb(150 110 60), rgb(90 62 30))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var glyphs = [], grains = [], cx = W / 2, cy = H * 0.48, R = Math.min(W, H) * 0.3;
      for (var gx = 40; gx < W; gx += 70) { for (var gy = 40; gy < H; gy += 80) { glyphs.push({ x: gx, y: gy, k: Math.floor(Math.random() * 5) }); } }
      var targets = [];
      for (var a = 0; a < Math.PI * 2; a += 0.025) { targets.push([cx + Math.cos(a) * R * 0.7, cy + Math.sin(a) * R]); }
      [-1, 1].forEach(function (side) { for (var e = 0; e < Math.PI * 2; e += 0.2) { targets.push([cx + side * R * 0.3 + Math.cos(e) * R * 0.12, cy - R * 0.2 + Math.sin(e) * R * 0.07]); } });
      for (var m = -1; m <= 1; m += 0.04) { targets.push([cx + m * R * 0.3, cy + R * 0.45 + Math.abs(m) * -R * 0.05]); }
      for (var nz = 0; nz < 1; nz += 0.06) { targets.push([cx, cy - R * 0.1 + nz * R * 0.35]); }
      var edge = targets.length;
      for (var fill = 0; fill < 900; fill++) {   // the body of the face: fainter sand inside the outline
        var fa = Math.random() * Math.PI * 2, fr = Math.sqrt(Math.random()) * 0.95;
        targets.push([cx + Math.cos(fa) * R * 0.7 * fr, cy + Math.sin(fa) * R * fr]);
      }
      targets.forEach(function (tg, i) { grains.push({ x: W + Math.random() * W * 0.5, y: Math.random() * H, tx: tg[0], ty: tg[1], vy: 0, d: Math.random() * 0.4, soft: i >= edge }); });
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgba(50, 32, 12, 0.45)'; g.lineWidth = 2;
        glyphs.forEach(function (gl) {
          g.beginPath();
          if (gl.k === 0) { g.arc(gl.x, gl.y, 10, 0, Math.PI * 2); }
          else if (gl.k === 1) { g.moveTo(gl.x - 10, gl.y + 10); g.lineTo(gl.x, gl.y - 12); g.lineTo(gl.x + 10, gl.y + 10); }
          else if (gl.k === 2) { g.ellipse(gl.x, gl.y - 9, 5, 6, 0, 0, Math.PI * 2); g.moveTo(gl.x, gl.y - 3); g.lineTo(gl.x, gl.y + 14); g.moveTo(gl.x - 8, gl.y + 1); g.lineTo(gl.x + 8, gl.y + 1); }
          else if (gl.k === 3) { g.ellipse(gl.x, gl.y, 12, 6, 0, 0, Math.PI * 2); g.moveTo(gl.x + 4, gl.y); g.arc(gl.x, gl.y, 3, 0, Math.PI * 2); }
          else { g.moveTo(gl.x - 10, gl.y); g.quadraticCurveTo(gl.x, gl.y - 16, gl.x + 10, gl.y); g.lineTo(gl.x + 10, gl.y + 10); }
          g.stroke();
        });
        var gather = Math.min(1, Math.max(0, (t - 0.6) / 1.6)), crumble = t > 3.1;
        grains.forEach(function (p) {
          g.fillStyle = p.soft ? 'rgba(225, 185, 120, 0.4)' : 'rgba(245, 215, 155, 0.95)';
          var k = Math.min(1, Math.max(0, gather - p.d) / (1 - p.d));
          var x, y;
          if (!crumble) { x = p.x + (p.tx - p.x) * k; y = p.y + (p.ty - p.y) * k + (k < 1 ? Math.sin(t * 5 + p.d * 20) * 6 : 0); p.cx = x; p.cy = y; }
          else { p.vy += 0.35; p.cy += p.vy; p.cx -= 0.6; x = p.cx; y = p.cy; }
          g.fillRect(x, y, 3, 3);
        });
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.8)); }
        return t < 4.4;
      });
    },

    // Superman: clouds rush past as if climbing; a red-and-blue streak shoots up through them,
    // and a flash as it breaks away.
    flight: function () {
      var c = curtain({ max: 5000, background: 'linear-gradient(to bottom, rgb(40 110 210), rgb(140 200 250))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var puffs = [];
      for (var i = 0; i < 26; i++) { puffs.push({ x: Math.random() * W, y: Math.random() * H, s: 40 + Math.random() * 80, v: 8 + Math.random() * 10 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        puffs.forEach(function (p) {
          p.y += p.v * (1 + Math.min(1, t / 1.5)); if (p.y - p.s > H) { p.y = -p.s; p.x = Math.random() * W; }
          g.fillStyle = 'rgba(255, 255, 255, 0.85)';
          for (var b = 0; b < 4; b++) { g.beginPath(); g.arc(p.x + (b - 1.5) * p.s * 0.45, p.y + (b % 2) * p.s * 0.15, p.s * 0.45, 0, Math.PI * 2); g.fill(); }
        });
        if (t > 1.5) {
          var rise = Math.min(1, (t - 1.5) / 0.7), head = H - rise * H * 1.2;
          g.lineCap = 'round';
          g.strokeStyle = 'rgba(220, 30, 40, 0.85)'; g.lineWidth = 22;
          g.beginPath(); g.moveTo(W / 2, H + 40); g.lineTo(W / 2, head); g.stroke();
          g.strokeStyle = 'rgba(30, 80, 220, 0.95)'; g.lineWidth = 10;
          g.beginPath(); g.moveTo(W / 2, H + 40); g.lineTo(W / 2, head); g.stroke();
        }
        if (t > 2.2) {
          var boom = (t - 2.2) / 0.8;
          g.strokeStyle = 'rgba(255, 255, 255, ' + Math.max(0, 1 - boom) + ')'; g.lineWidth = 8;
          g.beginPath(); g.arc(W / 2, 0, boom * Math.max(W, H), 0, Math.PI * 2); g.stroke();
          if (boom < 0.3) { g.fillStyle = 'rgba(255, 255, 255, ' + (0.6 - boom * 2) + ')'; g.fillRect(0, 0, W, H); }
          c.el.style.opacity = String(Math.max(0, 1 - Math.max(0, t - 2.6) / 0.7));
        }
        return t < 3.4;
      });
    },

    // ---------------------------------------------------------------- 0.65.0

    // Sharknado: a tornado spins up, sharks whirling round in it, then tears off sideways.
    twister: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(60 70 72), rgb(110 120 110))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var bits = [], sharks = [];
      for (var i = 0; i < 520; i++) { bits.push({ a: Math.random() * Math.PI * 2, h: Math.random(), s: 1 + Math.random() * 2.5 }); }
      for (var k = 0; k < 9; k++) { sharks.push({ a: Math.random() * Math.PI * 2, h: 0.15 + Math.random() * 0.7, size: 38 + Math.random() * 30 }); }
      var shark = function (x, y, size, facing, depth) {
        g.save(); g.translate(x, y); g.scale(facing * (0.6 + depth * 0.5), 0.6 + depth * 0.5);
        g.fillStyle = 'rgba(34, 44, 56, ' + (0.7 + depth * 0.3) + ')';
        g.beginPath(); g.moveTo(size, 0); g.quadraticCurveTo(size * 0.2, -size * 0.32, -size * 0.7, -size * 0.05);
        g.lineTo(-size, -size * 0.35); g.lineTo(-size * 0.9, 0); g.lineTo(-size, size * 0.3); g.lineTo(-size * 0.7, size * 0.05);
        g.quadraticCurveTo(size * 0.2, size * 0.28, size, 0); g.closePath(); g.fill();
        g.beginPath(); g.moveTo(-size * 0.05, -size * 0.2); g.lineTo(size * 0.12, -size * 0.55); g.lineTo(size * 0.3, -size * 0.18); g.closePath(); g.fill();
        g.restore();
      };
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var grow = Math.min(1, t / 1.2), leave = t > 3.0 ? Math.pow(t - 3.0, 2) * W * 1.4 : 0;
        var cx = W / 2 + Math.sin(t * 1.3) * W * 0.05 + leave, top = H * 0.02, height = H * 0.95;
        var radius = function (h) { return (W * 0.32 * (1 - h) + 24 * h) * grow; };
        // the funnel's body: a dark cone, with bands of wind wrapping round it
        var body = g.createLinearGradient(cx - radius(0), 0, cx + radius(0), 0);
        body.addColorStop(0, 'rgba(40, 46, 48, 0.15)'); body.addColorStop(0.5, 'rgba(40, 46, 48, 0.7)'); body.addColorStop(1, 'rgba(40, 46, 48, 0.15)');
        g.fillStyle = body;
        g.beginPath(); g.moveTo(cx - radius(0), top); g.lineTo(cx + radius(0), top); g.lineTo(cx + radius(1), top + height); g.lineTo(cx - radius(1), top + height); g.closePath(); g.fill();
        g.strokeStyle = 'rgba(200, 210, 210, 0.35)'; g.lineWidth = 2;
        for (var band = 0; band < 14; band++) {
          var bh = ((band / 14) + t * 0.15) % 1, br = radius(bh), off = Math.sin(t * 4 + band) * br * 0.3;
          g.beginPath(); g.ellipse(cx + off, top + bh * height, br, br * 0.12, 0, 0.2, Math.PI - 0.2); g.stroke();
        }
        g.fillStyle = 'rgba(40, 46, 46, 0.65)';
        bits.forEach(function (b) {
          var r = radius(b.h), a = b.a + t * (3 + (1 - b.h) * 2);
          g.fillRect(cx + Math.cos(a) * r, top + b.h * height + Math.sin(a) * r * 0.12, b.s * 2, b.s);
        });
        var sorted = sharks.map(function (s) { var a = s.a + t * 2.6; return { s: s, a: a, depth: (Math.sin(a) + 1) / 2 }; }).sort(function (p, q) { return p.depth - q.depth; });
        sorted.forEach(function (p) {
          var r = radius(p.s.h);
          shark(cx + Math.cos(p.a) * r, top + p.s.h * height + Math.sin(p.a) * r * 0.12, p.s.size, Math.sin(p.a) > 0 ? -1 : 1, p.depth);
        });
        if (t > 3.2) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.2) / 0.7)); }
        return t < 3.9;
      });
    },

    // The Ring: static, then a stone well in a dark clearing, static again, and the set switches
    // off to a line.
    well: function () {
      var c = curtain({ max: 5500, background: 'black' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var noise = document.createElement('canvas'); noise.width = 160; noise.height = 120;
      var n = noise.getContext('2d'), img = n.createImageData(160, 120);
      var staticFrame = function (alpha) {
        for (var i = 0; i < img.data.length; i += 4) { var v = Math.random() * 255; img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 255; }
        n.putImageData(img, 0, 0);
        g.globalAlpha = alpha; g.imageSmoothingEnabled = false; g.drawImage(noise, 0, 0, W, H); g.globalAlpha = 1;
      };
      var trees = [];
      for (var k = 0; k < 30; k++) { trees.push({ x: Math.random() * W, w: 20 + Math.random() * 40, h: H * (0.35 + Math.random() * 0.3) }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        if (t < 1.3 || (t > 3.3 && t < 3.8)) { staticFrame(1); return true; }
        if (t >= 3.8) {
          var off = Math.min(1, (t - 3.8) / 0.35);
          g.fillStyle = 'rgb(240 240 240)'; g.fillRect(W / 2 - W * (1 - off) / 2, H / 2 - 2 * (1 - off) - 1, Math.max(4, W * (1 - off)), 4 * (1 - off) + 2);
          return t < 4.4;
        }
        var sky = g.createLinearGradient(0, 0, 0, H);
        sky.addColorStop(0, 'rgb(40 48 56)'); sky.addColorStop(1, 'rgb(12 16 18)');
        g.fillStyle = sky; g.fillRect(0, 0, W, H);
        g.fillStyle = 'rgb(10 12 12)';
        trees.forEach(function (tr) { g.beginPath(); g.moveTo(tr.x, H * 0.72 - tr.h); g.lineTo(tr.x + tr.w / 2, H * 0.72); g.lineTo(tr.x - tr.w / 2, H * 0.72); g.closePath(); g.fill(); });
        g.fillStyle = 'rgb(28 32 30)'; g.fillRect(0, H * 0.72, W, H * 0.28);
        var wx = W / 2, wy = H * 0.66, wr = Math.min(W, H) * 0.14;
        g.fillStyle = 'rgb(70 72 70)'; g.fillRect(wx - wr, wy, wr * 2, wr * 0.7);
        g.strokeStyle = 'rgba(30, 30, 30, 0.8)'; g.lineWidth = 2;
        for (var row = 0; row < 3; row++) { for (var col = 0; col < 6; col++) { g.strokeRect(wx - wr + col * wr / 3 + (row % 2) * wr / 6, wy + row * wr * 0.23, wr / 3, wr * 0.23); } }
        g.fillStyle = 'rgb(84 86 84)'; g.beginPath(); g.ellipse(wx, wy, wr, wr * 0.28, 0, 0, Math.PI * 2); g.fill();
        g.fillStyle = 'rgb(4 4 4)'; g.beginPath(); g.ellipse(wx, wy, wr * 0.82, wr * 0.2, 0, 0, Math.PI * 2); g.fill();
        staticFrame(0.12);
        return true;
      });
    },

    // 28 Days Later: an empty city map at dawn, a red spread from one point, a stage per film,
    // until it covers everything.
    outbreak: function () {
      var c = curtain({ max: 5500, background: 'rgb(14 16 18)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var roads = [], blocks = [];
      for (var x = 0; x < W; x += 60 + Math.random() * 60) { roads.push([x, 0, x + (Math.random() - 0.5) * 80, H]); }
      for (var y = 0; y < H; y += 50 + Math.random() * 50) { roads.push([0, y, W, y + (Math.random() - 0.5) * 60]); }
      for (var b = 0; b < 260; b++) { blocks.push([Math.random() * W, Math.random() * H, 8 + Math.random() * 22]); }
      var ox = W * (0.3 + Math.random() * 0.4), oy = H * (0.3 + Math.random() * 0.4);
      var stages = Math.max(4, Math.min(10, (page.steps.length || 4) + page.missing.length));
      var caption = text('p', 'sc-intro-caption', 'Day 1', c.el);
      caption.style.color = 'rgb(230 70 60)';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgba(150, 160, 170, 0.18)'; g.lineWidth = 2;
        roads.forEach(function (r) { g.beginPath(); g.moveTo(r[0], r[1]); g.lineTo(r[2], r[3]); g.stroke(); });
        g.fillStyle = 'rgba(150, 160, 170, 0.12)';
        blocks.forEach(function (bk) { g.fillRect(bk[0], bk[1], bk[2], bk[2] * 0.7); });
        var spread = Math.min(1, t / 3.4), stage = Math.ceil(spread * stages);
        var reach = (stage / stages) * Math.hypot(W, H);
        for (var s = 0; s < 3; s++) {
          var red = g.createRadialGradient(ox, oy, 0, ox, oy, reach * (1 - s * 0.12));
          red.addColorStop(0, 'rgba(200, 20, 20, 0.35)'); red.addColorStop(0.85, 'rgba(200, 20, 20, 0.25)'); red.addColorStop(1, 'rgba(200, 20, 20, 0)');
          g.fillStyle = red; g.fillRect(0, 0, W, H);
        }
        caption.textContent = 'Day ' + Math.max(1, Math.round(spread * 28));
        if (t > 3.7) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.7) / 0.7)); }
        return t < 4.4;
      });
    },

    // Blair Witch: shaky torchlight in dark woods, twig figures hanging from the branches, and the
    // camera drops.
    torch: function () {
      var c = curtain({ max: 5500, background: 'black' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var trunks = [], figures = [];
      for (var i = 0; i < 26; i++) { trunks.push({ x: Math.random() * W, w: 10 + Math.random() * 30 }); }
      for (var f = 0; f < 7; f++) { figures.push({ x: W * (0.1 + Math.random() * 0.8), y: H * (0.2 + Math.random() * 0.35), s: 30 + Math.random() * 30 }); }
      var rec = text('p', 'sc-hud', '● REC', c.el);
      rec.style.color = 'rgb(255 60 60)'; rec.style.top = '6%';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var drop = t > 3.1 ? Math.min(1, (t - 3.1) / 0.5) : 0;
        g.save();
        if (drop) { g.translate(W / 2, H / 2); g.rotate(drop * 1.2); g.translate(-W / 2, -H / 2 + drop * H * 0.4); }
        var bx = W / 2 + Math.sin(t * 2.1) * W * 0.25 + Math.sin(t * 7.3) * 18, by = H * 0.45 + Math.sin(t * 1.7) * H * 0.15 + Math.cos(t * 9.1) * 14;
        var R = Math.min(W, H) * 0.38;
        var lit = function (x, y) { return Math.max(0, 1 - Math.hypot(x - bx, y - by) / R); };
        trunks.forEach(function (tr) {
          var l = lit(tr.x, by);
          g.fillStyle = 'rgba(150, 140, 120, ' + l * 0.9 + ')'; g.fillRect(tr.x - tr.w / 2, 0, tr.w, H);
        });
        figures.forEach(function (fg) {
          var l = lit(fg.x, fg.y);
          if (l <= 0) { return; }
          g.strokeStyle = 'rgba(200, 180, 150, ' + l + ')'; g.lineWidth = 3;
          g.beginPath();
          g.moveTo(fg.x, fg.y - fg.s * 0.8); g.lineTo(fg.x, fg.y + fg.s);
          g.moveTo(fg.x - fg.s * 0.6, fg.y - fg.s * 0.2); g.lineTo(fg.x + fg.s * 0.6, fg.y - fg.s * 0.2);
          g.moveTo(fg.x, fg.y + fg.s * 0.4); g.lineTo(fg.x - fg.s * 0.5, fg.y + fg.s * 1.1);
          g.moveTo(fg.x, fg.y + fg.s * 0.4); g.lineTo(fg.x + fg.s * 0.5, fg.y + fg.s * 1.1);
          g.moveTo(fg.x, fg.y - fg.s * 0.8); g.lineTo(fg.x, fg.y - fg.s * 1.6);
          g.stroke();
        });
        var beam = g.createRadialGradient(bx, by, 0, bx, by, R);
        beam.addColorStop(0, 'rgba(255, 240, 200, 0.18)'); beam.addColorStop(1, 'rgba(255, 240, 200, 0)');
        g.fillStyle = beam; g.fillRect(0, 0, W, H);
        g.restore();
        g.fillStyle = 'rgba(255, 255, 255, 0.05)';
        for (var s = 0; s < 400; s++) { g.fillRect(Math.random() * W, Math.random() * H, 1.5, 1.5); }
        if (drop >= 1) { g.fillStyle = 'black'; g.fillRect(0, 0, W, H); rec.style.opacity = '0'; }
        return t < 4.1;
      });
    },

    // Deadpool: comic captions that know they're in an intro, then two slashes cut it in pieces.
    captions: function () {
      var c = curtain({ max: 8000, background: 'rgb(26 10 12)' });
      var n = page.missing.length;
      var lines = [
        'Oh good, an intro. Everyone loves an intro.',
        page.total ? 'You have ' + page.have + ' of ' + page.total + '. ' + (n ? n + ' missing. Not judging. Okay, judging a little.' : 'All of them. Show-off.') : 'Big fan of the collection. Huge.',
        'You could have clicked to skip, you know. Any time. Still here? Fine.',
      ];
      var stack = document.createElement('div');
      stack.className = 'sc-captions';
      c.el.appendChild(stack);
      lines.forEach(function (words, i) {
        window.setTimeout(function () {
          var box = text('p', 'sc-caption-box', words, stack);
          box.style.background = i % 2 ? 'rgb(255 236 120)' : 'rgb(255 255 255)';
          box.style.color = 'rgb(20 10 10)';
          box.style.borderColor = 'rgb(20 10 10)';
          box.style.rotate = (i % 2 ? 2 : -2) + 'deg';
          if (box.animate) { box.animate([{ scale: 0.4, opacity: 0 }, { scale: 1.08, opacity: 1 }, { scale: 1, opacity: 1 }], { duration: 300, easing: 'ease-out', fill: 'both' }); }
        }, 300 + i * 1500);
      });
      window.setTimeout(function () {
        stack.remove();
        c.el.style.background = 'transparent';
        [['polygon(0 0, 100% 0, 100% 100%)', '50vw -50vh'], ['polygon(0 0, 100% 100%, 0 100%)', '-50vw 50vh']].forEach(function (half) {
          var part = document.createElement('span');
          part.className = 'sc-half';
          part.style.background = 'rgb(26 10 12)';
          part.style.clipPath = half[0];
          c.el.appendChild(part);
          if (part.animate) { part.animate([{ translate: '0 0' }, { translate: half[1] }], { duration: 700, easing: 'cubic-bezier(.6, 0, .8, .4)', fill: 'forwards' }); }
        });
        var cut = document.createElement('span');
        cut.className = 'sc-slash sc-slash--down';
        cut.style.background = 'rgb(255 255 255)';
        c.el.appendChild(cut);
        window.setTimeout(c.finish, 650);
      }, 300 + lines.length * 1500 + 600);
    },

    // Blade: a red strobe in the dark, then a silver blade arcs across and the page appears in
    // its wake.
    blade: function () {
      var c = curtain({ max: 5000, background: 'black' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        if (t < 1.6 && Math.floor(t * 9) % 2 === 0) { g.fillStyle = 'rgba(190, 0, 0, ' + (0.35 + Math.random() * 0.3) + ')'; g.fillRect(0, 0, W, H); }
        if (t > 1.6) {
          var sweep = Math.min(1, (t - 1.6) / 0.45), a = -Math.PI * 0.85 + sweep * Math.PI * 0.75, R = Math.max(W, H) * 0.8, cx = W * 0.15, cy = H * 1.1;
          if (sweep >= 1) { c.el.style.background = 'rgba(0, 0, 0, ' + Math.max(0, 1 - (t - 2.05) / 0.6) + ')'; }
          for (var k = 0; k < 10; k++) {
            var ak = a - k * 0.03;
            g.strokeStyle = 'rgba(230, 235, 245, ' + (sweep < 1 ? (1 - k / 10) * 0.9 : Math.max(0, 0.6 - (t - 2.05))) + ')';
            g.lineWidth = 6 - k * 0.4;
            g.beginPath(); g.arc(cx, cy, R, ak - 0.12, ak); g.stroke();
          }
        }
        return t < 3.0;
      });
    },

    // RoboCop: a robotic display boots, states three directives about the library, and scans
    // the title.
    directive: function () {
      var c = curtain({ max: 7000, background: 'rgb(8 16 28)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var n = page.missing.length;
      var hud = text('p', 'sc-hud sc-hud--left', '', c.el);
      hud.style.color = 'rgb(190 225 255)'; hud.style.whiteSpace = 'pre-line'; hud.style.top = '14%';
      typeOut(hud, 'UNIT 01 — SYSTEMS ONLINE\n\nPRIME DIRECTIVES\n1. Serve the library\n2. Protect the collection\n3. Recover the missing' +
        (n ? ' (' + n + ')' : '') + '\n\nTARGET: ' + page.short.toUpperCase(), 26);
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.fillStyle = 'rgba(190, 225, 255, 0.05)';
        for (var y = 0; y < H; y += 3) { g.fillRect(0, y, W, 1); }
        var bx = W * 0.62, by = H * 0.5, s = Math.min(W, H) * 0.22 * (1 + Math.max(0, 1 - t / 1.5) * 0.6);
        g.strokeStyle = 'rgba(190, 225, 255, 0.85)'; g.lineWidth = 2;
        [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(function (k) {
          g.beginPath(); g.moveTo(bx + k[0] * s, by + k[1] * s * 0.6); g.lineTo(bx + k[0] * s * 0.7, by + k[1] * s * 0.6);
          g.moveTo(bx + k[0] * s, by + k[1] * s * 0.6); g.lineTo(bx + k[0] * s, by + k[1] * s * 0.35); g.stroke();
        });
        var scan = by - s * 0.6 + ((t * 0.9) % 1) * s * 1.2;
        g.strokeStyle = 'rgba(120, 200, 255, 0.6)'; g.beginPath(); g.moveTo(bx - s, scan); g.lineTo(bx + s, scan); g.stroke();
        g.beginPath(); g.arc(bx, by, 6, 0, Math.PI * 2); g.stroke();
        if (t > 4.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 4.6) / 0.6)); }
        return t < 5.3;
      });
    },

    // Kingsman: a black umbrella spins open to fill the screen, then snaps shut on the page. The
    // page stays usable.
    umbrella: function () {
      var c = curtain({ max: 5000, through: true });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H / 2, full = Math.hypot(W, H) * 0.6, ribs = 8;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var open = t < 1.2 ? 1 - Math.pow(1 - t / 1.2, 3) : t < 2.2 ? 1 : Math.max(0, 1 - (t - 2.2) / 0.25);
        var r = full * open, spin = t * 1.6;
        if (r < 2) { return t < 2.6; }
        for (var i = 0; i < ribs; i++) {
          var a1 = spin + i / ribs * Math.PI * 2, a2 = spin + (i + 1) / ribs * Math.PI * 2, mid = (a1 + a2) / 2;
          g.fillStyle = i % 2 ? 'rgb(18 18 20)' : 'rgb(28 28 32)';
          g.beginPath(); g.moveTo(cx, cy);
          g.lineTo(cx + Math.cos(a1) * r, cy + Math.sin(a1) * r);
          g.quadraticCurveTo(cx + Math.cos(mid) * r * 0.9, cy + Math.sin(mid) * r * 0.9, cx + Math.cos(a2) * r, cy + Math.sin(a2) * r);
          g.closePath(); g.fill();
          g.strokeStyle = 'rgba(200, 200, 210, 0.35)'; g.lineWidth = 2;
          g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(a1) * r, cy + Math.sin(a1) * r); g.stroke();
        }
        g.fillStyle = 'rgb(160 130 70)'; g.beginPath(); g.arc(cx, cy, 6 + 8 * open, 0, Math.PI * 2); g.fill();
        return t < 2.6;
      });
    },

    // Men in Black: dark glasses slide down, then a flash wipes the screen -- and what you saw.
    flash: function () {
      var c = curtain({ max: 6500, background: 'black' });
      var glasses = document.createElement('div');
      glasses.className = 'sc-glasses';
      glasses.innerHTML = '<svg viewBox="0 0 200 60" aria-hidden="true"><path d="M8 10h76l-6 34a14 14 0 0 1-14 12H30a14 14 0 0 1-14-12z M116 10h76l-8 34a14 14 0 0 1-14 12h-34a14 14 0 0 1-14-12z" fill="rgb(16 16 18)" stroke="rgb(90 90 96)" stroke-width="2"/><path d="M84 18q16-8 32 0" fill="none" stroke="rgb(90 90 96)" stroke-width="4"/></svg>';
      c.el.appendChild(glasses);
      if (glasses.animate) { glasses.animate([{ translate: '-50% -120vh' }, { translate: '-50% -50%' }], { duration: 900, easing: 'cubic-bezier(.2, .9, .3, 1)', fill: 'both' }); }
      var line = text('p', 'sc-brief sc-brief--centre', 'Look here, please.', c.el);
      line.style.color = 'rgb(230 230 235)'; line.style.top = '72%';
      var n = page.missing.length;
      window.setTimeout(function () {
        glasses.remove();
        c.el.style.transition = 'background 0.15s';
        c.el.style.background = 'rgb(255 255 255)';
        line.style.color = 'rgb(20 20 24)';
        line.style.top = '50%';
        line.textContent = n ? 'You never saw that ' + n + (n === 1 ? ' film is' : ' films are') + ' missing. Carry on.' : 'You never saw this intro. Carry on.';
      }, 1900);
      window.setTimeout(c.finish, 4800);
    },

    // TRON: light trails race across a neon grid, turning square corners, then the grid flies off.
    grid: function () {
      var c = curtain({ max: 5500, background: 'rgb(2 6 12)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cell = 40, riders = [['rgb(80 230 255)', 0], ['rgb(255 150 40)', 1], ['rgb(240 250 255)', 2]].map(function (r) {
        var x = Math.round(Math.random() * W / cell) * cell, y = Math.round(Math.random() * H / cell) * cell, d = Math.floor(Math.random() * 4);
        return { colour: r[0], path: [[x, y]], x: x, y: y, d: d };
      });
      var flown = false;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgba(60, 200, 255, 0.16)'; g.lineWidth = 1;
        for (var x = 0; x < W; x += cell) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); }
        for (var y = 0; y < H; y += cell) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
        riders.forEach(function (r) {
          var step = 9, dirs = [[1, 0], [0, 1], [-1, 0], [0, -1]];
          r.x += dirs[r.d][0] * step; r.y += dirs[r.d][1] * step;
          if (r.x % cell === 0 && r.y % cell === 0 && Math.random() < 0.3) { r.d = (r.d + (Math.random() < 0.5 ? 1 : 3)) % 4; r.path.push([r.x, r.y]); }
          if (r.x < 0 || r.x > W || r.y < 0 || r.y > H) { r.d = (r.d + 2) % 4; r.path.push([r.x, r.y]); }
          g.strokeStyle = r.colour; g.lineWidth = 3; g.shadowColor = r.colour; g.shadowBlur = 12;
          g.beginPath(); g.moveTo(r.path[0][0], r.path[0][1]);
          r.path.forEach(function (p) { g.lineTo(p[0], p[1]); });
          g.lineTo(r.x, r.y); g.stroke(); g.shadowBlur = 0;
        });
        if (t > 3.0 && !flown) {
          flown = true;
          if (canvas.animate) { canvas.animate([{ scale: 1, opacity: 1 }, { scale: 3, opacity: 0 }], { duration: 800, easing: 'ease-in', fill: 'forwards' }); }
          c.el.style.transition = 'background 0.8s'; c.el.style.background = 'transparent';
        }
        return t < 3.9;
      });
    },

    // The Godfather: a dim, sepia room with smoke drifting under one lamp; the title fades up in
    // an elegant hand, then dissolves.
    sepia: function () {
      var c = curtain({ max: 6500, background: 'rgb(20 14 8)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var wisps = [];
      for (var i = 0; i < 14; i++) { wisps.push({ x: W * (0.3 + Math.random() * 0.4), y: H * (0.5 + Math.random() * 0.5), r: 60 + Math.random() * 100, v: 0.3 + Math.random() * 0.5 }); }
      var title = text('p', 'sc-sepia-title', page.short, c.el);
      title.style.color = 'rgb(232 210 170)';
      if (title.animate) { title.animate([{ opacity: 0, letterSpacing: '0.5em', filter: 'blur(6px)' }, { opacity: 1, letterSpacing: '0.12em', filter: 'blur(0)', offset: 0.45 }, { opacity: 1, offset: 0.75 }, { opacity: 0, filter: 'blur(8px)' }], { duration: 5000, delay: 300, easing: 'ease-in-out', fill: 'both' }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var lamp = g.createRadialGradient(W / 2, H * 0.1, 0, W / 2, H * 0.3, H * 0.8);
        lamp.addColorStop(0, 'rgba(200, 150, 80, 0.45)'); lamp.addColorStop(1, 'rgba(0, 0, 0, 0)');
        g.fillStyle = lamp; g.fillRect(0, 0, W, H);
        wisps.forEach(function (w) {
          w.y -= w.v; w.x += Math.sin(w.y / 60) * 0.5;
          var puff = g.createRadialGradient(w.x, w.y, 0, w.x, w.y, w.r);
          puff.addColorStop(0, 'rgba(200, 180, 150, 0.06)'); puff.addColorStop(1, 'rgba(200, 180, 150, 0)');
          g.fillStyle = puff; g.fillRect(w.x - w.r, w.y - w.r, w.r * 2, w.r * 2);
        });
        if (t > 4.8) { c.el.style.opacity = String(Math.max(0, 1 - (t - 4.8) / 0.6)); }
        return t < 5.5;
      });
    },

    // Planet of the Apes: a red sunset over overgrown ruins, and an ape's silhouette with a spear
    // rising on the skyline.
    ruins: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(120 30 30), rgb(230 110 50) 60%, rgb(250 170 80))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var towers = [];
      for (var i = 0; i < 9; i++) { towers.push({ x: i / 9 * W + Math.random() * 40, w: 50 + Math.random() * 70, h: H * (0.2 + Math.random() * 0.35), bite: Math.random() }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var fade = t > 3.7 ? Math.max(0, 1 - (t - 3.7) / 0.6) : 1;
        if (fade < 1) { c.el.style.opacity = String(fade); }
        g.fillStyle = 'rgba(255, 220, 140, 0.9)'; g.beginPath(); g.arc(W * 0.5, H * 0.66, H * 0.16, 0, Math.PI * 2); g.fill();
        var sky = H * 0.78;
        g.fillStyle = 'rgb(40 14 12)';
        towers.forEach(function (tw) {
          g.beginPath(); g.moveTo(tw.x, sky); g.lineTo(tw.x, sky - tw.h); g.lineTo(tw.x + tw.w * tw.bite, sky - tw.h * 0.85); g.lineTo(tw.x + tw.w, sky - tw.h * 0.95); g.lineTo(tw.x + tw.w, sky); g.closePath(); g.fill();
        });
        g.fillRect(0, sky, W, H - sky);
        var rise = Math.min(1, Math.max(0, (t - 0.8) / 1.4)), ax = W * 0.5, ay = sky - rise * H * 0.22, s = H * 0.11;
        g.save(); g.beginPath(); g.rect(0, 0, W, sky + 1); g.clip();
        g.fillStyle = 'rgb(20 8 8)';
        g.beginPath(); g.ellipse(ax, ay + s * 0.6, s * 0.55, s * 0.75, -0.2, 0, Math.PI * 2); g.fill();
        g.beginPath(); g.arc(ax + s * 0.25, ay - s * 0.15, s * 0.28, 0, Math.PI * 2); g.fill();
        g.beginPath(); g.ellipse(ax - s * 0.1, ay + s * 0.05, s * 0.6, s * 0.3, -0.3, 0, Math.PI * 2); g.fill();
        g.strokeStyle = 'rgb(20 8 8)'; g.lineWidth = s * 0.16; g.lineCap = 'round';
        g.beginPath(); g.moveTo(ax + s * 0.4, ay + s * 0.3); g.lineTo(ax + s * 0.75, ay - s * 0.3); g.stroke();
        g.lineWidth = s * 0.06; g.beginPath(); g.moveTo(ax + s * 0.8, ay - s * 1.6); g.lineTo(ax + s * 0.7, ay + s * 1.6); g.stroke();
        g.restore();
        return t < 4.3;
      });
    },

    // How to Train Your Dragon: a dragon silhouette swoops past through dusk clouds, wings
    // beating, and banks away.
    dragon: function () {
      var c = curtain({ max: 5000, background: 'linear-gradient(to bottom, rgb(60 50 110), rgb(220 120 110) 70%, rgb(250 180 120))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var clouds = [];
      for (var i = 0; i < 14; i++) { clouds.push({ x: Math.random() * W, y: H * (0.2 + Math.random() * 0.7), s: 50 + Math.random() * 90, v: 0.5 + Math.random() * 1.5 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        clouds.forEach(function (cl) {
          cl.x -= cl.v; if (cl.x + cl.s * 2 < 0) { cl.x = W + cl.s; }
          g.fillStyle = 'rgba(255, 210, 200, 0.35)';
          for (var b = 0; b < 4; b++) { g.beginPath(); g.arc(cl.x + b * cl.s * 0.5, cl.y + (b % 2) * cl.s * 0.15, cl.s * 0.4, 0, Math.PI * 2); g.fill(); }
        });
        var q = Math.min(1, t / 3.0);
        var x = -W * 0.1 + q * W * 1.25, y = H * 0.75 - Math.sin(q * Math.PI) * H * 0.45 - q * H * 0.2, s = H * (0.08 + Math.sin(q * Math.PI) * 0.08);
        var flap = Math.sin(t * 9) * 0.7, bank = -0.3 + q * 0.5;
        g.save(); g.translate(x, y); g.rotate(bank);
        g.fillStyle = 'rgb(20 14 30)';
        g.beginPath(); g.ellipse(0, 0, s * 0.9, s * 0.22, 0, 0, Math.PI * 2); g.fill();
        g.beginPath(); g.moveTo(s * 0.7, -s * 0.05); g.quadraticCurveTo(s * 1.1, -s * 0.3, s * 1.35, -s * 0.2); g.lineTo(s * 1.3, s * 0.02); g.quadraticCurveTo(s * 1.05, -s * 0.05, s * 0.7, s * 0.08); g.fill();
        g.beginPath(); g.moveTo(-s * 0.8, 0); g.quadraticCurveTo(-s * 1.4, s * 0.15, -s * 1.9, -s * 0.05); g.lineTo(-s * 2.1, s * 0.1); g.lineTo(-s * 1.85, s * 0.12); g.quadraticCurveTo(-s * 1.4, s * 0.3, -s * 0.8, s * 0.1); g.fill();
        [-1, 1].forEach(function (side) {
          g.beginPath(); g.moveTo(s * 0.2, 0);
          g.quadraticCurveTo(s * 0.1, side * s * (0.9 + flap * side * 0.6), -s * 0.4, side * s * (1.4 + flap * side * 0.8));
          g.lineTo(-s * 0.55, side * s * 0.3); g.closePath(); g.fill();
        });
        g.restore();
        if (t > 3.2) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.2) / 0.6)); }
        return t < 3.9;
      });
    },

    // Cars: racing stripes zoom past, then a checkered flag waves and sweeps the page in.
    flag: function () {
      var c = curtain({ max: 5000, background: 'rgb(30 30 34)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        if (t < 1.6) {
          [['rgb(220 30 30)', 0], ['rgb(255 210 30)', 1], ['rgb(220 30 30)', 2]].forEach(function (st) {
            var x = W * 1.4 - ((t * 2.2 + st[1] * 0.18) % 1.4) * W * 2.2;
            g.fillStyle = st[0];
            g.beginPath(); g.moveTo(x, 0); g.lineTo(x + W * 0.12, 0); g.lineTo(x + W * 0.12 - H * 0.4, H); g.lineTo(x - H * 0.4, H); g.closePath(); g.fill();
          });
        }
        if (t > 1.4) {
          var sweep = t > 3.0 ? Math.min(1, (t - 3.0) / 0.6) : 0, size = Math.min(W, H) / 14, cols = Math.ceil(W / size) + 2, rows = Math.ceil(H * 0.6 / size);
          if (sweep) { c.el.style.background = 'transparent'; }
          var top = H * 0.15 + sweep * H;
          for (var r = 0; r < rows; r++) {
            for (var k = 0; k < cols; k++) {
              var wave = Math.sin(k * 0.5 - t * 6) * size * 0.4;
              g.fillStyle = (r + k) % 2 ? 'rgb(20 20 20)' : 'rgb(245 245 245)';
              g.fillRect(k * size - size, top + r * size + wave, size + 1, size + 1);
            }
          }
        }
        return t < 3.7;
      });
    },

    // Night at the Museum: a dark hall, the lights flicker on, and a dinosaur skeleton turns its
    // head to look at you.
    museum: function () {
      var c = curtain({ max: 5500, background: 'rgb(6 6 8)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var floor = H * 0.84, cx = W * 0.5, s = Math.min(W, H) * 0.0045;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var light = t < 0.6 ? 0 : t < 1.4 ? (Math.random() > 0.5 ? 1 : 0.2) : 1;
        var fade = t > 3.9 ? Math.max(0, 1 - (t - 3.9) / 0.6) : 1;
        if (fade < 1) { c.el.style.opacity = String(fade); }
        if (light) {
          [0.2, 0.5, 0.8].forEach(function (p) {
            var spot = g.createRadialGradient(W * p, 0, 0, W * p, floor, H * 0.8);
            spot.addColorStop(0, 'rgba(255, 230, 180, ' + 0.35 * light + ')'); spot.addColorStop(1, 'rgba(255, 230, 180, 0)');
            g.fillStyle = spot; g.fillRect(0, 0, W, H);
          });
        }
        var bone = 'rgba(230, 220, 195, ' + (0.15 + light * 0.85) + ')';
        g.fillStyle = 'rgba(60, 50, 40, ' + (0.3 + light * 0.5) + ')';
        for (var col = 0; col < 6; col++) { g.fillRect(W * (0.05 + col * 0.18), H * 0.1, 26, floor - H * 0.1); }
        g.fillRect(0, floor, W, H - floor);
        g.strokeStyle = bone; g.fillStyle = bone; g.lineCap = 'round'; g.lineWidth = 6 * s;
        g.beginPath(); g.moveTo(cx - 120 * s, floor - 70 * s); g.quadraticCurveTo(cx, floor - 120 * s, cx + 70 * s, floor - 95 * s); g.stroke();
        g.beginPath(); g.moveTo(cx - 120 * s, floor - 70 * s); g.quadraticCurveTo(cx - 200 * s, floor - 60 * s, cx - 260 * s, floor - 30 * s); g.stroke();
        g.lineWidth = 3 * s;
        for (var rib = 0; rib < 7; rib++) { var rx = cx - 70 * s + rib * 18 * s; g.beginPath(); g.moveTo(rx, floor - 108 * s + Math.abs(rib - 3) * 2 * s); g.quadraticCurveTo(rx + 8 * s, floor - 70 * s, rx, floor - 50 * s); g.stroke(); }
        g.lineWidth = 7 * s;
        [[-40, 0], [20, 0]].forEach(function (leg) { g.beginPath(); g.moveTo(cx + leg[0] * s, floor - 85 * s); g.lineTo(cx + (leg[0] - 10) * s, floor - 40 * s); g.lineTo(cx + (leg[0] + 10) * s, floor); g.stroke(); });
        var turn = Math.min(1, Math.max(0, (t - 2.0) / 0.8));
        g.save(); g.translate(cx + 70 * s, floor - 95 * s); g.rotate(-0.15 - turn * 0.5); g.scale(1 - turn * 0.25, 1);
        g.lineWidth = 6 * s; g.beginPath(); g.moveTo(0, 0); g.lineTo(40 * s, -30 * s); g.stroke();
        g.beginPath(); g.moveTo(30 * s, -50 * s); g.lineTo(95 * s, -40 * s); g.lineTo(95 * s, -22 * s); g.lineTo(40 * s, -18 * s); g.closePath(); g.fill();
        g.fillStyle = 'rgb(6 6 8)'; g.beginPath(); g.arc(52 * s, -38 * s, 5 * s, 0, Math.PI * 2); g.fill();
        g.restore();
        return t < 4.5;
      });
    },

    // The Chronicles of Narnia: wardrobe doors open on snowy woods, a lamp-post glowing in the
    // snow.
    wardrobe: function () {
      var c = curtain({ max: 6000, background: 'linear-gradient(to bottom, rgb(150 165 190), rgb(220 228 238))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var flakes = [], trees = [];
      for (var i = 0; i < 180; i++) { flakes.push({ x: Math.random() * W, y: Math.random() * H, v: 0.5 + Math.random() * 1.5, r: 1 + Math.random() * 2.5 }); }
      for (var k = 0; k < 16; k++) { trees.push({ x: Math.random() * W, h: H * (0.3 + Math.random() * 0.35), w: 40 + Math.random() * 50 }); }
      var doors = document.createElement('div');
      doors.className = 'sc-doors';
      ['left', 'right'].forEach(function (side) {
        var door = document.createElement('span');
        door.className = 'sc-door sc-door--' + side;
        door.style.background = 'linear-gradient(90deg, rgb(70 44 26), rgb(96 62 36), rgb(70 44 26))';
        door.style.boxShadow = 'inset 0 0 0 0.6rem rgb(56 34 20), inset 0 0 3rem rgba(0, 0, 0, 0.6)';
        doors.appendChild(door);
        if (door.animate) {
          door.animate([{ rotate: 'y 0deg' }, { rotate: 'y ' + (side === 'left' ? '-' : '') + '105deg' }], { duration: 1600, delay: 700, easing: 'cubic-bezier(.5, 0, .3, 1)', fill: 'both' });
        }
      });
      c.el.appendChild(doors);
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var ground = H * 0.8;
        trees.forEach(function (tr) {
          g.fillStyle = 'rgb(40 60 56)';
          g.beginPath(); g.moveTo(tr.x, ground - tr.h); g.lineTo(tr.x + tr.w / 2, ground); g.lineTo(tr.x - tr.w / 2, ground); g.closePath(); g.fill();
          g.fillStyle = 'rgba(255, 255, 255, 0.85)';
          g.beginPath(); g.moveTo(tr.x, ground - tr.h); g.lineTo(tr.x + tr.w * 0.15, ground - tr.h * 0.7); g.lineTo(tr.x - tr.w * 0.15, ground - tr.h * 0.7); g.closePath(); g.fill();
        });
        g.fillStyle = 'rgb(245 248 252)'; g.fillRect(0, ground, W, H - ground);
        var lx = W * 0.5, top = H * 0.38;
        var glow = g.createRadialGradient(lx, top, 0, lx, top, H * 0.25);
        glow.addColorStop(0, 'rgba(255, 220, 140, ' + (0.6 + Math.sin(t * 5) * 0.05) + ')'); glow.addColorStop(1, 'rgba(255, 220, 140, 0)');
        g.fillStyle = glow; g.fillRect(0, 0, W, H);
        g.fillStyle = 'rgb(30 30 34)'; g.fillRect(lx - 4, top, 8, ground - top);
        g.fillRect(lx - 14, top - 26, 28, 6);
        g.fillStyle = 'rgba(255, 230, 160, 0.95)'; g.fillRect(lx - 10, top - 20, 20, 22);
        g.fillStyle = 'rgba(255, 255, 255, 0.9)';
        flakes.forEach(function (f) { f.y += f.v; f.x += Math.sin(f.y / 40) * 0.5; if (f.y > H) { f.y = -5; f.x = Math.random() * W; } g.beginPath(); g.arc(f.x, f.y, f.r, 0, Math.PI * 2); g.fill(); });
        if (t > 4.0) { c.el.style.opacity = String(Math.max(0, 1 - (t - 4.0) / 0.7)); }
        return t < 4.8;
      });
    },

    // ---------------------------------------------------------------- 0.66.0

    // Insidious: pitch dark; a red door at the far end glows, creaks open, and something breathes
    // out of it.
    reddoor: function () {
      var c = curtain({ max: 5500, background: 'black' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var dw = Math.min(W, H) * 0.16, dh = dw * 2.1, dx = W / 2 - dw / 2, dy = H * 0.52 - dh / 2, puffs = [];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var glow = Math.min(1, t / 1.2);
        var halo = g.createRadialGradient(W / 2, H * 0.52, 0, W / 2, H * 0.52, dh * 1.4);
        halo.addColorStop(0, 'rgba(150, 0, 0, ' + 0.35 * glow + ')'); halo.addColorStop(1, 'rgba(150, 0, 0, 0)');
        g.fillStyle = halo; g.fillRect(0, 0, W, H);
        var open = Math.min(1, Math.max(0, (t - 1.4) / 1.0));
        g.fillStyle = 'rgb(4 0 0)'; g.fillRect(dx, dy, dw, dh);
        g.fillStyle = 'rgba(' + Math.round(120 + glow * 60) + ', 10, 10, ' + glow + ')';
        g.fillRect(dx + dw * open, dy, dw * (1 - open * 0.85), dh);
        g.fillStyle = 'rgba(30, 0, 0, ' + glow + ')'; g.fillRect(dx + dw * open + dw * (1 - open * 0.85) - 8, dy + dh * 0.5, 5, 5);
        if (open > 0.5 && t < 3.4) { for (var p = 0; p < 2; p++) { puffs.push({ x: W / 2, y: H * 0.5, r: 10, a: 0.25, vx: (Math.random() - 0.5) * 3, vy: (Math.random() - 0.3) * 1.5 }); } }
        puffs.forEach(function (pf) {
          pf.x += pf.vx; pf.y += pf.vy; pf.r += 3; pf.a *= 0.97;
          g.fillStyle = 'rgba(180, 170, 170, ' + pf.a + ')'; g.beginPath(); g.arc(pf.x, pf.y, pf.r, 0, Math.PI * 2); g.fill();
        });
        if (t > 3.5 && t < 3.6) { g.fillStyle = 'rgba(200, 0, 0, 0.8)'; g.fillRect(0, 0, W, H); }
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.5)); }
        return t < 4.2;
      });
    },

    // The Shining: a long hotel corridor with a bold patterned carpet rushes past, down to a door
    // at the end.
    corridor: function () {
      var c = curtain({ max: 5500, background: 'rgb(30 20 14)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H * 0.45, fw = W * 0.06, fh = H * 0.1;
      var colours = ['rgb(190 70 30)', 'rgb(110 40 20)', 'rgb(230 140 40)'];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var travel = t * 1.6;
        var proj = function (z) { var k = 1 / z; return { l: cx - (cx - fw) * k - fw, r: cx + (W - cx - fw) * k + fw, t: cy - (cy - fh) * k - fh, b: cy + (H - cy - fh) * k + fh }; };
        g.fillStyle = 'rgb(220 200 160)'; g.fillRect(0, 0, W, H);
        g.fillStyle = 'rgb(140 110 80)';
        var far = proj(14);
        g.beginPath(); g.moveTo(0, 0); g.lineTo(W, 0); g.lineTo(far.r, far.t); g.lineTo(far.l, far.t); g.closePath(); g.fill();
        g.fillStyle = colours[1];   // the carpet under the nearest rows, so no wall shows below them
        g.beginPath(); g.moveTo(far.l, far.b); g.lineTo(far.r, far.b); g.lineTo(W, H); g.lineTo(0, H); g.closePath(); g.fill();
        for (var z = 14; z >= 1; z -= 0.5) {
          var zz = z - (travel % 1);
          if (zz < 1) { continue; }
          var a = proj(zz), b = proj(zz + 0.5), row = Math.floor(z * 2 + travel * 2);
          for (var k = 0; k < 6; k++) {
            g.fillStyle = colours[(row + k) % 3];
            var x1a = a.l + (a.r - a.l) * k / 6, x2a = a.l + (a.r - a.l) * (k + 1) / 6, x1b = b.l + (b.r - b.l) * k / 6, x2b = b.l + (b.r - b.l) * (k + 1) / 6;
            g.beginPath(); g.moveTo(x1a, a.b); g.lineTo(x2a, a.b); g.lineTo(x2b, b.b); g.lineTo(x1b, b.b); g.closePath(); g.fill();
          }
          g.strokeStyle = 'rgba(80, 50, 30, 0.35)'; g.beginPath(); g.moveTo(a.l, a.t); g.lineTo(a.l, a.b); g.moveTo(a.r, a.t); g.lineTo(a.r, a.b); g.stroke();
        }
        var door = proj(Math.max(1.4, 14 - t * 3));
        g.fillStyle = 'rgb(80 50 30)';
        g.fillRect(cx - (door.r - door.l) * 0.12, door.t + (door.b - door.t) * 0.15, (door.r - door.l) * 0.24, (door.b - door.t) * 0.85);
        if (t > 3.3) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.3) / 0.6)); }
        return t < 4.0;
      });
    },

    // The Thing: an Antarctic blizzard at night, a lone outpost light blinking, the snow thickening
    // to white-out.
    blizzard: function () {
      var c = curtain({ max: 5000, background: 'rgb(10 14 22)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var flakes = [];
      for (var i = 0; i < 700; i++) { flakes.push({ x: Math.random() * W, y: Math.random() * H, v: 4 + Math.random() * 10, r: 0.8 + Math.random() * 2 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var ground = H * 0.78;
        g.fillStyle = 'rgb(180 190 205)'; g.fillRect(0, ground, W, H - ground);
        g.fillStyle = 'rgb(20 24 32)'; g.fillRect(W * 0.55, ground - H * 0.12, W * 0.2, H * 0.12); g.fillRect(W * 0.6, ground - H * 0.2, 6, H * 0.08);
        if (Math.floor(t * 1.6) % 2 === 0) {
          var red = g.createRadialGradient(W * 0.6 + 3, ground - H * 0.2, 0, W * 0.6 + 3, ground - H * 0.2, 30);
          red.addColorStop(0, 'rgba(255, 50, 40, 0.9)'); red.addColorStop(1, 'rgba(255, 50, 40, 0)');
          g.fillStyle = red; g.fillRect(0, 0, W, H);
        }
        var storm = Math.min(1, t / 2.6);
        g.fillStyle = 'rgba(240, 245, 255, 0.85)';
        flakes.forEach(function (f, i) {
          if (i / flakes.length > 0.25 + storm * 0.75) { return; }
          f.x += f.v * (0.6 + storm); f.y += 1 + Math.sin(f.x / 50); if (f.x > W) { f.x = -5; f.y = Math.random() * H; }
          g.beginPath(); g.arc(f.x, f.y, f.r, 0, Math.PI * 2); g.fill();
        });
        if (t > 2.4) { g.fillStyle = 'rgba(235, 240, 248, ' + Math.min(1, (t - 2.4) / 0.9) + ')'; g.fillRect(0, 0, W, H); }
        if (t > 3.4) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.4) / 0.6)); }
        return t < 4.0;
      });
    },

    // Underworld: blue moonlit rain over gothic rooftops, the full moon behind cloud, lightning.
    moonrain: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(10 18 34), rgb(20 34 56))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var drops = [], roofs = [];
      for (var i = 0; i < 360; i++) { drops.push({ x: Math.random() * W, y: Math.random() * H, v: 14 + Math.random() * 10 }); }
      for (var r = 0; r < 10; r++) { roofs.push({ x: r / 10 * W, w: W / 10 + 10, h: H * (0.2 + Math.random() * 0.25), spire: Math.random() > 0.5 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var mx = W * 0.7, my = H * 0.25, mr = Math.min(W, H) * 0.1;
        var moon = g.createRadialGradient(mx, my, mr * 0.5, mx, my, mr * 3);
        moon.addColorStop(0, 'rgba(190, 210, 240, 0.5)'); moon.addColorStop(1, 'rgba(190, 210, 240, 0)');
        g.fillStyle = moon; g.fillRect(0, 0, W, H);
        g.fillStyle = 'rgb(215 228 245)'; g.beginPath(); g.arc(mx, my, mr, 0, Math.PI * 2); g.fill();
        g.fillStyle = 'rgba(30, 40, 60, 0.8)'; g.beginPath(); g.ellipse(mx - mr * 2 + t * 40, my + mr * 0.3, mr * 2.4, mr * 0.45, 0, 0, Math.PI * 2); g.fill();
        g.fillStyle = 'rgb(6 10 18)';
        roofs.forEach(function (rf) {
          var base = H;
          g.beginPath(); g.moveTo(rf.x, base); g.lineTo(rf.x, base - rf.h); g.lineTo(rf.x + rf.w / 2, base - rf.h - (rf.spire ? H * 0.12 : H * 0.04)); g.lineTo(rf.x + rf.w, base - rf.h); g.lineTo(rf.x + rf.w, base); g.closePath(); g.fill();
        });
        g.strokeStyle = 'rgba(150, 180, 220, 0.4)'; g.lineWidth = 1; g.beginPath();
        drops.forEach(function (d) { d.y += d.v; d.x -= d.v * 0.25; if (d.y > H) { d.y = -20; d.x = Math.random() * W * 1.2; } g.moveTo(d.x, d.y); g.lineTo(d.x + 4, d.y - 16); });
        g.stroke();
        [1.7, 2.9].forEach(function (at) {
          if (t > at && t < at + 0.12) {
            g.fillStyle = 'rgba(220, 230, 255, 0.55)'; g.fillRect(0, 0, W, H);
            g.strokeStyle = 'rgba(240, 245, 255, 0.95)'; g.lineWidth = 2;
            var x = W * (at > 2 ? 0.3 : 0.55), y = 0; g.beginPath(); g.moveTo(x, y);
            while (y < H * 0.55) { x += (Math.random() - 0.5) * 50; y += 25 + Math.random() * 20; g.lineTo(x, y); }
            g.stroke();
          }
        });
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.6)); }
        return t < 4.3;
      });
    },

    // Top Gun: jets streak across a sunset trailing contrails, a flare of sun as they bank away.
    jets: function () {
      var c = curtain({ max: 5000, background: 'linear-gradient(to bottom, rgb(250 140 60), rgb(230 90 70) 50%, rgb(90 50 80))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var jet = function (x, y, s, a) {
        g.save(); g.translate(x, y); g.rotate(a); g.fillStyle = 'rgb(30 24 34)';
        g.beginPath(); g.moveTo(s, 0); g.lineTo(-s * 0.6, -s * 0.12); g.lineTo(-s * 0.2, -s * 0.12); g.lineTo(-s * 0.55, -s * 0.7); g.lineTo(-s * 0.35, -s * 0.7);
        g.lineTo(s * 0.15, -s * 0.12); g.lineTo(s * 0.15, s * 0.12); g.lineTo(-s * 0.35, s * 0.7); g.lineTo(-s * 0.55, s * 0.7); g.lineTo(-s * 0.2, s * 0.12); g.lineTo(-s * 0.6, s * 0.12); g.closePath(); g.fill();
        g.restore();
      };
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var sx = W * 0.82, sy = H * 0.7;
        var sun = g.createRadialGradient(sx, sy, 0, sx, sy, H * 0.5);
        sun.addColorStop(0, 'rgba(255, 240, 200, 0.95)'); sun.addColorStop(0.15, 'rgba(255, 210, 140, 0.6)'); sun.addColorStop(1, 'rgba(255, 180, 100, 0)');
        g.fillStyle = sun; g.fillRect(0, 0, W, H);
        [0, 0.35, 0.7].forEach(function (lag, i) {
          var q = Math.min(1.2, Math.max(0, (t - lag) / 1.8));
          if (q <= 0) { return; }
          var x0 = -W * 0.1, y0 = H * (0.75 - i * 0.08), x = x0 + q * W * 1.2, y = y0 - q * H * 0.55 - Math.pow(q, 3) * H * 0.2, a = -0.45 - q * 0.3;
          g.strokeStyle = 'rgba(255, 250, 240, 0.7)'; g.lineWidth = 3;
          g.beginPath(); g.moveTo(x0, y0); g.quadraticCurveTo((x0 + x) / 2, y0 - (y0 - y) * 0.35, x, y); g.stroke();
          jet(x, y, Math.min(W, H) * 0.05, a);
        });
        if (t > 1.6) {
          var flare = Math.max(0, Math.sin((t - 1.6) / 1.2 * Math.PI));
          g.fillStyle = 'rgba(255, 245, 220, ' + 0.5 * flare + ')'; g.fillRect(0, 0, W, H);
          [0.3, 0.55, 0.75].forEach(function (k) { g.fillStyle = 'rgba(255, 220, 180, ' + 0.25 * flare + ')'; g.beginPath(); g.arc(sx + (W / 2 - sx) * k * 2, sy + (H / 2 - sy) * k * 2, 20 + k * 30, 0, Math.PI * 2); g.fill(); });
        }
        if (t > 3.0) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.0) / 0.6)); }
        return t < 3.7;
      });
    },

    // Ocean's: a bank vault -- the dial spins to a combination (what you have, how many there are,
    // how many are missing), the bolts slide back, and the door swings open.
    vault: function () {
      var c = curtain({ max: 6000, background: 'radial-gradient(circle at 50% 45%, rgb(50 52 56), rgb(12 12 14))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H * 0.48, R = Math.min(W, H) * 0.34;
      var combo = [parseInt(page.have, 10) || 3, parseInt(page.total, 10) || 7, page.missing.length || 1].map(function (v) { return v % 100; });
      var readout = text('p', 'sc-intro-caption', '', c.el);
      readout.style.color = 'rgb(220 200 140)'; readout.style.top = '86%';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var open = Math.min(1, Math.max(0, (t - 3.0) / 0.9));
        g.save(); g.translate(cx, cy); g.scale(1 - open * 0.85, 1);
        g.fillStyle = 'rgb(150 152 158)'; g.beginPath(); g.arc(0, 0, R, 0, Math.PI * 2); g.fill();
        g.strokeStyle = 'rgb(90 92 98)'; g.lineWidth = 8; g.beginPath(); g.arc(0, 0, R * 0.92, 0, Math.PI * 2); g.stroke();
        var retract = Math.min(1, Math.max(0, (t - 2.5) / 0.4));
        for (var b = 0; b < 12; b++) {
          var a = b / 12 * Math.PI * 2, d = R * (0.98 - retract * 0.18);
          g.save(); g.rotate(a); g.fillStyle = 'rgb(200 200 205)'; g.fillRect(d - R * 0.08, -R * 0.03, R * 0.14, R * 0.06); g.restore();
        }
        var stage = Math.min(2, Math.floor(t / 0.8)), into = Math.min(1, (t - stage * 0.8) / 0.7);
        var target = combo[stage] / 100 * Math.PI * 2 * (stage % 2 ? -1 : 1) + stage * Math.PI * 4 * (stage % 2 ? -1 : 1);
        var dial = t < 2.4 ? target * into : combo[2] / 100 * Math.PI * 2 + Math.PI * 8;
        g.fillStyle = 'rgb(60 62 68)'; g.beginPath(); g.arc(0, 0, R * 0.3, 0, Math.PI * 2); g.fill();
        g.save(); g.rotate(dial);
        g.strokeStyle = 'rgb(220 220 225)'; g.lineWidth = 2;
        for (var n = 0; n < 50; n++) { var na = n / 50 * Math.PI * 2; g.beginPath(); g.moveTo(Math.cos(na) * R * 0.26, Math.sin(na) * R * 0.26); g.lineTo(Math.cos(na) * R * (n % 5 ? 0.23 : 0.2), Math.sin(na) * R * (n % 5 ? 0.23 : 0.2)); g.stroke(); }
        g.restore();
        g.fillStyle = 'rgb(220 60 40)'; g.beginPath(); g.moveTo(0, -R * 0.33); g.lineTo(-6, -R * 0.38); g.lineTo(6, -R * 0.38); g.closePath(); g.fill();
        g.restore();
        readout.textContent = combo.slice(0, stage + 1).map(function (v) { return ('0' + v).slice(-2); }).join(' – ');
        if (open > 0) { c.el.style.background = 'rgba(12, 12, 14, ' + (1 - open) + ')'; }
        return t < 4.1;
      });
    },

    // The Equalizer: a stopwatch starts; the seconds race round while the room blurs past, then it
    // stops with a click.
    stopwatch: function () {
      var c = curtain({ max: 5000, background: 'rgb(14 14 16)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H * 0.5, R = Math.min(W, H) * 0.26, bokeh = [];
      for (var i = 0; i < 24; i++) { bokeh.push({ x: Math.random() * W, y: Math.random() * H, r: 20 + Math.random() * 60, v: 2 + Math.random() * 6, hue: Math.random() > 0.5 ? '255, 200, 120' : '140, 180, 255' }); }
      var stopAt = 2.8;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var running = t < stopAt;
        bokeh.forEach(function (b) {
          if (running) { b.x += b.v; if (b.x - b.r > W) { b.x = -b.r; } }
          g.fillStyle = 'rgba(' + b.hue + ', 0.12)'; g.beginPath(); g.arc(b.x, b.y, b.r, 0, Math.PI * 2); g.fill();
        });
        g.fillStyle = 'rgb(200 200 205)'; g.fillRect(cx - R * 0.12, cy - R * 1.28, R * 0.24, R * 0.18);
        g.fillStyle = 'rgb(28 28 32)'; g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fill();
        g.strokeStyle = 'rgb(200 200 205)'; g.lineWidth = 6; g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.stroke();
        g.lineWidth = 2;
        for (var k = 0; k < 60; k++) { var a = k / 60 * Math.PI * 2; g.beginPath(); g.moveTo(cx + Math.cos(a) * R * 0.9, cy + Math.sin(a) * R * 0.9); g.lineTo(cx + Math.cos(a) * R * (k % 5 ? 0.85 : 0.78), cy + Math.sin(a) * R * (k % 5 ? 0.85 : 0.78)); g.stroke(); }
        var secs = Math.min(t, stopAt) * 6.2, hand = secs / 60 * Math.PI * 2 - Math.PI / 2;
        g.strokeStyle = 'rgb(220 60 40)'; g.lineWidth = 3;
        g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(hand) * R * 0.82, cy + Math.sin(hand) * R * 0.82); g.stroke();
        g.fillStyle = 'rgb(230 230 235)'; g.font = '700 ' + Math.round(R * 0.2) + 'px ui-monospace, monospace'; g.textAlign = 'center';
        g.fillText('00:' + ('0' + Math.floor(secs)).slice(-2) + '.' + Math.floor((secs % 1) * 10), cx, cy + R * 0.45);
        if (!running && t < stopAt + 0.15) { g.fillStyle = 'rgba(255, 255, 255, 0.4)'; g.fillRect(0, 0, W, H); }
        if (t > stopAt + 0.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - stopAt - 0.6) / 0.5)); }
        return t < stopAt + 1.2;
      });
    },

    // Lethal Weapon: red and blue lights sweep a dark street strung with Christmas lights.
    siren: function () {
      var c = curtain({ max: 5000, background: 'rgb(8 8 14)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var bulbs = [], colours = ['255, 60, 60', '60, 220, 90', '255, 210, 60', '80, 140, 255'];
      for (var i = 0; i < 40; i++) { bulbs.push({ x: i / 39 * W, c: colours[i % 4], p: Math.random() * 6 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.fillStyle = 'rgb(14 14 20)'; g.fillRect(0, H * 0.72, W, H * 0.28);
        g.strokeStyle = 'rgba(80, 80, 90, 0.8)'; g.lineWidth = 2; g.beginPath();
        bulbs.forEach(function (b, i) { var y = H * 0.12 + Math.sin(i / 39 * Math.PI) * H * 0.08; if (i) { g.lineTo(b.x, y); } else { g.moveTo(b.x, y); } });
        g.stroke();
        bulbs.forEach(function (b, i) {
          var y = H * 0.12 + Math.sin(i / 39 * Math.PI) * H * 0.08, on = 0.5 + 0.5 * Math.sin(t * 4 + b.p);
          g.fillStyle = 'rgba(' + b.c + ', ' + (0.4 + on * 0.6) + ')'; g.shadowColor = 'rgb(' + b.c.split(', ').join(' ') + ')'; g.shadowBlur = 10 * on;
          g.beginPath(); g.arc(b.x, y + 8, 6, 0, Math.PI * 2); g.fill();
        });
        g.shadowBlur = 0;
        var phase = Math.floor(t * 4) % 2;
        [['255, 30, 30', 0.3, phase], ['40, 90, 255', 0.7, 1 - phase]].forEach(function (s) {
          if (!s[2]) { return; }
          var x = W * s[1], wash = g.createRadialGradient(x, H * 0.85, 0, x, H * 0.85, W * 0.6);
          wash.addColorStop(0, 'rgba(' + s[0] + ', 0.55)'); wash.addColorStop(1, 'rgba(' + s[0] + ', 0)');
          g.fillStyle = wash; g.fillRect(0, 0, W, H);
        });
        if (t > 3.2) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.2) / 0.6)); }
        return t < 3.9;
      });
    },

    // 2001: A Space Odyssey: a black monolith against the dark, and a sunrise climbing over a
    // planet's edge into alignment above it.
    monolith: function () {
      var c = curtain({ max: 6000, background: 'black' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, planetR = Math.max(W, H) * 1.1, planetY = H + planetR * 0.82;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var rise = Math.min(1, t / 2.6), sunY = planetY - planetR - H * 0.02 - rise * H * 0.12;
        var sun = g.createRadialGradient(cx, sunY, 0, cx, sunY, H * 0.5 * (0.4 + rise));
        sun.addColorStop(0, 'rgba(255, 250, 235, ' + rise + ')'); sun.addColorStop(0.1, 'rgba(255, 230, 180, ' + 0.7 * rise + ')'); sun.addColorStop(1, 'rgba(255, 200, 140, 0)');
        g.fillStyle = sun; g.fillRect(0, 0, W, H);
        if (rise > 0.8) {
          var flare = (rise - 0.8) / 0.2;
          g.fillStyle = 'rgba(255, 245, 225, ' + 0.6 * flare + ')'; g.fillRect(cx - W * 0.5 * flare, sunY - 1, W * flare, 2);
        }
        g.fillStyle = 'rgb(6 8 14)'; g.beginPath(); g.arc(cx, planetY, planetR, 0, Math.PI * 2); g.fill();
        g.strokeStyle = 'rgba(160, 190, 255, ' + 0.6 * rise + ')'; g.lineWidth = 3; g.beginPath(); g.arc(cx, planetY, planetR, Math.PI * 1.3, Math.PI * 1.7); g.stroke();
        var mw = Math.min(W, H) * 0.06, mh = mw * 4;
        g.fillStyle = 'rgb(2 2 4)'; g.fillRect(cx - mw / 2, H * 0.92 - mh, mw, mh);
        g.strokeStyle = 'rgba(255, 240, 210, ' + 0.4 * rise + ')'; g.lineWidth = 1; g.strokeRect(cx - mw / 2, H * 0.92 - mh, mw, mh);
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.7)); }
        return t < 4.4;
      });
    },

    // Venom: glossy black tendrils creep in from the edges, writhing, then snap back. The page
    // stays usable.
    tendrils: function () {
      var c = curtain({ max: 5000, through: true });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var arms = [];
      for (var i = 0; i < 22; i++) {
        var side = i % 4, f = Math.random();
        arms.push({ x: side === 1 ? W : side === 3 ? 0 : f * W, y: side === 0 ? 0 : side === 2 ? H : f * H,
                    tx: W * (0.25 + Math.random() * 0.5), ty: H * (0.25 + Math.random() * 0.5), w: 10 + Math.random() * 22, p: Math.random() * 6 });
      }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var reach = t < 2.4 ? Math.min(1, t / 2.0) : Math.max(0, 1 - (t - 2.4) / 0.35);
        arms.forEach(function (a) {
          var steps = 26, pts = [];
          for (var k = 0; k <= steps * reach; k++) {
            var q = k / steps, wob = Math.sin(q * 8 + t * 5 + a.p) * 30 * q;
            pts.push([a.x + (a.tx - a.x) * q + wob * (a.ty - a.y) / H, a.y + (a.ty - a.y) * q - wob * (a.tx - a.x) / W]);
          }
          if (pts.length < 2) { return; }
          g.strokeStyle = 'rgb(8 8 12)'; g.lineCap = 'round';
          for (var s = 1; s < pts.length; s++) {
            g.lineWidth = a.w * (1 - s / (steps + 2));
            g.beginPath(); g.moveTo(pts[s - 1][0], pts[s - 1][1]); g.lineTo(pts[s][0], pts[s][1]); g.stroke();
          }
          g.strokeStyle = 'rgba(120, 130, 160, 0.35)'; g.lineWidth = 2;
          g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); pts.forEach(function (p) { g.lineTo(p[0] - 3, p[1] - 3); }); g.stroke();
        });
        return t < 2.9;
      });
    },

    // Wonder Woman: a golden lasso spins and widens into a ring of light that sweeps the screen.
    lasso: function () {
      var c = curtain({ max: 5000, background: 'radial-gradient(circle at 50% 50%, rgb(70 20 30), rgb(14 6 10))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H / 2, sparks = [];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var grow = t < 1.6 ? 0.15 + t / 1.6 * 0.15 : 0.3 + Math.pow(t - 1.6, 2) * 1.4;
        var R = Math.min(W, H) * grow, tilt = 0.32;
        g.save(); g.translate(cx, cy);
        g.shadowColor = 'rgb(255 200 80)'; g.shadowBlur = 20;
        g.lineWidth = 8; g.setLineDash([14, 6]); g.lineDashOffset = -t * 120;
        g.strokeStyle = 'rgb(240 190 70)'; g.beginPath(); g.ellipse(0, 0, R, R * tilt, Math.sin(t) * 0.2, 0, Math.PI * 2); g.stroke();
        g.setLineDash([]); g.shadowBlur = 0;
        g.restore();
        if (Math.random() < 0.8) { var a = Math.random() * Math.PI * 2; sparks.push({ x: cx + Math.cos(a) * R, y: cy + Math.sin(a) * R * tilt, a: 1 }); }
        sparks.forEach(function (s) { s.y -= 1; s.a *= 0.94; g.fillStyle = 'rgba(255, 230, 150, ' + s.a + ')'; g.fillRect(s.x, s.y, 3, 3); });
        if (t > 2.0) {
          var light = Math.min(1, (t - 2.0) / 0.6);
          var ring = g.createRadialGradient(cx, cy, R * 0.8, cx, cy, R * 1.1);
          ring.addColorStop(0, 'rgba(255, 220, 120, 0)'); ring.addColorStop(0.5, 'rgba(255, 220, 120, ' + 0.5 * light + ')'); ring.addColorStop(1, 'rgba(255, 220, 120, 0)');
          g.fillStyle = ring; g.fillRect(0, 0, W, H);
          c.el.style.opacity = String(Math.max(0, 1 - Math.max(0, t - 2.6) / 0.6));
        }
        return t < 3.3;
      });
    },

    // Spider-Man: a line of web shoots in from a corner, a web spreads out from the middle, and
    // the title is caught in it.
    web: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(14 24 54), rgb(40 30 70))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H * 0.45, spokes = 14, R = Math.hypot(W, H) * 0.6;
      var angles = [];
      for (var i = 0; i < spokes; i++) { angles.push(i / spokes * Math.PI * 2 + (Math.random() - 0.5) * 0.15); }
      var caught = text('p', 'sc-intro-caption', page.short, c.el);
      caught.style.color = 'rgb(240 240 245)'; caught.style.top = '40%'; caught.style.opacity = '0';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgba(235, 240, 250, 0.85)'; g.lineWidth = 1.5;
        var shot = Math.min(1, t / 0.4);
        g.beginPath(); g.moveTo(0, H); g.lineTo(cx * shot, H - (H - cy) * shot); g.stroke();
        if (t > 0.4) {
          var spread = Math.min(1, (t - 0.4) / 0.9);
          angles.forEach(function (a) { g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(a) * R * spread, cy + Math.sin(a) * R * spread); g.stroke(); });
          var rings = Math.floor(Math.min(1, (t - 0.8) / 1.2) * 12);
          for (var r = 1; r <= rings; r++) {
            var rr = r * R / 16;
            g.beginPath();
            angles.forEach(function (a, k) {
              var x = cx + Math.cos(a) * rr, y = cy + Math.sin(a) * rr;
              if (!k) { g.moveTo(x, y); } else { var pa = angles[k - 1], mx = cx + Math.cos((a + pa) / 2) * rr * 0.9, my = cy + Math.sin((a + pa) / 2) * rr * 0.9; g.quadraticCurveTo(mx, my, x, y); }
            });
            g.closePath(); g.stroke();
          }
        }
        if (t > 1.8) { caught.style.opacity = String(Math.min(1, (t - 1.8) / 0.4)); }
        if (t > 3.4) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.4) / 0.6)); }
        return t < 4.1;
      });
    },

    // The Lion King: a savanna sunrise -- a huge orange sun, acacia trees, and herds crossing the
    // horizon.
    savanna: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(250 170 60), rgb(240 110 40) 55%, rgb(120 40 30))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var horizon = H * 0.72, herd = [];
      for (var i = 0; i < 14; i++) { herd.push({ x: -i * 70 - Math.random() * 40, s: 14 + Math.random() * 8, p: Math.random() * 6 }); }
      var acacia = function (x, h) {
        g.fillStyle = 'rgb(40 16 10)'; g.fillRect(x - 4, horizon - h, 8, h);
        g.beginPath(); g.moveTo(x, horizon - h * 0.6); g.lineTo(x - h * 0.3, horizon - h); g.lineTo(x - h * 0.25, horizon - h); g.closePath(); g.fill();
        g.beginPath(); g.ellipse(x, horizon - h, h * 0.75, h * 0.14, 0, 0, Math.PI * 2); g.fill();
      };
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var rise = Math.min(1, t / 3), sy = horizon + H * 0.1 - rise * H * 0.3, sr = Math.min(W, H) * 0.32;
        g.fillStyle = 'rgba(255, 210, 90, 0.95)'; g.beginPath(); g.arc(W / 2, sy, sr, 0, Math.PI * 2); g.fill();
        g.fillStyle = 'rgb(50 20 12)'; g.fillRect(0, horizon, W, H - horizon);
        acacia(W * 0.18, H * 0.2); acacia(W * 0.78, H * 0.26); acacia(W * 0.62, H * 0.12);
        herd.forEach(function (a) {
          var x = a.x + t * 110, y = horizon - a.s, bob = Math.sin(t * 8 + a.p) * 2;
          g.fillStyle = 'rgb(40 16 10)';
          g.beginPath(); g.ellipse(x, y + bob, a.s, a.s * 0.4, 0, 0, Math.PI * 2); g.fill();
          g.beginPath(); g.ellipse(x + a.s * 1.05, y - a.s * 0.45 + bob, a.s * 0.3, a.s * 0.2, -0.5, 0, Math.PI * 2); g.fill();
          g.strokeStyle = 'rgb(40 16 10)'; g.lineWidth = 2;
          g.beginPath(); g.moveTo(x + a.s * 0.8, y + bob); g.lineTo(x + a.s * 1.1, y - a.s * 0.5 + bob);
          [-0.6, -0.2, 0.3, 0.7].forEach(function (k, j) { var sw = Math.sin(t * 10 + a.p + j) * 3; g.moveTo(x + k * a.s, y + bob); g.lineTo(x + k * a.s + sw, horizon); });
          g.moveTo(x + a.s * 1.2, y - a.s * 0.6 + bob); g.lineTo(x + a.s * 1.1, y - a.s * 1.1 + bob); g.stroke();
        });
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.7)); }
        return t < 4.4;
      });
    },

    // Wreck-It Ralph: the poster breaks into chunky 8-bit pixels that crumble away, then fly back
    // and rebuild.
    pixels: function () {
      var backdrop = document.querySelector('.collection-backdrop');
      var src = page.posters.length ? page.posters[0] : (backdrop ? backdrop.currentSrc || backdrop.src : null);
      var c = curtain({ max: 5000, background: 'rgb(20 16 40)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cols = 16, rows = 24, small = document.createElement('canvas'); small.width = cols; small.height = rows;
      var tiny = small.getContext('2d'), ready = false, picture = new Image();
      picture.onload = function () { tiny.drawImage(picture, 0, 0, cols, rows); ready = true; };
      if (src) { picture.src = src; }
      var ph = Math.min(H * 0.8, W * 0.9 * 1.5), pw = ph / 1.5, x0 = W / 2 - pw / 2, y0 = H / 2 - ph / 2, cw = pw / cols, ch = ph / rows;
      var cells = [];
      for (var r = 0; r < rows; r++) { for (var k = 0; k < cols; k++) { cells.push({ r: r, k: k, d: Math.random() * 0.6, vx: (Math.random() - 0.5) * 4 }); } }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.imageSmoothingEnabled = false;
        cells.forEach(function (cell) {
          var fall = t > 0.9 && t < 2.2 ? Math.max(0, t - 0.9 - cell.d) : 0;
          var back = t >= 2.2 ? Math.max(0, 1 - Math.max(0, t - 2.2 - cell.d * 0.5) / 0.7) : 1;
          var drop = (t >= 2.2 ? Math.pow(Math.max(0, 1.3 - cell.d), 2) * 600 * back : Math.pow(fall, 2) * 600);
          var x = x0 + cell.k * cw + cell.vx * drop * 0.1, y = y0 + cell.r * ch + drop;
          if (ready) { g.drawImage(small, cell.k, cell.r, 1, 1, x, y, cw + 0.5, ch + 0.5); }
          else { g.fillStyle = (cell.r + cell.k) % 2 ? 'rgb(90 60 160)' : 'rgb(240 120 60)'; g.fillRect(x, y, cw, ch); }
        });
        if (t > 3.3) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.3) / 0.5)); }
        return t < 3.9;
      });
    },

    // The Incredibles: retro sixties title cards -- bold colour blocks and shapes slide in and
    // out, then the title.
    retro: function () {
      var c = curtain({ max: 5500, background: 'rgb(240 220 180)' });
      var palette = ['rgb(230 90 40)', 'rgb(200 40 40)', 'rgb(30 120 130)', 'rgb(250 190 60)', 'rgb(30 30 40)'];
      var deck = document.createElement('div');
      deck.className = 'sc-retro';
      c.el.appendChild(deck);
      for (var i = 0; i < 9; i++) {
        var block = document.createElement('span');
        block.className = 'sc-retro-block' + (i % 3 === 0 ? ' is-round' : '');
        block.style.background = palette[i % palette.length];
        block.style.left = (Math.random() * 80) + '%'; block.style.top = (Math.random() * 80) + '%';
        block.style.width = (10 + Math.random() * 30) + 'vmin'; block.style.height = (10 + Math.random() * 30) + 'vmin';
        deck.appendChild(block);
        if (block.animate) {
          var from = (i % 2 ? '-' : '') + '120vw 0';
          block.animate([{ translate: from }, { translate: '0 0', offset: 0.3 }, { translate: '0 0', offset: 0.75 }, { translate: (i % 2 ? '' : '-') + '120vw 0' }],
                        { duration: 3200, delay: i * 90, easing: 'cubic-bezier(.7, 0, .3, 1)', fill: 'both' });
        }
      }
      var title = text('p', 'sc-retro-title', page.short, c.el);
      title.style.color = 'rgb(240 220 180)'; title.style.background = 'rgb(200 40 40)';
      if (title.animate) { title.animate([{ scale: 0, rotate: '-8deg' }, { scale: 1.1, rotate: '-3deg', offset: 0.4 }, { scale: 1, rotate: '-3deg' }], { duration: 700, delay: 1300, easing: 'ease-out', fill: 'both' }); }
      window.setTimeout(c.finish, 4300);
    },

    // Despicable Me: a shrink ray zaps the page down to nothing, then it pops back to full size.
    // The page stays usable.
    shrink: function () {
      var c = curtain({ max: 5000, through: true });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var main = document.querySelector('main');
      if (main && main.animate) {
        main.animate([{ scale: 1 }, { scale: 1, offset: 0.25 }, { scale: 0.06, offset: 0.45 }, { scale: 0.06, offset: 0.65 }, { scale: 1.08, offset: 0.85 }, { scale: 1 }],
                     { duration: 3400, easing: 'ease-in-out' });
      }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var gunX = W * 0.04, gunY = H * 0.85;
        g.fillStyle = 'rgb(120 130 140)'; g.fillRect(gunX - 30, gunY - 14, 70, 28); g.fillStyle = 'rgb(80 200 240)'; g.beginPath(); g.arc(gunX + 46, gunY, 12, 0, Math.PI * 2); g.fill();
        if (t > 0.7 && t < 1.6) {
          var a = Math.random() * 0.4;
          g.strokeStyle = 'rgba(120, 220, 255, ' + (0.6 + a) + ')'; g.lineWidth = 6 + Math.random() * 6; g.shadowColor = 'rgb(120 220 255)'; g.shadowBlur = 20;
          g.beginPath(); g.moveTo(gunX + 50, gunY);
          for (var k = 1; k <= 10; k++) { g.lineTo(gunX + 50 + (W / 2 - gunX - 50) * k / 10 + (Math.random() - 0.5) * 20, gunY + (H / 2 - gunY) * k / 10 + (Math.random() - 0.5) * 20); }
          g.stroke(); g.shadowBlur = 0;
        }
        if (t > 2.1 && t < 2.5) {
          g.strokeStyle = 'rgba(255, 255, 255, ' + (1 - (t - 2.1) / 0.4) + ')'; g.lineWidth = 4;
          g.beginPath(); g.arc(W / 2, H / 2, (t - 2.1) * W, 0, Math.PI * 2); g.stroke();
        }
        return t < 3.6;
      });
    },

    // ---------------------------------------------------------------- 0.67.0

    // Beverly Hills Cop: a sunny palm-lined boulevard rushing past, police lights flashing behind.
    boulevard: function () {
      var c = curtain({ max: 5000, background: 'linear-gradient(to bottom, rgb(80 170 240), rgb(180 225 250))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var hz = H * 0.42, palms = [];
      for (var i = 0; i < 16; i++) { palms.push({ z: i / 16, side: i % 2 ? 1 : -1 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.fillStyle = 'rgb(120 190 110)'; g.fillRect(0, hz, W, H - hz);
        g.fillStyle = 'rgb(70 72 80)';
        g.beginPath(); g.moveTo(W / 2 - 20, hz); g.lineTo(W / 2 + 20, hz); g.lineTo(W * 0.95, H); g.lineTo(W * 0.05, H); g.closePath(); g.fill();
        g.fillStyle = 'rgb(250 220 90)';
        for (var d = 0; d < 12; d++) {
          var z = ((d / 12) + t * 0.9) % 1, z2 = z + 0.03;
          var y1 = hz + Math.pow(z, 2) * (H - hz), y2 = hz + Math.pow(Math.min(1, z2), 2) * (H - hz);
          g.fillRect(W / 2 - 2 - z * 6, y1, 4 + z * 12, y2 - y1);
        }
        palms.forEach(function (p) {
          var z = (p.z + t * 0.45) % 1, e = Math.pow(z, 2), x = W / 2 + p.side * (30 + e * W * 0.6), base = hz + e * (H - hz), h = 20 + e * H * 0.8;
          g.strokeStyle = 'rgb(110 80 50)'; g.lineWidth = 2 + e * 10;
          g.beginPath(); g.moveTo(x, base); g.quadraticCurveTo(x + p.side * h * 0.1, base - h * 0.5, x + p.side * h * 0.05, base - h); g.stroke();
          g.fillStyle = 'rgb(40 120 50)';
          for (var f = 0; f < 6; f++) { var a = -Math.PI / 2 + (f - 2.5) * 0.55; g.beginPath(); g.ellipse(x + p.side * h * 0.05 + Math.cos(a) * h * 0.2, base - h + Math.sin(a) * h * 0.08 + h * 0.06, h * 0.24, h * 0.05, a, 0, Math.PI * 2); g.fill(); }
        });
        var phase = Math.floor(t * 5) % 2;
        var lamp = g.createRadialGradient(phase ? W * 0.1 : W * 0.9, H, 0, phase ? W * 0.1 : W * 0.9, H, W * 0.5);
        lamp.addColorStop(0, phase ? 'rgba(255, 40, 40, 0.5)' : 'rgba(40, 90, 255, 0.5)'); lamp.addColorStop(1, 'rgba(0, 0, 0, 0)');
        g.fillStyle = lamp; g.fillRect(0, 0, W, H);
        if (t > 3.0) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.0) / 0.6)); }
        return t < 3.7;
      });
    },

    // Kill Bill: a stark yellow screen with the title in black; a katana stroke slices it in two
    // and the halves slide apart.
    katana: function () {
      var c = curtain({ max: 5000, background: 'rgb(250 210 30)' });
      var halves = [['polygon(0 0, 100% 0, 100% 42%, 0 58%)', '-3vw -4vh'], ['polygon(0 58%, 100% 42%, 100% 100%, 0 100%)', '3vw 4vh']].map(function (h) {
        var copy = text('p', 'sc-katana-title', page.short, c.el);
        copy.style.color = 'rgb(16 14 12)';
        copy.style.clipPath = h[0];
        return [copy, h[1]];
      });
      window.setTimeout(function () {
        var cut = document.createElement('span');
        cut.className = 'sc-slash';
        cut.style.background = 'rgb(200 20 20)';
        cut.style.rotate = '-2deg';   // along the line the title is cut on
        c.el.appendChild(cut);
        halves.forEach(function (h) { if (h[0].animate) { h[0].animate([{ translate: '-50% -50%' }, { translate: 'calc(-50% + ' + h[1].split(' ')[0] + ') calc(-50% + ' + h[1].split(' ')[1] + ')' }], { duration: 700, delay: 200, easing: 'ease-out', fill: 'forwards' }); } });
      }, 1300);
      window.setTimeout(c.finish, 3200);
    },

    // Taken: a city map zooming in, a pin dropping for each missing film, tracking them down.
    pinpoint: function () {
      var c = curtain({ max: 6000, background: 'rgb(10 12 16)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var streets = [];
      for (var i = 0; i < 70; i++) { var a = Math.random() * Math.PI; streets.push([Math.random() * W, Math.random() * H, Math.cos(a), Math.sin(a), 80 + Math.random() * 300]); }
      var targets = (page.missing.length ? page.missing : ['(nothing missing)']).slice(0, 5).map(function (title) { return { title: title, x: W * (0.2 + Math.random() * 0.6), y: H * (0.2 + Math.random() * 0.6) }; });
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var zoom = 1 + Math.min(1, t / 3) * 0.5;
        g.save(); g.translate(W / 2, H / 2); g.scale(zoom, zoom); g.translate(-W / 2, -H / 2);
        g.strokeStyle = 'rgba(120, 160, 190, 0.25)'; g.lineWidth = 1.5;
        streets.forEach(function (s) { g.beginPath(); g.moveTo(s[0] - s[2] * s[4], s[1] - s[3] * s[4]); g.lineTo(s[0] + s[2] * s[4], s[1] + s[3] * s[4]); g.stroke(); });
        g.fillStyle = 'rgba(40, 80, 120, 0.25)'; g.beginPath(); g.ellipse(W * 0.5, H * 0.6, W * 0.4, H * 0.06, 0.2, 0, Math.PI * 2); g.fill();
        g.restore();
        targets.forEach(function (p, i) {
          var at = 0.6 + i * 0.6;
          if (t < at) { return; }
          var drop = Math.min(1, (t - at) / 0.25), x = W / 2 + (p.x - W / 2) * zoom, y = H / 2 + (p.y - H / 2) * zoom - (1 - drop) * 60;
          g.strokeStyle = 'rgba(255, 60, 50, ' + Math.max(0, 1 - ((t - at) % 1)) + ')'; g.lineWidth = 2;
          g.beginPath(); g.arc(x, y, ((t - at) % 1) * 40, 0, Math.PI * 2); g.stroke();
          g.fillStyle = 'rgb(255 60 50)'; g.beginPath(); g.arc(x, y - 14, 8, 0, Math.PI * 2); g.fill();
          g.beginPath(); g.moveTo(x - 6, y - 10); g.lineTo(x + 6, y - 10); g.lineTo(x, y); g.closePath(); g.fill();
          g.fillStyle = 'rgb(230 235 240)'; g.font = '600 14px ui-monospace, monospace'; g.textAlign = 'left';
          g.fillText(p.title, x + 14, y - 10);
        });
        if (t > 4.0) { c.el.style.opacity = String(Math.max(0, 1 - (t - 4.0) / 0.6)); }
        return t < 4.7;
      });
    },

    // The Expendables: a wall of fire, and a row of silhouettes walking out of it toward you --
    // one for each film you own.
    firewalk: function () {
      var c = curtain({ max: 5500, background: 'black' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var crew = Math.max(3, Math.min(7, parseInt(page.have, 10) || 5)), flames = [];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        for (var f = 0; f < 40; f++) { flames.push({ x: Math.random() * W, y: H * 0.75, v: 3 + Math.random() * 5, life: 1, r: 20 + Math.random() * 40 }); }
        flames.forEach(function (p) {
          p.y -= p.v; p.life -= 0.02; p.r *= 0.99;
          if (p.life > 0) {
            var fire = g.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r);
            fire.addColorStop(0, 'rgba(255, 220, 120, ' + p.life * 0.7 + ')'); fire.addColorStop(0.5, 'rgba(255, 110, 20, ' + p.life * 0.5 + ')'); fire.addColorStop(1, 'rgba(120, 20, 0, 0)');
            g.fillStyle = fire; g.fillRect(p.x - p.r, p.y - p.r, p.r * 2, p.r * 2);
          }
        });
        flames = flames.filter(function (p) { return p.life > 0; });
        var walk = Math.min(1, t / 3.2), s = H * (0.18 + walk * 0.35), base = H * (0.78 + walk * 0.18);
        for (var k = 0; k < crew; k++) {
          var x = W / 2 + (k - (crew - 1) / 2) * s * 0.55, sway = Math.sin(t * 6 + k) * s * 0.04;
          g.fillStyle = 'rgb(6 4 4)';
          g.beginPath(); g.arc(x, base - s * 0.92, s * 0.08, 0, Math.PI * 2); g.fill();
          g.beginPath(); g.moveTo(x - s * 0.17, base - s * 0.8); g.lineTo(x + s * 0.17, base - s * 0.8); g.lineTo(x + s * 0.12, base - s * 0.42); g.lineTo(x - s * 0.12, base - s * 0.42); g.closePath(); g.fill();
          g.fillRect(x - s * 0.1 + sway, base - s * 0.42, s * 0.08, s * 0.42); g.fillRect(x + s * 0.02 - sway, base - s * 0.42, s * 0.08, s * 0.42);
        }
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.6)); }
        return t < 4.3;
      });
    },

    // Austin Powers: a psychedelic sixties swirl -- bands of colour and flowers spinning out from
    // the middle.
    groovy: function () {
      var c = curtain({ max: 5000, background: 'rgb(250 230 90)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var palette = ['rgb(240 60 140)', 'rgb(250 150 30)', 'rgb(60 200 120)', 'rgb(80 120 240)', 'rgb(250 230 90)', 'rgb(160 70 200)'];
      var flowers = [];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var cx = W / 2, cy = H / 2, R = Math.hypot(W, H) * 0.6, spin = t * 1.8;
        for (var b = 0; b < 24; b++) {
          g.fillStyle = palette[b % palette.length];
          g.beginPath(); g.moveTo(cx, cy);
          for (var s = 0; s <= 20; s++) { var q = s / 20, a = spin + b / 24 * Math.PI * 2 + q * 2.2; g.lineTo(cx + Math.cos(a) * R * q, cy + Math.sin(a) * R * q); }
          for (var s2 = 20; s2 >= 0; s2--) { var q2 = s2 / 20, a2 = spin + (b + 1) / 24 * Math.PI * 2 + q2 * 2.2; g.lineTo(cx + Math.cos(a2) * R * q2, cy + Math.sin(a2) * R * q2); }
          g.closePath(); g.fill();
        }
        if (Math.random() < 0.4) { flowers.push({ a: Math.random() * Math.PI * 2, d: 0, c: palette[Math.floor(Math.random() * 6)] }); }
        flowers.forEach(function (f) {
          f.d += 6; var x = cx + Math.cos(f.a) * f.d, y = cy + Math.sin(f.a) * f.d, r = 6 + f.d * 0.05;
          g.fillStyle = 'rgb(255 255 255)';
          for (var p = 0; p < 5; p++) { var pa = p / 5 * Math.PI * 2 + t * 3; g.beginPath(); g.arc(x + Math.cos(pa) * r, y + Math.sin(pa) * r, r * 0.7, 0, Math.PI * 2); g.fill(); }
          g.fillStyle = f.c; g.beginPath(); g.arc(x, y, r * 0.6, 0, Math.PI * 2); g.fill();
        });
        if (t > 3.0) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.0) / 0.6)); }
        return t < 3.7;
      });
    },

    // The Mask: a green whirlwind spins across the screen and stops dead with a cartoon pop.
    // The page stays usable.
    whirlwind: function () {
      var c = curtain({ max: 4500, through: true });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var bits = [];
      for (var i = 0; i < 400; i++) { bits.push({ a: Math.random() * Math.PI * 2, h: Math.random(), s: 2 + Math.random() * 4 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var go = Math.min(1, t / 2.0), cx = -W * 0.2 + go * W * 0.7, stopped = t > 2.1;
        if (!stopped) {
          bits.forEach(function (b) {
            var r = 30 + (1 - b.h) * 140, a = b.a + t * 12;
            g.fillStyle = 'rgba(' + Math.round(60 + Math.random() * 60) + ', 210, 60, 0.85)';
            g.fillRect(cx + Math.cos(a) * r, H * 0.1 + b.h * H * 0.8 + Math.sin(a) * r * 0.15, b.s, b.s);
          });
        } else if (t < 3.1) {
          var pop = Math.min(1, (t - 2.1) / 0.2), fade = t > 2.6 ? Math.max(0, 1 - (t - 2.6) / 0.5) : 1, cy = H / 2, R = Math.min(W, H) * 0.3 * pop;
          g.fillStyle = 'rgba(255, 230, 40, ' + fade + ')'; g.strokeStyle = 'rgba(20, 20, 20, ' + fade + ')'; g.lineWidth = 5;
          g.beginPath();
          for (var k = 0; k < 24; k++) { var a = k / 24 * Math.PI * 2, rr = k % 2 ? R * 0.6 : R; if (!k) { g.moveTo(W / 2 + Math.cos(a) * rr, cy + Math.sin(a) * rr); } else { g.lineTo(W / 2 + Math.cos(a) * rr, cy + Math.sin(a) * rr); } }
          g.closePath(); g.fill(); g.stroke();
          g.fillStyle = 'rgba(40, 170, 50, ' + fade + ')'; g.font = '900 ' + Math.round(R * 0.32) + 'px Impact, system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
          g.fillText('POP!', W / 2, cy);
        }
        return t < 3.2;
      });
    },

    // Zombieland: survival rules stamped on screen one at a time, in this library's own terms.
    rules: function () {
      var c = curtain({ max: 7000, background: 'linear-gradient(to bottom, rgb(40 46 36), rgb(18 20 16))' });
      var n = page.missing.length;
      var stack = document.createElement('div');
      stack.className = 'sc-rules';
      c.el.appendChild(stack);
      [['#1', 'Check the missing list.'], ['#2', 'Double-tap the Add button.'],
       ['#3', page.total ? 'Enjoy the little things — like owning ' + page.have + ' of ' + page.total + '.' : 'Enjoy the little things.'],
       ['#4', n ? 'Never leave ' + plural(n, 'film') + ' behind.' : 'Leave no film behind. (You didn’t.)']].forEach(function (rule, i) {
        window.setTimeout(function () {
          var line = document.createElement('p');
          line.className = 'sc-rule';
          line.style.color = 'rgb(240 236 220)';
          var num = text('span', 'sc-rule-num', 'Rule ' + rule[0] + ' ', line);
          num.style.color = 'rgb(220 50 40)';
          line.appendChild(document.createTextNode(rule[1]));
          stack.appendChild(line);
          if (line.animate) { line.animate([{ scale: 2.2, opacity: 0 }, { scale: 1, opacity: 1 }], { duration: 260, easing: 'cubic-bezier(.3, 1.4, .6, 1)', fill: 'both' }); }
          shakePage(3, 160);
        }, 300 + i * 1000);
      });
      window.setTimeout(c.finish, 5600);
    },

    // Hotel Transylvania: bats swirling round a spooky castle hotel at night, its windows lighting
    // up one by one.
    bats: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(30 20 60), rgb(70 40 90))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, base = H * 0.92, flock = [], windows = [];
      for (var i = 0; i < 26; i++) { flock.push({ a: Math.random() * Math.PI * 2, r: W * (0.15 + Math.random() * 0.25), h: H * (0.15 + Math.random() * 0.4), v: 1 + Math.random() * 1.5, s: 8 + Math.random() * 10 }); }
      for (var w = 0; w < 18; w++) { windows.push({ x: cx + (Math.random() - 0.5) * W * 0.3, y: base - Math.random() * H * 0.45, at: Math.random() * 2.5 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.fillStyle = 'rgba(240, 235, 210, 0.95)'; g.beginPath(); g.arc(W * 0.78, H * 0.2, Math.min(W, H) * 0.08, 0, Math.PI * 2); g.fill();
        g.fillStyle = 'rgb(16 10 26)';
        [[-0.18, 0.3, 0.05], [-0.08, 0.5, 0.07], [0, 0.6, 0.09], [0.1, 0.45, 0.07], [0.19, 0.32, 0.05]].forEach(function (tw) {
          var x = cx + tw[0] * W, h = tw[1] * H, w2 = tw[2] * W;
          g.fillRect(x - w2 / 2, base - h, w2, h);
          g.beginPath(); g.moveTo(x - w2 * 0.65, base - h); g.lineTo(x, base - h - w2 * 1.4); g.lineTo(x + w2 * 0.65, base - h); g.closePath(); g.fill();
        });
        g.fillRect(cx - W * 0.22, base - H * 0.25, W * 0.44, H * 0.25);
        windows.forEach(function (wn) { if (t > wn.at) { g.fillStyle = 'rgba(255, 210, 110, 0.9)'; g.fillRect(wn.x - 4, wn.y - 6, 8, 12); } });
        flock.forEach(function (b) {
          var a = b.a + t * b.v, x = cx + Math.cos(a) * b.r, y = H * 0.25 + Math.sin(a) * b.r * 0.25 + b.h * 0.3, flap = Math.sin(t * 18 + b.a) * b.s * 0.6;
          g.fillStyle = 'rgb(10 6 16)';
          g.beginPath(); g.moveTo(x, y); g.quadraticCurveTo(x - b.s * 0.6, y - flap, x - b.s, y + 2); g.quadraticCurveTo(x - b.s * 0.5, y + 1, x, y + 3);
          g.quadraticCurveTo(x + b.s * 0.5, y + 1, x + b.s, y + 2); g.quadraticCurveTo(x + b.s * 0.6, y - flap, x, y); g.fill();
        });
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.6)); }
        return t < 4.3;
      });
    },

    // Tomb Raider: a torch-lit tomb floor whose stone tiles crack and fall away one by one,
    // leaving the page beneath.
    tomb: function () {
      var c = curtain({ max: 5500, background: 'transparent' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var size = Math.max(70, Math.min(W, H) / 7), tiles = [];
      for (var y = 0; y < H; y += size) { for (var x = 0; x < W; x += size) { tiles.push({ x: x, y: y, at: 1.0 + Math.random() * 2.2, shade: 80 + Math.random() * 40 }); } }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        tiles.forEach(function (tl) {
          var fall = Math.max(0, t - tl.at);
          if (fall > 0.6) { return; }
          var s = size * (1 - fall / 0.6), off = (size - s) / 2, d = Math.round(tl.shade * (1 - fall));
          g.fillStyle = 'rgb(' + d + ' ' + Math.round(d * 0.8) + ' ' + Math.round(d * 0.6) + ')';
          g.fillRect(tl.x + off + 2, tl.y + off + 2, s - 4, s - 4);
          if (t > tl.at - 0.5 && fall === 0) {
            g.strokeStyle = 'rgba(30, 20, 10, 0.8)'; g.lineWidth = 2;
            g.beginPath(); g.moveTo(tl.x + size * 0.2, tl.y + size * 0.3); g.lineTo(tl.x + size * 0.5, tl.y + size * 0.55); g.lineTo(tl.x + size * 0.8, tl.y + size * 0.4); g.stroke();
          }
        });
        var flick = 0.85 + Math.random() * 0.15;
        var torch = g.createRadialGradient(W * 0.15, H * 0.2, 0, W * 0.15, H * 0.2, Math.max(W, H) * 0.9);
        torch.addColorStop(0, 'rgba(255, 170, 70, ' + 0.35 * flick + ')'); torch.addColorStop(0.5, 'rgba(60, 30, 10, 0.2)'); torch.addColorStop(1, 'rgba(0, 0, 0, 0.55)');
        g.fillStyle = torch; g.fillRect(0, 0, W, H);
        return t < 3.9;
      });
    },

    // Pacific Rim: rain over a dark sea; a giant robot's silhouette rises, and its chest lights up.
    mech: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(14 20 30), rgb(26 36 50))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var drops = [];
      for (var i = 0; i < 320; i++) { drops.push({ x: Math.random() * W, y: Math.random() * H, v: 14 + Math.random() * 10 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var rise = Math.min(1, t / 2.2), cx = W / 2, s = H * 0.5, top = H * 0.95 - rise * s * 1.15;
        g.fillStyle = 'rgb(8 12 18)';
        g.beginPath(); g.moveTo(cx - s * 0.12, top); g.lineTo(cx + s * 0.12, top); g.lineTo(cx + s * 0.1, top + s * 0.14); g.lineTo(cx - s * 0.1, top + s * 0.14); g.closePath(); g.fill();
        g.beginPath(); g.moveTo(cx - s * 0.5, top + s * 0.2); g.lineTo(cx + s * 0.5, top + s * 0.2); g.lineTo(cx + s * 0.32, top + s * 0.75); g.lineTo(cx - s * 0.32, top + s * 0.75); g.closePath(); g.fill();
        g.fillRect(cx - s * 0.62, top + s * 0.2, s * 0.16, s * 0.6); g.fillRect(cx + s * 0.46, top + s * 0.2, s * 0.16, s * 0.6);
        g.fillRect(cx - s * 0.25, top + s * 0.75, s * 0.18, s * 0.6); g.fillRect(cx + s * 0.07, top + s * 0.75, s * 0.18, s * 0.6);
        g.fillStyle = 'rgba(120, 200, 255, ' + (0.4 + rise * 0.4) + ')'; g.fillRect(cx - s * 0.08, top + s * 0.05, s * 0.16, s * 0.025);
        if (t > 2.3) {
          var glow = Math.min(1, (t - 2.3) / 0.4);
          var core = g.createRadialGradient(cx, top + s * 0.38, 0, cx, top + s * 0.38, s * 0.5 * glow);
          core.addColorStop(0, 'rgba(160, 230, 255, 0.95)'); core.addColorStop(0.2, 'rgba(80, 180, 255, 0.6)'); core.addColorStop(1, 'rgba(80, 180, 255, 0)');
          g.fillStyle = core; g.fillRect(0, 0, W, H);
        }
        g.fillStyle = 'rgba(20, 40, 60, 0.95)';
        g.beginPath(); g.moveTo(0, H);
        for (var x = 0; x <= W; x += 20) { g.lineTo(x, H * 0.86 + Math.sin(x / 60 + t * 2) * 8); }
        g.lineTo(W, H); g.closePath(); g.fill();
        g.strokeStyle = 'rgba(160, 190, 220, 0.35)'; g.lineWidth = 1; g.beginPath();
        drops.forEach(function (d) { d.y += d.v; d.x -= 3; if (d.y > H) { d.y = -20; d.x = Math.random() * W * 1.2; } g.moveTo(d.x, d.y); g.lineTo(d.x + 3, d.y - 14); });
        g.stroke();
        if (t > 1.2 && t < 1.3) { g.fillStyle = 'rgba(220, 230, 255, 0.5)'; g.fillRect(0, 0, W, H); }
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.6)); }
        return t < 4.3;
      });
    },

    // National Treasure: an old map warms, and hidden writing appears on it -- the missing films,
    // as clues.
    cipher: function () {
      var c = curtain({ max: 7000, background: 'rgb(222 200 160)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var clues = (page.missing.length ? page.missing.slice(0, 5) : ['Every film is accounted for']).map(function (title, i) {
        return { words: title, x: W * (0.2 + (i % 2) * 0.35 + Math.random() * 0.1), y: H * (0.22 + i * 0.13) };
      });
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgba(110, 80, 40, 0.5)'; g.lineWidth = 2;
        g.beginPath(); g.moveTo(W * 0.05, H * 0.6);
        for (var x = W * 0.05; x < W * 0.95; x += 30) { g.lineTo(x, H * 0.6 + Math.sin(x / 70) * 30 + Math.sin(x / 23) * 8); }
        g.stroke();
        var rx = W * 0.85, ry = H * 0.78, rr = Math.min(W, H) * 0.08;
        g.beginPath(); for (var k = 0; k < 8; k++) { var a = k / 8 * Math.PI * 2; g.moveTo(rx, ry); g.lineTo(rx + Math.cos(a) * rr * (k % 2 ? 0.5 : 1), ry + Math.sin(a) * rr * (k % 2 ? 0.5 : 1)); } g.stroke();
        var hx = W * (-0.1 + Math.min(1.2, t / 3) * 1.1), hy = H * 0.45 + Math.sin(t * 2) * H * 0.2;
        var heat = g.createRadialGradient(hx, hy, 0, hx, hy, Math.min(W, H) * 0.35);
        heat.addColorStop(0, 'rgba(255, 150, 40, 0.35)'); heat.addColorStop(1, 'rgba(255, 150, 40, 0)');
        g.fillStyle = heat; g.fillRect(0, 0, W, H);
        g.font = 'italic 600 ' + Math.round(Math.min(W, H) * 0.03) + 'px Georgia, serif'; g.textAlign = 'left';
        clues.forEach(function (cl) {
          cl.seen = Math.max(cl.seen || 0, Math.max(0, 1 - Math.abs(hx - cl.x - 80) / (W * 0.25)));
          g.fillStyle = 'rgba(100, 50, 20, ' + cl.seen + ')';
          g.fillText(cl.words, cl.x, cl.y);
        });
        if (t > 4.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 4.6) / 0.6)); }
        return t < 5.3;
      });
    },

    // Sherlock Holmes: a magnifying glass sweeps a foggy gaslit street, noting clues about the
    // collection.
    magnifier: function () {
      var c = curtain({ max: 6500, background: 'linear-gradient(to bottom, rgb(40 44 48), rgb(70 72 70))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var n = page.missing.length;
      var notes = [page.total ? 'Owned: ' + page.have + ' of ' + page.total : 'A collection, much loved', n ? 'Missing: ' + n : 'Missing: none', n ? 'Conclusion: a trip to Radarr' : 'Conclusion: elementary'];
      var scene = function (sharp) {
        g.fillStyle = sharp ? 'rgb(60 50 44)' : 'rgba(30, 30, 30, 0.6)';
        for (var b = 0; b < 6; b++) { g.fillRect(b * W / 6 + 10, H * (0.25 + (b % 3) * 0.05), W / 6 - 20, H); }
        for (var l = 0; l < 3; l++) {
          var lx = W * (0.2 + l * 0.3);
          g.fillStyle = sharp ? 'rgb(30 30 30)' : 'rgba(20, 20, 20, 0.7)'; g.fillRect(lx - 3, H * 0.45, 6, H * 0.4);
          g.fillStyle = sharp ? 'rgba(255, 220, 140, 0.95)' : 'rgba(255, 220, 140, 0.4)'; g.beginPath(); g.arc(lx, H * 0.44, 10, 0, Math.PI * 2); g.fill();
        }
        g.fillStyle = sharp ? 'rgb(90 86 80)' : 'rgba(60, 60, 60, 0.6)'; g.fillRect(0, H * 0.85, W, H * 0.15);
      };
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        scene(false);
        g.fillStyle = 'rgba(180, 185, 190, 0.25)'; g.fillRect(0, 0, W, H);
        var mx = W * (0.15 + Math.min(1, t / 3.6) * 0.7), my = H * 0.5 + Math.sin(t * 1.7) * H * 0.15, R = Math.min(W, H) * 0.14;
        g.save(); g.beginPath(); g.arc(mx, my, R, 0, Math.PI * 2); g.clip(); g.fillStyle = 'rgb(70 70 74)'; g.fillRect(0, 0, W, H); scene(true); g.restore();
        g.strokeStyle = 'rgb(160 120 60)'; g.lineWidth = 8; g.beginPath(); g.arc(mx, my, R, 0, Math.PI * 2); g.stroke();
        g.strokeStyle = 'rgb(70 40 20)'; g.lineWidth = 14; g.beginPath(); g.moveTo(mx + R * 0.7, my + R * 0.7); g.lineTo(mx + R * 1.5, my + R * 1.5); g.stroke();
        g.fillStyle = 'rgb(240 230 210)'; g.font = 'italic 600 ' + Math.round(Math.min(W, H) * 0.028) + 'px Georgia, serif'; g.textAlign = 'left';
        notes.forEach(function (note, i) { if (t > 0.8 + i * 1.1) { g.fillText(note, W * 0.06, H * (0.12 + i * 0.06)); } });
        if (t > 4.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 4.6) / 0.6)); }
        return t < 5.3;
      });
    },

    // Knives Out: a sunburst ring of knives turns slowly; one is drawn out, and the ring falls
    // apart.
    knives: function () {
      var c = curtain({ max: 5500, background: 'radial-gradient(circle at 50% 50%, rgb(60 40 30), rgb(20 14 10))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H / 2, R = Math.min(W, H) * 0.34, count = 18, knives = [];
      for (var i = 0; i < count; i++) { knives.push({ a: i / count * Math.PI * 2, vx: 0, vy: 0, x: 0, y: 0, spin: 0 }); }
      var knife = function (len) {
        g.fillStyle = 'rgb(200 205 215)'; g.beginPath(); g.moveTo(0, 0); g.lineTo(len * 0.62, -len * 0.05); g.lineTo(len * 0.62, len * 0.05); g.closePath(); g.fill();
        g.fillStyle = 'rgb(40 30 24)'; g.fillRect(len * 0.62, -len * 0.045, len * 0.38, len * 0.09);
      };
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var turn = t * 0.25, fallen = t > 2.5;
        knives.forEach(function (k, i) {
          var a = k.a + turn, pull = i === 0 ? Math.min(1, Math.max(0, (t - 1.8) / 0.6)) * R * 0.8 : 0;
          if (fallen && i) { if (!k.vy) { k.vy = -2 - Math.random() * 3; k.vx = (Math.random() - 0.5) * 4; } k.vy += 0.5; k.x += k.vx; k.y += k.vy; k.spin += 0.08; }
          g.save(); g.translate(cx + Math.cos(a) * (R * 0.35 + pull) + k.x, cy + Math.sin(a) * (R * 0.35 + pull) + k.y); g.rotate(a + k.spin);
          knife(R * 0.75);
          g.restore();
        });
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.6)); }
        return t < 4.3;
      });
    },

    // Teenage Mutant Ninja Turtles: sewer pipes, and four coloured masks flashing past one after
    // another.
    masks: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(20 34 26), rgb(10 18 14))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var colours = ['rgb(40 110 230)', 'rgb(220 40 40)', 'rgb(150 70 200)', 'rgb(250 140 30)'], drips = [];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgb(50 70 56)'; g.lineWidth = 30;
        [[0, H * 0.18, W, H * 0.22], [W * 0.15, 0, W * 0.12, H], [W * 0.85, 0, W * 0.88, H]].forEach(function (p) { g.beginPath(); g.moveTo(p[0], p[1]); g.lineTo(p[2], p[3]); g.stroke(); });
        if (Math.random() < 0.3) { drips.push({ x: Math.random() * W, y: H * 0.2, v: 2 }); }
        g.fillStyle = 'rgba(140, 200, 120, 0.7)';
        drips.forEach(function (d) { d.v += 0.3; d.y += d.v; g.fillRect(d.x, d.y, 2, 6); });
        colours.forEach(function (col, i) {
          var at = 0.4 + i * 0.6, q = Math.min(1, Math.max(0, (t - at) / 0.45)), settle = 1 - Math.pow(1 - q, 3);
          if (q <= 0) { return; }
          var y = H * (0.3 + i * 0.13), x = -W * 0.6 + settle * W * 1.1, w = W * 0.5, h = H * 0.09;
          g.fillStyle = col;
          g.beginPath(); g.moveTo(x - w / 2, y - h / 2); g.lineTo(x + w / 2, y - h / 2); g.lineTo(x + w / 2 + h * 0.8, y + h * 0.8); g.lineTo(x + w / 2 + h * 0.4, y + h); g.lineTo(x + w / 2, y + h / 2); g.lineTo(x - w / 2, y + h / 2); g.closePath(); g.fill();
          g.fillStyle = 'rgb(255 255 255)';
          g.beginPath(); g.ellipse(x - w * 0.12, y, h * 0.32, h * 0.22, 0.15, 0, Math.PI * 2); g.ellipse(x + w * 0.12, y, h * 0.32, h * 0.22, -0.15, 0, Math.PI * 2); g.fill();
        });
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.6)); }
        return t < 4.3;
      });
    },

    // Sonic the Hedgehog: a blue streak loops around the screen collecting gold rings, then zooms
    // off.
    rings: function () {
      var c = curtain({ max: 5000, background: 'linear-gradient(to bottom, rgb(60 140 240), rgb(150 210 250))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var path = function (q) {
        if (q < 0.35) { return [W * 0.05 + q / 0.35 * W * 0.4, H * 0.72]; }
        if (q < 0.75) { var a = (q - 0.35) / 0.4 * Math.PI * 2; return [W * 0.5 + Math.sin(a) * H * 0.22, H * 0.5 + Math.cos(a) * H * 0.22]; }
        return [W * 0.5 + (q - 0.75) / 0.25 * W * 0.7, H * 0.72];
      };
      var rings = [];
      for (var i = 0; i < 20; i++) { var q = 0.05 + i / 20 * 0.85, p = path(q); rings.push({ q: q, x: p[0], y: p[1] - 24, got: false }); }
      var counter = text('p', 'sc-hud sc-hud--left', 'RINGS 0', c.el);
      counter.style.color = 'rgb(255 220 60)';
      var got = 0;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        for (var x = 0; x < W; x += 40) { g.fillStyle = (Math.floor(x / 40) % 2) ? 'rgb(60 160 60)' : 'rgb(80 190 70)'; g.fillRect(x, H * 0.78, 40, H * 0.22); }
        g.fillStyle = 'rgb(150 100 50)'; g.fillRect(0, H * 0.86, W, H * 0.14);
        var at = Math.min(1, t / 2.6), me = path(at);
        rings.forEach(function (r) {
          if (!r.got && r.q <= at) { r.got = true; got++; }
          if (r.got) { return; }
          var wide = Math.abs(Math.cos(t * 6 + r.q * 10));
          g.strokeStyle = 'rgb(255 210 40)'; g.lineWidth = 4; g.beginPath(); g.ellipse(r.x, r.y, 10 * Math.max(0.15, wide), 10, 0, 0, Math.PI * 2); g.stroke();
        });
        counter.textContent = 'RINGS ' + got;
        for (var k = 0; k < 8; k++) { var tq = Math.max(0, at - k * 0.015), tp = path(tq); g.fillStyle = 'rgba(40, 90, 230, ' + (0.6 - k * 0.07) + ')'; g.beginPath(); g.arc(tp[0], tp[1] - 20, 18 - k, 0, Math.PI * 2); g.fill(); }
        g.fillStyle = 'rgb(30 80 220)'; g.beginPath(); g.arc(me[0], me[1] - 20, 18, 0, Math.PI * 2); g.fill();
        if (t > 3.0) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.0) / 0.6)); }
        return t < 3.7;
      });
    },

    // ---------------------------------------------------------------- 0.68.0

    // It: rain on a dark street, and a single red balloon floating up out of a storm drain.
    balloon: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(30 34 38), rgb(14 16 18))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var drops = [];
      for (var i = 0; i < 300; i++) { drops.push({ x: Math.random() * W, y: Math.random() * H, v: 12 + Math.random() * 8 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.fillStyle = 'rgb(40 42 44)'; g.fillRect(0, H * 0.8, W, H * 0.2);
        g.fillStyle = 'rgb(70 72 74)'; g.fillRect(0, H * 0.79, W, 8);
        var dx = W * 0.5;
        g.fillStyle = 'rgb(6 6 8)'; g.fillRect(dx - W * 0.08, H * 0.8, W * 0.16, H * 0.05);
        g.strokeStyle = 'rgb(60 60 62)'; g.lineWidth = 3;
        for (var b = 0; b < 6; b++) { g.beginPath(); g.moveTo(dx - W * 0.07 + b * W * 0.028, H * 0.8); g.lineTo(dx - W * 0.07 + b * W * 0.028, H * 0.85); g.stroke(); }
        var rise = Math.min(1, Math.max(0, (t - 0.8) / 2.4)), bx = dx + Math.sin(t * 1.5) * 30, by = H * 0.82 - rise * H * 0.55, r = Math.min(W, H) * (0.05 + rise * 0.03);
        if (t > 0.8) {
          g.strokeStyle = 'rgba(230, 230, 230, 0.7)'; g.lineWidth = 1.5;
          g.beginPath(); g.moveTo(bx, by + r * 1.2); g.quadraticCurveTo(bx + 20, by + r * 3, bx - 10, by + r * 5); g.stroke();
          var red = g.createRadialGradient(bx - r * 0.35, by - r * 0.4, r * 0.1, bx, by, r * 1.2);
          red.addColorStop(0, 'rgb(255 120 110)'); red.addColorStop(0.4, 'rgb(210 20 20)'); red.addColorStop(1, 'rgb(110 0 0)');
          g.fillStyle = red; g.beginPath(); g.ellipse(bx, by, r, r * 1.2, 0, 0, Math.PI * 2); g.fill();
          g.fillStyle = 'rgb(150 0 0)'; g.beginPath(); g.moveTo(bx - 5, by + r * 1.2 + 6); g.lineTo(bx + 5, by + r * 1.2 + 6); g.lineTo(bx, by + r * 1.15); g.closePath(); g.fill();
        }
        g.strokeStyle = 'rgba(170, 180, 190, 0.35)'; g.lineWidth = 1; g.beginPath();
        drops.forEach(function (d) { d.y += d.v; if (d.y > H) { d.y = -20; d.x = Math.random() * W; } g.moveTo(d.x, d.y); g.lineTo(d.x - 2, d.y - 14); });
        g.stroke();
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.6)); }
        return t < 4.3;
      });
    },

    // Evil Dead: the camera rushes low and fast through dark woods to a lone cabin, whose door
    // bursts open.
    cabin: function () {
      var c = curtain({ max: 5500, background: 'rgb(8 10 8)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var trees = [];
      for (var i = 0; i < 40; i++) { trees.push({ x: (Math.random() - 0.5) * 2, z: Math.random() }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var hz = H * 0.5, rush = Math.min(1, t / 2.6);
        g.fillStyle = 'rgba(30, 40, 30, 0.5)'; g.fillRect(0, hz, W, H - hz);
        var cz = 0.08 + rush * 0.85, cs = cz * Math.min(W, H) * 0.9, cx = W / 2, cy = hz + cz * H * 0.2;
        g.fillStyle = 'rgb(30 22 16)'; g.fillRect(cx - cs * 0.6, cy - cs * 0.5, cs * 1.2, cs * 0.5);
        g.beginPath(); g.moveTo(cx - cs * 0.7, cy - cs * 0.5); g.lineTo(cx, cy - cs * 0.85); g.lineTo(cx + cs * 0.7, cy - cs * 0.5); g.closePath(); g.fill();
        var open = t > 2.6 ? Math.min(1, (t - 2.6) / 0.15) : 0;
        g.fillStyle = 'rgba(255, 200, 120, ' + (0.4 + open * 0.6) + ')'; g.fillRect(cx - cs * 0.42, cy - cs * 0.38, cs * 0.16, cs * 0.12);
        g.fillStyle = open ? 'rgb(255 240 200)' : 'rgb(50 36 24)'; g.fillRect(cx - cs * 0.08, cy - cs * 0.32, cs * 0.16, cs * 0.32);
        trees.forEach(function (tr) {
          var z = (tr.z + t * 0.6) % 1, s = 1 / (1.2 - z), x = W / 2 + tr.x * W * 0.5 * s, w = 6 * s;
          if (Math.abs(x - W / 2) < cs * 0.8 && z > 0.6) { return; }
          g.fillStyle = 'rgba(14, 18, 14, ' + Math.min(1, z * 1.5) + ')'; g.fillRect(x - w / 2, 0, w, H);
        });
        if (open) { g.fillStyle = 'rgba(255, 245, 220, ' + Math.min(0.9, (t - 2.6) * 2) + ')'; g.fillRect(0, 0, W, H); }
        if (t > 3.2) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.2) / 0.5)); }
        return t < 3.8;
      });
    },

    // Beetlejuice: black-and-white stripes swirl into a spiral, a little model town spinning in
    // the middle.
    stripes: function () {
      var c = curtain({ max: 5000, background: 'rgb(240 240 236)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var cx = W / 2, cy = H / 2, R = Math.hypot(W, H) * 0.6, spin = t * 1.4;
        g.fillStyle = 'rgb(18 18 20)';
        for (var b = 0; b < 16; b += 2) {
          g.beginPath(); g.moveTo(cx, cy);
          for (var s = 0; s <= 24; s++) { var q = s / 24, a = spin + b / 16 * Math.PI * 2 + q * 3.4; g.lineTo(cx + Math.cos(a) * R * q, cy + Math.sin(a) * R * q); }
          for (var s2 = 24; s2 >= 0; s2--) { var q2 = s2 / 24, a2 = spin + (b + 1) / 16 * Math.PI * 2 + q2 * 3.4; g.lineTo(cx + Math.cos(a2) * R * q2, cy + Math.sin(a2) * R * q2); }
          g.closePath(); g.fill();
        }
        var r = Math.min(W, H) * 0.14;
        g.save(); g.translate(cx, cy); g.rotate(-t * 0.8);
        g.fillStyle = 'rgb(110 160 80)'; g.beginPath(); g.arc(0, 0, r, 0, Math.PI * 2); g.fill();
        [[-0.5, -0.2, 0.3], [0.1, -0.45, 0.25], [0.35, 0.15, 0.28], [-0.25, 0.35, 0.22]].forEach(function (hs, i) {
          g.fillStyle = i % 2 ? 'rgb(230 220 200)' : 'rgb(200 120 90)';
          g.fillRect(hs[0] * r, hs[1] * r, hs[2] * r, hs[2] * r * 0.8);
          g.fillStyle = 'rgb(90 40 40)'; g.beginPath(); g.moveTo(hs[0] * r - 2, hs[1] * r); g.lineTo(hs[0] * r + hs[2] * r / 2, hs[1] * r - hs[2] * r * 0.5); g.lineTo(hs[0] * r + hs[2] * r + 2, hs[1] * r); g.closePath(); g.fill();
        });
        g.restore();
        if (t > 3.0) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.0) / 0.6)); }
        return t < 3.7;
      });
    },

    // Hocus Pocus: a black-flame candle lights, green fog rolls, and three witches on brooms
    // cross a full moon.
    witches: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(20 16 40), rgb(40 30 60))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var fog = [];
      for (var i = 0; i < 10; i++) { fog.push({ x: Math.random() * W, y: H * (0.7 + Math.random() * 0.3), r: 120 + Math.random() * 120, v: 0.4 + Math.random() * 0.6 }); }
      var witch = function (x, y, s) {
        g.fillStyle = 'rgb(8 6 12)';
        g.fillRect(x - s * 1.2, y, s * 2.4, s * 0.08);
        g.beginPath(); g.moveTo(x + s * 1.2, y - s * 0.1); g.lineTo(x + s * 1.6, y + s * 0.04); g.lineTo(x + s * 1.2, y + s * 0.18); g.closePath(); g.fill();
        g.beginPath(); g.moveTo(x - s * 0.4, y); g.lineTo(x + s * 0.3, y); g.lineTo(x, y - s * 0.7); g.closePath(); g.fill();
        g.beginPath(); g.arc(x, y - s * 0.75, s * 0.15, 0, Math.PI * 2); g.fill();
        g.beginPath(); g.moveTo(x - s * 0.3, y - s * 0.85); g.lineTo(x + s * 0.3, y - s * 0.85); g.lineTo(x + s * 0.05, y - s * 1.35); g.closePath(); g.fill();
      };
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var mx = W * 0.6, my = H * 0.3, mr = Math.min(W, H) * 0.18;
        g.fillStyle = 'rgba(245, 240, 210, 0.95)'; g.beginPath(); g.arc(mx, my, mr, 0, Math.PI * 2); g.fill();
        if (t > 1.2) {
          [0, 0.35, 0.7].forEach(function (lag) {
            var q = Math.min(1.3, Math.max(0, (t - 1.2 - lag) / 1.8));
            witch(-W * 0.1 + q * W * 1.1, my + (lag - 0.35) * mr * 1.2 + Math.sin(q * 6) * 10, Math.min(W, H) * 0.05);
          });
        }
        var cx = W * 0.2, cy = H * 0.85;
        g.fillStyle = 'rgb(230 220 200)'; g.fillRect(cx - 10, cy - 50, 20, 50);
        if (t > 0.4) {
          var flick = 0.8 + Math.random() * 0.2;
          g.fillStyle = 'rgb(10 10 14)'; g.beginPath(); g.ellipse(cx, cy - 62 * flick, 7, 14 * flick, 0, 0, Math.PI * 2); g.fill();
          var aura = g.createRadialGradient(cx, cy - 62, 0, cx, cy - 62, 60);
          aura.addColorStop(0, 'rgba(120, 255, 120, 0.4)'); aura.addColorStop(1, 'rgba(120, 255, 120, 0)');
          g.fillStyle = aura; g.fillRect(0, 0, W, H);
        }
        fog.forEach(function (f) {
          f.x += f.v; if (f.x - f.r > W) { f.x = -f.r; }
          var puff = g.createRadialGradient(f.x, f.y, 0, f.x, f.y, f.r);
          puff.addColorStop(0, 'rgba(110, 230, 120, ' + 0.22 * Math.min(1, t) + ')'); puff.addColorStop(1, 'rgba(110, 230, 120, 0)');
          g.fillStyle = puff; g.fillRect(f.x - f.r, f.y - f.r, f.r * 2, f.r * 2);
        });
        if (t > 3.8) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.8) / 0.6)); }
        return t < 4.5;
      });
    },

    // Dune: golden dunes shimmering in the heat, and a vast ripple travelling under the sand
    // toward you.
    worm: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(230 170 100), rgb(250 210 150))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var dunes = [['rgb(210 150 80)', 0.55, 40], ['rgb(195 135 70)', 0.66, 30], ['rgb(180 120 60)', 0.8, 22]];
        var near = Math.min(1, t / 3.0), rx = W * (0.15 + near * 0.35), ry = H * (0.6 + near * 0.32), rr = 30 + near * Math.min(W, H) * 0.4;
        dunes.forEach(function (d, i) {
          g.fillStyle = d[0]; g.beginPath(); g.moveTo(0, H);
          for (var x = 0; x <= W; x += 10) {
            var y = H * d[1] + Math.sin(x / (120 + i * 60) + i) * d[2] + Math.sin(x / 37 + t * 3) * 1.5;
            var dist = Math.hypot(x - rx, (y - ry) * 2);
            if (dist < rr && i === 2) { y -= Math.cos(dist / rr * Math.PI / 2) * 40 * near; }
            g.lineTo(x, y);
          }
          g.lineTo(W, H); g.closePath(); g.fill();
        });
        g.strokeStyle = 'rgba(255, 230, 180, ' + 0.4 * near + ')'; g.lineWidth = 2;
        for (var k = 0; k < 3; k++) { g.beginPath(); g.ellipse(rx, ry, rr * (0.5 + k * 0.25), rr * (0.12 + k * 0.06), 0, Math.PI, Math.PI * 2); g.stroke(); }
        g.fillStyle = 'rgba(255, 240, 210, 0.08)';
        for (var s = 0; s < 6; s++) { g.fillRect(0, H * 0.45 + s * 6 + Math.sin(t * 5 + s) * 3, W, 2); }
        if (t > 3.0) { shakePage(2, 120); }
        if (t > 3.4) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.4) / 0.6)); }
        return t < 4.1;
      });
    },

    // Blade Runner: a neon city in the rain at night, flying cars drifting past glowing towers.
    neon: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(10 8 20), rgb(30 20 40))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var towers = [], cars = [], drops = [];
      for (var i = 0; i < 18; i++) { towers.push({ x: i / 18 * W, w: W / 18 + 8, h: H * (0.3 + Math.random() * 0.6), lit: Math.random() }); }
      for (var k = 0; k < 6; k++) { cars.push({ x: Math.random() * W, y: H * (0.2 + Math.random() * 0.4), v: (Math.random() > 0.5 ? 1 : -1) * (1 + Math.random() * 2) }); }
      for (var d = 0; d < 260; d++) { drops.push({ x: Math.random() * W, y: Math.random() * H, v: 10 + Math.random() * 8 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        towers.forEach(function (tw, i) {
          g.fillStyle = 'rgb(14 12 22)'; g.fillRect(tw.x, H - tw.h, tw.w, tw.h);
          for (var y = H - tw.h + 10; y < H; y += 14) { for (var x = tw.x + 4; x < tw.x + tw.w - 4; x += 8) { if (Math.sin(x * 13 + y * 7 + i) > 0.6) { g.fillStyle = 'rgba(255, 200, 120, 0.55)'; g.fillRect(x, y, 3, 5); } } }
        });
        [['rgba(255, 40, 160, 0.8)', 0.22, 0.45], ['rgba(40, 220, 255, 0.8)', 0.72, 0.38]].forEach(function (ad) {
          var flick = Math.random() > 0.05 ? 1 : 0.3;
          g.fillStyle = ad[0].replace('0.8', String(0.8 * flick)); g.fillRect(W * ad[1], H * ad[2], W * 0.1, H * 0.16);
          var glow = g.createRadialGradient(W * (ad[1] + 0.05), H * (ad[2] + 0.08), 0, W * (ad[1] + 0.05), H * (ad[2] + 0.08), W * 0.2);
          glow.addColorStop(0, ad[0].replace('0.8', '0.25')); glow.addColorStop(1, 'rgba(0, 0, 0, 0)');
          g.fillStyle = glow; g.fillRect(0, 0, W, H);
        });
        cars.forEach(function (car) {
          car.x += car.v; if (car.x > W + 40) { car.x = -40; } if (car.x < -40) { car.x = W + 40; }
          g.fillStyle = 'rgb(20 20 28)'; g.fillRect(car.x - 16, car.y - 4, 32, 8);
          g.fillStyle = 'rgba(255, 240, 220, 0.9)'; g.fillRect(car.x + (car.v > 0 ? 14 : -18), car.y - 2, 4, 3);
          g.fillStyle = 'rgba(255, 60, 60, 0.9)'; g.fillRect(car.x + (car.v > 0 ? -18 : 14), car.y - 2, 4, 3);
        });
        g.strokeStyle = 'rgba(170, 160, 210, 0.3)'; g.lineWidth = 1; g.beginPath();
        drops.forEach(function (dr) { dr.y += dr.v; if (dr.y > H) { dr.y = -20; dr.x = Math.random() * W; } g.moveTo(dr.x, dr.y); g.lineTo(dr.x - 1, dr.y - 12); });
        g.stroke();
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.6)); }
        return t < 4.3;
      });
    },

    // Hellboy: red flames lick up the edges, then a great stone fist punches in and the screen
    // cracks.
    fist: function () {
      var c = curtain({ max: 5000, background: 'rgb(16 6 4)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var flames = [], hit = false, cracks = [];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        for (var f = 0; f < 20; f++) { var side = Math.random(); flames.push({ x: side < 0.5 ? Math.random() * W * 0.15 : W - Math.random() * W * 0.15, y: H, v: 3 + Math.random() * 5, life: 1, r: 20 + Math.random() * 30 }); }
        flames.forEach(function (p) {
          p.y -= p.v; p.life -= 0.015;
          if (p.life <= 0) { return; }
          var fire = g.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r);
          fire.addColorStop(0, 'rgba(255, 200, 80, ' + p.life * 0.6 + ')'); fire.addColorStop(1, 'rgba(200, 30, 0, 0)');
          g.fillStyle = fire; g.fillRect(p.x - p.r, p.y - p.r, p.r * 2, p.r * 2);
        });
        flames = flames.filter(function (p) { return p.life > 0; });
        var punch = Math.min(1, Math.max(0, (t - 1.2) / 0.35)), fx = W * 1.2 - punch * W * 0.75, fy = H * 0.5, s = Math.min(W, H) * 0.32;
        if (punch > 0) {
          g.fillStyle = 'rgb(120 40 30)';
          g.fillRect(fx, fy - s * 0.25, W, s * 0.5);
          g.fillStyle = 'rgb(150 50 36)'; g.beginPath(); g.ellipse(fx, fy, s * 0.5, s * 0.45, 0, 0, Math.PI * 2); g.fill();
          g.strokeStyle = 'rgb(80 24 18)'; g.lineWidth = 4;
          for (var k = -1; k <= 2; k++) { g.beginPath(); g.moveTo(fx - s * 0.45, fy + k * s * 0.18); g.lineTo(fx - s * 0.1, fy + k * s * 0.18); g.stroke(); }
        }
        if (punch >= 1 && !hit) {
          hit = true; shakePage(12, 400);
          for (var cr = 0; cr < 9; cr++) { var a = Math.random() * Math.PI * 2, pts = [[fx - s * 0.5, fy]]; for (var p2 = 1; p2 < 6; p2++) { pts.push([pts[p2 - 1][0] + Math.cos(a) * 60 + (Math.random() - 0.5) * 40, pts[p2 - 1][1] + Math.sin(a) * 60 + (Math.random() - 0.5) * 40]); } cracks.push(pts); }
        }
        g.strokeStyle = 'rgba(255, 255, 255, 0.85)'; g.lineWidth = 2;
        cracks.forEach(function (pts) { g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); pts.forEach(function (p) { g.lineTo(p[0], p[1]); }); g.stroke(); });
        if (t > 2.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 2.6) / 0.6)); }
        return t < 3.3;
      });
    },

    // Gladiator: a hand brushing through golden wheat at sunset, then arena gates grinding open.
    wheat: function () {
      var c = curtain({ max: 6000, background: 'linear-gradient(to bottom, rgb(200 140 70), rgb(240 200 120))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var stalks = [];
      for (var i = 0; i < 160; i++) { stalks.push({ x: Math.random() * W, h: H * (0.25 + Math.random() * 0.2), p: Math.random() * 6 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        if (t < 2.4) {
          var hx = W * (0.1 + t / 2.4 * 0.8);
          g.strokeStyle = 'rgb(200 150 60)'; g.lineWidth = 2;
          stalks.forEach(function (s) {
            var bend = Math.sin(t * 2 + s.p) * 6 + (Math.abs(s.x - hx) < 70 ? (s.x - hx) * 0.4 : 0);
            g.beginPath(); g.moveTo(s.x, H); g.quadraticCurveTo(s.x, H - s.h * 0.5, s.x + bend, H - s.h); g.stroke();
            g.fillStyle = 'rgb(220 170 70)'; g.beginPath(); g.ellipse(s.x + bend, H - s.h - 8, 3, 10, bend * 0.02, 0, Math.PI * 2); g.fill();
          });
          g.fillStyle = 'rgba(60, 40, 20, 0.85)'; g.beginPath(); g.ellipse(hx, H * 0.62, 26, 14, 0.3, 0, Math.PI * 2); g.fill();
          g.fillRect(hx - 10, H * 0.62, 20, H * 0.4);
        } else {
          var open = Math.min(1, (t - 2.4) / 1.2);
          g.fillStyle = 'rgb(120 100 80)'; g.fillRect(0, 0, W, H);
          g.fillStyle = 'rgb(250 230 180)'; g.fillRect(W * 0.3, H * 0.2, W * 0.4, H * 0.8);
          g.fillStyle = 'rgb(40 34 30)';
          var gw = W * 0.2 * (1 - open);
          g.fillRect(W * 0.3, H * 0.2, gw, H * 0.8); g.fillRect(W * 0.7 - gw, H * 0.2, gw, H * 0.8);
          g.strokeStyle = 'rgb(20 16 14)'; g.lineWidth = 6;
          for (var b = 0; b < 5; b++) { g.beginPath(); g.moveTo(W * 0.3 + b * gw / 5, H * 0.2); g.lineTo(W * 0.3 + b * gw / 5, H); g.moveTo(W * 0.7 - b * gw / 5, H * 0.2); g.lineTo(W * 0.7 - b * gw / 5, H); g.stroke(); }
          if (open > 0.6) { c.el.style.opacity = String(Math.max(0, 1 - (open - 0.6) / 0.4)); }
        }
        return t < 3.7;
      });
    },

    // Frozen: ice crystals spread from the centre into a great snowflake, then shatter into
    // sparkles.
    snowflake: function () {
      var c = curtain({ max: 5000, background: 'radial-gradient(circle at 50% 50%, rgb(60 110 170), rgb(14 30 60))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H / 2, R = Math.min(W, H) * 0.4, sparks = [], burst = false;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var grow = Math.min(1, t / 2.0);
        if (t < 2.5) {
          g.strokeStyle = 'rgba(220, 240, 255, 0.95)'; g.lineCap = 'round'; g.shadowColor = 'rgb(180 220 255)'; g.shadowBlur = 12;
          for (var arm = 0; arm < 6; arm++) {
            g.save(); g.translate(cx, cy); g.rotate(arm / 6 * Math.PI * 2 + t * 0.2);
            g.lineWidth = 5; g.beginPath(); g.moveTo(0, 0); g.lineTo(0, -R * grow); g.stroke();
            g.lineWidth = 3;
            [0.35, 0.6, 0.82].forEach(function (k) {
              if (grow < k) { return; }
              var len = R * 0.22 * (1 - k * 0.5) * Math.min(1, (grow - k) * 5);
              g.beginPath(); g.moveTo(0, -R * k); g.lineTo(-len, -R * k - len); g.moveTo(0, -R * k); g.lineTo(len, -R * k - len); g.stroke();
            });
            g.restore();
          }
          g.shadowBlur = 0;
        }
        if (t >= 2.5 && !burst) {
          burst = true;
          for (var s = 0; s < 260; s++) { var a = Math.random() * Math.PI * 2, d = Math.random() * R; sparks.push({ x: cx + Math.cos(a) * d, y: cy + Math.sin(a) * d, vx: Math.cos(a) * (2 + Math.random() * 6), vy: Math.sin(a) * (2 + Math.random() * 6), a: 1 }); }
        }
        sparks.forEach(function (p) { p.x += p.vx; p.y += p.vy; p.a *= 0.95; g.fillStyle = 'rgba(230, 245, 255, ' + p.a + ')'; g.fillRect(p.x, p.y, 3, 3); });
        if (t > 2.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 2.6) / 0.7)); }
        return t < 3.4;
      });
    },

    // Finding Nemo: underwater -- rays of light, bubbles, coral, and a small orange fish darting
    // across.
    reef: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(40 150 200), rgb(10 50 100))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var bubbles = [], corals = [];
      for (var i = 0; i < 40; i++) { bubbles.push({ x: Math.random() * W, y: H + Math.random() * H, r: 2 + Math.random() * 6, v: 1 + Math.random() * 2 }); }
      for (var k = 0; k < 16; k++) { corals.push({ x: k / 16 * W + Math.random() * 30, h: H * (0.08 + Math.random() * 0.14), c: ['rgb(240 110 140)', 'rgb(250 170 60)', 'rgb(160 90 200)', 'rgb(90 200 160)'][k % 4] }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        for (var r = 0; r < 5; r++) {
          g.fillStyle = 'rgba(255, 255, 255, ' + (0.06 + Math.sin(t + r) * 0.03) + ')';
          g.beginPath(); g.moveTo(W * (0.1 + r * 0.2), 0); g.lineTo(W * (0.16 + r * 0.2), 0); g.lineTo(W * (0.26 + r * 0.2), H); g.lineTo(W * (0.14 + r * 0.2), H); g.closePath(); g.fill();
        }
        corals.forEach(function (co) {
          g.fillStyle = co.c;
          for (var b = 0; b < 5; b++) { g.beginPath(); g.ellipse(co.x + (b - 2) * 8, H - co.h * (0.4 + (b % 3) * 0.3), 6, co.h * 0.35, (b - 2) * 0.2 + Math.sin(t * 2 + co.x) * 0.05, 0, Math.PI * 2); g.fill(); }
        });
        var q = Math.min(1, t / 3.0), fx = -60 + q * (W + 120), fy = H * 0.5 + Math.sin(t * 4) * 30, s = Math.min(W, H) * 0.05, wag = Math.sin(t * 20) * 0.3;
        g.save(); g.translate(fx, fy);
        g.fillStyle = 'rgb(255 120 30)';
        g.beginPath(); g.ellipse(0, 0, s, s * 0.55, 0, 0, Math.PI * 2); g.fill();
        g.beginPath(); g.moveTo(-s * 0.8, 0); g.lineTo(-s * 1.4, -s * 0.5 + wag * s); g.lineTo(-s * 1.4, s * 0.5 + wag * s); g.closePath(); g.fill();
        g.fillStyle = 'rgb(255 255 255)'; g.fillRect(-s * 0.15, -s * 0.52, s * 0.18, s * 1.04); g.fillRect(s * 0.35, -s * 0.4, s * 0.14, s * 0.8);
        g.fillStyle = 'rgb(20 20 20)'; g.beginPath(); g.arc(s * 0.65, -s * 0.12, s * 0.09, 0, Math.PI * 2); g.fill();
        g.restore();
        bubbles.forEach(function (b) {
          b.y -= b.v; b.x += Math.sin(b.y / 30) * 0.5; if (b.y < -10) { b.y = H + 10; }
          g.strokeStyle = 'rgba(220, 245, 255, 0.6)'; g.lineWidth = 1.5; g.beginPath(); g.arc(b.x, b.y, b.r, 0, Math.PI * 2); g.stroke();
        });
        if (t > 3.3) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.3) / 0.6)); }
        return t < 4.0;
      });
    },

    // Monsters, Inc.: doors whizz past on a factory rail; one stops, opens, and light spills out.
    doors: function () {
      var c = curtain({ max: 5000, background: 'linear-gradient(to bottom, rgb(40 50 70), rgb(20 24 34))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var palette = ['rgb(220 80 80)', 'rgb(80 160 220)', 'rgb(240 200 70)', 'rgb(130 200 110)', 'rgb(200 120 220)', 'rgb(250 150 60)'];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgb(120 130 150)'; g.lineWidth = 6; g.beginPath(); g.moveTo(0, H * 0.18); g.lineTo(W, H * 0.18); g.stroke();
        var speed = t < 1.6 ? 1 : Math.max(0, 1 - (t - 1.6) / 0.5), dw = Math.min(W, H) * 0.22, dh = dw * 1.9, gap = dw * 1.4;
        var shift = (t < 2.1 ? t * 1400 - Math.max(0, t - 1.6) * 700 : 1600 * 1 + 0) % gap;
        for (var i = -1; i < W / gap + 2; i++) {
          var x = i * gap - shift + (t >= 2.1 ? 0 : 0), cxDoor = W / 2;
          if (t >= 2.1) { x = cxDoor - dw / 2 + (i - Math.round(W / gap / 2)) * gap; }
          var col = palette[(i + 60) % palette.length];
          g.strokeStyle = 'rgb(90 100 120)'; g.lineWidth = 3; g.beginPath(); g.moveTo(x + dw / 2, H * 0.18); g.lineTo(x + dw / 2, H * 0.3); g.stroke();
          var isCentre = t >= 2.1 && Math.abs(x + dw / 2 - cxDoor) < 2;
          var open = isCentre ? Math.min(1, (t - 2.3) / 0.5) : 0;
          if (open > 0) {
            var light = g.createRadialGradient(cxDoor, H * 0.3 + dh / 2, 0, cxDoor, H * 0.3 + dh / 2, W * 0.6);
            light.addColorStop(0, 'rgba(255, 245, 210, ' + open * 0.9 + ')'); light.addColorStop(1, 'rgba(255, 245, 210, 0)');
            g.fillStyle = light; g.fillRect(0, 0, W, H);
            g.fillStyle = 'rgb(255 250 230)'; g.fillRect(x, H * 0.3, dw, dh);
          }
          g.fillStyle = col; g.fillRect(x + dw * open * 0.85, H * 0.3, dw * (1 - open * 0.85), dh);
          g.fillStyle = 'rgba(255, 255, 255, 0.25)'; g.fillRect(x + dw * 0.15 + dw * open * 0.85, H * 0.3 + dh * 0.1, dw * 0.7 * (1 - open * 0.85), dh * 0.35);
          g.fillStyle = 'rgb(240 220 120)'; g.beginPath(); g.arc(x + dw * 0.85, H * 0.3 + dh * 0.55, 6, 0, Math.PI * 2); g.fill();
        }
        if (t > 3.1) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.1) / 0.6)); }
        return t < 3.8;
      });
    },

    // Inside Out: glowing memory orbs in five colours roll in and line up -- one for each film.
    orbs: function () {
      var c = curtain({ max: 5500, background: 'radial-gradient(circle at 50% 40%, rgb(60 50 110), rgb(16 12 34))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var hues = ['255, 220, 60', '80, 140, 255', '230, 60, 60', '170, 90, 230', '110, 210, 90'];
      var count = Math.max(4, Math.min(12, page.steps.length || 6)), orbs = [];
      for (var i = 0; i < count; i++) { orbs.push({ hue: hues[i % 5], at: 0.3 + i * 0.22, owned: page.steps[i] ? page.steps[i].owned : true }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var r = Math.min(W / (count * 2.6), H * 0.07), row = H * 0.55;
        g.fillStyle = 'rgba(200, 190, 255, 0.15)'; g.fillRect(W * 0.05, row + r + 4, W * 0.9, 6);
        orbs.forEach(function (o, i) {
          var q = Math.min(1, Math.max(0, (t - o.at) / 0.6)), e = 1 - Math.pow(1 - q, 3);
          if (q <= 0) { return; }
          var tx = W / 2 + (i - (count - 1) / 2) * r * 2.4, x = -r + (tx + r) * e, y = row - Math.abs(Math.sin(e * Math.PI * 2)) * r * (1 - e);
          var glow = g.createRadialGradient(x, y, 0, x, y, r * 2.2);
          glow.addColorStop(0, 'rgba(' + o.hue + ', ' + (o.owned ? 0.5 : 0.15) + ')'); glow.addColorStop(1, 'rgba(' + o.hue + ', 0)');
          g.fillStyle = glow; g.fillRect(x - r * 2.2, y - r * 2.2, r * 4.4, r * 4.4);
          var ball = g.createRadialGradient(x - r * 0.3, y - r * 0.3, r * 0.1, x, y, r);
          ball.addColorStop(0, 'rgba(255, 255, 255, ' + (o.owned ? 0.95 : 0.4) + ')'); ball.addColorStop(0.4, 'rgba(' + o.hue + ', ' + (o.owned ? 0.95 : 0.35) + ')'); ball.addColorStop(1, 'rgba(' + o.hue + ', ' + (o.owned ? 0.7 : 0.2) + ')');
          g.fillStyle = ball; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
        });
        if (t > 4.0) { c.el.style.opacity = String(Math.max(0, 1 - (t - 4.0) / 0.6)); }
        return t < 4.7;
      });
    },

    // The Hangover: morning-after camera flashes -- a slideshow of blurry snapshots, ending on the
    // collection's own poster.
    snapshots: function () {
      var backdrop = document.querySelector('.collection-backdrop');
      var srcs = page.posters.map(bigger).slice(0, 5);
      if (!srcs.length && backdrop) { srcs = [backdrop.currentSrc || backdrop.src]; }
      var c = curtain({ max: 6000, background: 'rgb(16 14 12)' });
      var flash = document.createElement('span');
      flash.className = 'sc-flip-flash';
      flash.style.background = 'rgb(255 255 255)';
      c.el.appendChild(flash);
      var shots = srcs.length ? srcs : [null, null, null];
      shots.forEach(function (src, i) {
        window.setTimeout(function () {
          flash.classList.add('is-on'); window.setTimeout(function () { flash.classList.remove('is-on'); }, 120);
          var photo = document.createElement('div');
          photo.className = 'sc-snapshot';
          photo.style.background = 'rgb(246 244 238)';
          var img = document.createElement('span');
          img.className = 'sc-snapshot-image';
          img.style.background = src ? 'url("' + src.replace(/"/g, '%22') + '") center / cover' : 'rgb(80 70 60)';
          img.style.filter = i < shots.length - 1 ? 'blur(3px) saturate(1.3)' : 'none';
          photo.appendChild(img);
          photo.style.rotate = ((Math.random() - 0.5) * 24) + 'deg';
          photo.style.left = (30 + Math.random() * 40) + '%'; photo.style.top = (30 + Math.random() * 30) + '%';
          c.el.appendChild(photo);
        }, 300 + i * 700);
      });
      window.setTimeout(c.finish, 300 + shots.length * 700 + 900);
    },

    // Scooby-Doo: a groovy flower-painted van drives across, then a sheet ghost is unmasked.
    van: function () {
      var c = curtain({ max: 6000, background: 'linear-gradient(to bottom, rgb(40 30 70), rgb(90 60 110))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var n = page.missing.length;
      var caption = text('p', 'sc-intro-caption', '', c.el);
      caption.style.color = 'rgb(250 220 120)';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.fillStyle = 'rgb(30 24 40)'; g.fillRect(0, H * 0.78, W, H * 0.22);
        if (t < 2.4) {
          var x = -W * 0.3 + Math.min(1, t / 2.2) * W * 1.5, y = H * 0.78, s = Math.min(W, H) * 0.18;
          g.fillStyle = 'rgb(80 180 170)'; g.fillRect(x - s, y - s * 0.75, s * 2, s * 0.6);
          g.beginPath(); g.moveTo(x + s, y - s * 0.75); g.lineTo(x + s * 1.3, y - s * 0.45); g.lineTo(x + s * 1.3, y - s * 0.15); g.lineTo(x + s, y - s * 0.15); g.closePath(); g.fill();
          g.fillStyle = 'rgb(90 140 220)'; g.fillRect(x - s, y - s * 0.4, s * 2.3, s * 0.12);
          g.fillStyle = 'rgb(250 140 40)';
          [[-0.6, -0.55], [-0.1, -0.6], [0.45, -0.52]].forEach(function (p) { for (var k = 0; k < 5; k++) { var a = k / 5 * Math.PI * 2; g.beginPath(); g.arc(x + p[0] * s + Math.cos(a) * 8, y + p[1] * s + Math.sin(a) * 8, 6, 0, Math.PI * 2); g.fill(); } });
          g.fillStyle = 'rgb(20 20 24)'; g.beginPath(); g.arc(x - s * 0.6, y - s * 0.12, s * 0.16, 0, Math.PI * 2); g.arc(x + s * 0.8, y - s * 0.12, s * 0.16, 0, Math.PI * 2); g.fill();
        } else {
          var off = Math.min(1, (t - 2.4) / 0.6), gx = W / 2, gy = H * 0.5, gs = Math.min(W, H) * 0.22;
          g.fillStyle = 'rgba(240, 240, 245, 0.95)';
          g.beginPath(); g.moveTo(gx - gs * 0.5, gy + gs - off * gs * 2); g.quadraticCurveTo(gx - gs * 0.55, gy - gs * 0.6 - off * gs * 2, gx, gy - gs * 0.7 - off * gs * 2);
          g.quadraticCurveTo(gx + gs * 0.55, gy - gs * 0.6 - off * gs * 2, gx + gs * 0.5, gy + gs - off * gs * 2); g.closePath(); g.fill();
          if (off > 0.4) {
            g.fillStyle = 'rgb(250 220 120)'; g.font = '700 ' + Math.round(gs * 0.18) + 'px system-ui, sans-serif'; g.textAlign = 'center';
            caption.textContent = n ? 'And it was ' + plural(n, 'missing film') + ' all along!' : 'And it was a complete collection all along!';
          }
        }
        if (t > 4.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 4.6) / 0.6)); }
        return t < 5.3;
      });
    },

    // Joker: a playing card spins in purple and green light and lands face up on the joker.
    card: function () {
      var c = curtain({ max: 5000, background: 'radial-gradient(circle at 50% 50%, rgb(70 30 90), rgb(14 6 20))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var glow = g.createRadialGradient(W * 0.3, H * 0.3, 0, W * 0.3, H * 0.3, W * 0.5);
        glow.addColorStop(0, 'rgba(90, 220, 90, 0.25)'); glow.addColorStop(1, 'rgba(90, 220, 90, 0)');
        g.fillStyle = glow; g.fillRect(0, 0, W, H);
        var settle = Math.min(1, t / 2.2), spin = (1 - settle) * 16 + settle * 0, face = Math.cos(t * (1 - settle) * 14);
        var cw = Math.min(W, H) * 0.22, ch = cw * 1.45, x = W / 2, y = H / 2 - (1 - settle) * H * 0.2;
        g.save(); g.translate(x, y); g.rotate(spin * 0.15); g.scale(settle >= 1 ? 1 : Math.max(0.05, Math.abs(face)), 1);
        var up = settle >= 1 || face > 0;
        g.fillStyle = up ? 'rgb(248 246 240)' : 'rgb(120 30 40)';
        g.fillRect(-cw / 2, -ch / 2, cw, ch);
        g.strokeStyle = up ? 'rgb(90 40 110)' : 'rgb(240 220 200)'; g.lineWidth = 3; g.strokeRect(-cw / 2 + 6, -ch / 2 + 6, cw - 12, ch - 12);
        if (up) {
          g.fillStyle = 'rgb(90 40 110)'; g.font = '800 ' + Math.round(cw * 0.16) + 'px Georgia, serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
          g.fillText('JOKER', 0, ch * 0.3);
          g.fillStyle = 'rgb(60 160 60)'; g.beginPath(); g.moveTo(-cw * 0.25, -ch * 0.05); g.lineTo(0, -ch * 0.32); g.lineTo(cw * 0.25, -ch * 0.05); g.closePath(); g.fill();
          g.fillStyle = 'rgb(200 40 60)'; g.beginPath(); g.arc(0, -ch * 0.32, cw * 0.05, 0, Math.PI * 2); g.fill();
          g.beginPath(); g.arc(0, ch * 0.05, cw * 0.18, 0.15 * Math.PI, 0.85 * Math.PI); g.lineWidth = 4; g.strokeStyle = 'rgb(200 40 60)'; g.stroke();
        }
        g.restore();
        if (t > 3.2) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.2) / 0.6)); }
        return t < 3.9;
      });
    },

    // ---------------------------------------------------------------- 0.69.0

    // A Nightmare on Elm Street: a hot red boiler room hissing steam, then four claw marks slash
    // across the screen.
    claws: function () {
      var c = curtain({ max: 5000, background: 'linear-gradient(to bottom, rgb(60 10 6), rgb(20 4 2))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var steam = [], pipes = [];
      for (var i = 0; i < 6; i++) { pipes.push({ y: H * (0.15 + i * 0.13), h: 18 + Math.random() * 14 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        pipes.forEach(function (p) { g.fillStyle = 'rgb(70 30 20)'; g.fillRect(0, p.y, W, p.h); g.fillStyle = 'rgba(255, 120, 60, 0.25)'; g.fillRect(0, p.y, W, 3); });
        var glow = g.createRadialGradient(W / 2, H, 0, W / 2, H, H);
        glow.addColorStop(0, 'rgba(255, 90, 20, ' + (0.4 + Math.sin(t * 6) * 0.08) + ')'); glow.addColorStop(1, 'rgba(255, 90, 20, 0)');
        g.fillStyle = glow; g.fillRect(0, 0, W, H);
        if (Math.random() < 0.5) { steam.push({ x: Math.random() * W, y: pipes[Math.floor(Math.random() * pipes.length)].y, r: 10, a: 0.35 }); }
        steam.forEach(function (s) { s.y -= 1.5; s.r += 1.8; s.a *= 0.96; g.fillStyle = 'rgba(220, 210, 200, ' + s.a + ')'; g.beginPath(); g.arc(s.x, s.y, s.r, 0, Math.PI * 2); g.fill(); });
        if (t > 1.8) {
          var cut = Math.min(1, (t - 1.8) / 0.25);
          for (var k = 0; k < 4; k++) {
            var x0 = W * (0.2 + k * 0.12), y0 = H * 0.15, x1 = x0 + W * 0.3, y1 = H * 0.85;
            g.strokeStyle = 'rgba(10, 2, 2, 0.95)'; g.lineWidth = 14; g.lineCap = 'round';
            g.beginPath(); g.moveTo(x0, y0); g.lineTo(x0 + (x1 - x0) * cut, y0 + (y1 - y0) * cut); g.stroke();
            g.strokeStyle = 'rgba(255, 200, 160, 0.6)'; g.lineWidth = 2;
            g.beginPath(); g.moveTo(x0 + 6, y0); g.lineTo(x0 + 6 + (x1 - x0) * cut, y0 + (y1 - y0) * cut); g.stroke();
          }
          if (cut >= 1 && t < 2.1) { shakePage(5, 200); }
        }
        if (t > 3.0) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.0) / 0.6)); }
        return t < 3.7;
      });
    },

    // Saw: a flickering bulb over grimy tiles, a jigsaw-piece timer counting down, then the light
    // dies.
    jigsaw: function () {
      var c = curtain({ max: 5500, background: 'rgb(20 22 16)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var on = t < 3.4 && (Math.random() > 0.08) ? 1 : 0.15;
        var lamp = g.createRadialGradient(W / 2, H * 0.12, 0, W / 2, H * 0.3, H * 0.9);
        lamp.addColorStop(0, 'rgba(220, 230, 170, ' + 0.5 * on + ')'); lamp.addColorStop(1, 'rgba(0, 0, 0, 0)');
        g.strokeStyle = 'rgba(80, 90, 70, ' + (0.3 + on * 0.4) + ')'; g.lineWidth = 2;
        for (var x = 0; x < W; x += 50) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); }
        for (var y = 0; y < H; y += 50) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
        g.fillStyle = lamp; g.fillRect(0, 0, W, H);
        g.fillStyle = 'rgba(240, 240, 200, ' + on + ')'; g.beginPath(); g.arc(W / 2, H * 0.12, 10, 0, Math.PI * 2); g.fill();
        g.strokeStyle = 'rgb(40 40 40)'; g.beginPath(); g.moveTo(W / 2, 0); g.lineTo(W / 2, H * 0.12 - 10); g.stroke();
        var s = Math.min(W, H) * 0.28, cx = W / 2, cy = H * 0.55;
        g.fillStyle = 'rgba(150, 40, 30, ' + (0.4 + on * 0.6) + ')';
        g.beginPath(); g.moveTo(cx - s / 2, cy - s / 2); g.lineTo(cx - s * 0.12, cy - s / 2); g.arc(cx, cy - s / 2, s * 0.12, Math.PI, 0); g.lineTo(cx + s / 2, cy - s / 2);
        g.lineTo(cx + s / 2, cy - s * 0.12); g.arc(cx + s / 2, cy, s * 0.12, -Math.PI / 2, Math.PI / 2); g.lineTo(cx + s / 2, cy + s / 2); g.lineTo(cx - s / 2, cy + s / 2); g.closePath(); g.fill();
        var left = Math.max(0, 9.9 - t * 3);
        g.fillStyle = 'rgba(255, 70, 50, ' + (0.5 + on * 0.5) + ')'; g.font = '700 ' + Math.round(s * 0.28) + 'px ui-monospace, monospace'; g.textAlign = 'center'; g.textBaseline = 'middle';
        g.fillText('00:0' + left.toFixed(1), cx, cy);
        if (t > 3.4) { g.fillStyle = 'rgba(0, 0, 0, ' + Math.min(1, (t - 3.4) / 0.3) + ')'; g.fillRect(0, 0, W, H); }
        if (t > 3.8) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.8) / 0.5)); }
        return t < 4.4;
      });
    },

    // Psycho: in black and white, a shower curtain is torn aside, its rings snapping, and the
    // water spirals down the drain.
    shower: function () {
      var c = curtain({ max: 5500, background: 'rgb(30 30 30)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var rings = 14;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        if (t < 2.4) {
          var pull = Math.min(1, Math.max(0, (t - 0.9) / 0.4));
          g.fillStyle = 'rgb(210 210 210)'; g.fillRect(0, 0, W, H);
          g.strokeStyle = 'rgba(120, 120, 120, 0.6)'; g.lineWidth = 1;
          for (var y = 0; y < H; y += 30) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
          g.strokeStyle = 'rgb(60 60 60)'; g.lineWidth = 6; g.beginPath(); g.moveTo(0, H * 0.06); g.lineTo(W, H * 0.06); g.stroke();
          var right = W * (1 - pull * 0.92);
          for (var f = 0; f < 18; f++) {
            var x = f / 18 * right;
            g.fillStyle = f % 2 ? 'rgb(235 235 235)' : 'rgb(200 200 200)';
            g.fillRect(x, H * 0.08, right / 18 + 1, H);
          }
          for (var r = 0; r < rings; r++) {
            var rx = r / (rings - 1) * right, popped = pull > 0 && r > rings * (1 - pull);
            g.strokeStyle = 'rgb(40 40 40)'; g.lineWidth = 3;
            g.beginPath(); g.arc(rx + (popped ? (r - rings / 2) * 6 * pull : 0), H * 0.06 + (popped ? pull * 40 : 0), 8, 0, Math.PI * 2); g.stroke();
          }
        } else {
          var swirl = (t - 2.4) * 4, cx = W / 2, cy = H / 2;
          g.fillStyle = 'rgb(180 180 180)'; g.beginPath(); g.arc(cx, cy, Math.min(W, H) * 0.42, 0, Math.PI * 2); g.fill();
          g.strokeStyle = 'rgba(60, 60, 60, 0.8)'; g.lineWidth = 3;
          for (var a = 0; a < 6; a++) {
            g.beginPath();
            for (var s = 0; s < 40; s++) { var q = s / 40, ang = a / 6 * Math.PI * 2 + swirl + q * 6, rr = Math.min(W, H) * 0.4 * (1 - q); if (!s) { g.moveTo(cx + Math.cos(ang) * rr, cy + Math.sin(ang) * rr); } else { g.lineTo(cx + Math.cos(ang) * rr, cy + Math.sin(ang) * rr); } }
            g.stroke();
          }
          g.fillStyle = 'rgb(20 20 20)'; g.beginPath(); g.arc(cx, cy, Math.min(W, H) * 0.05, 0, Math.PI * 2); g.fill();
          if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.6)); }
        }
        return t < 4.3;
      });
    },

    // World War Z: a swarm of figures pours up and over a high wall like a wave.
    swarm: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(150 140 120), rgb(90 80 70))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var wallTop = H * 0.35, crowd = [];
      for (var i = 0; i < 700; i++) { crowd.push({ x: Math.random() * W, base: H + Math.random() * H * 0.3, d: Math.random() }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.fillStyle = 'rgb(140 130 110)'; g.fillRect(0, wallTop, W, H - wallTop);
        g.strokeStyle = 'rgba(90, 80, 70, 0.6)'; g.lineWidth = 2;
        for (var y = wallTop; y < H; y += 26) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
        var surge = Math.min(1.25, t / 2.6);
        g.fillStyle = 'rgb(30 26 24)';
        crowd.forEach(function (p) {
          var peak = W / 2 + Math.sin(p.x / 120) * W * 0.05, hump = Math.max(0, 1 - Math.abs(p.x - peak) / (W * 0.6));
          var level = H + 20 - surge * (H - wallTop + 80) * (0.5 + hump * 0.8) * (0.6 + p.d * 0.4);
          var y = Math.max(level, -20) + Math.sin(t * 8 + p.x) * 3;
          if (y > H + 10) { return; }
          g.fillRect(p.x, y, 4, 8); g.beginPath(); g.arc(p.x + 2, y - 3, 2.5, 0, Math.PI * 2); g.fill();
        });
        if (t > 3.4) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.4) / 0.6)); }
        return t < 4.1;
      });
    },

    // 300: a sepia sky over a wall of shields, then a volley of arrows that blots out the sun.
    arrows: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(200 150 90), rgb(120 80 50))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var volley = [];
      for (var i = 0; i < 400; i++) { volley.push({ x: Math.random() * W * 1.4 - W * 0.4, y: -Math.random() * H, v: 6 + Math.random() * 4 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.fillStyle = 'rgba(255, 230, 170, 0.9)'; g.beginPath(); g.arc(W * 0.7, H * 0.3, Math.min(W, H) * 0.1, 0, Math.PI * 2); g.fill();
        var count = Math.floor(W / 70) + 1;
        for (var s = 0; s < count; s++) {
          var x = s * 70 + 35, y = H * 0.82;
          g.fillStyle = 'rgb(140 60 30)'; g.beginPath(); g.arc(x, y, 34, 0, Math.PI * 2); g.fill();
          g.strokeStyle = 'rgb(80 34 16)'; g.lineWidth = 4; g.beginPath(); g.arc(x, y, 34, 0, Math.PI * 2); g.stroke();
          g.strokeStyle = 'rgb(60 50 40)'; g.lineWidth = 3; g.beginPath(); g.moveTo(x + 20, y - 34); g.lineTo(x + 34, y - 110); g.stroke();
        }
        if (t > 1.0) {
          var dark = Math.min(0.75, (t - 1.0) / 1.6);
          g.fillStyle = 'rgba(30, 20, 10, ' + dark + ')'; g.fillRect(0, 0, W, H * 0.7);
          g.strokeStyle = 'rgba(20, 14, 10, 0.95)'; g.lineWidth = 2; g.beginPath();
          volley.forEach(function (a) { a.y += a.v; a.x += a.v * 0.5; g.moveTo(a.x, a.y); g.lineTo(a.x - 12, a.y - 22); });
          g.stroke();
        }
        if (t > 3.5) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.5) / 0.6)); }
        return t < 4.2;
      });
    },

    // The Karate Kid: a silhouette balancing in a crane stance on a post by the sea at sunset.
    crane: function () {
      var c = curtain({ max: 5000, background: 'linear-gradient(to bottom, rgb(250 160 80), rgb(230 100 90) 55%, rgb(60 70 110))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var sea = H * 0.68;
        g.fillStyle = 'rgba(255, 210, 120, 0.9)'; g.beginPath(); g.arc(W * 0.5, sea, Math.min(W, H) * 0.16, Math.PI, 0); g.fill();
        g.fillStyle = 'rgb(50 50 90)'; g.fillRect(0, sea, W, H - sea);
        g.strokeStyle = 'rgba(255, 210, 140, 0.5)'; g.lineWidth = 2;
        for (var w = 0; w < 8; w++) { var y = sea + 10 + w * 16; g.beginPath(); g.moveTo(W * 0.5 - 80 + w * 6 + Math.sin(t * 2 + w) * 10, y); g.lineTo(W * 0.5 + 80 - w * 6 + Math.sin(t * 2 + w) * 10, y); g.stroke(); }
        var px = W * 0.5, top = sea - H * 0.04, s = H * 0.16, rise = Math.min(1, t / 1.4), wob = Math.sin(t * 3) * 0.03;
        g.fillStyle = 'rgb(30 20 30)'; g.fillRect(px - 6, top, 12, H - top);
        g.save(); g.translate(px, top); g.rotate(wob);
        g.strokeStyle = 'rgb(30 20 30)'; g.fillStyle = 'rgb(30 20 30)'; g.lineWidth = s * 0.08; g.lineCap = 'round';
        g.beginPath(); g.moveTo(0, 0); g.lineTo(0, -s * 0.5); g.stroke();
        g.beginPath(); g.moveTo(0, -s * 0.5); g.lineTo(-s * 0.2, -s * 0.35 * rise - s * 0.2); g.lineTo(-s * 0.05, -s * 0.15 - s * 0.2 * rise); g.stroke();
        g.beginPath(); g.moveTo(0, -s * 0.5); g.lineTo(0, -s * 1.05); g.stroke();
        g.beginPath(); g.arc(0, -s * 1.18, s * 0.11, 0, Math.PI * 2); g.fill();
        g.beginPath(); g.moveTo(0, -s * 0.95); g.lineTo(-s * 0.45 * rise - s * 0.1, -s * 0.95 - s * 0.35 * rise); g.moveTo(0, -s * 0.95); g.lineTo(s * 0.45 * rise + s * 0.1, -s * 0.95 - s * 0.35 * rise); g.stroke();
        g.restore();
        if (t > 3.2) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.2) / 0.6)); }
        return t < 3.9;
      });
    },

    // The Meg: a tiny boat on calm water, and a colossal shark's shadow gliding underneath.
    shadow: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(40 120 170), rgb(10 40 80))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.strokeStyle = 'rgba(200, 235, 255, 0.25)'; g.lineWidth = 2;
        for (var r = 0; r < 14; r++) { var y = H * 0.1 + r * H * 0.06; g.beginPath(); for (var x = 0; x <= W; x += 20) { var yy = y + Math.sin(x / 60 + t * 2 + r) * 3; if (!x) { g.moveTo(x, yy); } else { g.lineTo(x, yy); } } g.stroke(); }
        var q = Math.min(1, t / 3.2), sx = W * 1.3 - q * W * 1.6, sy = H * 0.55, L = W * 0.9;
        g.fillStyle = 'rgba(4, 12, 24, 0.6)';
        g.beginPath(); g.moveTo(sx, sy); g.quadraticCurveTo(sx + L * 0.4, sy - L * 0.16, sx + L * 0.85, sy - L * 0.03);
        g.lineTo(sx + L, sy - L * 0.15); g.lineTo(sx + L * 0.95, sy); g.lineTo(sx + L, sy + L * 0.12); g.lineTo(sx + L * 0.85, sy + L * 0.03);
        g.quadraticCurveTo(sx + L * 0.4, sy + L * 0.14, sx, sy); g.fill();
        g.beginPath(); g.moveTo(sx + L * 0.35, sy - L * 0.1); g.lineTo(sx + L * 0.5, sy - L * 0.32); g.lineTo(sx + L * 0.56, sy - L * 0.1); g.fill();
        var bx = W * 0.5, by = H * 0.4 + Math.sin(t * 2) * 4;
        g.fillStyle = 'rgb(240 240 235)'; g.beginPath(); g.moveTo(bx - 30, by); g.lineTo(bx + 30, by); g.lineTo(bx + 20, by + 10); g.lineTo(bx - 20, by + 10); g.closePath(); g.fill();
        g.fillStyle = 'rgb(220 70 50)'; g.fillRect(bx - 6, by - 14, 12, 14);
        if (t > 3.5) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.5) / 0.6)); }
        return t < 4.2;
      });
    },

    // Mortal Kombat: fire from one side, ice from the other; they meet in the middle in a flash.
    fireice: function () {
      var c = curtain({ max: 5000, background: 'rgb(10 10 14)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var bits = [];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var reach = Math.min(1, t / 1.8), meet = t > 1.8;
        for (var k = 0; k < 18; k++) {
          bits.push({ x: 0, y: H / 2 + (Math.random() - 0.5) * 60, vx: 10 + Math.random() * 8, vy: (Math.random() - 0.5) * 2, hot: true, life: 1 });
          bits.push({ x: W, y: H / 2 + (Math.random() - 0.5) * 60, vx: -10 - Math.random() * 8, vy: (Math.random() - 0.5) * 2, hot: false, life: 1 });
        }
        bits.forEach(function (b) {
          b.x += b.vx; b.y += b.vy; b.life -= 0.012;
          if ((b.hot && b.x > W / 2) || (!b.hot && b.x < W / 2)) { b.life = 0; }
          if (b.life <= 0) { return; }
          g.fillStyle = b.hot ? 'rgba(255, ' + Math.round(120 + Math.random() * 100) + ', 30, ' + b.life + ')' : 'rgba(150, 220, 255, ' + b.life + ')';
          g.beginPath(); g.arc(b.x, b.y, b.hot ? 6 : 4, 0, Math.PI * 2); g.fill();
        });
        bits = bits.filter(function (b) { return b.life > 0; });
        if (meet) {
          var f = Math.min(1, (t - 1.8) / 0.25), fade = t > 2.2 ? Math.max(0, 1 - (t - 2.2) / 0.6) : 1;
          var flash = g.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, W * 0.6 * f);
          flash.addColorStop(0, 'rgba(255, 255, 255, ' + fade + ')'); flash.addColorStop(1, 'rgba(255, 255, 255, 0)');
          g.fillStyle = flash; g.fillRect(0, 0, W, H);
          if (t < 2.0) { shakePage(6, 200); }
        }
        if (t > 2.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 2.6) / 0.6)); }
        return t < 3.3 && (reach >= 0);
      });
    },

    // Airplane!: a propeller plane bobbing through clouds as a 'fasten seat belts' sign flickers.
    seatbelt: function () {
      var c = curtain({ max: 5000, background: 'linear-gradient(to bottom, rgb(110 170 230), rgb(200 230 250))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var clouds = [];
      for (var i = 0; i < 12; i++) { clouds.push({ x: Math.random() * W, y: Math.random() * H, s: 40 + Math.random() * 70, v: 3 + Math.random() * 4 }); }
      var sign = text('p', 'sc-seatbelt', 'FASTEN SEAT BELTS', c.el);
      sign.style.color = 'rgb(255 220 120)'; sign.style.background = 'rgb(30 30 34)';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        clouds.forEach(function (cl) {
          cl.x -= cl.v; if (cl.x + cl.s * 2 < 0) { cl.x = W + cl.s; cl.y = Math.random() * H; }
          g.fillStyle = 'rgba(255, 255, 255, 0.9)';
          for (var b = 0; b < 4; b++) { g.beginPath(); g.arc(cl.x + b * cl.s * 0.5, cl.y + (b % 2) * cl.s * 0.15, cl.s * 0.4, 0, Math.PI * 2); g.fill(); }
        });
        var px = W * 0.45, py = H * 0.5 + Math.sin(t * 2.4) * 18, s = Math.min(W, H) * 0.12, tilt = Math.sin(t * 2.4) * 0.08;
        g.save(); g.translate(px, py); g.rotate(tilt);
        g.fillStyle = 'rgb(245 245 240)'; g.beginPath(); g.ellipse(0, 0, s, s * 0.18, 0, 0, Math.PI * 2); g.fill();
        g.fillStyle = 'rgb(200 60 50)'; g.fillRect(-s, -s * 0.04, s * 2, s * 0.06);
        g.fillStyle = 'rgb(230 230 225)'; g.beginPath(); g.moveTo(-s * 0.1, 0); g.lineTo(-s * 0.4, s * 0.6); g.lineTo(-s * 0.2, s * 0.6); g.lineTo(s * 0.2, 0); g.closePath(); g.fill();
        g.beginPath(); g.moveTo(-s * 0.85, 0); g.lineTo(-s, -s * 0.4); g.lineTo(-s * 0.8, -s * 0.4); g.lineTo(-s * 0.65, 0); g.closePath(); g.fill();
        g.strokeStyle = 'rgba(60, 60, 60, 0.6)'; g.lineWidth = 3; g.beginPath(); g.moveTo(s * 1.02, -s * 0.3 * Math.cos(t * 40)); g.lineTo(s * 1.02, s * 0.3 * Math.cos(t * 40)); g.stroke();
        g.restore();
        sign.style.opacity = Math.floor(t * 2.5) % 2 ? '0.25' : '1';
        if (t > 3.2) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.2) / 0.6)); }
        return t < 3.9;
      });
    },

    // Ace Ventura: a parade of jungle animal silhouettes trotting across a tropical sunset.
    parade: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(250 120 80), rgb(250 200 100) 60%, rgb(60 110 70))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var ground = H * 0.8;
      var animals = [
        function (x, s, b) { g.beginPath(); g.ellipse(x, ground - s * 0.6 + b, s * 0.7, s * 0.35, 0, 0, Math.PI * 2); g.fill(); g.fillRect(x + s * 0.4, ground - s * 1.3 + b, s * 0.16, s * 0.7); g.beginPath(); g.arc(x + s * 0.5, ground - s * 1.35 + b, s * 0.14, 0, Math.PI * 2); g.fill(); },
        function (x, s, b) { g.beginPath(); g.ellipse(x, ground - s * 0.55 + b, s * 0.8, s * 0.45, 0, 0, Math.PI * 2); g.fill(); g.beginPath(); g.arc(x + s * 0.75, ground - s * 0.65 + b, s * 0.28, 0, Math.PI * 2); g.fill(); g.fillRect(x + s * 0.95, ground - s * 0.6 + b, s * 0.1, s * 0.5); },
        function (x, s, b) { g.beginPath(); g.ellipse(x, ground - s * 0.5 + b, s * 0.5, s * 0.25, 0, 0, Math.PI * 2); g.fill(); g.beginPath(); g.arc(x + s * 0.45, ground - s * 0.7 + b, s * 0.2, 0, Math.PI * 2); g.fill(); g.beginPath(); g.moveTo(x - s * 0.45, ground - s * 0.55 + b); g.quadraticCurveTo(x - s * 0.9, ground - s * 1.1 + b, x - s * 0.6, ground - s * 1.2 + b); g.lineWidth = s * 0.08; g.strokeStyle = 'rgb(30 20 20)'; g.stroke(); },
        function (x, s, b) { g.beginPath(); g.ellipse(x, ground - s * 0.9 + b, s * 0.2, s * 0.32, 0, 0, Math.PI * 2); g.fill(); g.beginPath(); g.moveTo(x - s * 0.15, ground - s * 0.9 + b); g.lineTo(x - s * 0.5, ground - s * 0.7 + b); g.lineTo(x - s * 0.15, ground - s * 0.75 + b); g.fill(); g.fillRect(x - 2, ground - s * 0.6 + b, 3, s * 0.6); }
      ];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.fillStyle = 'rgba(255, 230, 150, 0.9)'; g.beginPath(); g.arc(W * 0.5, H * 0.55, Math.min(W, H) * 0.15, 0, Math.PI * 2); g.fill();
        g.fillStyle = 'rgb(30 40 30)'; g.fillRect(0, ground, W, H - ground);
        g.fillStyle = 'rgb(30 20 20)';
        for (var i = 0; i < 9; i++) { var x = -W * 0.2 + ((t * 160 + i * W * 0.17) % (W * 1.5)) - W * 0.1, s = H * (0.12 + (i % 3) * 0.03); animals[i % animals.length](x, s, -Math.abs(Math.sin(t * 8 + i)) * 6); }
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.6)); }
        return t < 4.3;
      });
    },

    // Anchorman: a seventies TV news card -- 'Breaking news', with the collection as the headline.
    newsdesk: function () {
      var c = curtain({ max: 6500, background: 'linear-gradient(to bottom, rgb(30 60 110), rgb(14 30 60))' });
      var n = page.missing.length;
      var card = document.createElement('div');
      card.className = 'sc-newscard';
      card.style.background = 'rgb(230 140 40)'; card.style.color = 'rgb(20 20 30)';
      text('p', 'sc-newscard-kicker', 'Breaking news', card);
      text('p', 'sc-newscard-head', page.short, card);
      text('p', 'sc-newscard-sub', page.total ? page.have + ' of ' + page.total + ' in the library' + (n ? ' — ' + plural(n, 'film') + ' still at large' : ' — the full set') : 'Exclusive report', card);
      c.el.appendChild(card);
      if (card.animate) { card.animate([{ translate: '-50% 120vh', rotate: '-6deg' }, { translate: '-50% -50%', rotate: '-2deg' }], { duration: 800, easing: 'cubic-bezier(.2, .9, .3, 1.1)', fill: 'both' }); }
      var ticker = text('p', 'sc-ticker', 'TOP STORY TONIGHT · ' + (n ? page.missing.join(' · ') + ' · ' : '') + 'MORE AT ELEVEN · ', c.el);
      ticker.style.color = 'rgb(255 255 255)'; ticker.style.background = 'rgb(160 30 30)';
      if (ticker.animate) { ticker.animate([{ translate: '100vw 0' }, { translate: '-100% 0' }], { duration: 8000, easing: 'linear', fill: 'both' }); }
      window.setTimeout(c.finish, 4800);
    },

    // Spaceballs: a ridiculously long spaceship takes forever to scroll past overhead.
    longship: function () {
      var c = curtain({ max: 7000, background: 'radial-gradient(1px 1px at 20% 30%, white, transparent), radial-gradient(1px 1px at 70% 60%, white, transparent), radial-gradient(1px 1px at 40% 80%, white, transparent) 0 0 / 200px 200px, black' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var length = W * 6;
      var caption = text('p', 'sc-intro-caption', '', c.el);
      caption.style.color = 'rgb(230 230 240)'; caption.style.top = '80%';
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var x = W - t * W * 1.4, y = H * 0.35, hh = H * 0.22;
        g.fillStyle = 'rgb(150 155 165)'; g.fillRect(Math.max(-10, x), y, Math.min(length, W + 20), hh);
        g.fillStyle = 'rgb(110 115 125)';
        for (var p = Math.max(0, Math.floor(-x / 80)); p < Math.min(length / 80, (W - x) / 80 + 1); p++) {
          var px = x + p * 80;
          g.fillRect(px, y + hh * 0.2, 50, hh * 0.15); g.fillRect(px + 20, y + hh * 0.6, 40, hh * 0.12);
          g.fillStyle = 'rgba(255, 230, 150, 0.8)'; g.fillRect(px + 8, y + hh * 0.45, 6, 4); g.fillStyle = 'rgb(110 115 125)';
        }
        if (x > 0) { g.fillStyle = 'rgb(170 175 185)'; g.beginPath(); g.moveTo(x, y); g.lineTo(x - hh * 0.8, y + hh / 2); g.lineTo(x, y + hh); g.closePath(); g.fill(); }
        caption.textContent = t > 1.5 ? (t > 3.5 ? 'Still going…' : 'Any second now…') : '';
        if (t > 4.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 4.6) / 0.6)); }
        return t < 5.3;
      });
    },

    // The NeverEnding Story: an old book glows and its pages fly out, swirling into a vortex.
    pages: function () {
      var c = curtain({ max: 5500, background: 'radial-gradient(circle at 50% 55%, rgb(70 50 30), rgb(14 10 6))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var cx = W / 2, cy = H * 0.62, leaves = [];
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var glow = g.createRadialGradient(cx, cy, 0, cx, cy, H * 0.5);
        glow.addColorStop(0, 'rgba(255, 220, 140, ' + Math.min(0.6, t / 2) + ')'); glow.addColorStop(1, 'rgba(255, 220, 140, 0)');
        g.fillStyle = glow; g.fillRect(0, 0, W, H);
        var bw = Math.min(W, H) * 0.42, bh = bw * 0.62;
        g.fillStyle = 'rgb(110 40 30)'; g.fillRect(cx - bw / 2 - 8, cy - bh / 2 - 6, bw + 16, bh + 12);
        g.fillStyle = 'rgb(240 225 190)'; g.fillRect(cx - bw / 2, cy - bh / 2, bw, bh);
        g.strokeStyle = 'rgb(150 120 80)'; g.beginPath(); g.moveTo(cx, cy - bh / 2); g.lineTo(cx, cy + bh / 2); g.stroke();
        if (t > 0.8 && Math.random() < 0.7) { leaves.push({ a: Math.random() * Math.PI * 2, r: 0, spin: Math.random() * 6 }); }
        leaves.forEach(function (l) {
          l.r += 4; l.a += 0.06; l.spin += 0.2;
          var x = cx + Math.cos(l.a) * l.r, y = cy - bh / 2 - l.r * 0.5 + Math.sin(l.a) * l.r * 0.4;
          g.save(); g.translate(x, y); g.rotate(l.spin); g.scale(Math.cos(l.spin), 1);
          g.fillStyle = 'rgba(245, 232, 200, 0.95)'; g.fillRect(-14, -18, 28, 36);
          g.strokeStyle = 'rgba(120, 90, 60, 0.5)'; g.beginPath(); for (var k = 0; k < 4; k++) { g.moveTo(-10, -10 + k * 7); g.lineTo(10, -10 + k * 7); } g.stroke();
          g.restore();
        });
        if (t > 3.6) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.6) / 0.6)); }
        return t < 4.3;
      });
    },

    // The Polar Express: a steam train's headlight cutting through falling snow, steam billowing.
    train: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(14 20 40), rgb(30 40 70))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var flakes = [], steam = [];
      for (var i = 0; i < 260; i++) { flakes.push({ x: Math.random() * W, y: Math.random() * H, v: 1 + Math.random() * 2, r: 1 + Math.random() * 2.5 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var near = Math.min(1, t / 3.0), cx = W / 2, cy = H * 0.6, s = Math.min(W, H) * (0.08 + near * 0.32);
        var beam = g.createRadialGradient(cx, cy - s * 0.3, 0, cx, cy - s * 0.3, W * (0.3 + near * 0.6));
        beam.addColorStop(0, 'rgba(255, 245, 210, ' + (0.5 + near * 0.4) + ')'); beam.addColorStop(1, 'rgba(255, 245, 210, 0)');
        g.fillStyle = beam; g.fillRect(0, 0, W, H);
        g.fillStyle = 'rgb(16 16 22)';
        g.beginPath(); g.arc(cx, cy, s * 0.6, 0, Math.PI * 2); g.fill();
        g.fillRect(cx - s * 0.75, cy - s * 0.2, s * 1.5, s * 0.9);
        g.fillRect(cx - s * 0.15, cy - s * 1.1, s * 0.3, s * 0.5);
        g.fillStyle = 'rgba(255, 250, 220, 0.95)'; g.beginPath(); g.arc(cx, cy - s * 0.3, s * 0.16, 0, Math.PI * 2); g.fill();
        if (Math.random() < 0.6) { steam.push({ x: cx + (Math.random() - 0.5) * s * 0.2, y: cy - s * 1.1, r: s * 0.12, a: 0.5 }); }
        steam.forEach(function (p) { p.y -= 2; p.x += (Math.random() - 0.5) * 2 + 1; p.r += 1.5; p.a *= 0.97; g.fillStyle = 'rgba(220, 225, 235, ' + p.a + ')'; g.beginPath(); g.arc(p.x, p.y, p.r, 0, Math.PI * 2); g.fill(); });
        g.fillStyle = 'rgba(255, 255, 255, 0.9)';
        flakes.forEach(function (f) { f.y += f.v; f.x += Math.sin(f.y / 40) * 0.5; if (f.y > H) { f.y = -5; f.x = Math.random() * W; } g.beginPath(); g.arc(f.x, f.y, f.r, 0, Math.PI * 2); g.fill(); });
        if (t > 3.4) { c.el.style.opacity = String(Math.max(0, 1 - (t - 3.4) / 0.6)); }
        return t < 4.1;
      });
    },

    // Moana: ocean waves rise into a towering wall of sparkling water, which then parts.
    wave: function () {
      var c = curtain({ max: 5500, background: 'linear-gradient(to bottom, rgb(120 200 240), rgb(250 220 170))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var glints = [];
      for (var i = 0; i < 60; i++) { glints.push({ x: Math.random(), y: Math.random(), p: Math.random() * 6 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var rise = Math.min(1, t / 1.8), part = t > 2.4 ? Math.min(1, (t - 2.4) / 1.0) : 0, top = H * (0.85 - rise * 0.8);
        if (part) { c.el.style.background = 'rgba(250, 220, 170, ' + (1 - part) + ')'; }
        [-1, 1].forEach(function (side) {
          var shift = side * part * W * 0.6, from = side < 0 ? 0 : W / 2, to = side < 0 ? W / 2 : W;
          var water = g.createLinearGradient(0, top, 0, H);
          water.addColorStop(0, 'rgba(60, 180, 200, 0.95)'); water.addColorStop(1, 'rgba(10, 70, 120, 0.98)');
          g.fillStyle = water;
          g.beginPath(); g.moveTo(from + shift, H);
          for (var x = from; x <= to; x += 12) { g.lineTo(x + shift, top + Math.sin(x / 50 + t * 3) * 12); }
          g.lineTo(to + shift, H); g.closePath(); g.fill();
        });
        glints.forEach(function (gl) {
          var x = gl.x * W + (gl.x < 0.5 ? -1 : 1) * part * W * 0.6, y = top + gl.y * (H - top);
          g.fillStyle = 'rgba(255, 255, 255, ' + Math.max(0, Math.sin(t * 5 + gl.p)) * 0.8 + ')'; g.fillRect(x, y, 3, 3);
        });
        return t < 3.6;
      });
    },

    // Paddington: a little suitcase and hat, and a luggage label tied on with a note about the
    // collection.
    label: function () {
      var c = curtain({ max: 6500, background: 'linear-gradient(to bottom, rgb(130 110 90), rgb(80 64 50))' });
      var n = page.missing.length;
      var scene = document.createElement('div');
      scene.className = 'sc-luggage';
      scene.innerHTML = '<svg viewBox="0 0 300 220" aria-hidden="true">' +
        '<rect x="40" y="90" width="220" height="120" rx="12" fill="rgb(150 90 50)" stroke="rgb(90 50 24)" stroke-width="5"/>' +
        '<rect x="125" y="70" width="50" height="24" rx="8" fill="none" stroke="rgb(90 50 24)" stroke-width="7"/>' +
        '<rect x="40" y="140" width="220" height="10" fill="rgb(110 66 34)"/>' +
        '<path d="M90 92 Q130 40 170 40 Q210 40 230 70 L240 92 Z" fill="rgb(200 30 40)"/>' +
        '<ellipse cx="160" cy="92" rx="100" ry="12" fill="rgb(170 20 30)"/></svg>';
      c.el.appendChild(scene);
      var tag = document.createElement('div');
      tag.className = 'sc-tag';
      tag.style.background = 'rgb(240 225 190)'; tag.style.color = 'rgb(60 40 20)';
      text('p', null, 'Handle with care: one collection, travelling.', tag);
      text('p', null, page.total ? 'It has ' + page.have + ' of its ' + page.total + ' films' + (n ? ' and would like the other ' + n + '.' : ', and is very content.') : 'Thank you.', tag);
      c.el.appendChild(tag);
      if (tag.animate) { tag.animate([{ rotate: '-20deg', opacity: 0 }, { rotate: '8deg', opacity: 1, offset: 0.5 }, { rotate: '-4deg' }, { rotate: '2deg' }], { duration: 1600, delay: 600, easing: 'ease-out', fill: 'both' }); }
      window.setTimeout(c.finish, 5200);
    },
  };


  // ------------------------------------------------------------ genre intros (0.70.0)
  // Every collection or franchise page without an intro of its own gets a short one in the style
  // of its main genre (the server's data-mood, 0.60.0), or a plain cinema one -- built from the
  // page's own name, counts and posters. About two and a half seconds, so browsing doesn't drag.
  // (michael, 2026-10-03: "make intros for everything".)
  function genreTitle(c, cls, colour, sub) {
    var box = document.createElement('div');
    box.className = 'sc-gtitle ' + cls;
    box.style.color = colour;
    text('p', 'sc-gtitle-name', page.short, box);
    if (sub !== false) { text('p', 'sc-gtitle-sub', page.total ? page.have + ' of ' + page.total + ' in your library' : 'In your library', box); }
    c.el.appendChild(box);
    return box;
  }
  var GENRE = {
    // A cinema countdown leader, 3-2-1, then the title card.
    cinema: function () {
      var c = curtain({ max: 3600, background: 'rgb(16 14 12)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var title = null;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        if (t < 1.5) {
          var n = 3 - Math.floor(t / 0.5), sweep = (t % 0.5) / 0.5, cx = W / 2, cy = H / 2, R = Math.min(W, H) * 0.3;
          g.fillStyle = 'rgba(200, 190, 170, 0.15)'; g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, R, -Math.PI / 2, -Math.PI / 2 + sweep * Math.PI * 2); g.closePath(); g.fill();
          g.strokeStyle = 'rgba(220, 210, 190, 0.8)'; g.lineWidth = 3;
          g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.stroke(); g.beginPath(); g.arc(cx, cy, R * 0.85, 0, Math.PI * 2); g.stroke();
          g.beginPath(); g.moveTo(cx - R * 1.3, cy); g.lineTo(cx + R * 1.3, cy); g.moveTo(cx, cy - R * 1.3); g.lineTo(cx, cy + R * 1.3); g.stroke();
          g.fillStyle = 'rgb(235 225 205)'; g.font = '700 ' + Math.round(R * 0.9) + 'px Georgia, serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
          g.fillText(String(n), cx, cy);
        } else if (!title) {
          title = genreTitle(c, 'sc-gtitle--cinema', 'rgb(240 230 210)');
        }
        g.fillStyle = 'rgba(255, 240, 210, ' + (Math.random() * 0.05) + ')'; g.fillRect(0, 0, W, H);
        return t < 2.8;
      });
    },
    // Horror: flickering dark and a scratchy blood-red title, with a heartbeat thump.
    horror: function () {
      var c = curtain({ max: 3600, background: 'black' });
      var title = genreTitle(c, 'sc-gtitle--horror', 'rgb(190 20 20)');
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height, beat = 0;
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        title.style.opacity = Math.random() > 0.15 ? String(Math.min(1, t / 0.6)) : '0.1';
        if (Math.floor(t / 0.8) > beat) { beat = Math.floor(t / 0.8); shakePage(4, 160); }
        g.strokeStyle = 'rgba(200, 200, 200, 0.12)'; g.lineWidth = 1;
        for (var s = 0; s < 4; s++) { var x = Math.random() * W; g.beginPath(); g.moveTo(x, 0); g.lineTo(x + (Math.random() - 0.5) * 20, H); g.stroke(); }
        var edge = g.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.2, W / 2, H / 2, Math.max(W, H) * 0.7);
        edge.addColorStop(0, 'rgba(0, 0, 0, 0)'); edge.addColorStop(1, 'rgba(60, 0, 0, 0.6)');
        g.fillStyle = edge; g.fillRect(0, 0, W, H);
        return t < 2.6;
      });
    },
    // Sci-fi: a burst of hyperspace streaks, then the title glowing with a scanline.
    scifi: function () {
      var c = curtain({ max: 3600, background: 'rgb(2 4 12)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var stars = [], title = null;
      for (var i = 0; i < 220; i++) { stars.push({ a: Math.random() * Math.PI * 2, d: Math.random() * 0.2 }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var speed = t < 1.0 ? t : Math.max(0, 2 - t);
        g.strokeStyle = 'rgba(200, 225, 255, 0.85)'; g.lineWidth = 1.5; g.beginPath();
        stars.forEach(function (s) {
          s.d += 0.004 + speed * 0.05;
          if (s.d > 1.2) { s.d = Math.random() * 0.1; }
          var r1 = s.d * Math.hypot(W, H) * 0.6, r2 = r1 * (1 - speed * 0.25);
          g.moveTo(W / 2 + Math.cos(s.a) * r2, H / 2 + Math.sin(s.a) * r2); g.lineTo(W / 2 + Math.cos(s.a) * r1, H / 2 + Math.sin(s.a) * r1);
        });
        g.stroke();
        if (t > 1.0 && !title) { title = genreTitle(c, 'sc-gtitle--scifi', 'rgb(160 220 255)'); }
        if (title) { g.fillStyle = 'rgba(160, 220, 255, 0.08)'; g.fillRect(0, (t * 400) % H, W, 3); }
        return t < 2.6;
      });
    },
    // Animation: bright circles pop in, then the title bounces in.
    animation: function () {
      var c = curtain({ max: 3600, background: 'rgb(255 236 170)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var palette = ['rgb(255 100 120)', 'rgb(80 180 255)', 'rgb(120 220 120)', 'rgb(255 180 60)', 'rgb(180 120 255)'], dots = [];
      for (var i = 0; i < 24; i++) { dots.push({ x: Math.random() * W, y: Math.random() * H, r: 20 + Math.random() * 60, at: Math.random() * 0.8, c: palette[i % 5] }); }
      var title = genreTitle(c, 'sc-gtitle--animation', 'rgb(60 40 120)');
      if (title.animate) { title.animate([{ scale: 0, rotate: '-10deg' }, { scale: 1.2, rotate: '4deg', offset: 0.6 }, { scale: 0.95, offset: 0.8 }, { scale: 1, rotate: '0deg' }], { duration: 700, delay: 600, easing: 'ease-out', fill: 'both' }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        dots.forEach(function (d) {
          var p = Math.min(1, Math.max(0, (t - d.at) / 0.3)), s = p < 1 ? p * 1.2 : 1 + Math.sin((t - d.at) * 6) * 0.05;
          g.fillStyle = d.c; g.beginPath(); g.arc(d.x, d.y, d.r * s, 0, Math.PI * 2); g.fill();
        });
        return t < 2.6;
      });
    },
    // Western: a wanted poster -- the collection's poster, and the reward in films.
    western: function () {
      var c = curtain({ max: 3800, background: 'linear-gradient(to bottom, rgb(150 100 60), rgb(90 56 30))' });
      var n = page.missing.length;
      var bill = document.createElement('div');
      bill.className = 'sc-wanted';
      bill.style.background = 'rgb(232 210 160)'; bill.style.color = 'rgb(70 40 20)';
      text('p', 'sc-wanted-head', 'Wanted', bill);
      var pic = document.createElement('span');
      pic.className = 'sc-wanted-pic';
      pic.style.background = page.posters.length ? 'url("' + bigger(page.posters[0]).replace(/"/g, '%22') + '") center / cover' : 'rgb(120 90 60)';
      pic.style.filter = 'sepia(0.8) contrast(1.1)';
      bill.appendChild(pic);
      text('p', 'sc-wanted-name', page.short, bill);
      text('p', 'sc-wanted-reward', n ? 'Reward: ' + plural(n, 'film') : 'Captured: every one', bill);
      c.el.appendChild(bill);
      if (bill.animate) { bill.animate([{ translate: '-50% -150%', rotate: '-8deg' }, { translate: '-50% -50%', rotate: '-2deg' }], { duration: 600, easing: 'cubic-bezier(.2, .9, .3, 1.2)', fill: 'both' }); }
      window.setTimeout(c.finish, 2800);
    },
    // War: smoke and crossing searchlights, and a stencilled title.
    war: function () {
      var c = curtain({ max: 3600, background: 'linear-gradient(to bottom, rgb(30 32 30), rgb(60 58 50))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var title = genreTitle(c, 'sc-gtitle--war', 'rgb(220 210 180)');
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        [[0.2, 1], [0.8, -1]].forEach(function (l) {
          var a = -Math.PI / 2 + Math.sin(t * 1.5) * 0.5 * l[1], x = W * l[0];
          var beam = g.createLinearGradient(x, H, x + Math.cos(a) * H, H + Math.sin(a) * H);
          beam.addColorStop(0, 'rgba(255, 250, 220, 0.35)'); beam.addColorStop(1, 'rgba(255, 250, 220, 0)');
          g.fillStyle = beam; g.beginPath(); g.moveTo(x - 10, H); g.lineTo(x + Math.cos(a - 0.08) * H * 1.3, H + Math.sin(a - 0.08) * H * 1.3); g.lineTo(x + Math.cos(a + 0.08) * H * 1.3, H + Math.sin(a + 0.08) * H * 1.3); g.lineTo(x + 10, H); g.closePath(); g.fill();
        });
        for (var s = 0; s < 6; s++) { var puff = g.createRadialGradient(W * (s / 5), H * 0.85, 0, W * (s / 5), H * 0.85, 160); puff.addColorStop(0, 'rgba(120, 115, 100, 0.3)'); puff.addColorStop(1, 'rgba(120, 115, 100, 0)'); g.fillStyle = puff; g.fillRect(0, 0, W, H); }
        title.style.opacity = String(Math.min(1, t / 0.5));
        return t < 2.6;
      });
    },
    // Fantasy: sparkles swirl inward and the title glows gold.
    fantasy: function () {
      var c = curtain({ max: 3600, background: 'radial-gradient(circle at 50% 45%, rgb(50 30 80), rgb(10 6 20))' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var sparks = [], title = null;
      for (var i = 0; i < 160; i++) { sparks.push({ a: Math.random() * Math.PI * 2, r: Math.max(W, H) * (0.4 + Math.random() * 0.4) }); }
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        var pull = Math.min(1, t / 1.2);
        sparks.forEach(function (s) {
          var a = s.a + t * 2, r = s.r * (1 - pull * 0.92);
          g.fillStyle = 'rgba(255, 225, 140, ' + (0.4 + Math.random() * 0.6) + ')'; g.fillRect(W / 2 + Math.cos(a) * r, H / 2 + Math.sin(a) * r * 0.6, 2.5, 2.5);
        });
        if (t > 1.1 && !title) { title = genreTitle(c, 'sc-gtitle--fantasy', 'rgb(255 225 150)'); }
        return t < 2.6;
      });
    },
    // Crime: rain and venetian-blind shadows, the title typed out.
    crime: function () {
      var c = curtain({ max: 3800, background: 'rgb(18 20 24)' });
      var canvas = c.canvas(), g = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
      var drops = [];
      for (var i = 0; i < 200; i++) { drops.push({ x: Math.random() * W, y: Math.random() * H, v: 10 + Math.random() * 8 }); }
      var title = genreTitle(c, 'sc-gtitle--crime', 'rgb(230 225 210)', false);
      var nameEl = title.querySelector('.sc-gtitle-name');
      typeOut(nameEl, page.short, 60);
      run(c, function (t) {
        g.clearRect(0, 0, W, H);
        g.fillStyle = 'rgba(255, 240, 210, 0.08)';
        for (var b = 0; b < 12; b++) { g.fillRect(0, H * 0.1 + b * H * 0.07, W, H * 0.035); }
        g.strokeStyle = 'rgba(170, 185, 210, 0.35)'; g.lineWidth = 1; g.beginPath();
        drops.forEach(function (d) { d.y += d.v; if (d.y > H) { d.y = -20; d.x = Math.random() * W; } g.moveTo(d.x, d.y); g.lineTo(d.x - 2, d.y - 14); });
        g.stroke();
        return t < 2.8;
      });
    },
  };

  // A collection's or franchise's own intro if it has one, else its genre's; nothing on other
  // pages with a banner (a director's).
  var which = introFor(name);
  var mood = heading.getAttribute('data-mood');
  var play = which ? INTROS[which[1]] : (SET_PAGE.test(window.location.pathname) ? GENRE[GENRE[mood] ? mood : 'cinema'] : null);
  if (!play || reduce) { return; }

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
