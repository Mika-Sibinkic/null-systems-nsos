/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The engine base URL is server-side only (never NEXT_PUBLIC_*), so it is never
  // bundled into client JS. All engine calls go through server-side API routes.
};

export default nextConfig;
