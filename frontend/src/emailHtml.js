// Prepares received email HTML for the sandboxed viewer so that its links work. This runs on the
// HTML before it is displayed (not on iframe load, which waits for every image in the email).

const BARE_URL_RE = /(?:https?:\/\/|\bwww\.)[^\s<>"'​]+/gi;
const NO_LINKIFY = 'a, script, style, textarea, button, select, title, head, noscript';
const DOMAIN_LIKE = /^(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:[/?#]|$)/i;

// Drop sentence punctuation, and closing brackets that were not opened inside the URL
export function trimUrl(raw) {
  let url = raw;
  for (;;) {
    const last = url[url.length - 1];
    if (/[.,;:!?*]/.test(last || '')) {
      url = url.slice(0, -1);
    } else if (last === ')' || last === ']' || last === '}') {
      const open = { ')': '(', ']': '[', '}': '{' }[last];
      if (url.split(last).length <= url.split(open).length) return url;
      url = url.slice(0, -1);
    } else {
      return url;
    }
  }
}

// Returns a usable absolute href, or null when the link has no destination outside the dashboard
export function normalizeHref(raw, baseHref) {
  // Anything after <, > or " was swallowed by a malformed link, not part of the address
  const href = (raw || '').trim().replace(/[\t\r\n]/g, '').replace(/[<>"].*$/, '');
  if (!href || href.startsWith('#')) return null;
  if (/^(https?|mailto|tel|sms):/i.test(href)) return href;
  if (href.startsWith('//')) return `https:${href}`;
  if (DOMAIN_LIKE.test(href)) return `https://${href}`;
  if (/^[a-z][a-z0-9+.-]*:/i.test(href)) return null; // javascript:, data:, cid:, ...
  try {
    return baseHref ? new URL(href, baseHref).href : null;
  } catch (e) {
    return null;
  }
}

function linkifyText(doc) {
  const walker = doc.createTreeWalker(doc.body, 4 /* NodeFilter.SHOW_TEXT */);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);

  nodes.forEach((node) => {
    const text = node.nodeValue;
    if (!/https?:\/\/|www\./i.test(text) || node.parentElement.closest(NO_LINKIFY)) return;
    const frag = doc.createDocumentFragment();
    let last = 0;
    let found = false;
    for (const match of text.matchAll(BARE_URL_RE)) {
      const url = trimUrl(match[0]);
      if (!/^(?:https?:\/\/|www\.)[^/.]/i.test(url)) continue;
      found = true;
      frag.append(text.slice(last, match.index));
      const a = doc.createElement('a');
      a.setAttribute('href', /^http/i.test(url) ? url : `https://${url}`);
      a.setAttribute('style', 'overflow-wrap:anywhere;word-break:break-word');
      a.textContent = url;
      frag.append(a);
      last = match.index + url.length;
    }
    if (!found) return;
    frag.append(text.slice(last));
    node.replaceWith(frag);
  });
}

export function prepareEmailHtml(html) {
  if (!html) return '';
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const baseEl = doc.querySelector('base[href]');
  const baseHref = baseEl && /^https?:/i.test(baseEl.getAttribute('href')) ? baseEl.getAttribute('href') : null;

  linkifyText(doc);

  doc.querySelectorAll('a[href], area[href]').forEach((el) => {
    const raw = el.getAttribute('href').trim();
    const href = normalizeHref(raw, baseHref);
    if (href) {
      el.setAttribute('href', href);
      // Always a new tab: _self would load the site inside the email frame (most sites refuse
      // that) and _top/_parent are blocked by the sandbox, so the click would do nothing.
      el.setAttribute('target', '_blank');
      el.setAttribute('rel', 'noopener noreferrer');
    } else {
      // In-page anchors are scrolled to by the viewer. Anything else has no destination and
      // would otherwise resolve to a page of the dashboard itself.
      if (/^#./.test(raw)) el.setAttribute('data-email-anchor', raw.slice(1));
      el.removeAttribute('href');
      el.removeAttribute('target');
    }
  });

  // An email must not be able to navigate its own frame away from the message
  doc.querySelectorAll('meta[http-equiv]').forEach((el) => {
    if (/^refresh$/i.test(el.getAttribute('http-equiv').trim())) el.remove();
  });

  const doctype = /<!doctype/i.test(html.slice(0, 500)) ? '<!DOCTYPE html>' : '';
  return doctype + doc.documentElement.outerHTML;
}

// In-page links ("jump to section"), handled here because email scripts never run
export function wireInPageAnchors(doc) {
  doc.querySelectorAll('[data-email-anchor]').forEach((el) => {
    el.style.cursor = 'pointer';
    el.addEventListener('click', () => {
      let id = el.getAttribute('data-email-anchor');
      try { id = decodeURIComponent(id); } catch (e) { /* use as is */ }
      const target = doc.getElementById(id) || doc.getElementsByName(id)[0];
      if (target) target.scrollIntoView({ block: 'start' });
    });
  });
}
