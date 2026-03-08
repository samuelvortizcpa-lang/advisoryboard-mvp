/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
  async rewrites() {
    return [
      {
        source: '/__clerk/:path*',
        destination: 'https://clerk.myadvisoryboard.space/:path*',
      },
    ];
  },
};

export default nextConfig;
