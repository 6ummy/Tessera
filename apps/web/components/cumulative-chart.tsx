"use client";
import { useEffect, useRef, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Point } from "@/lib/performance-types";

export type Series = { id: string; name: string; color: string; data: Point[]; dashed?: boolean };

const ET = "America/New_York";
// Daily points anchor at NOON UTC so their ET calendar day is unambiguous
// (midnight-UTC would render as the previous evening in ET). Intraday points
// carry their own epoch `t`.
const tOf = (p: Point) => p.t ?? Date.parse(`${p.date}T12:00:00Z`);

export function CumulativeChart({
  series,
  height = 320,
  zoomable = false,
}: {
  series: Series[];
  height?: number;
  zoomable?: boolean;
}) {
  // Merge by TIMESTAMP, not index: real series sit on different calendars
  // (persona snapshots vs SPY bars vs intraday Alpaca equity), and daily +
  // intraday now coexist on one time axis. Missing points render as gaps
  // bridged by connectNulls.
  const stamps = Array.from(new Set(series.flatMap((s) => s.data.map(tOf)))).sort((a, b) => a - b);
  const valueByT = series.map((s) => new Map(s.data.map((p) => [tOf(p), p.value])));
  const merged = stamps.map((t) => {
    const row: Record<string, number | null> = { t };
    series.forEach((s, i) => {
      const v = valueByT[i].get(t);
      row[s.id] = v === undefined ? null : (v - 1) * 100;
    });
    return row;
  });

  // Wheel-zoom: keep a visible [lo, hi] index window over `merged`. Scroll
  // up zooms in (narrower window) centered on the cursor, down zooms out;
  // double-click resets to the full range. Disabled unless `zoomable`.
  const N = merged.length;
  const wrapRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<{ lo: number; hi: number }>({ lo: 0, hi: Math.max(0, N - 1) });
  useEffect(() => {
    setView({ lo: 0, hi: Math.max(0, N - 1) });
  }, [N]);
  useEffect(() => {
    const el = wrapRef.current;
    if (!zoomable || !el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      setView((v) => {
        const span = v.hi - v.lo;
        if (N < 6) return v;
        const minSpan = 4;
        const factor = e.deltaY < 0 ? 0.8 : 1.25;
        const newSpan = Math.max(minSpan, Math.min(N - 1, Math.round(span * factor || minSpan)));
        const rect = el.getBoundingClientRect();
        const frac = rect.width > 0 ? Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)) : 0.5;
        const center = v.lo + frac * span;
        let lo = Math.round(center - newSpan * frac);
        let hi = lo + newSpan;
        if (lo < 0) { lo = 0; hi = newSpan; }
        if (hi > N - 1) { hi = N - 1; lo = Math.max(0, hi - newSpan); }
        return { lo, hi };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomable, N]);
  const zoomed = zoomable && (view.lo > 0 || view.hi < N - 1);
  const data = zoomable ? merged.slice(view.lo, view.hi + 1) : merged;

  // Y-axis FIXED to the full-data range (computed over `merged`, not the
  // zoom slice) so wheel-zoom only changes the X window.
  const seriesIds = series.map((s) => s.id);
  const allY: number[] = [];
  for (const row of merged) {
    for (const id of seriesIds) {
      const v = row[id];
      if (typeof v === "number") allY.push(v);
    }
  }
  const yPad = allY.length ? Math.max(1, (Math.max(...allY) - Math.min(...allY)) * 0.08) : 1;
  const yDomain: [number, number] | undefined =
    zoomable && allY.length
      ? [Math.floor(Math.min(...allY) - yPad), Math.ceil(Math.max(...allY) + yPad)]
      : undefined;

  // X ticks over the time axis: MONTHS on a wide window, calendar DAYS on a
  // medium one, and clock TIME when zoomed into intraday (< 2 days).
  const visT = data.map((r) => r.t as number);
  const spanDays = visT.length > 1 ? (visT[visT.length - 1] - visT[0]) / 86_400_000 : 0;
  const wide = spanDays > 70;
  const intraday = spanDays > 0 && spanDays < 2;
  const monthKey = (t: number) => new Date(t).toLocaleDateString("en-US", { year: "numeric", month: "2-digit", timeZone: ET });
  const xTicks: number[] = [];
  if (visT.length) {
    if (wide) {
      const seen = new Set<string>();
      for (const t of visT) { const k = monthKey(t); if (!seen.has(k)) { seen.add(k); xTicks.push(t); } }
    } else {
      const step = Math.max(1, Math.floor(visT.length / 6));
      for (let i = 0; i < visT.length; i += step) xTicks.push(visT[i]);
    }
  }
  const fmtTick = (t: number) => {
    const d = new Date(t);
    if (intraday) return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: ET });
    if (wide) {
      const mo = d.toLocaleDateString("en-US", { month: "short", timeZone: ET });
      const isJan = d.toLocaleDateString("en-US", { month: "2-digit", timeZone: ET }) === "01";
      return isJan ? `${mo} '${d.toLocaleDateString("en-US", { year: "2-digit", timeZone: ET })}` : mo;
    }
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: ET });
  };
  const fmtLabel = (t: number) =>
    new Date(t).toLocaleString("en-US",
      intraday
        ? { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: ET }
        : { year: "numeric", month: "short", day: "numeric", timeZone: ET });

  return (
    <div ref={wrapRef} className="relative" onDoubleClick={() => setView({ lo: 0, hi: Math.max(0, N - 1) })}>
      {zoomable && (
        <div className="pointer-events-none absolute right-1 top-0 z-10 text-[10px] text-ink-400">
          {zoomed ? "double-click to reset" : "scroll to zoom"}
        </div>
      )}
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#1F1E1B" strokeOpacity={0.06} vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          scale="time"
          domain={["dataMin", "dataMax"]}
          tick={{ fontSize: 11 }}
          ticks={xTicks}
          tickFormatter={fmtTick}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tickFormatter={(v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(0)}%`}
          tick={{ fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={48}
          domain={yDomain}
          allowDataOverflow={!!yDomain}
        />
        <Tooltip
          contentStyle={{
            background: "#FAF9F5",
            border: "1px solid rgba(31,30,27,0.08)",
            borderRadius: 12,
            fontSize: 12,
            padding: "10px 12px",
            boxShadow: "0 12px 36px -16px rgba(31,30,27,0.25)",
          }}
          labelStyle={{ color: "#7C7870", marginBottom: 6, fontFamily: "var(--font-mono)" }}
          labelFormatter={(t: number) => fmtLabel(t)}
          formatter={(v: number, name: string) => [`${v >= 0 ? "+" : ""}${v.toFixed(2)}%`, name]}
        />
        {series.map((s) => (
          <Line
            key={s.id}
            type="monotone"
            dataKey={s.id}
            name={s.name}
            stroke={s.color}
            strokeWidth={s.dashed ? 1.5 : 2}
            strokeDasharray={s.dashed ? "4 4" : undefined}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
    </div>
  );
}
