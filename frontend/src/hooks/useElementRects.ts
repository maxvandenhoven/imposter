import { useCallback, useLayoutEffect, useRef, useState } from "react";

import type { BoardRect } from "@/lib/table";

/** The rects of keyed elements inside a container, and the container's size. */
export interface ElementRects {
  rects: Map<number, BoardRect>;
  width: number;
  height: number;
}

type ElementRef = (element: HTMLElement | null) => void;

/** Whether two measurements are the same, so a new one need not render again. */
function sameRects(a: ElementRects, b: ElementRects): boolean {
  if (a.width !== b.width || a.height !== b.height || a.rects.size !== b.rects.size) {
    return false;
  }

  for (const [key, rect] of a.rects) {
    const other = b.rects.get(key);

    if (
      other === undefined ||
      other.x !== rect.x ||
      other.y !== rect.y ||
      other.width !== rect.width ||
      other.height !== rect.height
    ) {
      return false;
    }
  }

  return true;
}

/**
 * Measure keyed elements relative to a container, again whenever any of them resizes.
 *
 * It only measures while `enabled` is set, because every measurement renders the
 * component again, and the elements resize on every frame while answers are written.
 * Returns a ref for the container, a stable ref callback per key for the elements, the
 * latest measurements and a function that measures again.
 */
export function useElementRects(enabled: boolean) {
  const container = useRef<HTMLDivElement | null>(null);
  const elements = useRef(new Map<number, HTMLElement>());
  const refs = useRef(new Map<number, ElementRef>());
  const observer = useRef<ResizeObserver | null>(null);
  const [measured, setMeasured] = useState<ElementRects>({
    rects: new Map(),
    width: 0,
    height: 0,
  });

  const measure = useCallback(() => {
    const box = container.current?.getBoundingClientRect();

    if (box === undefined) {
      return;
    }

    const rects = new Map<number, BoardRect>();

    for (const [key, element] of elements.current) {
      const rect = element.getBoundingClientRect();
      rects.set(key, {
        x: Math.round(rect.left - box.left),
        y: Math.round(rect.top - box.top),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      });
    }

    const next = { rects, width: Math.round(box.width), height: Math.round(box.height) };
    setMeasured((current) => (sameRects(current, next) ? current : next));
  }, []);

  useLayoutEffect(() => {
    if (!enabled) {
      return;
    }

    const resizeObserver = new ResizeObserver(measure);
    observer.current = resizeObserver;

    if (container.current !== null) {
      resizeObserver.observe(container.current);
    }

    for (const element of elements.current.values()) {
      resizeObserver.observe(element);
    }

    measure();

    return () => {
      resizeObserver.disconnect();
      observer.current = null;
    };
  }, [enabled, measure]);

  const elementRef = useCallback((key: number): ElementRef => {
    const cached = refs.current.get(key);

    if (cached !== undefined) {
      return cached;
    }

    const ref: ElementRef = (element) => {
      const previous = elements.current.get(key);

      if (previous !== undefined) {
        observer.current?.unobserve(previous);
        elements.current.delete(key);
      }

      if (element !== null) {
        elements.current.set(key, element);
        observer.current?.observe(element);
      }
    };
    refs.current.set(key, ref);

    return ref;
  }, []);

  return { containerRef: container, elementRef, measured, measure };
}
