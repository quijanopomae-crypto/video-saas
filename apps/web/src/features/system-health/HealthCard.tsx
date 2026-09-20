"use client";

import { useEffect, useState } from "react";

type Health = {
  status: string;
  service: string;
  environment: string;
};

export function HealthCard() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/health", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return (await response.json()) as Health;
      })
      .then((payload) => {
        if (active) setHealth(payload);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "unknown error");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="health" data-testid="health-card">
      <strong>Backend</strong>
      {health ? (
        <span className="ok">
          {health.service}: {health.status} ({health.environment})
        </span>
      ) : (
        <span className="waiting">
          {error ? `No disponible: ${error}` : "Comprobando conexión…"}
        </span>
      )}
    </div>
  );
}
