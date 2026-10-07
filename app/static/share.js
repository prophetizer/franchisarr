// The share card (0.72.0), both looks: a detail page's set drawn as one picture -- its posters in
// release order, owned in colour and the rest dimmed, with its name and how much you have -- for
// Reddit or a chat. Drawn here in the browser from TMDb's copies; nothing is uploaded. Shared
// through the phone's share sheet where there is one, otherwise saved as a PNG.
(function () {
  'use strict';

  var button = document.querySelector('[data-share-set]');
  var steps = document.querySelectorAll('.timeline-step');
  var probe = document.createElement('canvas');
  if (!button || steps.length < 2 || !probe.getContext || !probe.toBlob) { return; }
  button.hidden = false;

  // The page's name: the heading's text, or its logo's alt when the logo replaces it.
  var heading = document.querySelector('.collection-heading h1');
  var logo = heading && heading.querySelector('img');
  var name = (logo ? logo.alt : (heading ? heading.textContent : document.title.split(' — ')[0])).trim();

  // w154, loaded for reading: a size the page itself loads only the same way (Showcase's glow),
  // so no copy cached without CORS headers gets in the way (CLAUDE.md, the glow gotcha).
  var small = function (src) { return src.replace(/\/t\/p\/[^/]+\//, '/t/p/w154/'); };
  var load = function (src) {
    return new Promise(function (resolve) {
      if (!src) { resolve(null); return; }
      var img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = function () { resolve(img); };
      img.onerror = function () { resolve(null); };
      img.src = src;
    });
  };

  var CELL_W = 154, CELL_H = 231, GAP = 12, PAD = 36, HEAD = 112, FOOT = 44;
  var INK = 'rgb(240 242 246)', MUTED = 'rgb(150 158 170)', PAGE = 'rgb(20 23 28)', BLANK = 'rgb(44 50 60)';

  var wrap = function (ctx, text, x, y, width, lineHeight, lines) {
    var words = text.split(/\s+/), line = '', drawn = 0;
    for (var i = 0; i < words.length && drawn < lines; i++) {
      var next = line ? line + ' ' + words[i] : words[i];
      if (ctx.measureText(next).width > width && line) {
        ctx.fillText(line, x, y + drawn * lineHeight);
        drawn++;
        line = words[i];
      } else {
        line = next;
      }
    }
    if (drawn < lines && line) { ctx.fillText(line, x, y + drawn * lineHeight); }
  };

  var draw = function () {
    var items = Array.prototype.map.call(steps, function (step) {
      var img = step.querySelector('.timeline-poster img');
      var label = (step.querySelector('.timeline-poster') || step).getAttribute('title') || '';
      return { src: img ? small(img.currentSrc || img.src) : null,
               title: label.replace(/(?: \(\d{4}\))? — .*$/, ''),
               owned: step.classList.contains('timeline-step--owned') };
    });
    var cols = Math.min(items.length <= 12 ? 6 : 8, items.length);
    var rows = Math.ceil(items.length / cols);
    var width = PAD * 2 + cols * CELL_W + (cols - 1) * GAP;
    var height = HEAD + rows * CELL_H + (rows - 1) * GAP + FOOT + PAD;
    return Promise.all(items.map(function (item) { return load(item.src); })).then(function (images) {
      var canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      var ctx = canvas.getContext('2d');
      ctx.fillStyle = PAGE;
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = INK;
      ctx.font = '700 34px system-ui, sans-serif';
      ctx.textBaseline = 'top';
      wrap(ctx, name, PAD, PAD - 4, width - PAD * 2, 38, 1);
      ctx.fillStyle = MUTED;
      ctx.font = '400 20px system-ui, sans-serif';
      ctx.fillText((button.dataset.summary || '') + ' in my library', PAD, PAD + 44);
      items.forEach(function (item, n) {
        var x = PAD + (n % cols) * (CELL_W + GAP);
        var y = HEAD + Math.floor(n / cols) * (CELL_H + GAP);
        if (images[n]) {
          ctx.drawImage(images[n], x, y, CELL_W, CELL_H);
        } else {
          ctx.fillStyle = BLANK;
          ctx.fillRect(x, y, CELL_W, CELL_H);
          ctx.fillStyle = INK;
          ctx.font = '700 17px Georgia, serif';
          wrap(ctx, item.title, x + 12, y + 14, CELL_W - 24, 21, 6);
        }
        if (!item.owned) {
          // Dimmed, not filtered: canvas filters aren't everywhere yet.
          ctx.fillStyle = 'rgb(20 23 28 / 0.62)';
          ctx.fillRect(x, y, CELL_W, CELL_H);
          ctx.strokeStyle = MUTED;
          ctx.setLineDash([6, 5]);
          ctx.lineWidth = 2;
          ctx.strokeRect(x + 1, y + 1, CELL_W - 2, CELL_H - 2);
          ctx.setLineDash([]);
        }
      });
      ctx.fillStyle = MUTED;
      ctx.font = '400 15px system-ui, sans-serif';
      ctx.fillText('Missing ones dimmed · made with Franchisarr', PAD, height - PAD - 14);
      return new Promise(function (resolve, reject) {
        try {
          canvas.toBlob(function (blob) { if (blob) { resolve(blob); } else { reject(new Error('empty')); } }, 'image/png');
        } catch (e) { reject(e); }   // a poster that came back without CORS taints the canvas
      });
    });
  };

  button.addEventListener('click', function () {
    var label = button.textContent;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    draw().then(function (blob) {
      var file = name.replace(/[^\w\s-]+/g, '').trim().replace(/\s+/g, '-').toLowerCase() || 'set';
      var png = new File([blob], file + '.png', { type: 'image/png' });
      if (navigator.canShare && navigator.canShare({ files: [png] })) {
        return navigator.share({ files: [png], title: name }).catch(function () { /* closed the sheet */ });
      }
      var link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = png.name;
      document.body.appendChild(link);
      link.click();
      window.setTimeout(function () { URL.revokeObjectURL(link.href); link.remove(); }, 2000);
    }).catch(function () {
      button.textContent = 'Couldn’t make the picture';
      window.setTimeout(function () { button.textContent = label; }, 3000);
    }).then(function () {
      button.disabled = false;
      button.removeAttribute('aria-busy');
    });
  });
})();
