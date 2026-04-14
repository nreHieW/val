"use client";
import { useMemo } from "react";
import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  type ChartData,
  type ChartOptions,
  type Plugin,
} from "chart.js";
import { useTheme } from "next-themes";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip);
ChartJS.defaults.font.family = "Poppins, sans-serif";

export type BarChartData = {
  labels: string[]; // X axis
  datasets: { label: string; data: number[] }[]; // length of data should match length of labels string[]
};

type BarChartProps = {
  data: BarChartData;
  labels: string[];
};

type ChartPalette = {
  datasetColors: string[];
  axisText: string;
  totalLabelText: string;
  tooltipBackground: string;
  tooltipBorder: string;
};

const darkPalette: ChartPalette = {
  datasetColors: ["#1B2431", "#263246", "#34455D", "#4CC9F0"],
  axisText: "rgba(226, 232, 240, 0.68)",
  totalLabelText: "rgba(241, 245, 249, 0.90)",
  tooltipBackground: "rgba(8, 12, 21, 0.96)",
  tooltipBorder: "rgba(100, 116, 139, 0.20)",
};

const lightPalette: ChartPalette = {
  datasetColors: ["#F1F5F9", "#DBE4EE", "#BCC9D8", "#1A97B5"],
  axisText: "rgba(30, 41, 59, 0.62)",
  totalLabelText: "rgba(15, 23, 42, 0.85)",
  tooltipBackground: "rgba(255, 255, 255, 0.97)",
  tooltipBorder: "rgba(30, 41, 59, 0.10)",
};

function formatTooltipCurrency(value: number): string {
  const absoluteValue = Math.abs(value);

  if (absoluteValue >= 1e9) {
    return `$${(value / 1e9).toFixed(2)}B`;
  }

  if (absoluteValue >= 1e6) {
    return `$${(value / 1e6).toFixed(2)}M`;
  }

  if (absoluteValue >= 1e3) {
    return `$${(value / 1e3).toFixed(2)}K`;
  }

  return `$${value.toFixed(2)}`;
}

function StackedBarChart({ data, labels }: BarChartProps) {
  const { resolvedTheme } = useTheme();
  const palette = resolvedTheme === "dark" ? darkPalette : lightPalette;
  const devicePixelRatio =
    typeof window === "undefined"
      ? 2
      : Math.max(window.devicePixelRatio || 1, 2);

  const sumLabel: Plugin<"bar"> = {
    id: "sumLabel",
    afterDatasetsDraw(chart) {
      if (typeof window !== "undefined") {
        if (window.innerWidth < 640) {
          return;
        }
      }

      const { ctx } = chart;
      const datasetMetas = data.datasets.map((_, i) =>
        chart.getDatasetMeta(i)
      );
      const firstDataset = datasetMetas[0];
      if (!firstDataset) {
        return;
      }

      firstDataset.data.forEach((bar, index) => {
        const label = labels[index];
        const y = datasetMetas.reduce((acc, meta) => {
          const point = meta.data[index];
          return point ? Math.min(acc, point.y) : acc;
        }, chart.scales.y.top + 24);

        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillStyle = palette.totalLabelText;
        ctx.font = "600 11px Poppins, sans-serif";
        ctx.fillText(label, bar.x, y - 10);
        ctx.restore();
      });
    },
  };

  const maxAmt = data.datasets.reduce((acc, dataset) => {
    return Math.max(acc, ...dataset.data);
  }, 0);
  const grace = maxAmt * 0.25;

  const chartData = useMemo<ChartData<"bar">>(
    () => ({
      labels: data.labels,
      datasets: data.datasets.map((dataset, index) => ({
        ...dataset,
        backgroundColor: palette.datasetColors[index % palette.datasetColors.length],
        borderSkipped: false,
        borderRadius: 0,
        borderWidth: 0,
        inflateAmount: 0,
        barPercentage: 0.78,
        categoryPercentage: 0.72,
      })),
    }),
    [data, palette.datasetColors]
  );

  const options = useMemo<ChartOptions<"bar">>(() => ({
    responsive: true,
    maintainAspectRatio: false,
    devicePixelRatio,
    animation: false,
    normalized: true,
    interaction: {
      mode: "index",
      intersect: false,
    },
    layout: {
      padding: {
        top: 12,
      },
    },
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        displayColors: false,
        backgroundColor: palette.tooltipBackground,
        borderColor: palette.tooltipBorder,
        borderWidth: 1,
        padding: 12,
        titleColor: palette.totalLabelText,
        bodyColor: palette.totalLabelText,
        titleFont: {
          weight: 600,
        },
        callbacks: {
          label: (context) => {
            const label = context.dataset.label ?? "";
            const value = Number(context.raw ?? 0);
            return `${label}: ${formatTooltipCurrency(value)}`;
          },
        },
      },
    },
    scales: {
      x: {
        stacked: true,
        grid: {
          display: false,
          color: "transparent",
          drawTicks: false,
        },
        border: {
          display: false,
        },
        ticks: {
          color: palette.axisText,
          padding: 8,
          maxRotation: 0,
          font: {
            size: 11.5,
            weight: 500,
          },
        },
      },
      y: {
        stacked: true,
        display: false,
        grace: grace,
        border: {
          display: false,
        },
      },
    },
  }), [devicePixelRatio, grace, palette]);

  return (
    <div className="rounded-2xl border border-border/70 bg-card/70 p-4 shadow-sm backdrop-blur-sm sm:p-5">
      <div className="mb-4 flex flex-wrap gap-2">
        {data.datasets.map((dataset, index) => (
          <div
            key={dataset.label}
            className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-background/70 px-2.5 py-1 text-[11px] text-muted-foreground"
          >
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{
                backgroundColor:
                  palette.datasetColors[index % palette.datasetColors.length],
              }}
            />
            <span>{dataset.label}</span>
          </div>
        ))}
      </div>
      <div className="h-[320px] sm:h-[360px]">
        <Bar
          data={chartData}
          options={options}
          plugins={[sumLabel]}
          redraw={true}
        />
      </div>
    </div>
  );
}

export default StackedBarChart;
