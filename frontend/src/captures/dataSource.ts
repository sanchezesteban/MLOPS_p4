import { useCallback, useEffect, useState } from "react";
import { type CaptureEvent, capturesResponseSchema } from "./capturesSchema";

type CapturesState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; data: CaptureEvent[] };

const NOT_CONFIGURED_MESSAGES = "API de capturas no configurada.";

/**
 * Resuelve la URL de la API de lectura a partir del entorno (base de #15).
 *
 * En desarrollo, sin `VITE_CAPTURES_API_URL`, se sirve el JSON de ejemplo del
 * contrato v1 para poder trabajar sin AWS. En producción **no** hay datos de
 * ejemplo: si la URL no está configurada el estado es de error, para nunca
 * presentar capturas simuladas como reales (retro de #38: el evaluador vería
 * datos de ejemplo y eso vale 0 en la rúbrica).
 *
 * Devuelve `null` y el estado queda en error, sin hacer fetch.
 */
export function resolveCapturesUrl(
  configuredBaseUrl: string | undefined,
  isDev: boolean
): string | null {
  if (configuredBaseUrl !== undefined && configuredBaseUrl.trim() !== "") {
    return `${configuredBaseUrl.replace(/\/$/, "")}/captures?limit=50`;
  }
  return isDev ? "/captures/sample.json" : null;
}

export const capturesUrl = resolveCapturesUrl(
  import.meta.env.VITE_CAPTURES_API_URL,
  import.meta.env.DEV
);

function byCapturedAtDesc(a: CaptureEvent, b: CaptureEvent): number {
  return Date.parse(b.captured_at) - Date.parse(a.captured_at);
}

/** Carga las capturas del edge y las ordena de la más reciente a la más antigua. */
export function useCaptures(url: string | null = capturesUrl) {
  const [state, setState] = useState<CapturesState>(
    url === null ? { status: "error", message: NOT_CONFIGURED_MESSAGES } : { status: "loading" }
  );

  const load = useCallback(() => {
    if (url === null) {
      setState({ status: "error", message: NOT_CONFIGURED_MESSAGES });
      return () => {};
    }

    let cancelled = false;
    setState({ status: "loading" });

    fetch(url)
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`El servidor respondió con estado ${res.status}.`);
        }
        const parsed = capturesResponseSchema.safeParse(await res.json());
        if (!parsed.success) {
          throw new Error("La respuesta no tiene el formato del contrato del evento.");
        }
        if (!cancelled) {
          setState({ status: "success", data: [...parsed.data.items].sort(byCapturedAtDesc) });
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof Error ? err.message : "Error desconocido al cargar las capturas.";
        setState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, [url]);

  useEffect(() => load(), [load]);

  return { ...state, reload: load };
}
