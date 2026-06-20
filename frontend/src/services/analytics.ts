import { apiRequest } from "@/lib/api-client";
import type { Analytics } from "@/types/analytics";

export function getAnalytics(userId: string): Promise<Analytics> {
  return apiRequest<Analytics>("/memories/analytics", { query: { user_id: userId } });
}
