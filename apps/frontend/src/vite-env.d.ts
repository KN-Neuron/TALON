/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_URL?: string
  readonly VITE_STREAM_ID?: string
  readonly VITE_STUN_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
