'use client';

/*
 * ClickSpark - from React Bits (https://github.com/DavidHDev/react-bits), MIT + Commons Clause.
 * LOCAL CHANGES for a long, scrolling app: the canvas is a fixed, viewport-sized overlay (instead of covering the whole
 * parent), the animation loop only runs while sparks are alive and the canvas is `display: none` while idle (zero idle cost),
 * and reduced-motion users get no sparks.
 */

import React, { useRef, useEffect, useCallback } from 'react';

interface ClickSparkProps {
  sparkColor?: string;
  sparkSize?: number;
  sparkRadius?: number;
  sparkCount?: number;
  duration?: number;
  easing?: 'linear' | 'ease-in' | 'ease-out' | 'ease-in-out';
  extraScale?: number;
  children?: React.ReactNode;
}

interface Spark {
  x: number;
  y: number;
  angle: number;
  startTime: number;
}

const ClickSpark: React.FC<ClickSparkProps> = ({
  sparkColor = '#fff',
  sparkSize = 10,
  sparkRadius = 15,
  sparkCount = 8,
  duration = 400,
  easing = 'ease-out',
  extraScale = 1.0,
  children
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sparksRef = useRef<Spark[]>([]);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      canvas.getContext('2d')?.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  const easeFunc = useCallback(
    (t: number) => {
      switch (easing) {
        case 'linear':
          return t;
        case 'ease-in':
          return t * t;
        case 'ease-in-out':
          return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
        default:
          return t * (2 - t);
      }
    },
    [easing]
  );

  const drawRef = useRef<(timestamp: number) => void>(() => {});
  useEffect(() => {
    drawRef.current = (timestamp: number) => {
      const canvas = canvasRef.current;
      const ctx = canvas?.getContext('2d');
      if (!canvas || !ctx) return;
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

      sparksRef.current = sparksRef.current.filter((spark: Spark) => {
        const elapsed = timestamp - spark.startTime;
        if (elapsed >= duration) return false;

        const eased = easeFunc(elapsed / duration);
        const distance = eased * sparkRadius * extraScale;
        const lineLength = sparkSize * (1 - eased);

        ctx.strokeStyle = sparkColor;
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(spark.x + distance * Math.cos(spark.angle), spark.y + distance * Math.sin(spark.angle));
        ctx.lineTo(
          spark.x + (distance + lineLength) * Math.cos(spark.angle),
          spark.y + (distance + lineLength) * Math.sin(spark.angle)
        );
        ctx.stroke();
        return true;
      });

      // only keep the loop alive while there is something to draw; hide the full-screen layer when idle
      if (sparksRef.current.length) {
        frameRef.current = requestAnimationFrame(t => drawRef.current(t));
      } else {
        frameRef.current = null;
        canvas.style.display = 'none';
      }
    };
  }, [sparkColor, sparkSize, sparkRadius, duration, easeFunc, extraScale]);

  useEffect(
    () => () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    },
    []
  );

  const handleClick = (e: React.MouseEvent<HTMLDivElement>): void => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const now = performance.now();
    sparksRef.current.push(
      ...Array.from({ length: sparkCount }, (_, i) => ({
        x: e.clientX,
        y: e.clientY,
        angle: (2 * Math.PI * i) / sparkCount,
        startTime: now
      }))
    );
    if (canvasRef.current) canvasRef.current.style.display = 'block';
    if (frameRef.current === null) frameRef.current = requestAnimationFrame(t => drawRef.current(t));
  };

  return (
    <div className="contents" onClick={handleClick}>
      <canvas ref={canvasRef} className="pointer-events-none fixed inset-0 z-[65] hidden h-full w-full" aria-hidden />
      {children}
    </div>
  );
};

export default ClickSpark;
