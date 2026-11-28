/*
  Softie Drop: next-live banner.
  Same schedule logic as softiedrop.com: reads <Worker>/schedule, works out the time left from the
  real clock (never by counting down), trusts the server's clock if the visitor's is clearly off,
  and hides the banner on any error or when nothing is scheduled.
*/
(() => {
  if (window.__softieLive) return;
  window.__softieLive = true;

  const safeLink = (u, fallback) => (/^https:\/\//i.test(u || '') ? u : fallback);
  const fmtWhen = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });

  function setup(root) {
    const worker = String(root.dataset.worker || '').replace(/\/+$/, '');
    const tiktok = safeLink(root.dataset.tiktok, '#');
    const textEl = root.querySelector('[data-softie-live-text]');
    const linkEl = root.querySelector('[data-softie-live-link]');
    let lives = [], skew = 0, loadedAt = 0, seq = 0, ready = false;

    const hide = () => { root.hidden = true; root.dataset.state = 'hidden'; };
    const setText = (el, t) => { if (el.textContent !== t) el.textContent = t; };
    const setHref = (el, v) => { if (el.getAttribute('href') !== v) el.setAttribute('href', v); };

    function render() {
      if (!ready) return;
      const now = Date.now() + skew;
      const on = lives.find(l => l.forced || (l.start <= now && now < l.end));
      const next = lives.find(l => l !== on && l.start > now);
      if (!on && !next) return hide();
      root.hidden = false;
      if (on) {
        root.dataset.state = 'live';
        setText(textEl, 'Live now — watch on TikTok');
        setText(linkEl, 'Watch now');
        setHref(linkEl, on.link || tiktok);
        return;
      }
      const mins = Math.max(0, Math.floor((next.start - now) / 60000));
      const d = Math.floor(mins / 1440), h = Math.floor(mins / 60) % 24, m = mins % 60;
      const left = mins < 1 ? 'starts any minute' : 'in ' + (d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`);
      root.dataset.state = 'next';
      setText(textEl, `Next live ${left} · ${fmtWhen.format(next.start)}`);
      setText(linkEl, 'Set a reminder');
      setHref(linkEl, next.link || tiktok);
    }

    async function load() {
      if (!worker || document.hidden || Date.now() - loadedAt < 20000) return;
      loadedAt = Date.now();
      const mine = ++seq;                       // if two loads overlap, only the newest may update the page
      try {
        const opts = 'AbortSignal' in window && AbortSignal.timeout ? { signal: AbortSignal.timeout(8000) } : {};
        const res = await fetch(worker + '/schedule', opts);
        if (!res.ok) throw new Error(res.status);
        const data = await res.json();
        if (mine !== seq) return;
        if (!Array.isArray(data.lives)) throw new Error('bad reply');
        lives = data.lives
          .map(l => ({ start: Date.parse(l.start), end: Date.parse(l.end), link: safeLink(l.link, ''), forced: l.live === true }))
          .filter(l => isFinite(l.start) && isFinite(l.end))
          .sort((a, b) => a.start - b.start);
        const off = Date.parse(data.now) - Date.now();
        skew = isFinite(off) && Math.abs(off) > 120000 ? off : 0;
        ready = true;
        render();
      } catch (err) {
        if (mine !== seq) return;
        if (!ready) hide();                     // never loaded: hide. Already showing: keep the last good schedule.
      }
    }

    const onVisible = () => { if (!document.hidden) { load(); render(); } };
    const timers = [setInterval(render, 30000), setInterval(load, 300000)];
    document.addEventListener('visibilitychange', onVisible);
    // Theme editor: when this section is re-rendered or removed, stop the old copy's timers.
    root._softieStop = () => { timers.forEach(clearInterval); document.removeEventListener('visibilitychange', onVisible); };
    load();
  }

  const start = () => document.querySelectorAll('[data-softie-live]').forEach(el => { if (!el.dataset.bound) { el.dataset.bound = '1'; setup(el); } });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  document.addEventListener('shopify:section:unload', e => e.target.querySelectorAll('[data-softie-live]').forEach(el => el._softieStop && el._softieStop()));
  document.addEventListener('shopify:section:load', start);   // theme editor
})();
