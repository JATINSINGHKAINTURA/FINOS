import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

const EASE = "cubic-bezier(.2,.7,.25,1)";

export { EASE };

function reducedMotion() {
  return typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Scroll-triggered staggered reveal: blur-fade-rise, fires once. Above-fold content plays on mount. */
export function Reveal({ children, className = "", delay = 0, as: Tag = "div" }: {
  children: ReactNode; className?: string; delay?: number; as?: "div" | "section" | "li" | "span";
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [on, setOn] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reducedMotion()) { setOn(true); return; }
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) { setOn(true); io.disconnect(); }
    }, { threshold: 0.1, rootMargin: "0px 0px -6% 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <Tag ref={ref as never} className={`rv${on ? " on" : ""}${className ? ` ${className}` : ""}`}
      style={{ "--rv-d": `${delay}ms` } as CSSProperties}>
      {children}
    </Tag>
  );
}

/** Animated number: counts 0 → to on mount (~900ms ease-out). Instant under reduced motion. */
export function CountUp({ to, format = (n: number) => String(Math.round(n)) }: {
  to: number; format?: (n: number) => string;
}) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (reducedMotion() || to <= 0) { setV(to); return; }
    let raf = 0;
    const t0 = performance.now(), dur = 900;
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      setV(to * e);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [to]);
  return <>{format(v)}</>;
}
