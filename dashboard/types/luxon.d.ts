declare module "luxon" {
  // Minimal shim for deployments where `@types/luxon` is not installed.
  // This keeps the dashboard build green on Vercel; runtime uses the real library.
  export const DateTime: any;
}

