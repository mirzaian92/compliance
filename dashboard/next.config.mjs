/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // This dashboard is intentionally static and reads data from a JSON snapshot
  // published by the Python pipeline into `dashboard/public/data/latest.json`.
  // Using static export avoids Serverless Function invocations (and related 500s)
  // for a simple internal "read-only" UI.
  output: "export",
  // Windows environments (and some locked-down machines) can fail when Next spawns
  // child processes during build (`spawn EPERM`). Worker threads avoid that.
  experimental: {
    workerThreads: true
  }
};

export default nextConfig;
