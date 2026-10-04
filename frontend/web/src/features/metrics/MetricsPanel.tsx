import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { MetricPoint } from "../../types/api";

interface MetricsPanelProps {
  metrics: MetricPoint[];
}

export function MetricsPanel({ metrics }: MetricsPanelProps) {
  const series = metrics
    .filter((point) => typeof point.metric_value === "number" && point.step_index !== null)
    .map((point) => ({
      step: point.step_index ?? 0,
      name: point.metric_name,
      value: point.metric_value ?? 0,
    }));

  if (!series.length) {
    return <div className="empty-panel">No numeric metrics yet.</div>;
  }

  return (
    <div className="chart-panel">
      <ResponsiveContainer width="100%" height={190}>
        <LineChart data={series}>
          <XAxis dataKey="step" tickLine={false} axisLine={false} />
          <YAxis tickLine={false} axisLine={false} width={42} />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#2563eb" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
