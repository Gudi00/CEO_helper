// Applies an AnswerResult to a question in the live Google Form.
//
// `window.__gfa.apply(qid, result, mode)` where:
//   qid    = the `data-gfa-qid` set by parser.js
//   result = { answer_indices:[..], answer_text:"..", confidence, reasoning }
//   mode   = "suggest" | "autofill"
//
// We never click the form's Submit button — by design.
(function () {
  window.__gfa = window.__gfa || {};

  var STYLE_ID = 'gfa-styles';
  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent =
      '[data-gfa="hit"]{outline:2px solid #2ecc71 !important;outline-offset:2px !important;' +
      'background:rgba(46,204,113,.10) !important;border-radius:6px;}' +
      '[data-gfa="hit-low"]{outline:2px solid #f39c12 !important;outline-offset:2px !important;' +
      'background:rgba(243,156,18,.10) !important;border-radius:6px;}' +
      '.gfa-badge{display:block;margin:8px 0;padding:8px 12px;background:#064e3b;color:#d1fae5;' +
      'border-left:4px solid #10b981;border-radius:6px;font:600 14px/1.4 system-ui,sans-serif;}' +
      '.gfa-badge--low{background:#78350f;color:#fef3c7;border-left-color:#f59e0b;}' +
      '.gfa-pending{background:#1f2937;color:#e5e7eb;border-left-color:#9ca3af;}' +
      '.gfa-badge__meta{font-weight:400;font-size:11px;opacity:.85;}' +
      '.gfa-fill-btn{margin-left:8px;padding:2px 10px;border:0;border-radius:4px;cursor:pointer;' +
      'background:#10b981;color:#fff;font:600 12px/1.4 system-ui;}';
    document.head.appendChild(s);
  }

  function item(qid) {
    return document.querySelector('[data-gfa-qid="' + qid + '"]');
  }

  function optionEls(container) {
    var r = container.querySelectorAll('[role="radio"]');
    if (r.length) return r;
    return container.querySelectorAll('[role="checkbox"]');
  }

  function nativeClick(el) {
    el.scrollIntoView({ block: 'center' });
    var rect = el.getBoundingClientRect();
    var o = {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: rect.left + rect.width / 2,
      clientY: rect.top + rect.height / 2,
      button: 0,
    };
    el.dispatchEvent(new MouseEvent('mousedown', o));
    el.dispatchEvent(new MouseEvent('mouseup', o));
    el.dispatchEvent(new MouseEvent('click', o));
  }

  // Google text fields are controlled; a plain `.value=` won't register. Use
  // the native setter then dispatch an input event.
  function setNativeValue(el, value) {
    var proto =
      el.tagName === 'TEXTAREA'
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function badge(container, result, extraBtn) {
    injectStyles();
    var old = container.querySelector('.gfa-badge');
    if (old) old.remove();
    var low = (result.confidence || 0) < 0.6;
    var div = document.createElement('div');
    div.className = 'gfa-badge' + (low ? ' gfa-badge--low' : '');
    var pct = Math.round((result.confidence || 0) * 100);
    var label =
      result.answer_text && result.answer_text.length
        ? 'AI: ' + result.answer_text
        : 'AI: вариант ' +
          (result.answer_indices || []).map(function (i) { return i + 1; }).join(', ');
    // Model output is untrusted: build the badge from text nodes, never HTML.
    div.appendChild(document.createTextNode(label + ' '));
    var meta = document.createElement('span');
    meta.className = 'gfa-badge__meta';
    meta.textContent = pct + '%' + (result.from_cache ? ' · из кеша' : '');
    div.appendChild(meta);
    if (extraBtn) div.appendChild(extraBtn);
    var anchor = container.querySelector('[role="heading"]') || container.firstChild;
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(div, anchor.nextSibling);
    } else {
      container.insertBefore(div, container.firstChild);
    }
  }

  function applyChoice(container, result, mode) {
    var els = optionEls(container);
    var variant = (result.confidence || 0) < 0.6 ? 'hit-low' : 'hit';
    (result.answer_indices || []).forEach(function (idx) {
      var el = els[idx];
      if (!el) return;
      if (mode === 'autofill') {
        nativeClick(el);
      } else {
        injectStyles();
        el.setAttribute('data-gfa', variant);
      }
    });
    badge(container, result, null);
  }

  function applyText(container, result, mode) {
    var field =
      container.querySelector('input[type="text"]') ||
      container.querySelector('textarea');
    if (!field) return;
    if (mode === 'autofill') {
      setNativeValue(field, result.answer_text || '');
      badge(container, result, null);
    } else {
      var btn = document.createElement('button');
      btn.className = 'gfa-fill-btn';
      btn.textContent = 'Вписать';
      btn.addEventListener('click', function () {
        setNativeValue(field, result.answer_text || '');
      });
      badge(container, result, btn);
    }
  }

  function insertBadge(container, el) {
    var anchor = container.querySelector('[role="heading"]') || container.firstChild;
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(el, anchor.nextSibling);
    } else {
      container.insertBefore(el, container.firstChild);
    }
  }

  // Show a "thinking" placeholder while the AI is answering this question.
  window.__gfa.pending = function (qid) {
    var c = item(qid);
    if (!c) return;
    injectStyles();
    var old = c.querySelector('.gfa-badge');
    if (old) old.remove();
    var d = document.createElement('div');
    d.className = 'gfa-badge gfa-pending';
    d.textContent = '🤖 AI думает…';
    insertBadge(c, d);
  };

  // Remove the "thinking" placeholder (used when no answer is produced).
  window.__gfa.clearPending = function (qid) {
    var c = item(qid);
    if (!c) return;
    var p = c.querySelector('.gfa-pending');
    if (p) p.remove();
  };

  window.__gfa.apply = function (qid, result, mode) {
    var container = item(qid);
    if (!container) return false;
    if (result.answer_text && result.answer_text.length) {
      applyText(container, result, mode);
    } else {
      applyChoice(container, result, mode);
    }
    return true;
  };
})();
