"use client"
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
} from "chart.js";
import { Line } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
);

export default function LineAreaChart({
  priceHistory,
  good,
  title,
}: {
  priceHistory: number[];
  good: boolean;
  title: string;
}) {
  const lineColor = good
    ? "hsl(163, 100%, 38%)"
    : "hsl(345, 72%, 55%)";

  return (
    <div className="mt-3">
      <p className="text-center text-xxs text-muted-foreground mb-1">{title}</p>
      <Line
        data={{
          labels: Array.from({ length: priceHistory.length }, (_, i) => i),
          datasets: [
            {
              data: priceHistory,
              fill: false,
              borderColor: lineColor,
              pointRadius: 0,
              borderWidth: 1.5,
            },
          ],
        }}
        options={{
          responsive: true,
          animation: false,
          scales: {
            x: {
              display: false,
              grid: { display: false },
            },
            y: {
              display: true,
              grid: { display: false },
              border: { display: false },
              ticks: {
                font: {
                  family: "Poppins, sans-serif",
                  weight: "normal",
                  size: 9,
                },
                padding: 4,
              },
            },
          },
          plugins: {
            legend: { display: false },
          },
        }}
      />
    </div>
  );
}
