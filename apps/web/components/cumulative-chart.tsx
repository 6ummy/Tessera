"use client";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Point } from "@/lib/mock/performance";

export type Series = { id: string; name: string; color: string; data: Point[]; dashed?: boolean };

export function CumulativeChart({ series, height = 320 }: { series: Series[]; height?: number }) {
  // Merge data by day index
  const len = Math.min(...series.map((s) => s.data.length));
  const merged = Array.from({ length: len }).map((_, i) => {
    const row: Record<string, number | string> = { date: series[0].data[i].date };
    series.forEach((s) => (row[s.id] = (s.data[i].value - 1) * 100));
    return row;
  });

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={merged} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#1F1E1B" strokeOpacity={0.06} vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11 }}
          tickFormatter={(v: string) => v.slice(5)}
          minTickGap={42}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tickFormatter={(v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(0)}%`}
          tick={{ fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={48}
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
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
