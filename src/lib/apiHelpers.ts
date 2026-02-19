import { DCFInputData } from "../components/ticker-display/types";

const baseURL = process.env.URL;
export async function getDCFInputs(query: string) {
  const response = await fetch(
    `${baseURL}/api/ticker?ticker=${encodeURIComponent(query)}`,{ next: { revalidate: 60 } }
  );
  let data = await response.json();
  return data[0];
}
export async function getPriceHistory(query: string) {
  const response = await fetch(
    `${baseURL}/api/history?ticker=${encodeURIComponent(query)}`,
    { next: { revalidate: 60 } },
  );
  let data = await response.json();

  return Array.isArray(data.history) ? data.history : [];
}
export async function getDCFOutput(inputData: DCFInputData) {
  if (!inputData) return;

  const response = await fetch(`${baseURL}/api/dcf`, {
    
    cache: "no-store",
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(inputData),
  });

  const data = await response.json();
  return data;
}

