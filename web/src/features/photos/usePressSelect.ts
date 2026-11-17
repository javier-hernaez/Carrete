import { useEffect, useRef, type RefObject } from "react";

const LONG_PRESS_MS = 450;
const SLOP = 10; // píxeles que puede moverse el dedo antes de que cuente como desplazar la página
const EDGE = 90; // cerca del borde de la pantalla, la página se desplaza sola al arrastrar

interface Options {
  enabled: boolean;
  ids: () => readonly string[];
  selected: () => ReadonlySet<string>;
  replace: (next: Set<string>) => void;
}

/**
 * Selección con el dedo, como en la galería del móvil: mantener pulsada una foto la selecciona y, sin
 * soltar, deslizar marca todas las fotos entre la primera y la que está bajo el dedo (o las desmarca si
 * la primera ya estaba seleccionada). Solo táctil; con ratón están la casilla y Mayús+clic.
 */
export function usePressSelect(ref: RefObject<HTMLElement | null>, options: Options) {
  const latest = useRef(options);
  useEffect(() => {
    latest.current = options;
  });

  useEffect(() => {
    const el = ref.current;
    if (!el || !options.enabled) return;
    let timer: number | null = null;
    let start: { x: number; y: number; index: number } | null = null;
    let active: { anchor: number; current: number; base: Set<string>; add: boolean } | null = null;
    let last = { x: 0, y: 0 };
    let frame: number | null = null;
    let swallowClick = false;

    const indexAt = (x: number, y: number) => {
      const hit = document.elementFromPoint(x, y)?.closest<HTMLElement>("[data-index]");
      if (!hit || !el.contains(hit)) return null;
      const index = Number(hit.dataset.index);
      return Number.isInteger(index) ? index : null;
    };
    const apply = (to: number) => {
      if (!active) return;
      active.current = to;
      const ids = latest.current.ids();
      const next = new Set(active.base);
      const [from, until] = active.anchor < to ? [active.anchor, to] : [to, active.anchor];
      for (const id of ids.slice(from, until + 1)) {
        if (active.add) next.add(id);
        else next.delete(id);
      }
      latest.current.replace(next);
    };
    const cancelTimer = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
    };
    const scrollLoop = () => {
      frame = null;
      if (!active) return;
      const speed = last.y < EDGE ? -14 : last.y > window.innerHeight - EDGE * 1.6 ? 14 : 0;
      if (speed !== 0) {
        window.scrollBy(0, speed);
        const index = indexAt(last.x, last.y);
        if (index !== null && index !== active.current) apply(index);
      }
      frame = window.requestAnimationFrame(scrollLoop);
    };
    const finish = () => {
      cancelTimer();
      if (active) {
        swallowClick = true;
        window.setTimeout(() => {
          swallowClick = false;
        }, 500);
      }
      active = null;
      start = null;
      if (frame !== null) window.cancelAnimationFrame(frame);
      frame = null;
    };

    const onTouchStart = (e: TouchEvent) => {
      const touch = e.touches[0];
      if (e.touches.length !== 1 || !touch) {
        finish();
        return;
      }
      const index = indexAt(touch.clientX, touch.clientY);
      if (index === null) return;
      start = { x: touch.clientX, y: touch.clientY, index };
      last = { x: touch.clientX, y: touch.clientY };
      cancelTimer();
      timer = window.setTimeout(() => {
        timer = null;
        if (!start) return;
        const id = latest.current.ids()[start.index];
        if (!id) return;
        const base = new Set(latest.current.selected());
        active = { anchor: start.index, current: start.index, base, add: !base.has(id) };
        apply(start.index);
        if ("vibrate" in navigator) navigator.vibrate(15);
        frame = window.requestAnimationFrame(scrollLoop);
      }, LONG_PRESS_MS);
    };
    const onTouchMove = (e: TouchEvent) => {
      const touch = e.touches[0];
      if (!touch) return;
      last = { x: touch.clientX, y: touch.clientY };
      if (active) {
        // Mientras se selecciona deslizando, el dedo no desplaza la página.
        if (e.cancelable) e.preventDefault();
        const index = indexAt(touch.clientX, touch.clientY);
        if (index !== null && index !== active.current) apply(index);
      } else if (start && Math.hypot(touch.clientX - start.x, touch.clientY - start.y) > SLOP) {
        cancelTimer();
        start = null;
      }
    };
    const onContextMenu = (e: Event) => {
      // El menú del navegador al mantener pulsada una imagen (guardar, compartir…) estorba aquí.
      if (start || active) e.preventDefault();
    };
    const onClickCapture = (e: Event) => {
      if (!swallowClick) return;
      swallowClick = false;
      e.preventDefault();
      e.stopPropagation();
    };

    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchmove", onTouchMove, { passive: false });
    el.addEventListener("touchend", finish);
    el.addEventListener("touchcancel", finish);
    el.addEventListener("contextmenu", onContextMenu);
    el.addEventListener("click", onClickCapture, true);
    return () => {
      finish();
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
      el.removeEventListener("touchend", finish);
      el.removeEventListener("touchcancel", finish);
      el.removeEventListener("contextmenu", onContextMenu);
      el.removeEventListener("click", onClickCapture, true);
    };
  }, [ref, options.enabled]);
}
