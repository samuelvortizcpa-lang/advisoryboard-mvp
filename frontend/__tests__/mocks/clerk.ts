import { vi } from "vitest";

export const mockGetToken = vi.fn().mockResolvedValue("mock-jwt-token");

export const mockAuth = {
  userId: "user_test123",
  getToken: mockGetToken,
  isLoaded: true,
  isSignedIn: true,
};

export const mockUser = {
  id: "user_test123",
  firstName: "Test",
  lastName: "User",
  emailAddresses: [{ emailAddress: "test@example.com" }],
};

export function setupClerkMock() {
  vi.mock("@clerk/nextjs", () => ({
    useAuth: () => mockAuth,
    useUser: () => ({ user: mockUser, isLoaded: true }),
    ClerkProvider: ({ children }: { children: React.ReactNode }) => children,
    UserButton: () => null,
  }));
}
