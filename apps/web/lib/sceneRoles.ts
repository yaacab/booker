/* Role copy and anchor photos shared with Scene 01 (Scene01LiveHome ROLES).
   The intro keeps its own constants untouched; these values mirror them so the
   registration header shows the very same photo and wording. */

export type SceneRole = "customer" | "artist" | "venue";

const un = (id: string, w: number) => `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=${w}&q=72`;

export const SCENE_ROLES: Record<SceneRole, { kicker: string; title: string; text: string; photo: string }> = {
  customer: { kicker: "Я организую", title: "Заказчик", text: "Соберите событие целиком: артисты, площадка, дата и гости — в одном месте.", photo: un("1414235077428-338989a2e8c0", 760) },
  artist: { kicker: "Я выступаю", title: "Исполнитель", text: "Музыканты, DJ, ведущие и шоу. Получайте запросы на выступления напрямую.", photo: un("1493225457124-a3eb161ffa5f", 760) },
  venue: { kicker: "Я принимаю гостей", title: "Площадка", text: "Рестораны, лофты и террасы. Покажите пространство и свободные даты.", photo: un("1517248135467-4c7edcad34c4", 760) },
};

export function isSceneRole(value: unknown): value is SceneRole {
  return value === "customer" || value === "artist" || value === "venue";
}
