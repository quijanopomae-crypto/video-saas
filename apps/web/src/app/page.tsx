import { HealthCard } from "@/features/system-health/HealthCard";

export default function Home() {
  return (
    <main>
      <section className="hero">
        <p className="eyebrow">VIDEO-SAAS</p>
        <h1>Infraestructura lista para construir el producto.</h1>
        <p className="lede">
          Este entorno usa FastAPI, Next.js, PostgreSQL y adapters locales. Las APIs
          externas permanecen deshabilitadas durante esta fase.
        </p>
        <HealthCard />
      </section>
    </main>
  );
}
