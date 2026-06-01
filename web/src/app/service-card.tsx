import type { Service } from "./services";

export function ServiceCard({ service }: { service: Service }) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-950">{service.name}</h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">{service.description}</p>
      <p className="mt-4 font-mono text-xs text-slate-500">{service.path}</p>
    </article>
  );
}
