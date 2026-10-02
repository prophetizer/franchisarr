// Showcase's cinema pieces (0.60.0), loaded after showcase.js and showcase-intros.js:
//   ticket     -- adding a film prints a ticket stub in the dialog, and its stub tears off
//   marquee    -- a complete collection's or franchise's banner gets chasing marquee bulbs
//   credits    -- the foot of a detail page rolls up like end credits (The End / To be continued)
//   beam       -- a projector's cone of light over the home spotlight, flickering on at load
//   moods      -- the set's main genre sets the banner's atmosphere (stars, rain, dust, fog...)
//   shelf      -- the Collections and Franchises grids can be shown as box-set spines on a shelf
//   lightbox   -- an owned or upcoming film's poster, or the page's own, opens large
//   scenes     -- empty and finished pages get a small scene instead of bare words
// "Reduce motion" keeps them all still: no printing, chasing, rolling, flicker or drifting.
(function () {
  'use strict';

  var root = document.documentElement;
  if (root.dataset.look !== 'showcase') { return; }
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var phone = window.matchMedia('(pointer: coarse), (max-width: 767px)').matches;
  // Colours that are the object's own rather than the theme's -- a bulb is warm whatever the
  // theme -- set here, as showcase.css holds no colour of its own (test_theming).
  root.style.setProperty('--sc-bulb', 'rgb(255 214 128)');
  root.style.setProperty('--sc-paper', 'rgb(240 226 196)');
  root.style.setProperty('--sc-paper-ink', 'rgb(118 34 30)');
  root.style.setProperty('--sc-wood', 'rgb(96 64 38)');
  root.style.setProperty('--sc-wood-hi', 'rgb(150 104 64)');
  root.style.setProperty('--sc-beam', 'rgb(255 246 222)');

  function make(tag, className, text) {
    var el = document.createElement(tag);
    if (className) { el.className = className; }
    if (text != null) { el.textContent = text; }
    return el;
  }
  // An element's words as a reader sees them: a rolled number's digit columns left out.
  function plain(el) {
    if (!el) { return ''; }
    var copy = el.cloneNode(true);
    copy.querySelectorAll('.sc-odo').forEach(function (odo) { odo.remove(); });
    return copy.textContent.replace(/\s+/g, ' ').trim();
  }
  function random(from, to) { return from + Math.random() * (to - from); }
  // Specks for a layer: each with its own place, size, pace and head start.
  function specks(layer, count, size, pace) {
    for (var n = 0; n < count; n++) {
      var s = make('span');
      var t = random(pace[0], pace[1]);
      s.style.setProperty('--sc-x', random(0, 100).toFixed(1) + '%');
      s.style.setProperty('--sc-y', random(0, 100).toFixed(1) + '%');
      s.style.setProperty('--sc-size', random(size[0], size[1]).toFixed(1) + 'px');
      s.style.setProperty('--sc-t', t.toFixed(2) + 's');
      s.style.setProperty('--sc-wait', (-Math.random() * t).toFixed(2) + 's');   // already on its way
      s.style.setProperty('--sc-dx', random(-3, 3).toFixed(1) + 'rem');
      layer.appendChild(s);
    }
    return layer;
  }

  // ------------------------------------------------------------ ticket
  // The add dialog says "Added"; Showcase hands you a ticket for it. It prints down out of the
  // dialog's header, and a moment later its stub tears along the perforation and drops away.
  var serial = function () { return ('00000' + Math.floor(Math.random() * 1e6)).slice(-6); };
  var printTicket = function (dialog) {
    var title = dialog.getAttribute('data-ticket');
    var article = dialog.querySelector('article');
    if (!title || !article || article.querySelector('.sc-ticket')) { return; }
    var ticket = make('div', 'sc-ticket' + (reduce ? ' is-still' : ''));
    ticket.setAttribute('aria-hidden', 'true');   // the dialog's own words say it for a reader
    var main = make('div', 'sc-ticket-main');
    main.appendChild(make('small', null, dialog.hasAttribute('data-ticket-requested') ? 'Requested · admit one' : 'Admit one'));
    main.appendChild(make('strong', null, title));
    main.appendChild(make('span', null, (dialog.getAttribute('data-ticket-to') || '') + ' · No. ' + serial()));
    var stub = make('div', 'sc-ticket-stub');
    stub.appendChild(make('small', null, 'Admit'));
    stub.appendChild(make('b', null, 'One'));
    ticket.appendChild(main);
    ticket.appendChild(stub);
    var header = article.querySelector('header');
    article.insertBefore(ticket, header ? header.nextSibling : article.firstChild);
    if (!reduce) {
      setTimeout(function () { ticket.classList.add('is-torn'); }, 1700);
      stub.addEventListener('animationend', function () { ticket.classList.add('is-gone'); });
    }
  };
  document.querySelectorAll('dialog[data-ticket]').forEach(printTicket);

  // ------------------------------------------------------------ marquee
  // Bulbs round a complete set's banner, in three groups lit in turn: the classic chase. Laid
  // out along its edges by count, so they're redrawn (cheaply) when the banner changes size.
  var bulbsFor = function (band) {
    var frame = make('span', 'sc-marquee');
    frame.setAttribute('aria-hidden', 'true');
    band.appendChild(frame);
    var lay = function () {
      var w = band.offsetWidth, h = band.offsetHeight;
      if (!w || !h) { return; }
      var gap = phone ? 30 : 24;
      var across = Math.max(2, Math.round(w / gap)), down = Math.max(2, Math.round(h / gap));
      // A banner that runs from edge to edge of the window has no sides to light.
      var sides = band.getBoundingClientRect().left > 4;
      var spots = [], i;
      for (i = 0; i < across; i++) { spots.push([i / across * 100, 0]); }
      for (i = 0; sides && i < down; i++) { spots.push([100, i / down * 100]); }
      for (i = 0; i < across; i++) { spots.push([100 - i / across * 100, 100]); }
      for (i = 0; sides && i < down; i++) { spots.push([0, 100 - i / down * 100]); }
      frame.textContent = '';
      spots.forEach(function (spot, n) {
        var bulb = make('i');
        bulb.style.left = spot[0].toFixed(2) + '%';
        bulb.style.top = spot[1].toFixed(2) + '%';
        bulb.style.setProperty('--sc-phase', String(n % 3));
        frame.appendChild(bulb);
      });
    };
    lay();
    if ('ResizeObserver' in window) {
      var last = '';
      new ResizeObserver(function () {
        var size = band.offsetWidth + 'x' + band.offsetHeight;
        if (size !== last) { last = size; lay(); }
      }).observe(band);
    }
  };
  document.querySelectorAll('.collection-heading[data-complete]').forEach(bulbsFor);

  // ------------------------------------------------------------ end credits
  // They roll when they come on screen, at a reading pace, and stop with The End (or To be
  // continued) in the middle of the window; ↺ rolls them again. Still: the list, standing.
  var credits = document.querySelector('.end-credits');
  if (credits) {
    var win = credits.querySelector('.end-credits-window');
    var roll = credits.querySelector('.end-credits-roll');
    var end = credits.querySelector('.end-credits-end');
    var again = credits.querySelector('.end-credits-replay');
    if (reduce || !('IntersectionObserver' in window)) {
      credits.classList.add('is-still');
    } else {
      var play = function () {
        // The roll stops with the end card centred in the window (the roll is its offsetParent).
        var stop = end ? end.offsetTop + end.offsetHeight / 2 - win.clientHeight / 2 : roll.offsetHeight;
        var distance = win.clientHeight + Math.max(0, stop);
        roll.style.setProperty('--sc-from', win.clientHeight + 'px');
        roll.style.setProperty('--sc-to', -Math.max(0, stop) + 'px');
        roll.style.setProperty('--sc-roll', (distance / (phone ? 45 : 55)).toFixed(1) + 's');
        credits.classList.remove('is-rolling');
        void roll.offsetWidth;   // restart the animation
        credits.classList.add('is-rolling');
      };
      roll.addEventListener('animationend', function () { if (again) { again.hidden = false; } });
      if (again) { again.addEventListener('click', function () { again.hidden = true; play(); }); }
      credits.classList.add('is-waiting');
      var seen = new IntersectionObserver(function (entries) {
        if (entries.some(function (e) { return e.isIntersecting; })) { seen.disconnect(); play(); }
      }, { threshold: 0.35 });
      seen.observe(credits);
    }
  }

  // ------------------------------------------------------------ projector beam
  // A cone of light from the top corner over the home page's spotlight, with dust turning in it.
  var band = document.querySelector('.spotlight-band');
  if (band) {
    var beam = make('div', 'sc-beam' + (reduce ? ' is-still' : ''));
    beam.setAttribute('aria-hidden', 'true');
    beam.appendChild(make('span', 'sc-beam-cone'));
    if (!reduce) { beam.appendChild(specks(make('span', 'sc-beam-dust'), phone ? 8 : 18, [1.5, 4], [10, 20])); }
    band.insertBefore(beam, band.querySelector('.spotlight-trailer, .spotlight-dots'));
  }

  // ------------------------------------------------------------ genre moods
  // A set that's mostly one genre (the server decides: data-mood) gives its banner that genre's
  // weather, in place of the plain motes; the picture's grade changes to suit (showcase.css).
  var MOODS = {
    horror: { ink: 'rgb(205 214 224)', count: [3, 3], size: [0, 0], pace: [26, 44] },       // fog
    animation: { ink: 'rgb(255 255 255)', count: [12, 6], size: [8, 22], pace: [7, 12] },  // bubbles
    western: { ink: 'rgb(236 198 140)', count: [26, 10], size: [1.5, 3.5], pace: [9, 16] },  // dust
    war: { ink: 'rgb(255 132 52)', count: [22, 10], size: [2, 4.5], pace: [4, 8] },          // embers
    scifi: { ink: 'rgb(226 238 255)', count: [56, 24], size: [1, 2.6], pace: [2.5, 6] },      // stars
    fantasy: { ink: 'rgb(255 226 150)', count: [16, 8], size: [8, 16], pace: [3, 6] },        // sparkles
    crime: { ink: 'rgb(186 202 224)', count: [44, 20], size: [14, 30], pace: [0.6, 1.1] },    // rain
  };
  var moody = document.querySelector('.collection-heading[data-mood]');
  var mood = moody && MOODS[moody.dataset.mood];
  if (mood) {
    root.dataset.mood = moody.dataset.mood;
    root.style.setProperty('--sc-mood-ink', mood.ink);
    if (!reduce && moody.classList.contains('has-backdrop')) {
      var weather = specks(make('div', 'sc-mood sc-mood--' + moody.dataset.mood), mood.count[phone ? 1 : 0], mood.size, mood.pace);
      weather.setAttribute('aria-hidden', 'true');
      if (moody.dataset.mood === 'fantasy') {
        weather.querySelectorAll('span').forEach(function (s) { s.textContent = '✦'; });
      }
      if (moody.dataset.mood === 'scifi' && !phone) {
        weather.appendChild(make('b', 'sc-shooting'));   // now and then, a shooting star
      }
      moody.classList.add('sc-moody');
      moody.appendChild(weather);
    }
  }

  // ------------------------------------------------------------ shelf
  // Collections and Franchises as box sets on a shelf: one spine per card, its poster as the
  // spine's art, its name down it, how complete it is along the foot. Pointing pulls one out.
  // A per-browser choice, like the VHS game, kept with the page's look rather than as a setting.
  var shelfKey = 'sc-shelf';
  var shelfOn = function () { try { return window.localStorage.getItem(shelfKey) === 'on'; } catch (e) { return false; } };
  var hash = function (text) { var h = 0; for (var i = 0; i < text.length; i++) { h = (h * 31 + text.charCodeAt(i)) | 0; } return Math.abs(h); };
  document.querySelectorAll('.collection-grid[data-shelf]').forEach(function (grid) {
    var shelf = null;
    var build = function () {
      shelf = make('div', 'sc-shelf');
      grid.querySelectorAll(':scope > .collection-card').forEach(function (card) {
        var link = card.querySelector('header a');
        if (!link) { return; }
        var name = plain(link);
        var img = card.querySelector('.collection-poster img');
        var bar = card.querySelector('progress.completeness');
        var spine = make('a', 'sc-spine');
        spine.href = link.href;
        spine.title = name + (bar ? ' — ' + bar.getAttribute('aria-label') : '');
        spine.setAttribute('aria-label', spine.title);
        if (img) { spine.style.setProperty('--sc-art', 'url("' + (img.currentSrc || img.src).replace(/"/g, '%22') + '")'); }
        if (bar) { spine.style.setProperty('--sc-pct', Math.round(bar.value / (bar.max || 1) * 100) + '%'); }
        var h = hash(name);
        spine.style.setProperty('--sc-w', (2.7 + (h % 9) / 10).toFixed(1) + 'rem');
        spine.style.setProperty('--sc-h', (88 + (h >> 4) % 13) + '%');
        spine.appendChild(make('span', 'sc-spine-name', name.replace(/\s+collection$/i, '')));   // the page says that
        var mark = card.querySelector('.sc-intro-mark');   // showcase-intros.js marked the card first
        if (mark) { spine.appendChild(mark.cloneNode(true)); }
        shelf.appendChild(spine);
      });
      grid.parentNode.insertBefore(shelf, grid.nextSibling);
    };
    var show = function (on, button) {
      if (on && !shelf) { build(); }
      grid.hidden = on;
      if (shelf) { shelf.hidden = !on; }
      button.setAttribute('aria-pressed', on ? 'true' : 'false');
      button.textContent = on ? '▦ Grid' : '📚 Shelf';
    };
    var controls = grid.parentNode.querySelector('.gap-controls');
    var button = make('button', 'secondary outline sc-shelf-toggle');
    button.type = 'button';
    button.title = 'Show these as box sets on a shelf, or as cards';
    button.addEventListener('click', function () {
      var on = button.getAttribute('aria-pressed') !== 'true';
      try { window.localStorage.setItem(shelfKey, on ? 'on' : 'off'); } catch (e) { /* just this visit, then */ }
      show(on, button);
    });
    if (controls) { controls.appendChild(button); } else { grid.parentNode.insertBefore(button, grid); }
    show(shelfOn(), button);
  });

  // ------------------------------------------------------------ lightbox
  // A poster that doesn't already do something when pressed -- an owned, upcoming or folded
  // film's, and the page's own -- opens large over a blur of itself. TMDb's bigger copy is
  // swapped in when it arrives. Click, Esc or a swipe down closes it; a mouse tilts it.
  var POSTERS = '.film-tile:not([data-about]) .collection-poster img, img.collection-heading-poster';
  var box = null;
  var bigger = function (src) { return src.replace(/\/t\/p\/w\d+\//, '/t/p/w780/'); };
  var captionOf = function (img) {
    var tile = img.closest('.film-tile');
    if (tile) {
      // A collection's tiles have the year under the title; a franchise's, beside it.
      var year = tile.querySelector('.collection-counts span') || tile.querySelector('header small.muted');
      return [plain(tile.querySelector('.film-title')), year ? plain(year).replace(/^\((.*)\)$/, '$1') : ''];
    }
    var heading = img.closest('.collection-heading');
    var h1 = heading && heading.querySelector('h1');
    var logo = h1 && h1.querySelector('img');
    return [logo ? logo.alt : plain(h1), ''];
  };
  var openBox = function (img) {
    if (!box) {
      box = make('dialog', 'sc-lightbox');
      box.setAttribute('aria-label', 'Poster');
      box.innerHTML = '<img class="sc-lightbox-glow" alt="" aria-hidden="true"><figure><img class="sc-lightbox-poster" alt="">' +
        '<figcaption><strong></strong> <small class="muted"></small></figcaption></figure>' +
        '<button type="button" class="sc-lightbox-close secondary outline" aria-label="Close">✕</button>';
      document.body.appendChild(box);
      box.addEventListener('click', function () { box.close(); });
      var startY = null;
      box.addEventListener('pointerdown', function (e) { startY = e.clientY; });
      box.addEventListener('pointerup', function (e) {
        if (startY !== null && e.clientY - startY > 70) { box.close(); }
        startY = null;
      });
      if (!reduce && !phone) {
        box.addEventListener('pointermove', function (e) {
          box.style.setProperty('--sc-ly', ((e.clientX / window.innerWidth - 0.5) * 10).toFixed(2) + 'deg');
          box.style.setProperty('--sc-lx', ((0.5 - e.clientY / window.innerHeight) * 10).toFixed(2) + 'deg');
        });
      }
    }
    var small = img.currentSrc || img.src;
    var poster = box.querySelector('.sc-lightbox-poster');
    var words = captionOf(img);
    box.querySelector('.sc-lightbox-glow').src = small;
    poster.src = small;
    poster.alt = words[0] ? 'Poster of ' + words[0] : 'Poster';
    box.querySelector('figcaption strong').textContent = words[0];
    box.querySelector('figcaption small').textContent = words[1];
    var large = bigger(small);
    if (large !== small) {
      var loader = new Image();
      loader.onload = function () { if (poster.src === small) { poster.src = large; } };
      loader.src = large;
    }
    if (typeof box.showModal === 'function') { box.showModal(); } else { box.setAttribute('open', ''); }
  };
  document.addEventListener('click', function (event) {
    var img = event.target.closest && event.target.closest(POSTERS);
    if (img && !event.defaultPrevented) { event.preventDefault(); openBox(img); }
  });
  var heroPoster = document.querySelector('img.collection-heading-poster');
  if (heroPoster) {
    heroPoster.tabIndex = 0;
    heroPoster.setAttribute('role', 'button');
    heroPoster.setAttribute('aria-label', 'Show the poster larger');
    heroPoster.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openBox(heroPoster); }
    });
  }

  // ------------------------------------------------------------ scenes
  // Words like "Nothing missing" or "Nothing scanned yet" get a little scene above them: an usher
  // sweeping a torch over empty seats (finished), a theatre's ghost light on a bare stage
  // (nothing found), an empty reel turning (nothing yet). The markup marks which, with
  // data-scene on the words' own element, or on a hidden span inside them.
  var seats = '';
  for (var r = 0; r < 3; r++) {
    for (var c = 0; c < 7; c++) {
      seats += '<rect x="' + (14 + c * 20 + r * 4) + '" y="' + (58 + r * 15) + '" width="15" height="11" rx="3"/>';
    }
  }
  var SCENES = {
    usher: '<svg viewBox="0 0 240 110"><g class="sc-scene-seats" fill="currentColor" opacity="0.45">' + seats + '</g>' +
      '<g class="sc-scene-torch"><polygon points="196,60 40,40 60,96" class="sc-scene-light"/></g>' +
      '<g fill="currentColor"><circle cx="205" cy="34" r="7"/><rect x="198" y="28" width="14" height="4" rx="1.5"/>' +
      '<rect x="198" y="42" width="15" height="30" rx="5"/><rect x="199" y="72" width="5" height="22" rx="2"/>' +
      '<rect x="207" y="72" width="5" height="22" rx="2"/><rect x="190" y="56" width="10" height="5" rx="2"/></g>' +
      '<rect x="186" y="55" width="8" height="7" rx="1.5" class="sc-scene-lamp"/></svg>',
    ghostlight: '<svg viewBox="0 0 240 110"><ellipse cx="120" cy="100" rx="105" ry="7" fill="currentColor" opacity="0.25"/>' +
      '<circle cx="120" cy="30" r="34" class="sc-scene-halo"/>' +
      '<g fill="none" stroke="currentColor" stroke-width="2"><path d="M120 44 V98 M108 98 H132"/>' +
      '<path d="M111 22 Q120 8 129 22 V36 H111 Z" opacity="0.7"/></g>' +
      '<circle cx="120" cy="29" r="6" class="sc-scene-bulb"/>' +
      '<g class="sc-scene-moth"><circle cx="142" cy="29" r="1.6" fill="currentColor"/></g></svg>',
    reel: '<svg viewBox="0 0 240 110"><g class="sc-scene-reel" fill="none" stroke="currentColor" stroke-width="3">' +
      '<circle cx="90" cy="52" r="40"/><circle cx="90" cy="52" r="7"/>' +
      '<circle cx="90" cy="27" r="10"/><circle cx="114" cy="45" r="10"/><circle cx="105" cy="73" r="10"/>' +
      '<circle cx="75" cy="73" r="10"/><circle cx="66" cy="45" r="10"/></g>' +
      '<path d="M128 60 C150 66 150 96 176 96 S214 84 226 98" fill="none" stroke="currentColor" stroke-width="9" opacity="0.4"/>' +
      '<path d="M128 60 C150 66 150 96 176 96 S214 84 226 98" fill="none" class="sc-scene-sprockets" stroke-width="3" stroke-dasharray="3 5"/></svg>',
  };
  var stage = function (scope) {
    (scope || document).querySelectorAll('[data-scene]').forEach(function (mark) {
      var host = mark.hidden ? mark.parentElement : mark;
      var art = SCENES[mark.getAttribute('data-scene')];
      if (!art || !host || host.dataset.scened) { return; }
      host.dataset.scened = 'yes';
      var scene = make('div', 'sc-scene sc-scene--' + mark.getAttribute('data-scene'));
      scene.setAttribute('aria-hidden', 'true');
      scene.innerHTML = art;
      if (host.tagName === 'ARTICLE') { host.insertBefore(scene, host.firstChild); }
      else { host.parentNode.insertBefore(scene, host); }
    });
  };
  stage();

  // htmx brings new content -- a result dialog, a re-rendered list, search results.
  document.addEventListener('htmx:afterSwap', function (event) {
    var target = event.target;
    if (!target || !target.querySelectorAll) { return; }
    target.querySelectorAll('dialog[data-ticket]').forEach(printTicket);
    stage(target);
  });
})();
