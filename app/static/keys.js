// Keyboard shortcuts (0.72.0), both looks: ? opens a sheet of every shortcut, and g then a letter
// jumps to a section (g c: Collections). Never while typing, never with a modifier held.
(function () {
  'use strict';

  var me = document.currentScript;
  // The app's base URL without its trailing slash (url('') gives "/" or "/sub/"), or a jump to
  // "/collections" would become "//collections" -- another host.
  var base = ((me && me.dataset.base) || '').replace(/\/+$/, '');
  var showcase = document.documentElement.dataset.look === 'showcase';
  var GO = [
    ['h', '/', 'Home'], ['f', '/franchises', 'Franchises'], ['c', '/collections', 'Collections'],
    ['s', '/shows', 'Spin-offs'], ['u', '/upcoming', 'Upcoming'], ['d', '/directors', 'Directors'],
    ['t', '/trophies', 'Trophy case'], ['n', '/stats', 'In numbers']
  ];
  var typing = function (el) {
    return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
  };
  var sheet = null;
  var row = function (keys, what, joiner) {
    return '<tr><td>' + keys.map(function (k) { return '<kbd>' + k + '</kbd>'; }).join(joiner || ' then ') + '</td><td>' + what + '</td></tr>';
  };
  var open = function () {
    if (!sheet) {
      sheet = document.createElement('dialog');
      sheet.className = 'key-sheet';
      sheet.setAttribute('aria-label', 'Keyboard shortcuts');
      var rows = [row(['?'], 'This list'), row(['/'], 'Search')];
      if (showcase) { rows.push(row(['Ctrl+K'], 'Quick find (⌘K on a Mac)')); }
      rows.push(row(['Esc'], 'Close a dialog, a menu or the trailer'));
      if (showcase) { rows.push(row(['←', '→'], 'Step through posters in the large view', ' or ')); }
      GO.forEach(function (g) { rows.push(row(['g', g[0]], g[2])); });
      sheet.innerHTML = '<article><header><strong>Keyboard shortcuts</strong></header><table>' + rows.join('') +
        '</table><footer><button type="button" class="secondary">Close</button></footer></article>';
      sheet.querySelector('button').addEventListener('click', function () { sheet.close(); });
      sheet.addEventListener('click', function (e) { if (e.target === sheet) { sheet.close(); } });
      document.body.appendChild(sheet);
    }
    if (sheet.open) { sheet.close(); return; }
    if (typeof sheet.showModal === 'function') { sheet.showModal(); } else { sheet.setAttribute('open', ''); }
  };
  var pending = null;
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey || typing(e.target) || e.defaultPrevented) { return; }
    if (e.key === '?') { e.preventDefault(); open(); return; }
    if (pending) {
      window.clearTimeout(pending);
      pending = null;
      var hit = GO.filter(function (g) { return g[0] === e.key.toLowerCase(); })[0];
      if (hit) { e.preventDefault(); window.location.href = base + hit[1]; }
      return;
    }
    if (e.key === 'g') { pending = window.setTimeout(function () { pending = null; }, 1200); }
  });
})();
