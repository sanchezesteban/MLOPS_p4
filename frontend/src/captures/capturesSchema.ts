import { z } from "zod";

/**
 * Contrato del evento de captura v1 (ver `docs/p4/contrato-evento.md`): es lo
 * que el portal consume de `GET /captures` (AWS → portal). La Pi genera los
 * campos; AWS agrega `received_at` e `image_key` y una `image_url` firmada.
 *
 * Se valida en el borde con Zod para no pintar datos incompletos o de otro
 * formato (mismo criterio que el resto del portal: nada sin validar).
 */
export const captureEventSchema = z.object({
  capture_id: z.uuid(),
  captured_at: z.iso.datetime({ offset: true }),
  received_at: z.iso.datetime({ offset: true }).optional(),
  device_id: z.string().min(1),
  model_version: z.string().min(1),
  model_sha256: z.string().regex(/^[0-9a-f]{64}$/),
  predicted_class: z.enum(["cat", "dog"]),
  confidence: z.number().min(0).max(1),
  latency_ms: z.number().nonnegative(),
  crop: z.object({ x: z.number(), y: z.number(), w: z.number(), h: z.number() }).nullable(),
  image_key: z.string().optional(),
  image_url: z.string().min(1),
});

export const capturesResponseSchema = z.object({ items: z.array(captureEventSchema) });

export type CaptureEvent = z.infer<typeof captureEventSchema>;
export type CapturesResponse = z.infer<typeof capturesResponseSchema>;
