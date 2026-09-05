import { animate, createTimeline, stagger } from 'animejs';

export const prefersReducedMotion = (): boolean => {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
};

/**
 * Timing Tiers (ms)
 * MICRO: 120–180ms
 * STANDARD: 220–320ms
 * SIGNIFICANT: 500–900ms
 * EVALUATION / CHART: 900–1200ms
 */
export const MOTION_TIMING = {
  micro: 150,
  standard: 260,
  drawer: 300,
  counter: 800,
  chart: 1050,
};

/**
 * Animate numeric values smoothly from start to target.
 * Uses requestAnimationFrame / anime.js with polished ease-out curve.
 */
export const animateCounter = (
  target: HTMLElement | null,
  startVal: number,
  endVal: number,
  options?: {
    duration?: number;
    decimals?: number;
    prefix?: string;
    suffix?: string;
    formatter?: (val: number) => string;
  }
) => {
  if (!target) return;
  if (prefersReducedMotion()) {
    if (options?.formatter) {
      target.textContent = options.formatter(endVal);
    } else {
      const fixed = options?.decimals !== undefined ? endVal.toFixed(options.decimals) : String(Math.round(endVal));
      target.textContent = `${options?.prefix || ''}${fixed}${options?.suffix || ''}`;
    }
    return;
  }

  const obj = { val: startVal };
  try {
    animate(obj, {
      val: endVal,
      duration: options?.duration || MOTION_TIMING.counter,
      ease: 'outQuart',
      onUpdate: () => {
        if (!target) return;
        if (options?.formatter) {
          target.textContent = options.formatter(obj.val);
        } else {
          const fixed = options?.decimals !== undefined ? obj.val.toFixed(options.decimals) : String(Math.round(obj.val));
          target.textContent = `${options?.prefix || ''}${fixed}${options?.suffix || ''}`;
        }
      },
      onComplete: () => {
        if (!target) return;
        if (options?.formatter) {
          target.textContent = options.formatter(endVal);
        } else {
          const fixed = options?.decimals !== undefined ? endVal.toFixed(options.decimals) : String(Math.round(endVal));
          target.textContent = `${options?.prefix || ''}${fixed}${options?.suffix || ''}`;
        }
      },
    });
  } catch {
    // Fallback in case of animation target detaching
    if (options?.formatter) {
      target.textContent = options.formatter(endVal);
    }
  }
};

/**
 * Staggered entry animation for items, cards, or table rows.
 */
export const staggerReveal = (
  targets: string | HTMLElement[] | NodeListOf<Element>,
  options?: {
    delay?: number;
    stagger?: number;
    translateY?: number;
    translateX?: number;
    duration?: number;
  }
) => {
  if (prefersReducedMotion()) return;

  try {
    const animConfig: Record<string, any> = {
      opacity: [0, 1],
      delay: stagger(options?.stagger || 35, { start: options?.delay || 0 }),
      duration: options?.duration || MOTION_TIMING.standard,
      ease: 'outCubic',
    };

    if (options?.translateY !== undefined) {
      animConfig.translateY = [options.translateY, 0];
    } else if (options?.translateX === undefined) {
      animConfig.translateY = [6, 0];
    }

    if (options?.translateX !== undefined) {
      animConfig.translateX = [options.translateX, 0];
    }

    animate(targets, animConfig);
  } catch (e) {
    console.warn('staggerReveal notice:', e);
  }
};

/**
 * Smooth horizontal bar width reveal for comparison charts (900–1200ms).
 */
export const animateBarGrowth = (
  targets: string | HTMLElement[] | NodeListOf<Element>,
  options?: {
    stagger?: number;
    duration?: number;
    delay?: number;
  }
) => {
  if (prefersReducedMotion()) return;

  try {
    animate(targets, {
      scaleX: [0, 1],
      opacity: [0.6, 1],
      duration: options?.duration || MOTION_TIMING.chart,
      delay: stagger(options?.stagger || 80, { start: options?.delay || 60 }),
      ease: 'outCubic',
    });
  } catch (e) {
    console.warn('animateBarGrowth notice:', e);
  }
};

export const animateBarWidth = animateBarGrowth;

/**
 * Sequential pipeline progression cascade.
 */
export const animatePipelineStages = (
  selector: string,
  stageCount: number,
  onComplete?: () => void
) => {
  if (prefersReducedMotion()) {
    onComplete?.();
    return;
  }

  try {
    const tl = createTimeline({
      defaults: {
        ease: 'outCubic',
      },
      onComplete,
    });

    for (let i = 0; i < stageCount; i++) {
      tl.add(
        `${selector} [data-stage-index="${i}"]`,
        {
          opacity: [0, 1],
          translateY: [6, 0],
          duration: 180,
        },
        i === 0 ? 0 : '-=110'
      );
    }
  } catch (e) {
    console.warn('animatePipelineStages notice:', e);
    onComplete?.();
  }
};

/**
 * Route transition on page entry.
 */
export const animateRouteArrival = (target: string | HTMLElement) => {
  if (prefersReducedMotion()) return;

  try {
    animate(target, {
      opacity: [0, 1],
      translateY: [8, 0],
      duration: 270,
      ease: 'outCubic',
    });
  } catch (e) {
    console.warn('animateRouteArrival notice:', e);
  }
};

export const animatePageArrival = animateRouteArrival;

/**
 * Navigation Drawer visible slide in from left (translateX -100% -> 0%)
 * with backdrop fade-in and menu item staggered cascade.
 */
export const animateDrawerOpen = (
  drawerEl: HTMLElement | null,
  backdropEl: HTMLElement | null,
  onComplete?: () => void
) => {
  if (!drawerEl) return;
  if (prefersReducedMotion()) {
    onComplete?.();
    return;
  }
  try {
    if (backdropEl) {
      animate(backdropEl, {
        opacity: [0, 1],
        duration: 260,
        ease: 'outCubic',
      });
    }

    animate(drawerEl, {
      translateX: ['-100%', '0%'],
      opacity: [0.7, 1],
      duration: MOTION_TIMING.drawer,
      ease: 'outCubic',
      onComplete: () => {
        onComplete?.();
      },
    });

    // Stagger menu items
    staggerReveal('.drawer-nav-item', {
      delay: 70,
      stagger: 30,
      translateX: -8,
      duration: 200,
    });
  } catch (e) {
    console.warn('Drawer open notice:', e);
    onComplete?.();
  }
};

export const animateDrawerClose = (
  drawerEl: HTMLElement | null,
  backdropEl: HTMLElement | null,
  onComplete?: () => void
) => {
  if (!drawerEl) {
    onComplete?.();
    return;
  }
  if (prefersReducedMotion()) {
    onComplete?.();
    return;
  }
  try {
    if (backdropEl) {
      animate(backdropEl, {
        opacity: [1, 0],
        duration: 200,
        ease: 'inCubic',
      });
    }
    animate(drawerEl, {
      translateX: ['0%', '-100%'],
      opacity: [1, 0.4],
      duration: 240,
      ease: 'inCubic',
      onComplete: onComplete || (() => {}),
    });
  } catch (e) {
    console.warn('Drawer close notice:', e);
    onComplete?.();
  }
};
