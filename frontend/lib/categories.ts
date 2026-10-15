import { useCategories } from "@/lib/api/queries";
import { categoryOptions } from "@/lib/import";

/**
 * The category names a person can choose for a transaction: the built-in ones, then their own.
 * If the list cannot be fetched (for example the categories table has not been set up yet) it
 * falls back to the built-in set plus whatever the ledger already uses, so adding or importing a
 * transaction never stops working because the category list is unavailable.
 */
export function useAssignableCategories(seen: Iterable<string> = []): string[] {
  const { data } = useCategories();
  if (data) return data.categories.filter((c) => c.assignable).map((c) => c.name);
  return categoryOptions(seen);
}
