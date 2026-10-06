// Copyright (c) 2026 He-Zixuan. LicenseRef-Classroom-Personal-NonCommercial-1.0; see LICENSE.
/* Small, interruptible transitions; speech updates never wait on animation. */
const Motion = (() => {
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  const running = new WeakMap(), visibility = new WeakMap();
  const ease = 'cubic-bezier(.16,1,.3,1)';

  function animate(el, frames, duration = 200) {
    if (!el?.animate) return null;
    running.get(el)?.cancel();
    const animation = el.animate(frames, {duration: preference.matches ? Math.min(duration, 100) : duration, easing: ease});
    running.set(el, animation);
    animation.finished.catch(() => {}).finally(() => {if (running.get(el) === animation) running.delete(el);});
    return animation;
  }
  function text(el, value) {
    value = String(value ?? '');
    if (el.textContent === value) return;
    el.textContent = value;
    if (!el.hidden && value) animate(el, [{opacity: .65}, {opacity: 1}], 160);
  }
  function visible(el, show) {
    const previous = visibility.get(el);
    if (previous ? previous.show === show : el.hidden === !show) return;
    const from = el.hidden ? 0 : el.getBoundingClientRect().height;
    previous?.animation?.cancel();
    const state = {show, animation: null};
    visibility.set(el, state);
    el.hidden = false; el.inert = !show; el.setAttribute('aria-hidden', String(!show));
    const style = getComputedStyle(el), expanded = el.getBoundingClientRect().height;
    const full = {height: `${expanded}px`, opacity: 1, paddingTop: style.paddingTop, paddingBottom: style.paddingBottom, marginTop: style.marginTop, marginBottom: style.marginBottom, clipPath: 'inset(0)'};
    const collapsed = {height: '0px', opacity: 0, paddingTop: '0px', paddingBottom: '0px', marginTop: '0px', marginBottom: '0px', clipPath: 'inset(0 0 100%)'};
    const frames = preference.matches ? [{opacity: show ? .6 : 1}, {opacity: show ? 1 : 0}] : show ? [{...collapsed, height: `${from}px`}, full] : [{...full, height: `${from}px`}, collapsed];
    const animation = el.animate?.(frames, {duration: preference.matches ? 100 : show ? 220 : 130, easing: ease});
    state.animation = animation;
    const finish = () => {if (visibility.get(el) !== state) return; el.hidden = !show; visibility.delete(el);};
    if (animation) return animation.finished.then(finish).catch(() => {});
    finish();
  }
  function reset(el, show) {
    visibility.get(el)?.animation?.cancel(); visibility.delete(el);
    running.get(el)?.cancel(); running.delete(el);
    el.hidden = !show; el.inert = !show; el.setAttribute('aria-hidden', String(!show));
  }
  function panelSwap(el, update) {
    el.querySelector('.motion-ghost')?.remove();
    const height = el.getBoundingClientRect().height;
    const ghost = el.cloneNode(true);
    ghost.removeAttribute('id'); ghost.className = 'motion-ghost'; ghost.inert = true;
    ghost.setAttribute('aria-hidden', 'true');
    for (const child of ghost.querySelectorAll('[id]')) child.removeAttribute('id');
    update();
    const nextHeight = el.getBoundingClientRect().height;
    el.append(ghost);
    const animation = ghost.animate?.([{opacity: 1}, {opacity: 0}], {duration: preference.matches ? 80 : 120, easing: ease});
    if (animation) animation.finished.then(() => ghost.remove()).catch(() => ghost.remove()); else ghost.remove();
    for (const panel of el.querySelectorAll(':scope > section:not([hidden])')) enter(panel);
    if (!preference.matches) animate(el, [{height: `${height}px`}, {height: `${nextHeight}px`}], 240);
  }
  function enter(el) {
    animate(el, preference.matches ? [{opacity: .6}, {opacity: 1}] : [{opacity: .35, transform: 'translateY(5px)', clipPath: 'inset(0 0 8px)'}, {opacity: 1, transform: 'none', clipPath: 'inset(0)'}], 220);
  }
  function live(el, value) {
    if (el.textContent === value) return;
    const previous = el.textContent;
    if (previous && value.startsWith(previous)) {
      const tail = document.createElement('span'); tail.textContent = value.slice(previous.length);
      el.replaceChildren(document.createTextNode(previous), tail);
      animate(tail, [{opacity: .3}, {opacity: 1}], 120);
    } else text(el, value);
  }
  function snapshot(el) {
    const ghost=el.cloneNode(true);
    ghost.className='motion-ghost transcript-ghost';ghost.inert=true;ghost.setAttribute('aria-hidden','true');
    const originals=[el,...el.querySelectorAll('[id]')],copies=[ghost,...ghost.querySelectorAll('[id]')];
    const special=new Set(['sessionState','empty','emptyTitle','emptyHelp','live','liveText','sizeValue']);
    const properties=['font-size','font-weight','line-height','color','padding','margin','text-align','max-width','display','flex'];
    originals.forEach((original,i)=>{
      if(special.has(original.id)){const style=getComputedStyle(original);for(const property of properties)copies[i].style.setProperty(property,style.getPropertyValue(property));}
      copies[i].removeAttribute('id');
    });
    return ghost;
  }
  async function swap(update, target) {
    // A local crossfade keeps header controls clickable while captions change.
    target.querySelector('.motion-ghost')?.remove();
    const ghost=snapshot(target);
    update();target.append(ghost);
    const exit=ghost.animate?.([{opacity:1},{opacity:0}],{duration:preference.matches?80:130,easing:ease});
    if(exit)exit.finished.then(()=>ghost.remove()).catch(()=>ghost.remove());else ghost.remove();
    for(const child of target.children){if(child!==ghost&&!child.hidden)animate(child,preference.matches?[{opacity:.6},{opacity:1}]:[{opacity:.25,transform:'translateY(4px)'},{opacity:1,transform:'none'}],220);}
  }
  return {text, visible, reset, panelSwap, enter, live, swap, animate, get reduced() {return preference.matches;}};
})();
