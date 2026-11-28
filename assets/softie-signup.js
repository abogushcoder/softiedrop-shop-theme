/*
  Softie Drop: live-alerts signup, same behaviour and messages as softiedrop.com.
  Posts { email, phone, smsOk, hp } to the Worker. Never sends anything to analytics.
*/
(() => {
  if (window.__softieSignup) return;
  window.__softieSignup = true;

  const OFFLINE = 'You seem to be offline. Check your connection and try again.';
  const TROUBLE = 'We couldn’t sign you up just now. Please try again in a minute.';

  function setup(form) {
    const worker = String(form.dataset.worker || '').replace(/\/+$/, '');
    const emailEl = form.elements.email, phoneEl = form.elements.phone, smsOk = form.elements.smsOk;
    const smsRow = form.querySelector('[data-sms-row]'), msg = form.querySelector('.softie-form__msg');
    const btn = form.querySelector('button[type="submit"]'), btnText = btn.textContent;
    let sending = false;

    function say(text, kind, field) {
      msg.textContent = text; msg.className = 'softie-form__msg' + (kind ? ' ' + kind : '');
      for (const el of [emailEl, phoneEl]) el.removeAttribute('aria-invalid');
      if (field) { field.setAttribute('aria-invalid', 'true'); field.focus(); }
    }
    phoneEl.addEventListener('input', () => { smsRow.hidden = !phoneEl.value.trim(); });
    for (const el of [emailEl, phoneEl, smsOk]) el.addEventListener('input', () => { if (!sending && msg.classList.contains('err')) say('', ''); });

    form.addEventListener('submit', async e => {
      e.preventDefault();
      if (sending) return;
      const email = emailEl.value.trim(), phone = phoneEl.value.trim();
      if (!email) return say('Please enter your email.', 'err', emailEl);
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return say('That email doesn’t look right. Check it for typos.', 'err', emailEl);
      if (phone && phone.replace(/\D/g, '').length < 10) return say('That phone number looks too short. Include the area code.', 'err', phoneEl);
      if (phone && !smsOk.checked) { say('Tick the box to get text alerts, or clear the phone number.', 'err'); smsOk.focus(); return; }
      if (!worker) return say('Sign-ups aren’t open yet. Follow us on TikTok for now.', 'err');
      if (navigator.onLine === false) return say(OFFLINE, 'err');
      sending = true; btn.disabled = true; btn.textContent = 'Signing you up…'; say('', '');
      try {
        const opts = 'AbortSignal' in window && AbortSignal.timeout ? { signal: AbortSignal.timeout(30000) } : {};
        const res = await fetch(worker + '/', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, ...opts,
          body: JSON.stringify({ email, phone: phone || '', smsOk: smsOk.checked, hp: form.elements.sd_hp_x7.value })
        });
        const out = await res.json().catch(() => ({}));
        if (res.ok) {
          say(out.sms ? 'You’re in! We’ll email you before each live and text you when we start.'
            : phone ? 'You’re in for email alerts! We couldn’t add that phone number, so text alerts aren’t on.'
            : 'You’re in! We’ll email you before every live.', 'good');
          form.reset(); smsRow.hidden = true;
        } else if (res.status === 400 && /email|phone/i.test(out.error || '')) {   // the Worker's friendly messages only
          say(out.error, 'err', /phone/i.test(out.error) ? phoneEl : /email/i.test(out.error) ? emailEl : null);
        } else if (res.status === 429) {
          say('Too many tries in a row. Please wait a minute and try again.', 'err');
        } else {
          say(TROUBLE, 'err');
        }
      } catch (err) {
        say(navigator.onLine === false ? OFFLINE : err && err.name === 'TimeoutError' ? 'That took too long. Please try again.' : TROUBLE, 'err');
      }
      sending = false; btn.disabled = false; btn.textContent = btnText;
    });
  }

  const start = () => document.querySelectorAll('form[data-softie-signup]').forEach(f => { if (!f.dataset.bound) { f.dataset.bound = '1'; setup(f); } });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  document.addEventListener('shopify:section:load', start);   // theme editor
})();
