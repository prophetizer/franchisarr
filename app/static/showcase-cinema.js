// Showcase's cinema pieces (0.60.0), loaded after showcase.js and showcase-intros.js:
//   ticket     -- adding a film prints a ticket stub in the dialog, and its stub tears off
//   credits    -- the foot of a detail page rolls up like end credits (The End / To be continued)
//   beam       -- a projector's cone of light over the home spotlight, flickering on at load
//   moods      -- the set's main genre grades the banner's picture
//   shelf      -- the Collections and Franchises grids can be shown as box-set spines on a shelf
//   lightbox   -- an owned or upcoming film's poster, or the page's own, opens large
//   scenes     -- empty and finished pages get a small scene instead of bare words
// and since 0.62.0:
//   colour     -- a set's poster is black and white, colour risen up it as far as you own
//   box        -- a detail page's poster stands as a 3D box set, turning with the pointer
//   flaps      -- a coming-soon film counts down its days on a split-flap board
//   punch      -- a watched film's poster has a ticket-punch hole where the tag was
//   screens    -- a TV show's poster sits in an old CRT screen
//   house      -- playing a trailer dims the room; closing it brings the lights back up
//   projector  -- a running scan plays on a projector into a countdown leader
//   stubs      -- Activity's adds as a roll of ticket stubs
// "Reduce motion" keeps them all still: no printing, rolling or flicker.
// The marquee bulbs, the banner weather and the beam's dust went in 0.70.1, michael's call.
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
  // A cone of light from the top corner over the home page's spotlight.
  var band = document.querySelector('.spotlight-band');
  if (band) {
    var beam = make('div', 'sc-beam' + (reduce ? ' is-still' : ''));
    beam.setAttribute('aria-hidden', 'true');
    beam.appendChild(make('span', 'sc-beam-cone'));
    band.insertBefore(beam, band.querySelector('.spotlight-trailer, .spotlight-dots'));
  }

  // ------------------------------------------------------------ genre moods
  // A set that's mostly one genre (the server decides: data-mood) has its banner's picture graded
  // to suit (showcase.css).
  var moody = document.querySelector('.collection-heading[data-mood]');
  if (moody) { root.dataset.mood = moody.dataset.mood; }

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

  // ------------------------------------------------------------ colour fills as you collect (0.62.0)
  // A set's poster is black and white with colour risen up it as far as you own: a coloured copy
  // over a greyscale one, cut off at the owned share, rising into place as the page opens. A
  // complete set's poster is all colour.
  var fillPoster = function (img, host, share) {
    if (!img || img.tagName !== 'IMG' || !(share < 1) || host.querySelector(':scope > .sc-colour')) { return; }
    var colour = img.cloneNode(false);
    colour.className = 'sc-colour';
    colour.alt = '';
    colour.removeAttribute('loading');
    colour.setAttribute('aria-hidden', 'true');
    host.classList.add('sc-filling');
    img.classList.add('sc-grey');
    host.appendChild(colour);
    var pct = (Math.max(0, share) * 100).toFixed(1) + '%';
    if (reduce) { colour.style.setProperty('--sc-fill', pct); return; }
    setTimeout(function () { colour.style.setProperty('--sc-fill', pct); }, 60);   // after a first paint at none
  };
  var fillCards = function (scope) {
    scope.querySelectorAll('.collection-card:not(.film-tile)').forEach(function (card) {
      var bar = card.querySelector('progress.completeness');
      var poster = card.querySelector('.collection-poster');
      if (bar && poster) { fillPoster(poster.querySelector(':scope > img'), poster, bar.value / (bar.max || 1)); }
    });
  };
  fillCards(document);

  // ------------------------------------------------------------ 3D box set (0.62.0)
  // A detail page's poster stands as a box set: the poster its front, a darker strip of the same
  // art its spine, turned a little and following the pointer. It holds the colour fill too.
  var heading = document.querySelector('.collection-heading');
  var face = heading && (heading.querySelector('.sc-holo-wrap') || heading.querySelector('.collection-heading-poster'));
  if (face) {
    var art = face.tagName === 'IMG' ? face : face.querySelector('img');
    var boxSet = make('span', 'sc-box');
    var turn = make('span', 'sc-box-turn');
    var spine = make('span', 'sc-box-spine');
    var front = make('span', 'sc-box-front');
    spine.setAttribute('aria-hidden', 'true');
    if (art) { spine.style.setProperty('--sc-art', 'url("' + (art.currentSrc || art.src).replace(/"/g, '%22') + '")'); }
    face.parentNode.insertBefore(boxSet, face);
    boxSet.appendChild(turn);
    turn.appendChild(spine);
    turn.appendChild(front);
    front.appendChild(face);
    var have = parseInt(heading.getAttribute('data-have'), 10), of = parseInt(heading.getAttribute('data-of'), 10);
    if (face.tagName === 'IMG' && of > 0) { fillPoster(face, front, have / of); }
    if (!reduce && !phone) {
      heading.addEventListener('pointermove', function (event) {
        var rect = heading.getBoundingClientRect();
        var x = (event.clientX - rect.left) / rect.width, y = (event.clientY - rect.top) / rect.height;
        turn.style.setProperty('--sc-by', (6 + x * 26).toFixed(1) + 'deg');
        turn.style.setProperty('--sc-bx', ((0.5 - y) * 8).toFixed(1) + 'deg');
      });
      heading.addEventListener('pointerleave', function () {
        turn.style.removeProperty('--sc-by');
        turn.style.removeProperty('--sc-bx');
      });
    }
  }

  // ------------------------------------------------------------ split-flap countdowns (0.62.0)
  // A film that isn't out yet counts down on a station board: the days to its release flick
  // through the digits and settle, when the board comes on screen.
  var today = new Date();
  today.setHours(0, 0, 0, 0);
  var flipTo = function (cell, final, delay) {
    if (reduce) { cell.textContent = final; return; }
    var spins = 4 + Math.floor(delay / 90);
    var tick = function () {
      cell.classList.remove('is-flipping');
      void cell.offsetWidth;
      cell.classList.add('is-flipping');
      if (spins-- > 0) {
        cell.textContent = /\d/.test(final) ? String(Math.floor(Math.random() * 10)) : final;
        setTimeout(tick, 70);
      } else {
        cell.textContent = final;
      }
    };
    setTimeout(tick, delay);
  };
  var boards = [];
  var playBoard = function (board) {
    if (board.dataset.played) { return; }
    board.dataset.played = 'yes';
    board.querySelectorAll('.sc-flap-cell').forEach(function (cell, i) { flipTo(cell, cell.dataset.final, i * 140); });
  };
  var boardWatch = 'IntersectionObserver' in window ? new IntersectionObserver(function (entries) {
    entries.forEach(function (e) { if (e.isIntersecting) { boardWatch.unobserve(e.target); playBoard(e.target); } });
  }, { threshold: 0.6 }) : null;
  // An on-screen check behind the observer, which the browser pane has been known to skip.
  var boardsOnScreen = function () {
    boards.forEach(function (board) {
      var r = board.getBoundingClientRect();
      if (r.top < window.innerHeight && r.bottom > 0 && r.width) { playBoard(board); }
    });
  };
  window.addEventListener('scroll', boardsOnScreen, { passive: true });
  window.addEventListener('load', boardsOnScreen);
  var countdowns = function (scope) {
    scope.querySelectorAll('.film-tile time[datetime]').forEach(function (time) {
      var tile = time.closest('.film-tile');
      if (tile.querySelector('.sc-flap')) { return; }
      var day = new Date(time.getAttribute('datetime') + 'T00:00:00');
      var days = Math.round((day - today) / 864e5);
      if (isNaN(days) || days < 0) { return; }
      var text = days === 0 ? 'TODAY' : (days > 999 ? '999' : ('00' + days).slice(-3));
      var board = make('span', 'sc-flap');
      board.setAttribute('aria-hidden', 'true');   // the date beside it says the same
      text.split('').forEach(function (ch) {
        var cell = make('span', 'sc-flap-cell', ch);   // right from the start: the flip is a flourish
        cell.dataset.final = ch;
        board.appendChild(cell);
      });
      if (days !== 0) { board.appendChild(make('small', 'sc-flap-unit', (days > 999 ? '+ ' : '') + (days === 1 ? 'day' : 'days'))); }
      var line = time.closest('p') || time.parentNode;
      line.parentNode.insertBefore(board, line.nextSibling);
      if (boardWatch) { boardWatch.observe(board); } else { playBoard(board); }
      boards.push(board);
    });
  };
  countdowns(document);

  // ------------------------------------------------------------ punched tickets (0.62.0)
  // A film you've watched has its ticket punched: a hole in the poster's corner, where the
  // "watched" tag was (the tag stays for screen readers, and as the hole's tooltip).
  var punch = function (scope) {
    scope.querySelectorAll('.film-tile .watched-mark').forEach(function (mark) {
      var poster = mark.closest('.film-tile').querySelector('.collection-poster');
      if (!poster || poster.querySelector('.sc-punch')) { return; }
      var hole = make('span', 'sc-punch');
      hole.title = mark.title || 'Watched';
      hole.setAttribute('aria-hidden', 'true');
      poster.appendChild(hole);
      mark.classList.add('sc-sr');
    });
  };
  punch(document);

  // ------------------------------------------------------------ old TV screens (0.62.0)
  // A show's poster sits in a rounded CRT screen, with faint scanlines across it.
  var screens = function (scope) {
    scope.querySelectorAll('.collection-card.is-show .collection-poster').forEach(function (poster) {
      if (poster.querySelector('.sc-crt')) { return; }
      var glass = make('span', 'sc-crt');
      glass.setAttribute('aria-hidden', 'true');
      poster.appendChild(glass);
    });
  };
  screens(document);

  // ------------------------------------------------------------ house lights (0.62.0)
  // Playing a trailer dims the room like a cinema before the film; closing it brings the lights
  // back up. The trailer arrives in #trailer and leaves by being emptied.
  root.style.setProperty('--sc-dark', 'rgb(0 0 0)');
  var screenRoom = document.getElementById('trailer');
  if (screenRoom) {
    var house = null;
    new MutationObserver(function () {
      var playing = !!screenRoom.firstElementChild;
      if (playing && !house) {
        house = make('div', 'sc-house');
        house.setAttribute('aria-hidden', 'true');
        document.body.appendChild(house);
        setTimeout(function () { if (house) { house.classList.add('is-down'); } }, 30);
      } else if (!playing && house) {
        var leaving = house;
        house = null;
        leaving.classList.remove('is-down');
        setTimeout(function () { leaving.remove(); }, reduce ? 0 : 1500);
      }
    }).observe(screenRoom, { childList: true });
  }

  // ------------------------------------------------------------ scan projector (0.62.0)
  // A running scan is shown on a projector: reels turning, film running into a countdown leader
  // that fills to the scan's progress, with the percentage in its middle.
  var PROJECTOR = '<svg class="sc-projector-art" viewBox="0 0 130 74">' +
    '<g class="sc-projector-reel" style="transform-origin: 30px 20px"><circle cx="30" cy="20" r="17"/>' +
    '<circle cx="30" cy="9" r="4" class="sc-hole"/><circle cx="40" cy="25" r="4" class="sc-hole"/><circle cx="20" cy="25" r="4" class="sc-hole"/></g>' +
    '<g class="sc-projector-reel" style="transform-origin: 70px 20px"><circle cx="70" cy="20" r="17"/>' +
    '<circle cx="70" cy="9" r="4" class="sc-hole"/><circle cx="80" cy="25" r="4" class="sc-hole"/><circle cx="60" cy="25" r="4" class="sc-hole"/></g>' +
    '<path d="M30 37 L44 37 M70 37 L56 37" class="sc-projector-film"/>' +
    '<rect x="16" y="36" width="70" height="28" rx="5" class="sc-projector-body"/>' +
    '<rect x="86" y="43" width="12" height="14" rx="2" class="sc-projector-body"/>' +
    '<polygon points="98,46 130,30 130,70 98,54" class="sc-projector-beam"/></svg>';
  var projector = function () {
    var article = document.querySelector('#scan-status article[aria-busy="true"]');
    if (!article || article.querySelector('.sc-projector')) { return; }
    var bar = article.querySelector('progress');
    var known = bar && bar.hasAttribute('value') && bar.max;
    var pct = known ? Math.min(100, Math.round(bar.value / bar.max * 100)) : null;
    var rig = make('div', 'sc-projector');
    rig.setAttribute('aria-hidden', 'true');   // the words and the progress bar say it for a reader
    rig.innerHTML = PROJECTOR;
    var leader = make('span', 'sc-leader' + (known ? '' : ' is-unknown'));
    leader.style.setProperty('--sc-p', String(pct || 0));
    leader.appendChild(make('b', null, known ? pct + '%' : '…'));
    rig.appendChild(leader);
    var header = article.querySelector('header');
    article.insertBefore(rig, header ? header.nextSibling : article.firstChild);
  };
  projector();

  // ------------------------------------------------------------ ticket stubs (0.62.0)
  // Activity's adds as a roll of torn ticket stubs, newest first: the title and where it went on
  // the ticket, the moment it happened stamped on the stub. The table stays for Classic.
  var ledger = document.querySelector('table[data-stubs]');
  if (ledger) {
    var stubRoll = make('ol', 'sc-stubs');
    ledger.querySelectorAll('tbody tr').forEach(function (row, i) {
      var cells = row.querySelectorAll('td');
      if (cells.length < 4) { return; }
      var stub = make('li', 'sc-stub');
      stub.style.setProperty('--i', String(i % 12));
      var main = make('div', 'sc-stub-main');
      main.appendChild(make('small', 'sc-stub-kicker', 'Admit one'));
      var title = make('strong');
      Array.prototype.forEach.call(cells[1].childNodes, function (n) { title.appendChild(n.cloneNode(true)); });
      main.appendChild(title);
      var where = [plain(cells[2]), plain(cells[3])].filter(function (w) { return w && w !== '—'; });
      main.appendChild(make('span', 'sc-stub-where', where.join(' · ')));
      var side = make('div', 'sc-stub-side');
      side.appendChild(make('span', 'sc-stub-stamp', plain(cells[0])));
      stub.appendChild(main);
      stub.appendChild(side);
      stubRoll.appendChild(stub);
    });
    ledger.parentNode.insertBefore(stubRoll, ledger);
    ledger.hidden = true;
  }

  // htmx brings new content -- a result dialog, a re-rendered list, search results, the scan's
  // status every two seconds (which replaces itself, so the projector is looked for page-wide).
  document.addEventListener('htmx:afterSwap', function (event) {
    var target = event.target;
    if (!target || !target.querySelectorAll) { return; }
    target.querySelectorAll('dialog[data-ticket]').forEach(printTicket);
    stage(target);
    fillCards(target);
    countdowns(target);
    punch(target);
    screens(target);
    projector();
  });
})();
