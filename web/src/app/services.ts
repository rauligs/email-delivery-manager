export type Service = {
  name: string;
  path: string;
  description: string;
};

export const services: Service[] = [
  { name: "API", path: "../api", description: "FastAPI service boundary" },
  { name: "Background", path: "../background", description: "Worker and scraping jobs" },
  { name: "Shared", path: "../shared", description: "Models shared across Python services" },
  { name: "Web", path: ".", description: "Next.js user interface" },
];
