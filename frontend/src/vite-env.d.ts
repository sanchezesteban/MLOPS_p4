/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** P4-14/#15: base de la API de lectura de capturas edge; vacía = solo dev usa el JSON de ejemplo. */
  readonly VITE_CAPTURES_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
