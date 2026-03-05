/** @type {import('next').NextConfig} */
const nextConfig = {
  // NEXT_PUBLIC_API_URL is baked in at build time by Next.js.
  // Set it in the Railway frontend service environment before building:
  //   NEXT_PUBLIC_API_URL=https://your-backend.railway.app
  // Falls back to http://localhost:8000 when not set (local dev).
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};

export default nextConfig;
