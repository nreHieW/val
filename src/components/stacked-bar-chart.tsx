"use client";
import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
} from "chart.js";
import { useTheme } from "next-themes";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip);

export type BarChartData = {
  labels: string[]; // X axis
  datasets: { label: string; data: number[] }[]; // length of data should match length of labels string[]
};

type BarChartProps = {
  data: BarChartData;
  labels: string[];
};
const darkColors = [
  "rgba(52, 78, 65,1)",
  "rgba(58, 90, 64,1)",
  "rgba(88, 129, 87,1)",
  "rgba(163, 177, 138,1)",
];

const lightColors = [
  "rgba(202, 240, 248,1)",
  "rgba(144, 224, 239,1)",
  "rgba(0, 180, 216,1)",
  "rgba(0, 119, 182,1)",
];

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
  const sumLabel = {
    id: "sumLabel",
    beforeDatasetDraw(chart: any, args: Object, plugins: any) {
      if (window !== undefined) {
        if (window.innerWidth < 640) {
          return;
        }
      }
      const { ctx } = chart;
      const datasetMetas = Array.from(Array(4).keys()).map((i) =>
        chart.getDatasetMeta(i)
      );
      datasetMetas[0].data.forEach((bar: any, index: number) => {
        const label = labels[index];
        const y = datasetMetas.reduce((acc, meta) => {
          return Math.min(acc, meta.data[index].y);
        }, 400);
        ctx.save();
        ctx.textAlign = "center";
        ctx.fillStyle = resolvedTheme === "dark" ? "white" : "black";
        ctx.font = "10px Poppins";
        ctx.fillText(label, bar.x, y - 8);
        ctx.restore();
      });
    },
  };

  const maxAmt = data.datasets.reduce((acc, dataset) => {
    return Math.max(acc, ...dataset.data);
  }, 0);
  const grace = maxAmt * 0.25;

  const options = {
    responsive: true,
    plugins: {
      tooltip: {
        callbacks: {
          label: (context: any) => {
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
          drawBorder: false,
          color: "transparent",
          drawTicks: false,
        },
        ticks: {
          font: {
            size: 11,
          },
        },
      },
      y: {
        stacked: true,
        display: false,
        grace: grace,
      },
    },
  };

  return (
    <div className="">
      {resolvedTheme === "dark" ? (
        <Bar
          data={{
            labels: data.labels,
            datasets: data.datasets.map((dataset, index) => {
              return {
                ...dataset,
                backgroundColor: darkColors[index],
              };
            }),
          }}
          options={options}
          plugins={[sumLabel]}
          redraw={true}
        />
      ) : (
        <Bar
          data={{
            labels: data.labels,
            datasets: data.datasets.map((dataset, index) => {
              return {
                ...dataset,
                backgroundColor: lightColors[index],
              };
            }),
          }}
          options={options}
          plugins={[sumLabel]}
          redraw={true}
        />
      )}
    </div>
  );
}

export default StackedBarChart;
