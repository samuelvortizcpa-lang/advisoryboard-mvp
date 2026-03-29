import { vi } from "vitest";

export const mockPathname = vi.fn().mockReturnValue("/dashboard");
export const mockRouter = {
  push: vi.fn(),
  replace: vi.fn(),
  back: vi.fn(),
  prefetch: vi.fn(),
};

export function setupNextNavigationMock() {
  vi.mock("next/navigation", () => ({
    usePathname: () => mockPathname(),
    useRouter: () => mockRouter,
    useSearchParams: () => new URLSearchParams(),
  }));
}
