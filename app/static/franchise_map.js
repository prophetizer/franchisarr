// The Franchise map (0.55.0): one franchise's collections, other films and shows, drawn three
// ways, all kept after a trial (0.55.1) -- lanes (a timeline lane per series), a tree, and a
// constellation to drag about. The data is the JSON the page carries (franchise_map.build);
// each person's choice of shape is saved to their account. Loaded in both looks; the Showcase
// look adds motion through showcase.css, and "reduce motion" keeps everything still.
(function () {
  'use strict';

  var box = document.querySelector('.fm-canvas');
  var source = document.querySelector('.fm-data');
  if (!box || !source) { return; }
  var data;
  try { data = JSON.parse(source.textContent); } catch (e) { return; }
  var base = box.dataset.base || '';
  var SVG = 'http://www.w3.org/2000/svg';
  var byId = {};
  data.nodes.forEach(function (n) { byId[n.id] = n; });
  var STATE = { owned: 'in your library', missing: 'missing', upcoming: 'coming' };

  function svg(name, attrs, parent) {
    var el = document.createElementNS(SVG, name);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    if (parent) { parent.appendChild(el); }
    return el;
  }
  function html(tag, cls, text, parent) {
    var el = document.createElement(tag);
    if (cls) { el.className = cls; }
    if (text != null) { el.textContent = text; }
    if (parent) { parent.appendChild(el); }
    return el;
  }
  function label(n) { return n.title + (n.year ? ' (' + n.year + ')' : '') + ' — ' + STATE[n.state]; }
  // Where a title leads: its collection's page, or a search for it.
  function hrefOf(n) {
    var group = data.groups[n.group];
    return base + (group && group.href ? group.href : '/search?q=' + encodeURIComponent(n.title));
  }

  // ------------------------------------------------------------ lanes
  // Years across, a lane per series; titles sit at their year, owned filled, missing hollow,
  // coming dashed. A spin-off arcs from its show; a film-to-show continuation crosses lanes.
  function lanes() {
    if (!data.years) { tree(); return; }
    var first = data.years[0], last = data.years[1] + 1;   // +1: room for undated titles
    var narrow = box.clientWidth < 640;
    var labelW = narrow ? 110 : 190, laneH = 46, top = 30, right = 24;
    var perYear = Math.max(narrow ? 16 : 12, (box.clientWidth - labelW - right) / (last - first + 1));
    var width = Math.round(labelW + (last - first + 1) * perYear + right);
    var height = top + data.groups.length * laneH + 10;
    var x = function (year) { return labelW + ((year || last) - first + 0.5) * perYear; };
    var root = svg('svg', { viewBox: '0 0 ' + width + ' ' + height, width: width, height: height,
                            class: 'fm-lanes', role: 'img', 'aria-label': data.name + ', as a timeline' }, box);
    var step = (last - first) > 60 ? 10 : (last - first) > 25 ? 5 : (last - first) > 10 ? 2 : 1;
    for (var year = Math.ceil(first / step) * step; year <= last; year += step) {
      svg('line', { x1: x(year), x2: x(year), y1: top - 6, y2: height - 6, class: 'fm-tick' }, root);
      svg('text', { x: x(year), y: top - 12, class: 'fm-year', 'text-anchor': 'middle' }, root).textContent = String(year);
    }
    var pos = {};
    data.groups.forEach(function (group, g) {
      var y = top + g * laneH + laneH / 2;
      var name = svg('text', { x: 8, y: y + 4, class: 'fm-lane-name' }, root);
      name.textContent = group.name.length > (narrow ? 14 : 26) ? group.name.slice(0, narrow ? 13 : 25) + '…' : group.name;
      svg('title', {}, name).textContent = group.name;
      var members = data.nodes.filter(function (n) { return n.group === g; });
      if (!members.length) { return; }
      var xs = members.map(function (n) { return x(n.year); });
      svg('line', { x1: Math.min.apply(null, xs), x2: Math.max.apply(null, xs), y1: y, y2: y, class: 'fm-lane',
                    style: '--fm-i: ' + g }, root);
      var used = {};
      members.forEach(function (n, i) {
        var nx = x(n.year), key = Math.round(nx);
        var shift = used[key] = (used[key] || 0) + 1;     // same year, same lane: stagger
        var ny = y + (shift === 1 ? 0 : (shift % 2 ? 1 : -1) * Math.ceil((shift - 1) / 2) * 9);
        pos[n.id] = [nx, ny];
        var link = svg('a', { href: hrefOf(n), class: 'fm-node fm-' + n.state + (n.type === 'show' ? ' fm-show' : ''),
                              style: '--fm-i: ' + (g * 3 + i) }, root);
        svg('title', {}, link).textContent = label(n);
        svg(n.type === 'show' ? 'rect' : 'circle', n.type === 'show'
          ? { x: nx - 6.5, y: ny - 6.5, width: 13, height: 13, rx: 3 } : { cx: nx, cy: ny, r: 7 }, link);
      });
    });
    data.edges.forEach(function (e) {
      var a = pos[e[0]], b = pos[e[1]];
      if (!a || !b) { return; }
      var lift = Math.abs(a[1] - b[1]) < 2 ? -Math.min(30, Math.abs(b[0] - a[0]) / 2 + 8) : 0;
      svg('path', { d: 'M' + a[0] + ' ' + a[1] + ' Q ' + (a[0] + b[0]) / 2 + ' ' + ((a[1] + b[1]) / 2 + lift) + ' ' + b[0] + ' ' + b[1],
                    class: 'fm-edge fm-edge--' + e[2] }, root);
    });
    // Behind the nodes: move every edge to just after the ticks.
    root.querySelectorAll('.fm-edge').forEach(function (p) { root.insertBefore(p, root.querySelector('.fm-lane-name')); });
    var key = html('p', 'fm-key muted');
    key.innerHTML = '<span class="fm-k fm-owned"></span> in your library <span class="fm-k fm-missing"></span> missing ' +
      '<span class="fm-k fm-upcoming"></span> coming <span class="fm-k fm-k-show"></span> TV';
    box.appendChild(key);
  }

  // ------------------------------------------------------------ tree
  // The franchise at the top; each series a branch beneath it; its titles down the branch, a
  // spin-off indented under the show it came from.
  function tree() {
    var wrap = html('div', 'fm-tree', null, box);
    html('div', 'fm-root', data.name, wrap);
    var branches = html('div', 'fm-branches', null, wrap);
    var parentOf = {};
    data.edges.forEach(function (e) {
      var a = byId[e[0]], b = byId[e[1]];
      if (e[2] === 'spin-off' && a && b && a.group === b.group && !parentOf[e[1]]) { parentOf[e[1]] = e[0]; }
    });
    data.groups.forEach(function (group, g) {
      var members = data.nodes.filter(function (n) { return n.group === g; });
      var branch = html('div', 'fm-branch', null, branches);
      branch.style.setProperty('--fm-i', g);
      var have = members.filter(function (n) { return n.state === 'owned'; }).length;
      var head = html(group.href ? 'a' : 'span', 'fm-group', group.name, branch);
      if (group.href) { head.href = base + group.href; }
      html('small', 'muted', ' ' + have + ' of ' + members.length, head);
      var list = html('ul', null, null, branch);
      var items = {}, placing = {};
      var place = function (n) {
        if (items[n.id]) { return items[n.id]; }
        var holder = list;
        placing[n.id] = true;
        if (parentOf[n.id] && !placing[parentOf[n.id]]) {   // a loop of spin-offs: top level
          var parent = place(byId[parentOf[n.id]]);
          holder = parent.querySelector(':scope > ul') || html('ul', null, null, parent);
        }
        var li = html('li', 'fm-item fm-' + n.state, null, holder);
        var a = html('a', null, null, li);
        a.href = hrefOf(n);
        a.title = label(n);
        if (n.poster) { var img = html('img', null, null, a); img.src = n.poster; img.alt = ''; img.loading = 'lazy'; img.decoding = 'async'; }
        else { html('span', 'fm-noposter', null, a); }
        html('span', 'fm-name', n.title, a);
        if (n.year) { html('small', 'muted', ' ' + n.year, a); }
        items[n.id] = li;
        return li;
      };
      members.forEach(place);
    });
  }

  // ------------------------------------------------------------ constellation
  // The franchise in the middle, its series around it, their titles around those. A small force
  // layout settles it once; then any star can be dragged, its lines following.
  function constellation() {
    var W = 900, H = 620;
    var stars = [{ id: '@root', kind: 'root', name: data.name }];
    var links = [];
    data.groups.forEach(function (group, g) {
      stars.push({ id: '@g' + g, kind: 'group', name: group.name, href: group.href });
      links.push(['@root', '@g' + g, 130]);
    });
    data.nodes.forEach(function (n) {
      stars.push({ id: n.id, kind: 'title', node: n });
      links.push(['@g' + n.group, n.id, 55]);
    });
    data.edges.forEach(function (e) { links.push([e[0], e[1], 70, e[2]]); });
    var at = {};
    stars.forEach(function (s, i) {
      var angle = i * 2.399963, r = s.kind === 'root' ? 0 : s.kind === 'group' ? 140 : 240 + (i % 7) * 6;
      s.x = W / 2 + Math.cos(angle) * r; s.y = H / 2 + Math.sin(angle) * r; s.vx = 0; s.vy = 0;
      at[s.id] = s;
    });
    // A few hundred steps of springs, repulsion and a pull to the middle; settled before drawing.
    for (var tick = 0; tick < 320; tick++) {
      var heat = 1 - tick / 320;
      for (var i = 0; i < stars.length; i++) {
        for (var j = i + 1; j < stars.length; j++) {
          var a = stars[i], b = stars[j], dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy + 0.01;
          var push = (a.kind === 'title' && b.kind === 'title' ? 900 : 2600) / d2;
          a.vx -= dx * push; a.vy -= dy * push; b.vx += dx * push; b.vy += dy * push;
        }
      }
      links.forEach(function (l) {
        var a = at[l[0]], b = at[l[1]];
        if (!a || !b) { return; }
        var dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1, pull = (d - l[2]) * 0.04;
        a.vx += dx / d * pull; a.vy += dy / d * pull; b.vx -= dx / d * pull; b.vy -= dy / d * pull;
      });
      stars.forEach(function (s) {
        s.vx += (W / 2 - s.x) * 0.004; s.vy += (H / 2 - s.y) * 0.004;
        if (s.kind === 'root') { s.vx = 0; s.vy = 0; s.x = W / 2; s.y = H / 2; }
        s.x += Math.max(-12, Math.min(12, s.vx)) * heat; s.y += Math.max(-12, Math.min(12, s.vy)) * heat;
        s.vx *= 0.6; s.vy *= 0.6;
      });
    }
    // Fit what settled into the frame.
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    stars.forEach(function (s) { minX = Math.min(minX, s.x); minY = Math.min(minY, s.y); maxX = Math.max(maxX, s.x); maxY = Math.max(maxY, s.y); });
    var scale = Math.min((W - 120) / Math.max(1, maxX - minX), (H - 80) / Math.max(1, maxY - minY), 1.6);
    stars.forEach(function (s) { s.x = W / 2 + (s.x - (minX + maxX) / 2) * scale; s.y = H / 2 + (s.y - (minY + maxY) / 2) * scale; });

    var root = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, class: 'fm-sky', role: 'img',
                            'aria-label': data.name + ', as a constellation' }, box);
    var lines = links.map(function (l) {
      var a = at[l[0]], b = at[l[1]];
      if (!a || !b) { return null; }
      return { a: a, b: b, el: svg('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y,
                                             class: 'fm-wire' + (l[3] ? ' fm-edge--' + l[3] : '') }, root) };
    }).filter(Boolean);
    stars.forEach(function (s, i) {
      var g = svg(s.node ? 'a' : 'g', { class: 'fm-star fm-star--' + s.kind + (s.node ? ' fm-' + s.node.state : ''),
                                        style: '--fm-i: ' + (i % 24) }, root);
      if (s.node) { g.setAttribute('href', hrefOf(s.node)); }
      else if (s.href) { g = svg('a', { href: base + s.href }, g); }
      svg('title', {}, g).textContent = s.node ? label(s.node) : s.name;
      var r = s.kind === 'root' ? 18 : s.kind === 'group' ? 10 : 6;
      s.dot = svg('circle', { cx: s.x, cy: s.y, r: r }, g);
      if (s.kind !== 'title') {
        s.text = svg('text', { x: s.x, y: s.y + r + 14, 'text-anchor': 'middle' }, g);
        s.text.textContent = s.name.length > 28 ? s.name.slice(0, 27) + '…' : s.name;
      }
      s.el = g;
    });
    // Drag a star (a click without a drag still follows its link).
    var dragging = null, moved = false;
    root.addEventListener('pointerdown', function (event) {
      var hit = stars.filter(function (s) { return s.el.contains(event.target); })[0];
      if (!hit) { return; }
      dragging = hit; moved = false;
      try { root.setPointerCapture(event.pointerId); } catch (e) { /* a pointer that's already gone */ }
    });
    root.addEventListener('pointermove', function (event) {
      if (!dragging) { return; }
      var box2 = root.getBoundingClientRect();
      dragging.x = (event.clientX - box2.left) / box2.width * W;
      dragging.y = (event.clientY - box2.top) / box2.height * H;
      moved = true;
      dragging.dot.setAttribute('cx', dragging.x); dragging.dot.setAttribute('cy', dragging.y);
      if (dragging.text) { dragging.text.setAttribute('x', dragging.x); dragging.text.setAttribute('y', dragging.y + Number(dragging.dot.getAttribute('r')) + 14); }
      lines.forEach(function (l) {
        if (l.a === dragging) { l.el.setAttribute('x1', dragging.x); l.el.setAttribute('y1', dragging.y); }
        if (l.b === dragging) { l.el.setAttribute('x2', dragging.x); l.el.setAttribute('y2', dragging.y); }
      });
    });
    var drop = function () { dragging = null; };
    root.addEventListener('pointerup', drop);
    root.addEventListener('pointercancel', drop);
    root.addEventListener('click', function (event) { if (moved) { event.preventDefault(); moved = false; } }, true);
  }

  // ------------------------------------------------------------ the switch
  var SHAPES = { lanes: lanes, tree: tree, constellation: constellation };
  function draw(shape) {
    box.innerHTML = '';
    box.dataset.shape = shape;
    (SHAPES[shape] || lanes)();
  }
  document.querySelectorAll('.fm-switch [data-shape]').forEach(function (button) {
    button.addEventListener('click', function () {
      var shape = button.dataset.shape;
      document.querySelectorAll('.fm-switch [data-shape]').forEach(function (b) {
        b.setAttribute('aria-selected', b === button ? 'true' : 'false');
      });
      draw(shape);
      var body = new URLSearchParams({ shape: shape });
      fetch(box.dataset.save, { method: 'POST', body: body, credentials: 'same-origin' }).catch(function () {});
    });
  });
  draw(box.dataset.shape);
  // Lanes are laid out to the width they have; a phone turned sideways has more.
  var wide = box.clientWidth;
  window.addEventListener('resize', function () {
    if (Math.abs(box.clientWidth - wide) > 40 && box.dataset.shape === 'lanes') { wide = box.clientWidth; draw('lanes'); }
  });
})();
