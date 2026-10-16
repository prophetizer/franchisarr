// Story order (0.74.0): drag a title, or press its arrows, to move it. The hidden inputs travel with
// their rows, so the form posts the order on screen. Both looks.
(function () {
  'use strict';

  var list = document.getElementById('story-order');
  if (!list) { return; }
  var dragging = null;
  list.addEventListener('dragstart', function (e) {
    dragging = e.target.closest('li');
    if (dragging) { dragging.classList.add('is-dragging'); e.dataTransfer.effectAllowed = 'move'; }
  });
  list.addEventListener('dragend', function () {
    if (dragging) { dragging.classList.remove('is-dragging'); }
    dragging = null;
  });
  list.addEventListener('dragover', function (e) {
    if (!dragging) { return; }
    e.preventDefault();
    var over = e.target.closest('li');
    if (!over || over === dragging) { return; }
    var box = over.getBoundingClientRect();
    list.insertBefore(dragging, e.clientY > box.top + box.height / 2 ? over.nextSibling : over);
  });
  list.addEventListener('click', function (e) {
    var button = e.target.closest('[data-move]');
    if (!button) { return; }
    var row = button.closest('li');
    if (button.dataset.move === '-1' && row.previousElementSibling) {
      list.insertBefore(row, row.previousElementSibling);
    } else if (button.dataset.move === '1' && row.nextElementSibling) {
      list.insertBefore(row.nextElementSibling, row);
    }
    button.focus();
  });
})();
