import { ServiceCard } from "./service-card";
import { services } from "./services";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-10 px-6 py-12 sm:py-16">
      <section className="space-y-4">
        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">Project scaffold</p>
        <h1 className="max-w-3xl text-4xl font-semibold tracking-normal text-slate-950 sm:text-5xl">
          Four runnable layers, ready for product work.
        </h1>
        <p className="max-w-2xl text-lg leading-8 text-slate-600">
          Use the API for HTTP contracts, background for durable jobs, shared for common models,
          and web for the user-facing Next.js app.
        </p>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Project apps">
        {services.map((service) => (
          <ServiceCard key={service.name} service={service} />
        ))}
      </section>
    </main>
  );
}
