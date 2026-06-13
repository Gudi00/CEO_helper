// Injected into the Google Forms /viewform page. Parses questions out of the
// DOM (using stable ARIA roles, since Google's class names are obfuscated),
// tags each question container with `data-gfa-qid`, and pushes the list to the
// Flutter side via the `onQuestions` handler.
//
// Supported types: single_choice (role=radio), multiple_choice (role=checkbox),
// text_input (input[type=text] / textarea). Everything else (section headers,
// descriptions, scales, grids, file upload) is skipped.
(function () {
  if (window.__gfa && window.__gfa._installed) return;

  function formId() {
    var m = location.href.match(/\/forms\/d\/(?:e\/)?([^/]+)/);
    return m ? m[1] : 'form';
  }

  function headingText(item) {
    var h = item.querySelector('[role="heading"]');
    var t = (h ? h.textContent : '') || '';
    // Drop a trailing required-marker "*" and collapse whitespace.
    return t.replace(/\*/g, '').replace(/\s+/g, ' ').trim();
  }

  function optionText(el) {
    return (
      el.getAttribute('data-value') ||
      el.getAttribute('data-answer-value') ||
      el.getAttribute('aria-label') ||
      (el.textContent || '')
    )
      .replace(/\s+/g, ' ')
      .trim();
  }

  function parseItem(item, index, fid) {
    var radios = item.querySelectorAll('[role="radio"]');
    var checks = item.querySelectorAll('[role="checkbox"]');
    var textEl =
      item.querySelector('input[type="text"]') ||
      item.querySelector('textarea');

    var type = null;
    var optionEls = [];
    if (radios.length >= 2) {
      type = 'single_choice';
      optionEls = radios;
    } else if (checks.length >= 1) {
      type = 'multiple_choice';
      optionEls = checks;
    } else if (textEl) {
      type = 'text_input';
    } else {
      return null;
    }

    var text = headingText(item);
    if (!text) return null;

    var options = [];
    for (var i = 0; i < optionEls.length; i++) {
      var ot = optionText(optionEls[i]);
      if (!ot) continue;
      options.push({ index: options.length, value: ot, text: ot });
    }
    if (type !== 'text_input' && options.length < 2) return null;

    var qid = fid + ':' + index;
    item.setAttribute('data-gfa-qid', qid);

    return {
      id: qid,
      type: type,
      text: text,
      options: options,
      formId: fid,
      index: index,
      hasImages: !!item.querySelector('img'),
    };
  }

  function parseAll() {
    var fid = formId();
    var items = document.querySelectorAll('div[role="listitem"]');
    var out = [];
    var qIndex = 0;
    for (var i = 0; i < items.length; i++) {
      var q = parseItem(items[i], qIndex, fid);
      if (q) {
        out.push(q);
        qIndex++;
      }
    }
    return out;
  }

  // Signature of the last pushed set, so we only notify Flutter when the
  // questions themselves change. Our own DOM edits (answer badges, "thinking"
  // markers) and Google's incidental mutations (ripples, focus rings) don't
  // change this, which stops the MutationObserver → push feedback loop that
  // otherwise re-fired every few ms and never let an answer settle.
  var lastSig = '';
  function signature(questions) {
    var parts = [];
    for (var i = 0; i < questions.length; i++) {
      var q = questions[i];
      var opts = q.options.map(function (o) { return o.text; }).join('~');
      parts.push(q.id + '|' + q.type + '|' + q.text + '|' + opts);
    }
    return parts.join('§');
  }

  function push() {
    try {
      var questions = parseAll();
      if (!questions.length) return;
      var sig = signature(questions);
      if (sig === lastSig) return; // nothing new — don't re-push
      lastSig = sig;
      if (
        window.flutter_inappwebview &&
        window.flutter_inappwebview.callHandler
      ) {
        window.flutter_inappwebview.callHandler('onQuestions', questions);
      }
    } catch (e) {
      if (window.flutter_inappwebview) {
        window.flutter_inappwebview.callHandler('log', 'parser error: ' + e);
      }
    }
  }

  var debounce = null;
  function schedulePush() {
    if (debounce) clearTimeout(debounce);
    debounce = setTimeout(push, 400);
  }

  window.__gfa = window.__gfa || {};
  window.__gfa._installed = true;
  window.__gfa.parseNow = push;

  // Google Forms is an SPA: re-parse on DOM changes (page navigation, lazy
  // rendering) with a debounce.
  var obs = new MutationObserver(schedulePush);
  obs.observe(document.body, { childList: true, subtree: true });

  schedulePush();
})();
