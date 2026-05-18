// Deterministic mock cumulative return series per persona over ~365 days.
// Generated with a seeded random walk so charts look realistic without backend.

import { PERSONAS } from "./personas";

function seededRand(seed: number) {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

export type Point = { day: number; date: string; value: number };

const START = new Date();
START.setDate(START.getDate() - 365);

function genSeries(seed: number, driftAnnual: number, vol: number, days = 365): Point[] {
  const rand = seededRand(seed);
  const dailyDrift = driftAnnual / 252;
  const dailyVol = vol / Math.sqrt(252);
  let value = 1;
  const out: Point[] = [];
  for (let d = 0; d < days; d++) {
    const z = (rand() + rand() + rand() + rand() - 2) * 1.225; // approx normal
    value = value * (1 + dailyDrift + dailyVol * z);
    const date = new Date(START);
    date.setDate(date.getDate() + d);
    out.push({
      day: d,
      date: date.toISOString().slice(0, 10),
      value: Number(value.toFixed(4)),
    });
  }
  return out;
}

const PARAMS: Record<string, { seed: number; drift: number; vol: number }> = {
  warren:  { seed: 17, drift: 0.14,  vol: 0.13 },
  cathie:  { seed: 43, drift: 0.28,  vol: 0.42 },
  ray:     { seed: 71, drift: 0.09,  vol: 0.08 },
  peter:   { seed: 29, drift: 0.18,  vol: 0.18 },
  sp500:   { seed: 99, drift: 0.10,  vol: 0.16 },
};

export const SERIES: Record<string, Point[]> = Object.fromEntries(
  Object.entries(PARAMS).map(([id, p]) => [id, genSeries(p.seed, p.drift, p.vol)])
);

export const SPARKLINES: Record<string, Point[]> = Object.fromEntries(
  PERSONAS.map((p) => [p.id, SERIES[p.id].slice(-90)])
);

export const BENCHMARK = SERIES.sp500;
